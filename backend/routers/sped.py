"""SPED Fiscal — conferir, completar as notas e baixar o arquivo.

O caminho da tela é sempre o mesmo, nesta ordem:

1. **Conferir** — o sistema diz o que falta antes de gerar. Enquanto houver
   impedimento, o download não sai: melhor descobrir aqui do que no PVA.
2. **Completar as notas** — resolve o impedimento mais comum de todos: nota de
   entrada que a SEFAZ entregou só como resumo, ou com o XML completo mas sem os
   itens gravados. Dá ciência da operação, busca os documentos de novo e grava os
   itens.
3. **Baixar o arquivo** — o .txt em ISO-8859-1, com o nome que o contador espera.

Assinar e transmitir não é daqui: quem faz isso é o contador, no PVA.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import notas as regras_notas
from .. import sped
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import Usuario
from ..utils import parse_data, serializar

# A porta do servidor: o SPED Fiscal vive do mesmo módulo da nota fiscal.
router = APIRouter(
    prefix="/api/sped", tags=["sped"],
    dependencies=[Depends(exigir_modulo("NFE"))],
)


# --------------------------------------------------------------------------- #
# Período
# --------------------------------------------------------------------------- #
def _periodo(de: str | None, ate: str | None) -> tuple[date, date]:
    """O período do arquivo é sempre um mês fechado — é assim que a EFD funciona.

    A tela manda o primeiro e o último dia; quem manda só o primeiro recebe o mês
    inteiro. Período que atravessa mês é recusado aqui, porque o PVA recusaria
    depois com uma frase bem menos clara.
    """
    hoje = date.today()
    inicio = parse_data(de, date(hoje.year, hoje.month, 1))
    inicio = date(inicio.year, inicio.month, 1)
    if ate:
        fim = parse_data(ate)
    else:
        fim = None
    if fim is None:
        proximo = date(inicio.year + (inicio.month // 12), inicio.month % 12 + 1, 1)
        fim = date.fromordinal(proximo.toordinal() - 1)
    if (fim.year, fim.month) != (inicio.year, inicio.month):
        raise HTTPException(
            400, "O SPED Fiscal é de um mês por arquivo. Escolha um mês só.")
    if inicio > fim:
        raise HTTPException(400, "Data inicial maior que a data final.")
    return inicio, fim


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
class ConfigSpedIn(BaseModel):
    empresa_id: int
    perfil: str = "A"
    atividade: str = "1"
    csosn_para_cst: str | None = None
    itens_das_saidas: bool = False
    contador_nome: str | None = None
    contador_cpf: str | None = None
    contador_crc: str | None = None
    contador_cnpj: str | None = None
    contador_cep: str | None = None
    contador_logradouro: str | None = None
    contador_numero: str | None = None
    contador_complemento: str | None = None
    contador_bairro: str | None = None
    contador_telefone: str | None = None
    contador_email: str | None = None
    contador_codigo_municipio: str | None = None


@router.get("/config")
def ver_config(empresa_id: int, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    config = sped.config_da_empresa(db, empresa_id)
    db.commit()
    return {
        "config": serializar(config),
        "perfis": sped.PERFIS,
        "tipos_de_item": sped.TIPOS_DE_ITEM,
        "csosn_padrao": sped.CSOSN_PARA_CST,
    }


@router.put("/config")
def salvar_config(dados: ConfigSpedIn, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    config = sped.config_da_empresa(db, dados.empresa_id)
    perfil = (dados.perfil or "A").upper()[:1]
    if perfil not in sped.PERFIS:
        raise HTTPException(400, "O perfil do arquivo é A, B ou C.")
    config.perfil = perfil
    config.atividade = "0" if (dados.atividade or "1") == "0" else "1"
    config.itens_das_saidas = bool(dados.itens_das_saidas)
    for campo in (
        "csosn_para_cst", "contador_nome", "contador_cpf", "contador_crc",
        "contador_cnpj", "contador_cep", "contador_logradouro", "contador_numero",
        "contador_complemento", "contador_bairro", "contador_telefone",
        "contador_email", "contador_codigo_municipio",
    ):
        setattr(config, campo, (getattr(dados, campo) or "").strip() or None)
    from datetime import datetime
    config.atualizado_em = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return {"ok": True, "config": serializar(config),
            "mensagem": "Configuração do SPED Fiscal salva."}


# --------------------------------------------------------------------------- #
# Conferência
# --------------------------------------------------------------------------- #
@router.get("/conferir")
def conferir(empresa_id: int, de: str | None = None, ate: str | None = None,
             db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    """O que falta para o arquivo do mês sair — antes de gerar."""
    validar_empresa(db, empresa_id, usuario)
    inicio, fim = _periodo(de, ate)
    resultado = sped.conferir(db, empresa_id, inicio, fim)
    db.commit()                      # a conferência pode ter criado a config em branco
    resultado["de"] = inicio.isoformat()
    resultado["ate"] = fim.isoformat()
    return resultado


@router.get("/previa")
def previa(empresa_id: int, de: str | None = None, ate: str | None = None,
           perfil: str | None = None, inventario: bool = False,
           linhas: int = 40, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    """Gera o arquivo e devolve só o resumo, as contagens e as primeiras linhas.

    Serve para conferir sem baixar: quem abre o .txt no Bloco de Notas antes de
    mandar para o contador quer ver o 0000 e o 0150, não o arquivo inteiro.
    """
    validar_empresa(db, empresa_id, usuario)
    inicio, fim = _periodo(de, ate)
    conferencia = sped.conferir(db, empresa_id, inicio, fim)
    resultado = sped.gerar(db, empresa_id, inicio, fim, perfil, inventario)
    db.commit()
    quantas = max(5, min(int(linhas or 40), 200))
    todas = resultado["texto"].splitlines()
    return {
        "resumo": resultado["resumo"],
        # lista de pares, não dicionário: em JavaScript a chave "1001" é inteira
        # e pula para a frente do objeto, bagunçando a ordem do arquivo na tela
        "contagem": [[r, q] for r, q in resultado["contagem"].items()],
        "linhas": resultado["linhas"],
        "nome": resultado["nome"],
        "primeiras": todas[:quantas],
        "ultimas": todas[-4:],
        "impedimentos": conferencia["impedimentos"],
        "avisos": conferencia["avisos"],
    }


# --------------------------------------------------------------------------- #
# Completar as notas de entrada
# --------------------------------------------------------------------------- #
class CompletarIn(BaseModel):
    empresa_id: int
    de: str | None = None
    ate: str | None = None
    # dar ciência na SEFAZ nas notas que só vieram como resumo
    dar_ciencia: bool = True
    # depois da ciência, buscar os documentos de novo para receber o XML inteiro
    buscar: bool = True


@router.post("/completar")
def completar(dados: CompletarIn, db: Session = Depends(get_db),
              usuario: Usuario = Depends(acesso_liberado)):
    """Deixa as notas de entrada do mês prontas para entrar no arquivo.

    Três passos, cada um resolvendo uma situação diferente:

    1. nota só com resumo e sem manifestação → **ciência da operação** na SEFAZ
       (é o que autoriza a SEFAZ a entregar o XML inteiro);
    2. uma busca de documentos → o XML completo chega e substitui o resumo;
    3. nota com XML completo e sem itens → **importa** (grava itens, pagamentos,
       o fornecedor e o produto do cadastro). Não gera título: quem decide
       faturar é a tela de Notas Fiscais.

    Cada passo é tentado por nota, e o erro de uma não derruba as outras — a
    resposta conta o que deu e o que não deu, nota por nota.
    """
    validar_empresa(db, dados.empresa_id, usuario)
    inicio, fim = _periodo(dados.de, dados.ate)
    pendentes = sped.pendentes_de_completar(db, dados.empresa_id, inicio, fim)

    ciencias = 0
    falhas: list[str] = []

    # ---- 1. ciência das notas que estão só como resumo ----
    if dados.dar_ciencia and pendentes["resumo"]:
        from . import dfe as rotas_dfe
        from ..schemas import ManifestarIn
        for nota in pendentes["resumo"]:
            if nota.manifestacao:
                continue                      # já manifestada: falta só a busca
            try:
                rotas_dfe.manifestar(
                    nota.id, ManifestarIn(tipo="CIENCIA"), db=db, usuario=usuario)
                ciencias += 1
            except HTTPException as erro:
                falhas.append(f"Nota {nota.numero or nota.chave[:8]}: {erro.detail}")
            except Exception as erro:          # noqa: BLE001 — a SEFAZ erra de muitos jeitos
                falhas.append(f"Nota {nota.numero or nota.chave[:8]}: {erro}")

    # ---- 2. buscar os documentos de novo ----
    busca = {}
    if dados.buscar and pendentes["resumo"]:
        from . import dfe as rotas_dfe
        from ..schemas import BuscarDFeIn
        try:
            busca = rotas_dfe.buscar(
                BuscarDFeIn(empresa_id=dados.empresa_id), db=db, usuario=usuario)
        except HTTPException as erro:
            falhas.append(f"Busca na SEFAZ: {erro.detail}")
        except Exception as erro:              # noqa: BLE001
            falhas.append(f"Busca na SEFAZ: {erro}")

    # ---- 3. gravar os itens do XML que já está aqui ----
    importadas = 0
    depois = sped.pendentes_de_completar(db, dados.empresa_id, inicio, fim)
    for nota in depois["sem_itens"]:
        try:
            regras_notas.importar_xml(db, nota, criar_parceiro=True,
                                      atualizar_produtos=True)
            importadas += 1
        except HTTPException as erro:
            falhas.append(f"Nota {nota.numero or nota.chave[:8]}: {erro.detail}")
        except Exception as erro:              # noqa: BLE001
            falhas.append(f"Nota {nota.numero or nota.chave[:8]}: {erro}")
    db.commit()

    restam = sped.pendentes_de_completar(db, dados.empresa_id, inicio, fim)
    partes = []
    if ciencias:
        partes.append(f"{ciencias} ciência(s) registrada(s) na SEFAZ")
    if busca.get("atualizadas"):
        partes.append(f"{busca['atualizadas']} nota(s) receberam o XML completo")
    if importadas:
        partes.append(f"{importadas} nota(s) tiveram os itens gravados")
    if not partes:
        partes.append("nada a completar")

    faltam = len(restam["resumo"]) + len(restam["sem_itens"])
    mensagem = "Feito: " + ", ".join(partes) + "."
    if restam["resumo"]:
        mensagem += (
            f" Ainda faltam {len(restam['resumo'])} nota(s) sem o XML completo — depois da "
            "ciência a SEFAZ costuma levar algumas horas para liberar o documento. "
            "Tente de novo mais tarde.")
    elif faltam:
        mensagem += f" Ainda faltam {faltam} nota(s)."

    return {
        "ok": True,
        "ciencias": ciencias,
        "importadas": importadas,
        "busca": busca.get("mensagem", ""),
        "faltam": faltam,
        "falhas": falhas[:20],
        "mensagem": mensagem,
    }


# --------------------------------------------------------------------------- #
# O arquivo
# --------------------------------------------------------------------------- #
@router.get("/arquivo")
def arquivo(empresa_id: int, de: str | None = None, ate: str | None = None,
            perfil: str | None = None, inventario: bool = False,
            finalidade: str = "0", forcar: bool = False,
            db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """O .txt da EFD ICMS/IPI, em ISO-8859-1, como o PVA espera.

    ``finalidade`` é o campo COD_FIN do registro 0000: 0 é a remessa original do
    arquivo, 1 é a substituta (quando o contador precisa reenviar o mês).

    ``forcar`` existe para o caso em que o contador quer o arquivo mesmo com
    pendência — para olhar, ou para completar à mão no PVA. Sem ele, pendência
    que o PVA recusaria barra o download aqui.
    """
    validar_empresa(db, empresa_id, usuario)
    inicio, fim = _periodo(de, ate)
    conferencia = sped.conferir(db, empresa_id, inicio, fim)
    if conferencia["impedimentos"] and not forcar:
        raise HTTPException(400, " ".join(conferencia["impedimentos"]))
    if finalidade not in ("0", "1"):
        raise HTTPException(400, "A finalidade do arquivo é 0 (original) ou 1 (substituto).")

    resultado = sped.gerar(db, empresa_id, inicio, fim, perfil, inventario, finalidade)
    db.commit()
    return Response(
        resultado["bytes"],
        media_type="text/plain; charset=iso-8859-1",
        headers={"Content-Disposition": f'attachment; filename="{resultado["nome"]}"'},
    )
