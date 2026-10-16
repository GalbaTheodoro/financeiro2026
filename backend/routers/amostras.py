"""Amostras de café — cadastro, classificação e laudo.

Rotas
-----
GET    /api/amostras/tabelas     defeitos, peneiras, bebidas, atributos da prova...
POST   /api/amostras/calcular    o resultado do que está na tela, sem gravar
GET    /api/amostras             a lista, com filtros
POST   /api/amostras             cria (o número sai sozinho, em sequência por empresa)
GET    /api/amostras/{id}        abre, já com o resultado calculado
PUT    /api/amostras/{id}        salva
DELETE /api/amostras/{id}        apaga
GET    /api/amostras/{id}/laudo  tudo o que o laudo impresso precisa
GET    /api/amostras/impressao   dados dos fitilhos e etiquetas (amostras e/ou envios)

Envios (controle de quem recebeu a amostra e o que respondeu)
GET    /api/amostras/envios               todos os envios, com filtros
POST   /api/amostras/{id}/envios          registra um envio
PUT    /api/amostras/envios/{envio_id}    atualiza (inclusive a resposta do comprador)
DELETE /api/amostras/envios/{envio_id}    apaga

Contratos: a amostra pode estar em **vários** contratos (tabela amostra_contratos).

O cálculo mora em ``backend/classificacao.py``. Classificar café é o dia a dia de
quem trabalha com contrato de café, então a tela é do módulo de contratos —
está em todos os planos.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import classificacao as regras
from ..database import get_db
from ..deps import exigir_modulo, validar_empresa
from ..models import (
    AmostraCafe,
    AmostraContrato,
    Contrato,
    Empresa,
    EnvioAmostra,
    Parceiro,
    Usuario,
)
from ..utils import parse_data, serializar

router = APIRouter(prefix="/api/amostras", tags=["amostras de café"])
_do_plano = exigir_modulo("CONTRATOS")

SITUACOES = ("RECEBIDA", "CLASSIFICADA")
SITUACOES_ENVIO = {
    "AGUARDANDO": "Aguardando resposta",
    "APROVADA": "Aprovada",
    "RECUSADA": "Recusada",
    "DEVOLVIDA": "Devolvida",
}
FORMAS_ENVIO = {
    "CORREIOS": "Correios",
    "TRANSPORTADORA": "Transportadora",
    "MOTOBOY": "Motoboy",
    "EM_MAOS": "Em mãos",
    "MALOTE": "Malote",
    "OUTRO": "Outro",
}


class AmostraIn(BaseModel):
    empresa_id: int
    situacao: str | None = "RECEBIDA"
    data_recebimento: str | None = None
    data_classificacao: str | None = None
    parceiro_id: int | None = None
    produtor_nome: str | None = None
    fazenda: str | None = None
    municipio: str | None = None
    uf: str | None = None
    contratos: list[int] = []
    contrato_id: int | None = None      # telas antigas: vira um item de `contratos`
    lote: str | None = None
    sacas: float | None = 0
    armazem: str | None = None
    safra: str | None = None
    especie: str | None = "ARABICA"
    variedade: str | None = None
    preparo: str | None = None
    altitude: int | None = None

    peso_amostra: float | None = 300
    peso_peneiras: float | None = 100
    umidade: float | None = None
    catacao: float | None = None
    impurezas: float | None = None
    cor: str | None = None
    aspecto: str | None = None
    torracao: str | None = None
    defeitos: dict = {}
    peneiras: dict = {}

    bebida: str | None = None
    gostos_estranhos: str | None = None
    sensorial: dict = {}
    sensorial_defeitos: float | None = 0
    descritores: str | None = None

    tipo: str | None = None
    tipo_manual: bool = False
    padrao: str | None = None
    classificador: str | None = None
    registro_classificador: str | None = None
    observacao: str | None = None


class CalcularIn(BaseModel):
    peso_amostra: float | None = 300
    peso_peneiras: float | None = 100
    impurezas: float | None = None
    especie: str | None = None
    defeitos: dict = {}
    peneiras: dict = {}
    bebida: str | None = None
    sensorial: dict = {}
    sensorial_defeitos: float | None = 0
    tipo: str | None = None
    tipo_manual: bool = False
    padrao: str | None = None


# --------------------------------------------------------------------------- #
# Ajudantes
# --------------------------------------------------------------------------- #
def _amostra(db: Session, amostra_id: int, usuario: Usuario) -> AmostraCafe:
    amostra = db.get(AmostraCafe, amostra_id)
    if not amostra:
        raise HTTPException(404, "Amostra não encontrada.")
    validar_empresa(db, amostra.empresa_id, usuario)
    return amostra


def _dados_de_calculo(a: AmostraCafe) -> dict:
    return {
        "peso_amostra": a.peso_amostra, "peso_peneiras": a.peso_peneiras,
        "impurezas": a.impurezas, "especie": a.especie,
        "defeitos": regras.ler_json(a.defeitos), "peneiras": regras.ler_json(a.peneiras),
        "bebida": a.bebida, "sensorial": regras.ler_json(a.sensorial),
        "sensorial_defeitos": a.sensorial_defeitos, "tipo": a.tipo,
        "tipo_manual": a.tipo_manual, "padrao": a.padrao,
    }


def _ficha(a: AmostraCafe, resultado: dict | None = None) -> dict:
    resultado = resultado or regras.calcular(_dados_de_calculo(a))
    return serializar(a, extras={
        "defeitos": regras.ler_json(a.defeitos),
        "peneiras": regras.ler_json(a.peneiras),
        "sensorial": regras.ler_json(a.sensorial),
        "parceiro_nome": a.parceiro.nome if a.parceiro else None,
        "contratos": _contratos_da_amostra(a),
        "envios": [_envio(e) for e in a.envios],
        "resultado": resultado,
    })


def _contrato_resumo(c: Contrato) -> dict:
    parte = c.comprador.nome if getattr(c, "comprador", None) else (
        c.vendedor.nome if getattr(c, "vendedor", None) else "")
    return {"id": c.id, "numero": c.numero, "data": c.data, "parte": parte,
            "quantidade": c.quantidade, "unidade": c.unidade}


def _contratos_da_amostra(a: AmostraCafe) -> list[dict]:
    vistos = {}
    for ligacao in a.contratos:
        if ligacao.contrato:
            vistos[ligacao.contrato.id] = _contrato_resumo(ligacao.contrato)
    # banco antigo: o contrato único que a amostra tinha também aparece
    if a.contrato and a.contrato.id not in vistos:
        vistos[a.contrato.id] = _contrato_resumo(a.contrato)
    return list(vistos.values())


def _padrao_final(a: AmostraCafe) -> str:
    """O padrão que vale: o digitado, ou o sugerido pela classificação."""
    return a.padrao or regras.calcular(_dados_de_calculo(a))["padrao"] or ""


def _envio(e: EnvioAmostra) -> dict:
    return serializar(e, extras={
        "situacao_nome": SITUACOES_ENVIO.get(e.situacao, e.situacao),
        "forma_nome": FORMAS_ENVIO.get(e.forma_envio or "", e.forma_envio or ""),
        "amostra_numero": e.amostra.numero if e.amostra else None,
        "amostra_padrao": _padrao_final(e.amostra) if e.amostra else None,
        "amostra_produtor": e.amostra.produtor_nome if e.amostra else None,
        "amostra_lote": e.amostra.lote if e.amostra else None,
        "dias": (date.today() - e.data_envio).days if e.data_envio else None,
    })


def _texto(valor, tamanho: int) -> str | None:
    valor = (valor or "").strip() if isinstance(valor, str) else valor
    return valor[:tamanho] if valor else None


def _aplicar(db: Session, a: AmostraCafe, dados: AmostraIn) -> dict:
    """Copia a tela para a amostra, recalcula e grava o resultado."""
    if dados.parceiro_id:
        parceiro = db.get(Parceiro, dados.parceiro_id)
        if not parceiro or parceiro.empresa_id != a.empresa_id:
            raise HTTPException(400, "Produtor/cliente não encontrado nesta empresa.")
        a.parceiro_id = parceiro.id
        # o que a tela não preencheu vem do cadastro
        dados.produtor_nome = dados.produtor_nome or parceiro.nome
        dados.municipio = dados.municipio or parceiro.cidade
        dados.uf = dados.uf or parceiro.uf
    else:
        a.parceiro_id = None
    ids = list(dict.fromkeys(int(x) for x in (dados.contratos or []) if x))
    if dados.contrato_id and dados.contrato_id not in ids:
        ids.append(dados.contrato_id)
    for contrato_id in ids:
        contrato = db.get(Contrato, contrato_id)
        if not contrato or contrato.empresa_id != a.empresa_id:
            raise HTTPException(400, "Contrato não encontrado nesta empresa.")
    # troca as ligações pelas da tela: o que saiu é desligado, o que entrou é ligado
    atuais = {lig.contrato_id: lig for lig in a.contratos}
    for contrato_id, ligacao in atuais.items():
        if contrato_id not in ids:
            a.contratos.remove(ligacao)
    for contrato_id in ids:
        if contrato_id not in atuais:
            a.contratos.append(AmostraContrato(contrato_id=contrato_id))
    a.contrato_id = None          # a coluna antiga deixa de ser usada

    situacao = (dados.situacao or "RECEBIDA").upper()
    if situacao not in SITUACOES:
        raise HTTPException(400, "Situação inválida.")
    especie = (dados.especie or "ARABICA").upper()
    if especie not in regras.ESPECIES:
        raise HTTPException(400, "Espécie inválida.")
    preparo = (dados.preparo or "").upper() or None
    if preparo and preparo not in regras.PREPAROS:
        raise HTTPException(400, "Preparo inválido.")
    for nome, valor, maximo in (("umidade", dados.umidade, 100), ("catação", dados.catacao, 100),
                                ("impurezas", dados.impurezas, 100)):
        if valor is not None and not 0 <= valor <= maximo:
            raise HTTPException(400, f"A {nome} vai de 0 a {maximo}%.")
    for nome, valor in (("peso da amostra", dados.peso_amostra),
                        ("peso das peneiras", dados.peso_peneiras)):
        if valor is not None and valor <= 0:
            raise HTTPException(400, f"O {nome} tem de ser maior que zero.")
    try:
        recebimento = parse_data(dados.data_recebimento, a.data_recebimento or date.today())
        classificacao = parse_data(dados.data_classificacao)
    except ValueError:
        raise HTTPException(400, "Data inválida.") from None

    a.situacao = situacao
    a.data_recebimento = recebimento
    a.data_classificacao = classificacao
    a.produtor_nome = _texto(dados.produtor_nome, 160)
    a.fazenda = _texto(dados.fazenda, 160)
    a.municipio = _texto(dados.municipio, 80)
    a.uf = (_texto(dados.uf, 2) or "").upper() or None
    a.lote = _texto(dados.lote, 40)
    a.sacas = max(float(dados.sacas or 0), 0)
    a.armazem = _texto(dados.armazem, 120)
    a.safra = _texto(dados.safra, 9)
    a.especie = especie
    a.variedade = _texto(dados.variedade, 60)
    a.preparo = preparo
    a.altitude = dados.altitude if dados.altitude and dados.altitude > 0 else None
    a.peso_amostra = dados.peso_amostra or 300
    a.peso_peneiras = dados.peso_peneiras or 100
    a.umidade = dados.umidade
    a.catacao = dados.catacao
    a.impurezas = dados.impurezas
    a.cor = _texto(dados.cor, 30)
    a.aspecto = _texto(dados.aspecto, 15)
    a.torracao = _texto(dados.torracao, 15)
    a.defeitos = json.dumps(regras.limpar(dados.defeitos, regras.CHAVES_DEFEITO))
    a.peneiras = json.dumps(regras.limpar(dados.peneiras, regras.CHAVES_PENEIRA))
    a.bebida = _texto(dados.bebida, 20)
    a.gostos_estranhos = _texto(dados.gostos_estranhos, 200)
    a.sensorial = json.dumps(regras.provar(dados.sensorial)["notas"])
    a.sensorial_defeitos = max(float(dados.sensorial_defeitos or 0), 0)
    a.descritores = _texto(dados.descritores, 300)
    a.tipo_manual = bool(dados.tipo_manual and (dados.tipo or "").strip())
    a.tipo = _texto(dados.tipo, 15) if a.tipo_manual else None
    a.padrao = _texto(dados.padrao, 120)
    a.classificador = _texto(dados.classificador, 120)
    a.registro_classificador = _texto(dados.registro_classificador, 40)
    a.observacao = dados.observacao or None

    resultado = regras.calcular(_dados_de_calculo(a))
    a.total_defeitos = resultado["defeitos"]["total_300g"]
    a.tipo = resultado["tipo"] or None
    a.pontuacao = resultado["sensorial"]["pontuacao"]
    if a.situacao == "CLASSIFICADA" and not a.data_classificacao:
        a.data_classificacao = date.today()
    return resultado


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@router.get("/tabelas")
def tabelas(usuario: Usuario = Depends(_do_plano)):
    return {**regras.tabelas(), "situacoes_envio": SITUACOES_ENVIO,
            "formas_envio": FORMAS_ENVIO}


@router.post("/calcular")
def calcular(dados: CalcularIn, usuario: Usuario = Depends(_do_plano)):
    return regras.calcular(dados.model_dump())


# --------------------------------------------------------------------------- #
# Envios — declarados antes de /{amostra_id}, senão "envios" seria lido como id
# --------------------------------------------------------------------------- #
class EnvioIn(BaseModel):
    data_envio: str | None = None
    destinatario_id: int | None = None
    destinatario_nome: str | None = None
    destinatario_contato: str | None = None
    destinatario_endereco: str | None = None
    destinatario_cidade: str | None = None
    destinatario_uf: str | None = None
    destinatario_cep: str | None = None
    quantidade_g: float | None = 0
    forma_envio: str | None = None
    rastreio: str | None = None
    situacao: str | None = "AGUARDANDO"
    data_retorno: str | None = None
    preco_oferecido: float | None = None
    observacao: str | None = None


def _aplicar_envio(db: Session, envio: EnvioAmostra, dados: EnvioIn) -> None:
    if dados.destinatario_id:
        parceiro = db.get(Parceiro, dados.destinatario_id)
        if not parceiro or parceiro.empresa_id != envio.empresa_id:
            raise HTTPException(400, "Destinatário não encontrado nesta empresa.")
        envio.destinatario_id = parceiro.id
        # o endereço da etiqueta vem do cadastro quando a tela não trouxe outro
        endereco = ", ".join(x for x in (parceiro.logradouro, parceiro.numero,
                                         parceiro.complemento, parceiro.bairro) if x)
        dados.destinatario_nome = dados.destinatario_nome or parceiro.nome
        dados.destinatario_endereco = dados.destinatario_endereco or endereco
        dados.destinatario_cidade = dados.destinatario_cidade or parceiro.cidade
        dados.destinatario_uf = dados.destinatario_uf or parceiro.uf
        dados.destinatario_cep = dados.destinatario_cep or parceiro.cep
    else:
        envio.destinatario_id = None
    if not (dados.destinatario_nome or "").strip():
        raise HTTPException(400, "Informe para quem a amostra foi enviada.")
    situacao = (dados.situacao or "AGUARDANDO").upper()
    if situacao not in SITUACOES_ENVIO:
        raise HTTPException(400, "Situação do envio inválida.")
    forma = (dados.forma_envio or "").upper() or None
    if forma and forma not in FORMAS_ENVIO:
        raise HTTPException(400, "Forma de envio inválida.")
    if dados.quantidade_g is not None and dados.quantidade_g < 0:
        raise HTTPException(400, "A quantidade não pode ser negativa.")
    if dados.preco_oferecido is not None and dados.preco_oferecido < 0:
        raise HTTPException(400, "O preço oferecido não pode ser negativo.")
    try:
        envio.data_envio = parse_data(dados.data_envio, envio.data_envio or date.today())
        envio.data_retorno = parse_data(dados.data_retorno)
    except ValueError:
        raise HTTPException(400, "Data inválida.") from None
    if envio.data_retorno and envio.data_envio and envio.data_retorno < envio.data_envio:
        raise HTTPException(400, "O retorno não pode ser antes do envio.")
    envio.destinatario_nome = _texto(dados.destinatario_nome, 160)
    envio.destinatario_contato = _texto(dados.destinatario_contato, 120)
    envio.destinatario_endereco = _texto(dados.destinatario_endereco, 200)
    envio.destinatario_cidade = _texto(dados.destinatario_cidade, 80)
    envio.destinatario_uf = (_texto(dados.destinatario_uf, 2) or "").upper() or None
    envio.destinatario_cep = _texto(dados.destinatario_cep, 12)
    envio.quantidade_g = dados.quantidade_g or 0
    envio.forma_envio = forma
    envio.rastreio = _texto(dados.rastreio, 60)
    envio.situacao = situacao
    envio.preco_oferecido = dados.preco_oferecido
    envio.observacao = _texto(dados.observacao, 400)
    # respondeu e ninguém anotou quando: hoje
    if situacao != "AGUARDANDO" and not envio.data_retorno:
        envio.data_retorno = date.today()
    if situacao == "AGUARDANDO":
        envio.data_retorno = None


def _envio_da_conta(db: Session, envio_id: int, usuario: Usuario) -> EnvioAmostra:
    envio = db.get(EnvioAmostra, envio_id)
    if not envio:
        raise HTTPException(404, "Envio não encontrado.")
    validar_empresa(db, envio.empresa_id, usuario)
    return envio


@router.get("/envios")
def listar_envios(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    situacao: str | None = None,
    destinatario_id: int | None = None,
    busca: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(_do_plano),
):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(EnvioAmostra).filter(EnvioAmostra.empresa_id == empresa_id)
    try:
        inicio, fim = parse_data(de), parse_data(ate)
    except ValueError:
        raise HTTPException(400, "Data inválida.") from None
    if inicio:
        consulta = consulta.filter(EnvioAmostra.data_envio >= inicio)
    if fim:
        consulta = consulta.filter(EnvioAmostra.data_envio <= fim)
    if situacao:
        consulta = consulta.filter(EnvioAmostra.situacao == situacao.upper())
    if destinatario_id:
        consulta = consulta.filter(EnvioAmostra.destinatario_id == destinatario_id)
    if busca:
        alvo = f"%{busca.strip()}%"
        consulta = consulta.filter(EnvioAmostra.destinatario_nome.ilike(alvo)
                                   | EnvioAmostra.rastreio.ilike(alvo))
    envios = consulta.order_by(EnvioAmostra.data_envio.desc(), EnvioAmostra.id.desc()).limit(500).all()
    linhas = [_envio(e) for e in envios]
    respondidos = [x for x in linhas if x["situacao"] in ("APROVADA", "RECUSADA")]
    return {
        "envios": linhas,
        "resumo": {
            "total": len(linhas),
            "aguardando": sum(1 for x in linhas if x["situacao"] == "AGUARDANDO"),
            # aguardando há mais de 7 dias: hora de cobrar uma resposta
            "atrasados": sum(1 for x in linhas
                             if x["situacao"] == "AGUARDANDO" and (x["dias"] or 0) > 7),
            "aprovadas": sum(1 for x in linhas if x["situacao"] == "APROVADA"),
            "recusadas": sum(1 for x in linhas if x["situacao"] == "RECUSADA"),
            "aprovacao": (round(100 * sum(1 for x in respondidos if x["situacao"] == "APROVADA")
                                / len(respondidos), 1) if respondidos else None),
        },
    }


@router.put("/envios/{envio_id}")
def salvar_envio(envio_id: int, dados: EnvioIn, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(_do_plano)):
    envio = _envio_da_conta(db, envio_id, usuario)
    _aplicar_envio(db, envio, dados)
    db.commit()
    db.refresh(envio)
    return _envio(envio)


@router.delete("/envios/{envio_id}")
def apagar_envio(envio_id: int, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(_do_plano)):
    envio = _envio_da_conta(db, envio_id, usuario)
    db.delete(envio)
    db.commit()
    return {"ok": True}


def _empresa_impressao(empresa: Empresa | None) -> dict:
    if not empresa:
        return {}
    endereco = ", ".join(x for x in (empresa.logradouro, empresa.numero, empresa.complemento,
                                     empresa.bairro) if x)
    return {
        "razao_social": empresa.razao_social, "nome_fantasia": empresa.nome_fantasia or "",
        "cnpj": empresa.cnpj or "", "endereco": endereco, "cidade": empresa.cidade or "",
        "uf": empresa.uf or "", "cep": empresa.cep or "", "telefone": empresa.telefone or "",
        "email": empresa.email or "", "logo": empresa.logo,
    }


@router.get("/impressao")
def impressao(
    empresa_id: int,
    amostras: str | None = None,
    envios: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(_do_plano),
):
    """Os dados dos fitilhos e etiquetas: amostras (``amostras=1,2``) e/ou envios."""
    validar_empresa(db, empresa_id, usuario)

    def ids(texto):
        try:
            return [int(x) for x in (texto or "").split(",") if x.strip()]
        except ValueError:
            raise HTTPException(400, "Lista de códigos inválida.") from None

    lista_amostras = []
    for amostra_id in ids(amostras)[:300]:
        a = db.get(AmostraCafe, amostra_id)
        if not a or a.empresa_id != empresa_id:
            raise HTTPException(404, "Amostra não encontrada nesta empresa.")
        lista_amostras.append(_ficha(a))
    lista_envios = []
    for envio_id in ids(envios)[:300]:
        e = db.get(EnvioAmostra, envio_id)
        if not e or e.empresa_id != empresa_id:
            raise HTTPException(404, "Envio não encontrado nesta empresa.")
        lista_envios.append(_envio(e))
    return {"empresa": _empresa_impressao(db.get(Empresa, empresa_id)),
            "amostras": lista_amostras, "envios": lista_envios,
            "preparos": regras.PREPAROS, "especies": regras.ESPECIES}


@router.get("")
def listar(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    parceiro_id: int | None = None,
    contrato_id: int | None = None,
    situacao: str | None = None,
    busca: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(_do_plano),
):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(AmostraCafe).filter(AmostraCafe.empresa_id == empresa_id)
    if contrato_id:
        ligadas = db.query(AmostraContrato.amostra_id).filter(
            AmostraContrato.contrato_id == contrato_id)
        consulta = consulta.filter(AmostraCafe.id.in_(ligadas)
                                   | (AmostraCafe.contrato_id == contrato_id))
    try:
        inicio, fim = parse_data(de), parse_data(ate)
    except ValueError:
        raise HTTPException(400, "Data inválida.") from None
    if inicio:
        consulta = consulta.filter(AmostraCafe.data_recebimento >= inicio)
    if fim:
        consulta = consulta.filter(AmostraCafe.data_recebimento <= fim)
    if parceiro_id:
        consulta = consulta.filter(AmostraCafe.parceiro_id == parceiro_id)
    if situacao:
        consulta = consulta.filter(AmostraCafe.situacao == situacao.upper())
    if busca:
        alvo = f"%{busca.strip()}%"
        filtro = (AmostraCafe.produtor_nome.ilike(alvo) | AmostraCafe.fazenda.ilike(alvo)
                  | AmostraCafe.lote.ilike(alvo) | AmostraCafe.padrao.ilike(alvo))
        if busca.strip().isdigit():
            filtro = filtro | (AmostraCafe.numero == int(busca.strip()))
        consulta = consulta.filter(filtro)
    amostras = consulta.order_by(AmostraCafe.numero.desc()).limit(500).all()
    linhas = [serializar(a, exclude={"defeitos", "peneiras", "sensorial", "observacao"},
                         extras={
                             "parceiro_nome": a.parceiro.nome if a.parceiro else None,
                             "padrao": _padrao_final(a),
                             "contratos": [c["numero"] for c in _contratos_da_amostra(a)],
                             "envios": len(a.envios),
                             "envios_aguardando": sum(
                                 1 for e in a.envios if e.situacao == "AGUARDANDO"),
                             "envios_aprovados": sum(
                                 1 for e in a.envios if e.situacao == "APROVADA"),
                         })
              for a in amostras]
    pontuadas = [x["pontuacao"] for x in linhas if x["pontuacao"]]
    return {
        "amostras": linhas,
        "resumo": {
            "total": len(linhas),
            "recebidas": sum(1 for x in linhas if x["situacao"] == "RECEBIDA"),
            "classificadas": sum(1 for x in linhas if x["situacao"] == "CLASSIFICADA"),
            "sacas": round(sum(float(x["sacas"] or 0) for x in linhas), 2),
            "especiais": sum(1 for p in pontuadas if p >= 80),
            "media_pontos": round(sum(pontuadas) / len(pontuadas), 2) if pontuadas else None,
        },
    }


@router.post("")
def criar(dados: AmostraIn, db: Session = Depends(get_db),
          usuario: Usuario = Depends(_do_plano)):
    validar_empresa(db, dados.empresa_id, usuario)
    ultimo = (db.query(func.max(AmostraCafe.numero))
              .filter(AmostraCafe.empresa_id == dados.empresa_id).scalar()) or 0
    amostra = AmostraCafe(empresa_id=dados.empresa_id, numero=ultimo + 1)
    resultado = _aplicar(db, amostra, dados)
    db.add(amostra)
    db.commit()
    db.refresh(amostra)
    return _ficha(amostra, resultado)


@router.get("/{amostra_id}")
def abrir(amostra_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(_do_plano)):
    return _ficha(_amostra(db, amostra_id, usuario))


@router.put("/{amostra_id}")
def salvar(amostra_id: int, dados: AmostraIn, db: Session = Depends(get_db),
           usuario: Usuario = Depends(_do_plano)):
    amostra = _amostra(db, amostra_id, usuario)
    if dados.empresa_id != amostra.empresa_id:
        raise HTTPException(400, "A amostra é de outra empresa.")
    resultado = _aplicar(db, amostra, dados)
    db.commit()
    db.refresh(amostra)
    return _ficha(amostra, resultado)


@router.delete("/{amostra_id}")
def apagar(amostra_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(_do_plano)):
    amostra = _amostra(db, amostra_id, usuario)
    db.delete(amostra)
    db.commit()
    return {"ok": True}


@router.get("/{amostra_id}/laudo")
def laudo(amostra_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(_do_plano)):
    amostra = _amostra(db, amostra_id, usuario)
    return {
        "amostra": _ficha(amostra),
        "empresa": _empresa_impressao(db.get(Empresa, amostra.empresa_id)),
        "preparos": regras.PREPAROS,
        "especies": regras.ESPECIES,
    }


@router.post("/{amostra_id}/envios")
def criar_envio(amostra_id: int, dados: EnvioIn, db: Session = Depends(get_db),
                usuario: Usuario = Depends(_do_plano)):
    amostra = _amostra(db, amostra_id, usuario)
    envio = EnvioAmostra(empresa_id=amostra.empresa_id, amostra_id=amostra.id)
    _aplicar_envio(db, envio, dados)
    db.add(envio)
    db.commit()
    db.refresh(envio)
    return _envio(envio)
