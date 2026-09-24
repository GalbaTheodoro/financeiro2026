"""GTA — Guia de Trânsito Animal: controle das guias e ficha de preparo.

Rotas
-----
GET    /api/gta/tabelas        espécies, faixas de idade, finalidades, portais
GET    /api/gta                a lista, com filtros e o resumo de validade
POST   /api/gta                cria
GET    /api/gta/{id}           abre
PUT    /api/gta/{id}           salva
DELETE /api/gta/{id}           apaga
POST   /api/gta/{id}/situacao  marca emitida / utilizada / cancelada
GET    /api/gta/{id}/preparo   a ficha para levar ao portal
GET    /api/gta/{id}/anexo     baixa o PDF da guia, quando anexado

**Não existe "transmitir".** A GTA não tem webservice: quem emite é o produtor
ou o médico-veterinário, dentro do sistema fechado do estado (em Minas o SIAPEC,
do IMA). O que este módulo faz é guardar as guias, avisar de validade e
preparar a digitação. O porquê está escrito por extenso em ``backend/gta.py``.
"""
from __future__ import annotations

import base64
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import gta as regras
from ..database import get_db
from ..deps import acesso_liberado, validar_empresa
from ..models import (
    Contrato,
    Empresa,
    GuiaAnimalCategoria,
    GuiaTransitoAnimal,
    Nota,
    Parceiro,
    Usuario,
)
from ..utils import parse_data, serializar

router = APIRouter(prefix="/api/gta", tags=["gta"])


class CategoriaIn(BaseModel):
    sexo: str = "M"
    faixa: str = ""
    quantidade: int = 0
    observacao: str | None = None


class GuiaIn(BaseModel):
    empresa_id: int
    numero: str | None = None
    serie: str | None = None
    uf_emissora: str | None = None
    situacao: str | None = "PREPARO"
    data_emissao: str | None = None
    data_validade: str | None = None
    finalidade: str | None = None

    produtor_id: int | None = None
    origem_nome: str | None = None
    origem_documento: str | None = None
    origem_inscricao: str | None = None
    origem_propriedade: str | None = None
    origem_municipio: str | None = None
    origem_uf: str | None = None

    destino_id: int | None = None
    destino_nome: str | None = None
    destino_documento: str | None = None
    destino_inscricao: str | None = None
    destino_propriedade: str | None = None
    destino_municipio: str | None = None
    destino_uf: str | None = None

    especie: str | None = None
    veterinario: str | None = None
    crmv: str | None = None
    transportador: str | None = None
    placa: str | None = None
    meio_transporte: str | None = "RODOVIARIO"

    contrato_id: int | None = None
    nota_id: int | None = None
    observacao: str | None = None

    # o PDF da guia emitida, quando o usuário anexa (base64, sem o cabeçalho)
    arquivo_nome: str | None = None
    arquivo: str | None = None

    categorias: list[CategoriaIn] = []


class SituacaoIn(BaseModel):
    empresa_id: int
    situacao: str
    numero: str | None = None
    serie: str | None = None
    data_emissao: str | None = None
    data_validade: str | None = None


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
@router.get("/tabelas")
def tabelas(usuario: Usuario = Depends(acesso_liberado)):
    """As listas de escolha da tela. Vêm do servidor para não ficarem duplicadas."""
    return regras.tabelas()


def _guia(db: Session, guia_id: int, usuario: Usuario) -> GuiaTransitoAnimal:
    guia = db.get(GuiaTransitoAnimal, guia_id)
    if not guia:
        raise HTTPException(404, "Guia não encontrada.")
    validar_empresa(db, guia.empresa_id, usuario)
    return guia


def _ficha(guia: GuiaTransitoAnimal, hoje: date | None = None) -> dict:
    """A guia como a tela recebe — sem o PDF, que é pesado e tem rota própria."""
    faltas = regras.conferir(guia, hoje)
    return serializar(guia, exclude={"arquivo"}, extras={
        "situacao_mostrada": regras.situacao_mostrada(guia, hoje),
        "aviso": regras.aviso_de_validade(guia, hoje),
        "dias_para_vencer": regras.dias_para_vencer(guia, hoje),
        "faltas": faltas,
        "pronta": not faltas,
        "tem_anexo": bool(guia.arquivo),
        "produtor_nome": guia.produtor.nome if guia.produtor else None,
        "categorias": [serializar(c) for c in guia.categorias],
    })


