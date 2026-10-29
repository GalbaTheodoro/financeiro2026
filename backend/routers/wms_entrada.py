"""WMS — Guia de entrada, quadras e lotes do armazém.

A guia de entrada é o documento da descarga e tem três níveis::

    Guia (cabeçalho)   data, número, cliente, cliente de origem, contrato de
                       compra, unidade, peso total e sacas (do ticket)
      └ Lote           número/sequência (15/1, 15/2...), peneira, padrão,
                       peso, sacas, unidade e valor por saca
          └ Local      quadra, pilha, sacas e peso

Enquanto está **ABERTA** a guia é rascunho. Ao **FECHAR**, o sistema confere:

* a soma dos lotes bate com o peso e as sacas do cabeçalho;
* a soma dos locais bate com as sacas (e o peso) de cada lote — local sem peso
  recebe a parte proporcional às sacas;
* toda quadra é do armazém da guia;

e então gera, para cada lote, o ``LoteArmazem`` (código "15/1"), as suas
``LotePosicao`` (quadra + pilha) e a entrada no saldo (``MovimentoArmazem``
tipo ENTRADA, com ``lote = "15/1"``) — é ela que as telas de Saídas,
Transferências e Remoção enxergam.

**Reabrir** desfaz tudo isso, e só é aceito se nenhum lote da guia teve saída,
transferência ou remoção. **Cancelar** só vale para guia aberta.

Rotas
-----
GET  /api/wms/quadras                       quadras (filtro por armazém)
POST /api/wms/quadras                       nova quadra
PUT  /api/wms/quadras/{id}                  alterar quadra
GET  /api/wms/contratos-compra              contratos de compra para a guia
GET  /api/wms/guias-entrada                 lista das guias
GET  /api/wms/guias-entrada/{id}            a guia completa (lotes e locais)
POST /api/wms/guias-entrada                 nova guia (aberta)
PUT  /api/wms/guias-entrada/{id}            salvar a guia aberta
POST /api/wms/guias-entrada/{id}/fechar     fecha e gera lotes e posições
POST /api/wms/guias-entrada/{id}/reabrir    volta para aberta
POST /api/wms/guias-entrada/{id}/cancelar   cancela a guia aberta
GET  /api/wms/lotes                         lotes gerados, com as posições
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import (
    Armazem,
    Contrato,
    GuiaEntrada,
    GuiaEntradaLocal,
    GuiaEntradaLote,
    LoteArmazem,
    LotePosicao,
    MovimentoArmazem,
    Parceiro,
    Produto,
    QuadraArmazem,
    Unidade,
    Usuario,
)
from ..utils import parse_data, serializar
from .wms import TOLERANCIA, _n, _negativos, _somar_saldos

router = APIRouter(prefix="/api/wms", tags=["wms"],
                   dependencies=[Depends(exigir_modulo("WMS"))])


def saidas_por_posicao(db: Session, empresa_id: int,
                       ignorar_guia_id: int | None = None,
                       ignorar_transferencia_id: int | None = None) -> dict[int, dict]:
    """Quanto já deixou cada posição (quadra + pilha): o que saiu pelas guias de
    saída fechadas e o que passou para outro dono pelas guias de transferência
    fechadas (esse café vira posição do lote novo)."""
    from ..models import GuiaSaida, GuiaSaidaItem, GuiaTransferencia, GuiaTransferenciaItem

    total: dict[int, dict] = {}

    def juntar(linhas):
        for pid, sc, kg in linhas:
            atual = total.setdefault(pid, {"sacas": 0.0, "peso": 0.0})
            atual["sacas"] += float(sc or 0)
            atual["peso"] += float(kg or 0)

    saidas = (db.query(GuiaSaidaItem.posicao_id, func.sum(GuiaSaidaItem.sacas),
                       func.sum(GuiaSaidaItem.peso))
              .join(GuiaSaida, GuiaSaida.id == GuiaSaidaItem.guia_id)
              .filter(GuiaSaida.empresa_id == empresa_id, GuiaSaida.status == "FECHADA"))
    if ignorar_guia_id:
        saidas = saidas.filter(GuiaSaida.id != ignorar_guia_id)
    juntar(saidas.group_by(GuiaSaidaItem.posicao_id).all())

    transf = (db.query(GuiaTransferenciaItem.posicao_id, func.sum(GuiaTransferenciaItem.sacas),
                       func.sum(GuiaTransferenciaItem.peso))
              .join(GuiaTransferencia, GuiaTransferencia.id == GuiaTransferenciaItem.guia_id)
              .filter(GuiaTransferencia.empresa_id == empresa_id,
                      GuiaTransferencia.status == "FECHADA"))
    if ignorar_transferencia_id:
        transf = transf.filter(GuiaTransferencia.id != ignorar_transferencia_id)
    juntar(transf.group_by(GuiaTransferenciaItem.posicao_id).all())
    return total


def _num(valor) -> float:
    try:
        return round(float(valor or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _texto(valor: str | None, limite: int) -> str | None:
    return (str(valor or "")).strip()[:limite] or None


def _armazem(db: Session, armazem_id, empresa_id: int) -> Armazem:
    armazem = db.get(Armazem, armazem_id) if armazem_id else None
    if not armazem or armazem.empresa_id != empresa_id:
        raise HTTPException(400, "Escolha o armazém.")
    return armazem


# --------------------------------------------------------------------------- #
# Quadras
# --------------------------------------------------------------------------- #
class QuadraIn(BaseModel):
    empresa_id: int
    armazem_id: int | None = None
    nome: str
    x: float = 0
    y: float = 0
    ativo: bool = True


def _ficha_quadra(q: QuadraArmazem, ocupadas: dict | None = None) -> dict:
    return serializar(q, extras={
        "armazem_nome": q.armazem.nome if q.armazem else "-",
        # o que está na quadra hoje: entrou pelas guias de entrada, menos o que
        # saiu dela pelas guias de saída
        "sacas_atuais": round((ocupadas or {}).get(q.id, 0.0), 2),
    })


@router.get("/quadras")
def listar_quadras(empresa_id: int, armazem_id: int | None = None,
                   db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(QuadraArmazem).filter(QuadraArmazem.empresa_id == empresa_id)
    if armazem_id:
        consulta = consulta.filter(QuadraArmazem.armazem_id == armazem_id)
    quadras = consulta.order_by(QuadraArmazem.armazem_id, QuadraArmazem.nome).all()
    saiu = saidas_por_posicao(db, empresa_id)
    ocupadas: dict[int, float] = {}
    for pos in (db.query(LotePosicao).join(LoteArmazem, LoteArmazem.id == LotePosicao.lote_id)
                .filter(LoteArmazem.empresa_id == empresa_id)):
        resta = float(pos.sacas or 0) - saiu.get(pos.id, {"sacas": 0.0})["sacas"]
        ocupadas[pos.quadra_id] = ocupadas.get(pos.quadra_id, 0.0) + resta
    return [_ficha_quadra(q, ocupadas) for q in quadras]


def _gravar_quadra(db: Session, quadra: QuadraArmazem, dados: QuadraIn) -> None:
    nome = (dados.nome or "").strip().upper()
    if not nome:
        raise HTTPException(400, "Dê um nome à quadra (ex.: A1).")
    armazem = _armazem(db, dados.armazem_id, dados.empresa_id)
    repetida = db.query(QuadraArmazem).filter(
        QuadraArmazem.armazem_id == armazem.id, func.upper(QuadraArmazem.nome) == nome,
        QuadraArmazem.id != (quadra.id or 0)).first()
    if repetida:
        raise HTTPException(400, f"Já existe a quadra {nome} em {armazem.nome}.")
    quadra.empresa_id = dados.empresa_id
    quadra.armazem_id = armazem.id
    quadra.nome = nome[:40]
    quadra.x = _num(dados.x)
    quadra.y = _num(dados.y)
    quadra.ativo = dados.ativo


@router.post("/quadras")
def criar_quadra(dados: QuadraIn, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    quadra = QuadraArmazem()
    _gravar_quadra(db, quadra, dados)
    db.add(quadra)
    db.commit()
    db.refresh(quadra)
    return _ficha_quadra(quadra)


@router.put("/quadras/{quadra_id}")
def alterar_quadra(quadra_id: int, dados: QuadraIn, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    quadra = db.get(QuadraArmazem, quadra_id)
    if not quadra or quadra.empresa_id != dados.empresa_id:
        raise HTTPException(404, "Quadra não encontrada nesta empresa.")
    _gravar_quadra(db, quadra, dados)
    db.commit()
    db.refresh(quadra)
    return _ficha_quadra(quadra)


# --------------------------------------------------------------------------- #
# Contratos de compra (para escolher na guia)
# --------------------------------------------------------------------------- #
def _entregue_por_contrato(db: Session, empresa_id: int) -> dict[int, float]:
    linhas = (db.query(GuiaEntrada.contrato_id, func.sum(GuiaEntrada.sacas))
              .filter(GuiaEntrada.empresa_id == empresa_id, GuiaEntrada.status == "FECHADA",
                      GuiaEntrada.contrato_id.isnot(None))
              .group_by(GuiaEntrada.contrato_id).all())
    return {c: float(s or 0) for c, s in linhas}


@router.get("/contratos-compra")
def contratos_compra(empresa_id: int, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(acesso_liberado)):
    """Contratos de compra que ainda não foram cancelados, com o já recebido."""
    validar_empresa(db, empresa_id, usuario)
    contratos = (db.query(Contrato)
                 .filter(Contrato.empresa_id == empresa_id, Contrato.tipo == "COMPRA",
                         Contrato.status != "CANCELADO")
                 .order_by(Contrato.data.desc(), Contrato.id.desc()).limit(300).all())
    entregue = _entregue_por_contrato(db, empresa_id)
    return [{
        "id": c.id, "numero": c.numero, "data": c.data.isoformat() if c.data else None,
        "vendedor_id": c.vendedor_id, "vendedor_nome": c.vendedor.nome if c.vendedor else "",
        "produto_id": c.produto_id, "produto": c.produto, "unidade_id": c.unidade_id,
        "quantidade": float(c.quantidade or 0), "peso_total": float(c.peso_total or 0),
        "preco_unitario": float(c.preco_unitario or 0),
        "sacas_recebidas": round(entregue.get(c.id, 0.0), 2),
    } for c in contratos]


# --------------------------------------------------------------------------- #
# A guia
# --------------------------------------------------------------------------- #
class LocalIn(BaseModel):
    quadra_id: int | None = None
    pilha: str | None = None
    sacas: float = 0
    peso: float = 0


class LoteIn(BaseModel):
    peneira: str | None = None
    padrao: str | None = None
    peso: float = 0
    sacas: float = 0
    unidade_id: int | None = None
    valor_unitario: float = 0
    locais: list[LocalIn] = []


class GuiaIn(BaseModel):
    empresa_id: int
    data: str | None = None
    armazem_id: int | None = None
    cliente_id: int | None = None
    cliente_origem_id: int | None = None
    contrato_id: int | None = None
    produto_id: int | None = None
    unidade_id: int | None = None
    peso_total: float = 0
    sacas: float = 0
    documento: str | None = None
    placa: str | None = None
    motorista: str | None = None
    observacao: str | None = None
    lotes: list[LoteIn] = []


class MotivoIn(BaseModel):
    motivo: str | None = None


def _codigo(guia: GuiaEntrada, lote: GuiaEntradaLote) -> str:
    return f"{guia.numero}/{lote.sequencia}"


def _ficha_guia(guia: GuiaEntrada, completa: bool = False) -> dict:
    soma_sacas = round(sum(float(l.sacas or 0) for l in guia.lotes), 2)
    soma_peso = round(sum(float(l.peso or 0) for l in guia.lotes), 2)
    ficha = serializar(guia, extras={
        "armazem_nome": guia.armazem.nome if guia.armazem else "-",
        "cliente_nome": guia.cliente.nome if guia.cliente else "-",
        "cliente_origem_nome": guia.cliente_origem.nome if guia.cliente_origem else None,
        "contrato_numero": guia.contrato.numero if guia.contrato else None,
        "produto_nome": guia.produto.nome if guia.produto else None,
        "unidade_codigo": guia.unidade.codigo if guia.unidade else None,
        "qtd_lotes": len(guia.lotes),
        "lotes_sacas": soma_sacas,
        "lotes_peso": soma_peso,
        "valor_total": round(sum(float(l.valor_total or 0) for l in guia.lotes), 2),
    })
    if completa:
        ficha["lotes"] = [serializar(l, extras={
            "codigo": _codigo(guia, l),
            "unidade_codigo": l.unidade.codigo if l.unidade else None,
            "locais": [serializar(loc, extras={
                "quadra_nome": loc.quadra.nome if loc.quadra else "-",
            }) for loc in l.locais],
        }) for l in guia.lotes]
    return ficha


def _guia(db: Session, guia_id: int, usuario: Usuario) -> GuiaEntrada:
    guia = db.get(GuiaEntrada, guia_id)
    if not guia:
        raise HTTPException(404, "Guia de entrada não encontrada.")
    validar_empresa(db, guia.empresa_id, usuario)
    return guia


def _do_cadastro(db: Session, modelo, ident, empresa_id: int, rotulo: str):
    if not ident:
        return None
    obj = db.get(modelo, ident)
    if not obj or obj.empresa_id != empresa_id:
        raise HTTPException(400, f"{rotulo} não encontrado nesta empresa.")
    return obj


def _gravar(db: Session, guia: GuiaEntrada, dados: GuiaIn) -> None:
    """Grava cabeçalho, lotes e locais. Aqui só se barra o que é impossível;
    as contas que precisam bater são conferidas no fechamento."""
    eid = dados.empresa_id
    armazem = _armazem(db, dados.armazem_id, eid)
    if not dados.cliente_id:
        raise HTTPException(400, "Escolha o cliente (dono do café).")
    cliente = _do_cadastro(db, Parceiro, dados.cliente_id, eid, "Cliente")
    origem = _do_cadastro(db, Parceiro, dados.cliente_origem_id, eid, "Cliente de origem")
    contrato = _do_cadastro(db, Contrato, dados.contrato_id, eid, "Contrato")
    if contrato and contrato.tipo != "COMPRA":
        raise HTTPException(400, f"O contrato {contrato.numero} não é de compra.")
    produto = _do_cadastro(db, Produto, dados.produto_id, eid, "Produto")
    unidade = _do_cadastro(db, Unidade, dados.unidade_id, eid, "Unidade")

    guia.empresa_id = eid
    guia.data = parse_data(dados.data) or guia.data or date.today()
    guia.armazem_id = armazem.id
    guia.cliente_id = cliente.id
    guia.cliente_origem_id = origem.id if origem else None
    guia.contrato_id = contrato.id if contrato else None
    guia.produto_id = produto.id if produto else None
    guia.unidade_id = unidade.id if unidade else None
    guia.peso_total = max(0.0, round(_num(dados.peso_total), 2))
    guia.sacas = max(0.0, round(_num(dados.sacas), 2))
    guia.documento = _texto(dados.documento, 40)
    guia.placa = (_texto(dados.placa, 10) or "").upper() or None
    guia.motorista = _texto(dados.motorista, 120)
    guia.observacao = _texto(dados.observacao, 300)

    quadras = {q.id: q for q in db.query(QuadraArmazem).filter(
        QuadraArmazem.empresa_id == eid)}
    guia.lotes.clear()
    db.flush()
    for seq, l in enumerate(dados.lotes, start=1):
        lote_unidade = _do_cadastro(db, Unidade, l.unidade_id, eid, "Unidade do lote")
        sacas = max(0.0, round(_num(l.sacas), 2))
        valor_unit = max(0.0, _num(l.valor_unitario))
        lote = GuiaEntradaLote(
            sequencia=seq, peneira=_texto(l.peneira, 20), padrao=_texto(l.padrao, 60),
            peso=max(0.0, round(_num(l.peso), 2)), sacas=sacas,
            unidade_id=(lote_unidade.id if lote_unidade else guia.unidade_id),
            valor_unitario=valor_unit, valor_total=round(sacas * valor_unit, 2),
        )
        for loc in l.locais:
            if not loc.quadra_id and not _num(loc.sacas):
                continue                          # linha em branco
            quadra = quadras.get(loc.quadra_id or 0)
            if not quadra:
                raise HTTPException(400, f"Lote {guia.numero or 'novo'}/{seq}: escolha a quadra.")
            lote.locais.append(GuiaEntradaLocal(
                quadra_id=quadra.id, pilha=(_texto(loc.pilha, 20) or "").upper() or None,
                sacas=max(0.0, round(_num(loc.sacas), 2)),
                peso=max(0.0, round(_num(loc.peso), 2))))
        guia.lotes.append(lote)


@router.get("/guias-entrada")
def listar_guias(empresa_id: int, de: str | None = None, ate: str | None = None,
                 armazem_id: int | None = None, cliente_id: int | None = None,
                 status: str | None = None, busca: str | None = None,
                 mostrar_cancelados: bool = False,
                 db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(GuiaEntrada).filter(GuiaEntrada.empresa_id == empresa_id)
    inicio, fim = parse_data(de), parse_data(ate)
    if inicio:
        consulta = consulta.filter(GuiaEntrada.data >= inicio)
    if fim:
        consulta = consulta.filter(GuiaEntrada.data <= fim)
    if armazem_id:
        consulta = consulta.filter(GuiaEntrada.armazem_id == armazem_id)
    if cliente_id:
        consulta = consulta.filter(or_(GuiaEntrada.cliente_id == cliente_id,
                                       GuiaEntrada.cliente_origem_id == cliente_id))
    if status:
        consulta = consulta.filter(GuiaEntrada.status == status.upper())
    elif not mostrar_cancelados:
        consulta = consulta.filter(GuiaEntrada.status != "CANCELADA")
    texto = (busca or "").strip()
    if texto:
        like = f"%{texto}%"
        filtros = [GuiaEntrada.documento.ilike(like), GuiaEntrada.placa.ilike(like)]
        if texto.split("/")[0].isdigit():
            filtros.append(GuiaEntrada.numero == int(texto.split("/")[0]))
        consulta = consulta.filter(or_(*filtros))
    guias = consulta.order_by(GuiaEntrada.data.desc(), GuiaEntrada.numero.desc()).limit(500).all()
    validas = [g for g in guias if g.status != "CANCELADA"]
    return {
        "guias": [_ficha_guia(g) for g in guias],
        "resumo": {
            "guias": len(validas),
            "abertas": sum(1 for g in validas if g.status == "ABERTA"),
            "sacas": round(sum(float(g.sacas or 0) for g in validas), 2),
            "peso_kg": round(sum(float(g.peso_total or 0) for g in validas), 2),
        },
    }


@router.get("/guias-entrada/{guia_id}")
def ver_guia(guia_id: int, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    return _ficha_guia(_guia(db, guia_id, usuario), completa=True)


@router.post("/guias-entrada")
def criar_guia(dados: GuiaIn, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    ultimo = db.query(func.max(GuiaEntrada.numero)).filter(
        GuiaEntrada.empresa_id == dados.empresa_id).scalar()
    guia = GuiaEntrada(numero=int(ultimo or 0) + 1, status="ABERTA", usuario_id=usuario.id)
    _gravar(db, guia, dados)       # entra na sessão só depois de preenchida
    db.add(guia)
    db.commit()
    db.refresh(guia)
    return _ficha_guia(guia, completa=True)


@router.put("/guias-entrada/{guia_id}")
def salvar_guia(guia_id: int, dados: GuiaIn, db: Session = Depends(get_db),
                usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.empresa_id != dados.empresa_id:
        raise HTTPException(400, "A guia é de outra empresa.")
    if guia.status != "ABERTA":
        raise HTTPException(400, f"A guia {guia.numero} está {guia.status.lower()} — "
                                 "reabra para alterar.")
    _gravar(db, guia, dados)
    db.commit()
    db.refresh(guia)
    return _ficha_guia(guia, completa=True)


# --------------------------------------------------------------------------- #
# Fechar, reabrir, cancelar
# --------------------------------------------------------------------------- #
def _bate(a: float, b: float) -> bool:
    return abs(round(a, 2) - round(b, 2)) <= TOLERANCIA * 2


def conferir(guia: GuiaEntrada) -> list[str]:
    """Tudo o que impede o fechamento, numa lista de frases para a tela."""
    problemas: list[str] = []
    if not guia.lotes:
        return ["A guia não tem nenhum lote."]
    soma_sacas = sum(float(l.sacas or 0) for l in guia.lotes)
    soma_peso = sum(float(l.peso or 0) for l in guia.lotes)
    if not _bate(soma_sacas, float(guia.sacas or 0)):
        problemas.append(f"Os lotes somam {_n(soma_sacas)} sacas e o cabeçalho diz "
                         f"{_n(float(guia.sacas or 0))}.")
    if not _bate(soma_peso, float(guia.peso_total or 0)):
        problemas.append(f"Os lotes somam {_n(soma_peso)} kg e o cabeçalho diz "
                         f"{_n(float(guia.peso_total or 0))} kg.")
    for l in guia.lotes:
        codigo = _codigo(guia, l)
        if float(l.sacas or 0) <= 0:
            problemas.append(f"Lote {codigo}: informe as sacas.")
            continue
        if not l.locais:
            problemas.append(f"Lote {codigo}: diga em que quadra ele foi guardado.")
            continue
        sacas_locais = sum(float(x.sacas or 0) for x in l.locais)
        if not _bate(sacas_locais, float(l.sacas or 0)):
            problemas.append(f"Lote {codigo}: os locais somam {_n(sacas_locais)} sacas e o "
                             f"lote tem {_n(float(l.sacas or 0))}.")
        peso_locais = sum(float(x.peso or 0) for x in l.locais)
        if peso_locais and not _bate(peso_locais, float(l.peso or 0)):
            problemas.append(f"Lote {codigo}: os locais somam {_n(peso_locais)} kg e o lote "
                             f"tem {_n(float(l.peso or 0))} kg.")
        for x in l.locais:
            if x.quadra and x.quadra.armazem_id != guia.armazem_id:
                problemas.append(f"Lote {codigo}: a quadra {x.quadra.nome} é de outro armazém.")
            if float(x.sacas or 0) <= 0:
                problemas.append(f"Lote {codigo}: o local na quadra "
                                 f"{x.quadra.nome if x.quadra else '?'} está sem sacas.")
    return problemas


def _distribuir_peso(lote: GuiaEntradaLote) -> None:
    """Local sem peso digitado recebe a parte do lote proporcional às sacas."""
    if any(float(x.peso or 0) for x in lote.locais) or not float(lote.peso or 0):
        return
    total = float(lote.sacas or 0)
    restante = round(float(lote.peso), 2)
    for i, x in enumerate(lote.locais):
        if i == len(lote.locais) - 1:
            x.peso = restante
        else:
            x.peso = round(float(lote.peso) * float(x.sacas or 0) / total, 2)
            restante = round(restante - float(x.peso), 2)


@router.post("/guias-entrada/{guia_id}/fechar")
def fechar_guia(guia_id: int, db: Session = Depends(get_db),
                usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status != "ABERTA":
        raise HTTPException(400, f"A guia {guia.numero} já está {guia.status.lower()}.")
    if not guia.armazem or not guia.armazem.ativo:
        raise HTTPException(400, "O armazém da guia está inativo.")
    problemas = conferir(guia)
    if problemas:
        raise HTTPException(400, "Não deu para fechar a guia: " + " ".join(problemas))

    for l in guia.lotes:
        _distribuir_peso(l)
        codigo = _codigo(guia, l)
        lote = LoteArmazem(
            empresa_id=guia.empresa_id, guia_id=guia.id, guia_lote_id=l.id, codigo=codigo,
            data_entrada=guia.data, armazem_id=guia.armazem_id, depositante_id=guia.cliente_id,
            produto_id=guia.produto_id, peneira=l.peneira, padrao=l.padrao,
            sacas=l.sacas, peso=l.peso, unidade_id=l.unidade_id,
            valor_unitario=l.valor_unitario, valor_total=l.valor_total,
        )
        for x in l.locais:
            lote.posicoes.append(LotePosicao(quadra_id=x.quadra_id, pilha=x.pilha,
                                             sacas=x.sacas, peso=x.peso))
        db.add(lote)
        db.flush()
        religar_amostra(db, lote)
        # a entrada no saldo: é o que Saídas, Transferências e Remoção enxergam
        ultimo = db.query(func.max(MovimentoArmazem.numero)).filter(
            MovimentoArmazem.empresa_id == guia.empresa_id,
            MovimentoArmazem.tipo == "ENTRADA").scalar()
        db.add(MovimentoArmazem(
            empresa_id=guia.empresa_id, tipo="ENTRADA", numero=int(ultimo or 0) + 1,
            data=guia.data, armazem_id=guia.armazem_id, depositante_id=guia.cliente_id,
            produto_id=guia.produto_id, lote=codigo, sacas=l.sacas, peso_kg=l.peso,
            documento=f"Guia {guia.numero}", placa=guia.placa, motorista=guia.motorista,
            guia_entrada_id=guia.id, usuario_id=usuario.id,
            observacao=" · ".join(filter(None, [
                f"peneira {l.peneira}" if l.peneira else "", l.padrao or ""]))[:300] or None,
        ))
        db.flush()
    guia.status = "FECHADA"
    guia.fechada_em = datetime.utcnow()
    db.commit()
    db.refresh(guia)
    return _ficha_guia(guia, completa=True)


@router.post("/guias-entrada/{guia_id}/reabrir")
def reabrir_guia(guia_id: int, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status != "FECHADA":
        raise HTTPException(400, "Só guia fechada pode ser reaberta.")
    from ..models import GuiaSaida, GuiaSaidaItem

    from ..models import GuiaRemocao, GuiaTransferencia, GuiaTransferenciaItem

    removidos = (db.query(GuiaRemocao.numero)
                 .join(LoteArmazem, LoteArmazem.id == GuiaRemocao.lote_id)
                 .filter(LoteArmazem.guia_id == guia.id, GuiaRemocao.status == "ATIVA").all())
    if removidos:
        numeros = ", ".join(str(n[0]) for n in removidos)
        raise HTTPException(
            400, f"Não dá para reabrir a guia {guia.numero}: os lotes dela mudaram de local "
                 f"(remoção {numeros}). Estorne a(s) remoção(ões) primeiro.")
    em_transf = (db.query(GuiaTransferencia.numero)
                 .join(GuiaTransferenciaItem, GuiaTransferenciaItem.guia_id == GuiaTransferencia.id)
                 .join(LoteArmazem, LoteArmazem.id == GuiaTransferenciaItem.lote_id)
                 .filter(LoteArmazem.guia_id == guia.id, GuiaTransferencia.status != "CANCELADA")
                 .distinct().all())
    if em_transf:
        numeros = ", ".join(str(n[0]) for n in em_transf)
        raise HTTPException(
            400, f"Não dá para reabrir a guia {guia.numero}: os lotes dela estão na(s) guia(s) "
                 f"de transferência {numeros}. Reabra e tire os itens (ou cancele) essas guias primeiro.")
    em_saida = (db.query(GuiaSaida.numero).join(GuiaSaidaItem, GuiaSaidaItem.guia_id == GuiaSaida.id)
                .join(LoteArmazem, LoteArmazem.id == GuiaSaidaItem.lote_id)
                .filter(LoteArmazem.guia_id == guia.id, GuiaSaida.status != "CANCELADA")
                .distinct().all())
    if em_saida:
        numeros = ", ".join(str(n[0]) for n in em_saida)
        raise HTTPException(
            400, f"Não dá para reabrir a guia {guia.numero}: os lotes dela estão na(s) guia(s) "
                 f"de saída {numeros}. Reabra e tire os itens (ou cancele) essas guias primeiro.")
    entradas = db.query(MovimentoArmazem).filter(
        MovimentoArmazem.guia_entrada_id == guia.id, MovimentoArmazem.status == "ATIVO").all()
    # sem estas entradas, alguém fica com saldo negativo? então já saiu café da guia
    saldos = _somar_saldos(db, guia.empresa_id)
    for m in entradas:
        chave = (m.armazem_id, m.depositante_id, m.produto_id, (m.lote or "").upper())
        if chave in saldos:
            saldos[chave]["sacas"] -= float(m.sacas or 0)
    if _negativos(saldos):
        raise HTTPException(
            400, f"Não dá para reabrir a guia {guia.numero}: parte dos lotes dela já saiu, "
                 "foi transferida ou removida. Cancele esses lançamentos primeiro.")
    for m in entradas:
        db.delete(m)
    apagar = db.query(LoteArmazem).filter(LoteArmazem.guia_id == guia.id).all()
    desligar_amostras(db, [l.id for l in apagar])
    for lote in apagar:
        db.delete(lote)
    guia.status = "ABERTA"
    guia.fechada_em = None
    db.commit()
    db.refresh(guia)
    return _ficha_guia(guia, completa=True)


@router.post("/guias-entrada/{guia_id}/cancelar")
def cancelar_guia(guia_id: int, dados: MotivoIn, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status == "FECHADA":
        raise HTTPException(400, "A guia está fechada: reabra antes de cancelar.")
    if guia.status == "CANCELADA":
        raise HTTPException(400, "A guia já está cancelada.")
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise HTTPException(400, "Escreva o motivo do cancelamento.")
    guia.status = "CANCELADA"
    obs = f"Cancelada: {motivo}"
    guia.observacao = (f"{guia.observacao} | {obs}" if guia.observacao else obs)[:300]
    db.commit()
    db.refresh(guia)
    return _ficha_guia(guia)


# --------------------------------------------------------------------------- #
# Lotes gerados
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Amostra do lote: cada lote tem a sua (botão Classificar na tela Lotes)
# --------------------------------------------------------------------------- #
def desligar_amostras(db: Session, lote_ids: list[int]) -> None:
    """Antes de apagar lotes (reabrir guia), solta a amostra — ela continua,
    com o código do lote no campo Lote, e volta a se ligar quando o lote nascer
    de novo (ver ``religar_amostra``)."""
    from ..models import AmostraCafe

    if not lote_ids:
        return
    for amostra in db.query(AmostraCafe).filter(AmostraCafe.lote_armazem_id.in_(lote_ids)):
        amostra.lote_armazem_id = None
    db.flush()


def religar_amostra(db: Session, lote: LoteArmazem) -> None:
    """Lote que nasce de novo (guia fechada outra vez) recupera a amostra dele."""
    from ..models import AmostraCafe

    amostra = (db.query(AmostraCafe)
               .filter(AmostraCafe.empresa_id == lote.empresa_id,
                       AmostraCafe.lote_armazem_id.is_(None),
                       func.upper(AmostraCafe.lote) == lote.codigo.upper(),
                       AmostraCafe.parceiro_id == lote.depositante_id)
               .order_by(AmostraCafe.id.desc()).first())
    if amostra:
        amostra.lote_armazem_id = lote.id


def _amostras_dos_lotes(db: Session, ids: list[int]) -> dict:
    from ..models import AmostraCafe

    if not ids:
        return {}
    return {a.lote_armazem_id: a for a in db.query(AmostraCafe).filter(
        AmostraCafe.lote_armazem_id.in_(ids))}


@router.post("/lotes/{lote_id}/amostra")
def amostra_do_lote(lote_id: int, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(acesso_liberado)):
    """Abre a amostra do lote — e cria, se ainda não tiver.

    A amostra nasce preenchida com o que o lote já sabe: o dono (produtor), o
    código do lote, as sacas, o armazém e o produto; peneira e padrão da
    entrada vão na observação. Daí em diante é a ficha normal de Amostras.
    """
    from ..models import AmostraCafe

    lote = db.get(LoteArmazem, lote_id)
    if not lote:
        raise HTTPException(404, "Lote não encontrado.")
    validar_empresa(db, lote.empresa_id, usuario)
    existente = db.query(AmostraCafe).filter(AmostraCafe.lote_armazem_id == lote.id).first()
    if existente:
        return {"amostra_id": existente.id, "numero": existente.numero, "nova": False}
    ultimo = (db.query(func.max(AmostraCafe.numero))
              .filter(AmostraCafe.empresa_id == lote.empresa_id).scalar()) or 0
    entrada = " · ".join(filter(None, [
        f"peneira {lote.peneira}" if lote.peneira else "",
        f"padrão {lote.padrao}" if lote.padrao else ""]))
    amostra = AmostraCafe(
        empresa_id=lote.empresa_id, numero=int(ultimo) + 1, situacao="RECEBIDA",
        data_recebimento=date.today(), lote_armazem_id=lote.id,
        parceiro_id=lote.depositante_id,
        produtor_nome=lote.depositante.nome if lote.depositante else None,
        municipio=lote.armazem.cidade if lote.armazem else None,
        uf=lote.armazem.uf if lote.armazem else None,
        lote=lote.codigo, sacas=float(lote.sacas or 0),
        armazem=lote.armazem.nome if lote.armazem else None,
        observacao=(f"Amostra do lote {lote.codigo} do armazém"
                    + (f" (entrada: {entrada})" if entrada else "") + "."),
    )
    db.add(amostra)
    db.commit()
    db.refresh(amostra)
    return {"amostra_id": amostra.id, "numero": amostra.numero, "nova": True}


@router.get("/lotes")
def listar_lotes(empresa_id: int, armazem_id: int | None = None,
                 depositante_id: int | None = None, quadra_id: int | None = None,
                 guia_id: int | None = None, busca: str | None = None,
                 com_saldo: bool = False, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    """Os lotes, com as posições, o saldo de hoje e a amostra de cada um."""
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(LoteArmazem).filter(LoteArmazem.empresa_id == empresa_id)
    if armazem_id:
        consulta = consulta.filter(LoteArmazem.armazem_id == armazem_id)
    if depositante_id:
        consulta = consulta.filter(LoteArmazem.depositante_id == depositante_id)
    if guia_id:
        consulta = consulta.filter(LoteArmazem.guia_id == guia_id)
    if quadra_id:
        consulta = consulta.filter(LoteArmazem.posicoes.any(LotePosicao.quadra_id == quadra_id))
    texto = (busca or "").strip()
    if texto:
        like = f"%{texto}%"
        consulta = consulta.filter(or_(LoteArmazem.codigo.ilike(like),
                                       LoteArmazem.peneira.ilike(like),
                                       LoteArmazem.padrao.ilike(like)))
    lotes = consulta.order_by(LoteArmazem.data_entrada.desc(), LoteArmazem.id.desc()).limit(500).all()
    saldos = _somar_saldos(db, empresa_id)
    saiu = saidas_por_posicao(db, empresa_id)
    amostras = _amostras_dos_lotes(db, [l.id for l in lotes])
    origens = {l.id: l.codigo for l in db.query(LoteArmazem).filter(
        LoteArmazem.id.in_([l.lote_origem_id for l in lotes if l.lote_origem_id] or [0]))}
    saida = []
    for lote in lotes:
        chave = (lote.armazem_id, lote.depositante_id, lote.produto_id, lote.codigo.upper())
        # o lote todo, somando o que foi removido para outro armazém
        total = {"sacas": 0.0, "peso_kg": 0.0}
        for (a_id, d_id, p_id, cod), v in saldos.items():
            if d_id == lote.depositante_id and p_id == lote.produto_id and cod == lote.codigo.upper():
                total["sacas"] += v["sacas"]
                total["peso_kg"] += v["peso_kg"]
        if com_saldo and total["sacas"] <= TOLERANCIA:
            continue
        amostra = amostras.get(lote.id)
        saida.append(serializar(lote, extras={
            "guia_numero": lote.guia_id and db.get(GuiaEntrada, lote.guia_id).numero,
            "lote_origem_codigo": origens.get(lote.lote_origem_id),
            "saldo_peso": round(saldos.get(chave, {"peso_kg": 0.0})["peso_kg"], 2),
            "saldo_total": round(total["sacas"], 2),
            "saldo_outros_armazens": round(total["sacas"]
                                           - saldos.get(chave, {"sacas": 0.0})["sacas"], 2),
            "amostra": ({"id": amostra.id, "numero": amostra.numero, "situacao": amostra.situacao,
                         "tipo": amostra.tipo, "pontuacao": amostra.pontuacao,
                         "padrao": amostra.padrao, "bebida": amostra.bebida}
                        if amostra else None),
            "armazem_nome": lote.armazem.nome if lote.armazem else "-",
            "depositante_nome": lote.depositante.nome if lote.depositante else "-",
            "produto_nome": lote.produto.nome if lote.produto else None,
            "unidade_codigo": lote.unidade.codigo if lote.unidade else None,
            "saldo_sacas": round(saldos.get(chave, {"sacas": 0.0})["sacas"], 2),
            "posicoes": [serializar(p, extras={
                "quadra_nome": p.quadra.nome if p.quadra else "-",
                "quadra_x": float(p.quadra.x or 0) if p.quadra else 0,
                "quadra_y": float(p.quadra.y or 0) if p.quadra else 0,
                "sacas_disponiveis": round(float(p.sacas or 0)
                                           - saiu.get(p.id, {"sacas": 0.0})["sacas"], 2),
                "peso_disponivel": round(float(p.peso or 0)
                                         - saiu.get(p.id, {"peso": 0.0})["peso"], 2),
            }) for p in lote.posicoes],
        }))
    return saida