@router.get("")
def listar(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    produtor_id: int | None = None,
    especie: str | None = None,
    situacao: str | None = None,
    busca: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(GuiaTransitoAnimal).filter(
        GuiaTransitoAnimal.empresa_id == empresa_id)

    inicio, fim = parse_data(de), parse_data(ate)
    if inicio:
        consulta = consulta.filter(GuiaTransitoAnimal.data_emissao >= inicio)
    if fim:
        consulta = consulta.filter(GuiaTransitoAnimal.data_emissao <= fim)
    if produtor_id:
        consulta = consulta.filter(GuiaTransitoAnimal.produtor_id == produtor_id)
    if especie:
        consulta = consulta.filter(GuiaTransitoAnimal.especie == especie.upper())
    if busca:
        alvo = f"%{busca.strip()}%"
        consulta = consulta.filter(
            GuiaTransitoAnimal.numero.ilike(alvo)
            | GuiaTransitoAnimal.origem_nome.ilike(alvo)
            | GuiaTransitoAnimal.destino_nome.ilike(alvo)
            | GuiaTransitoAnimal.origem_propriedade.ilike(alvo)
            | GuiaTransitoAnimal.destino_propriedade.ilike(alvo)
        )

    guias = consulta.order_by(
        # guia sem data (ainda em preparo) vai para o fim. Escrito assim, e não
        # com NULLS LAST, porque SQLite antigo não conhece NULLS LAST.
        GuiaTransitoAnimal.data_emissao.is_(None),
        GuiaTransitoAnimal.data_emissao.desc(),
        GuiaTransitoAnimal.id.desc(),
    ).all()

    hoje = date.today()
    fichas = [_ficha(g, hoje) for g in guias]
    # o filtro de situação usa a situação **mostrada**: quem procura "vencida"
    # quer as que passaram da data, não só as marcadas na mão
    if situacao:
        alvo = situacao.strip().upper()
        fichas = [f for f in fichas if f["situacao_mostrada"] == alvo]

    return {"guias": fichas, "resumo": _resumo(fichas)}


def _resumo(fichas: list[dict]) -> dict:
    """Os números do cabeçalho: quantas valem, quantas estão vencendo, quantas venceram."""
    resumo = {"total": len(fichas), "animais": 0, "preparo": 0, "validas": 0,
              "vencendo": 0, "vencidas": 0, "utilizadas": 0, "canceladas": 0,
              "com_pendencia": 0}
    for ficha in fichas:
        resumo["animais"] += int(ficha.get("quantidade") or 0)
        if not ficha["pronta"]:
            resumo["com_pendencia"] += 1
        situacao = ficha["situacao_mostrada"]
        if situacao == "PREPARO":
            resumo["preparo"] += 1
        elif situacao == "UTILIZADA":
            resumo["utilizadas"] += 1
        elif situacao == "CANCELADA":
            resumo["canceladas"] += 1
        elif situacao == "VENCIDA":
            resumo["vencidas"] += 1
        elif situacao == "EMITIDA":
            resumo["validas"] += 1
            faltam = ficha.get("dias_para_vencer")
            if faltam is not None and faltam <= regras.DIAS_DE_AVISO:
                resumo["vencendo"] += 1
    return resumo


@router.get("/{guia_id}")
def abrir(guia_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    return {"guia": _ficha(_guia(db, guia_id, usuario))}


@router.get("/{guia_id}/preparo")
def preparo(guia_id: int, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """A ficha para levar ao portal do estado, na ordem em que ele pergunta."""
    guia = _guia(db, guia_id, usuario)
    empresa = db.get(Empresa, guia.empresa_id)
    return {"guia": _ficha(guia), "preparo": regras.ficha_preparo(guia, empresa)}


@router.get("/{guia_id}/anexo", response_class=None)
def anexo(guia_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    """O PDF da guia que o usuário guardou junto."""
    from fastapi.responses import Response

    guia = _guia(db, guia_id, usuario)
    if not guia.arquivo:
        raise HTTPException(404, "Esta guia não tem arquivo anexado.")
    try:
        conteudo = base64.b64decode(guia.arquivo)
    except Exception:
        raise HTTPException(400, "O arquivo guardado nesta guia está danificado.") from None
    nome = guia.arquivo_nome or f"GTA-{guia.numero or guia.id}.pdf"
    return Response(conteudo, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{nome}"'})


# --------------------------------------------------------------------------- #
# Gravação
# --------------------------------------------------------------------------- #
def _copiar_do_parceiro(db: Session, dados: GuiaIn, empresa_id: int) -> None:
    """Quem escolheu o produtor no cadastro não digita o endereço de novo.

    Só preenche o que veio em branco — o que o usuário digitou manda, porque a
    propriedade pode ser outra que não a do cadastro.
    """
    for campo_id, prefixo in (("produtor_id", "origem"), ("destino_id", "destino")):
        parceiro_id = getattr(dados, campo_id)
        if not parceiro_id:
            continue
        parceiro = db.get(Parceiro, parceiro_id)
        if not parceiro or parceiro.empresa_id != empresa_id:
            raise HTTPException(400, "O produtor escolhido não é desta empresa.")
        for campo, valor in (("nome", parceiro.nome),
                             ("documento", parceiro.cpf_cnpj),
                             ("inscricao", parceiro.rg_ie),
                             ("municipio", parceiro.cidade),
                             ("uf", parceiro.uf)):
            destino = f"{prefixo}_{campo}"
            if not (getattr(dados, destino) or "").strip():
                setattr(dados, destino, valor)


def _aplicar(db: Session, guia: GuiaTransitoAnimal, dados: GuiaIn) -> None:
    _copiar_do_parceiro(db, dados, guia.empresa_id)

    situacao = (dados.situacao or "PREPARO").strip().upper()
    if situacao not in regras.SITUACOES:
        raise HTTPException(400, f"Situação inválida. Use uma destas: "
                                 f"{', '.join(regras.SITUACOES)}.")
    especie = (dados.especie or "").strip().upper()
    if especie and especie not in regras.ESPECIES:
        raise HTTPException(400, f"Espécie desconhecida. As que o sistema conhece são: "
                                 f"{', '.join(sorted(regras.ESPECIES))}.")

    for campo_id, modelo, frase in ((dados.contrato_id, Contrato, "contrato"),
                                    (dados.nota_id, Nota, "nota")):
        if campo_id:
            alvo = db.get(modelo, campo_id)
            if not alvo or alvo.empresa_id != guia.empresa_id:
                raise HTTPException(400, f"O {frase} escolhido não é desta empresa.")

    guia.numero = (dados.numero or "").strip() or None
    guia.serie = (dados.serie or "").strip() or None
    guia.uf_emissora = (dados.uf_emissora or "").strip().upper() or None
    guia.situacao = situacao
    guia.data_emissao = parse_data(dados.data_emissao)
    guia.data_validade = parse_data(dados.data_validade)
    guia.finalidade = (dados.finalidade or "").strip().upper() or None
    guia.especie = especie or None

    guia.produtor_id = dados.produtor_id
    guia.destino_id = dados.destino_id
    for lado in ("origem", "destino"):
        for campo in ("nome", "documento", "inscricao", "propriedade", "municipio", "uf"):
            nome = f"{lado}_{campo}"
            valor = (getattr(dados, nome) or "").strip() or None
            if campo == "uf" and valor:
                valor = valor.upper()[:2]
            setattr(guia, nome, valor)

    guia.veterinario = (dados.veterinario or "").strip() or None
    guia.crmv = (dados.crmv or "").strip() or None
    guia.transportador = (dados.transportador or "").strip() or None
    guia.placa = (dados.placa or "").strip().upper().replace(" ", "") or None
    guia.meio_transporte = (dados.meio_transporte or "RODOVIARIO").strip().upper()
    guia.contrato_id = dados.contrato_id
    guia.nota_id = dados.nota_id
    guia.observacao = (dados.observacao or "").strip() or None

    if dados.arquivo is not None:
        conteudo = (dados.arquivo or "").strip()
        if conteudo:
            # a tela manda "data:application/pdf;base64,XXXX" — fica só o XXXX
            if "," in conteudo[:64] and conteudo.lower().startswith("data:"):
                conteudo = conteudo.split(",", 1)[1]
            try:
                base64.b64decode(conteudo, validate=True)
            except Exception:
                raise HTTPException(400, "Não consegui ler o arquivo anexado. "
                                         "Anexe o PDF da guia outra vez.") from None
            guia.arquivo = conteudo
            guia.arquivo_nome = (dados.arquivo_nome or "").strip() or "GTA.pdf"
        else:
            guia.arquivo = None
            guia.arquivo_nome = None

    guia.categorias.clear()
    total = 0
    faixas = regras.faixas_da_especie(especie)
    for linha in dados.categorias:
        quantidade = int(linha.quantidade or 0)
        if quantidade <= 0:
            continue
        sexo = (linha.sexo or "M").strip().upper()[:1]
        if sexo not in regras.SEXOS:
            raise HTTPException(400, "O sexo do animal é M (macho) ou F (fêmea).")
        guia.categorias.append(GuiaAnimalCategoria(
            sexo=sexo,
            faixa=(linha.faixa or "").strip() or (faixas[0] if faixas else ""),
            quantidade=quantidade,
            observacao=(linha.observacao or "").strip() or None,
        ))
        total += quantidade
    guia.quantidade = total
    guia.atualizado_em = datetime.utcnow()


@router.post("")
def criar(dados: GuiaIn, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    empresa = validar_empresa(db, dados.empresa_id, usuario)
    guia = GuiaTransitoAnimal(empresa_id=empresa.id, usuario_id=usuario.id)
    if not (dados.uf_emissora or "").strip():
        dados.uf_emissora = dados.origem_uf or empresa.uf
    db.add(guia)
    _aplicar(db, guia, dados)
    db.commit()
    db.refresh(guia)
    return {"guia": _ficha(guia)}


@router.put("/{guia_id}")
def salvar(guia_id: int, dados: GuiaIn, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if dados.empresa_id != guia.empresa_id:
        raise HTTPException(400, "Esta guia é de outra empresa.")
    _aplicar(db, guia, dados)
    db.commit()
    db.refresh(guia)
    return {"guia": _ficha(guia)}


@router.post("/{guia_id}/situacao")
def mudar_situacao(guia_id: int, dados: SituacaoIn, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(acesso_liberado)):
    """Marca a guia como emitida, utilizada ou cancelada — sem reabrir a tela toda.

    É o caminho de todo dia: a pessoa emitiu no portal e volta aqui só para
    anotar o número e a validade.
    """
    guia = _guia(db, guia_id, usuario)
    situacao = (dados.situacao or "").strip().upper()
    if situacao not in regras.SITUACOES:
        raise HTTPException(400, f"Situação inválida. Use uma destas: "
                                 f"{', '.join(regras.SITUACOES)}.")
    if dados.numero is not None:
        guia.numero = (dados.numero or "").strip() or None
    if dados.serie is not None:
        guia.serie = (dados.serie or "").strip() or None
    if dados.data_emissao is not None:
        guia.data_emissao = parse_data(dados.data_emissao)
    if dados.data_validade is not None:
        guia.data_validade = parse_data(dados.data_validade)

    if situacao == "EMITIDA":
        if not guia.numero:
            raise HTTPException(400, "Para marcar como emitida, informe o número da guia "
                                     "que saiu do portal.")
        if not guia.data_validade:
            raise HTTPException(400, "Para marcar como emitida, informe até quando a guia "
                                     "vale — é essa data que o sistema vigia.")
        if not guia.data_emissao:
            guia.data_emissao = date.today()
    if situacao == "UTILIZADA" and (guia.situacao or "") == "PREPARO":
        raise HTTPException(400, "Esta guia ainda está em preparo: não dá para marcar como "
                                 "utilizada uma guia que nunca foi emitida.")

    guia.situacao = situacao
    guia.atualizado_em = datetime.utcnow()
    db.commit()
    db.refresh(guia)
    return {"guia": _ficha(guia)}


@router.delete("/{guia_id}")
def apagar(guia_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if (guia.situacao or "") == "EMITIDA" and guia.numero:
        raise HTTPException(
            400, f"A GTA {guia.numero} já foi emitida no portal — apagar aqui não a "
                 "cancela lá. Cancele no portal e marque como cancelada, para o "
                 "histórico ficar certo.")
    db.delete(guia)
    db.commit()
    return {"ok": True}
