"""WMS — Guia de saída: de que lote e de que posição sai o café.

A guia tem dois níveis::

    Guia (cabeçalho)   data, número, armazém, cliente (dono do café),
                       destinatário, destino, contrato, documento, placa...
      └ Item           lote + posição (quadra e pilha), sacas e peso —
                       pode ser só uma parte do que está na pilha

As sacas e o peso da guia são a soma dos itens. Enquanto está **ABERTA** é
rascunho. Ao **FECHAR**, o sistema confere:

* cada posição tem as sacas que vão sair (o que entrou nela pela guia de
  entrada, menos o que já saiu por outras guias de saída fechadas);
* o cliente ainda tem aquele lote no saldo (uma transferência pode ter levado
  parte dele para outro dono);
* todo lote é do cliente e do armazém da guia;

e gera, para cada lote, uma saída no saldo (``MovimentoArmazem`` tipo SAIDA,
com ``guia_saida_id``). **Reabrir** apaga essas saídas e devolve as sacas às
posições. **Cancelar** só vale para guia aberta.

Rotas
-----
GET  /api/wms/contratos-saida               contratos de venda/corretagem
GET  /api/wms/posicoes-disponiveis          o que o cliente tem, por lote e posição
GET  /api/wms/guias-saida                   lista das guias
GET  /api/wms/guias-saida/{id}              a guia completa
POST /api/wms/guias-saida                   nova guia (aberta)
PUT  /api/wms/guias-saida/{id}              salvar a guia aberta
POST /api/wms/guias-saida/{id}/fechar       fecha e tira do saldo
POST /api/wms/guias-saida/{id}/reabrir      volta para aberta
POST /api/wms/guias-saida/{id}/cancelar     cancela a guia aberta
"""
from __future__ import annotations

from collections import defaultdict
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
    GuiaSaida,
    GuiaSaidaItem,
    LoteArmazem,
    LotePosicao,
    MovimentoArmazem,
    Parceiro,
    Usuario,
)
from ..utils import parse_data, serializar
from .wms import TOLERANCIA, _n, _somar_saldos
from .wms_entrada import saidas_por_posicao

router = APIRouter(prefix="/api/wms", tags=["wms"],
                   dependencies=[Depends(exigir_modulo("WMS"))])

# contratos que podem tirar café do armazém (a compra é a entrada)
TIPOS_DE_CONTRATO = ("VENDA", "CORRETAGEM")


def _num(valor) -> float:
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _texto(valor, limite: int) -> str | None:
    return (str(valor or "")).strip()[:limite] or None


# --------------------------------------------------------------------------- #
# Contratos e o que está disponível
# --------------------------------------------------------------------------- #
def _saido_por_contrato(db: Session, empresa_id: int) -> dict[int, float]:
    linhas = (db.query(GuiaSaida.contrato_id, func.sum(GuiaSaidaItem.sacas))
              .join(GuiaSaidaItem, GuiaSaidaItem.guia_id == GuiaSaida.id)
              .filter(GuiaSaida.empresa_id == empresa_id, GuiaSaida.status == "FECHADA",
                      GuiaSaida.contrato_id.isnot(None))
              .group_by(GuiaSaida.contrato_id).all())
    return {c: float(s or 0) for c, s in linhas}


@router.get("/contratos-saida")
def contratos_saida(empresa_id: int, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(acesso_liberado)):
    """Contratos de venda e de corretagem, com quanto já foi embarcado."""
    validar_empresa(db, empresa_id, usuario)
    contratos = (db.query(Contrato)
                 .filter(Contrato.empresa_id == empresa_id,
                         Contrato.tipo.in_(TIPOS_DE_CONTRATO), Contrato.status != "CANCELADO")
                 .order_by(Contrato.data.desc(), Contrato.id.desc()).limit(300).all())
    saido = _saido_por_contrato(db, empresa_id)
    return [{
        "id": c.id, "numero": c.numero, "tipo": c.tipo,
        "data": c.data.isoformat() if c.data else None,
        "comprador_id": c.comprador_id, "comprador_nome": c.comprador.nome if c.comprador else "",
        "vendedor_id": c.vendedor_id, "vendedor_nome": c.vendedor.nome if c.vendedor else "",
        "local_descarga": c.local_descarga or "",
        "quantidade": float(c.quantidade or 0),
        "sacas_embarcadas": round(saido.get(c.id, 0.0), 2),
    } for c in contratos]


def _disponivel(db: Session, empresa_id: int, armazem_id: int, cliente_id: int) -> list[dict]:
    """Cada posição de cada lote do cliente naquele armazém, com o que resta nela."""
    saiu = saidas_por_posicao(db, empresa_id)
    saldos = _somar_saldos(db, empresa_id)
    lotes = (db.query(LoteArmazem)
             .filter(LoteArmazem.empresa_id == empresa_id, LoteArmazem.armazem_id == armazem_id,
                     LoteArmazem.depositante_id == cliente_id)
             .order_by(LoteArmazem.data_entrada, LoteArmazem.id).all())
    linhas = []
    for lote in lotes:
        chave = (lote.armazem_id, lote.depositante_id, lote.produto_id, lote.codigo.upper())
        saldo_lote = round(saldos.get(chave, {"sacas": 0.0})["sacas"], 2)
        for p in lote.posicoes:
            ja = saiu.get(p.id, {"sacas": 0.0, "peso": 0.0})
            linhas.append({
                "lote_id": lote.id, "lote_codigo": lote.codigo,
                "peneira": lote.peneira, "padrao": lote.padrao,
                "produto_nome": lote.produto.nome if lote.produto else None,
                "saldo_lote": saldo_lote,
                "posicao_id": p.id, "quadra_nome": p.quadra.nome if p.quadra else "-",
                "pilha": p.pilha,
                "sacas_disponiveis": round(float(p.sacas or 0) - ja["sacas"], 2),
                "peso_disponivel": round(float(p.peso or 0) - ja["peso"], 2),
            })
    return linhas


@router.get("/posicoes-disponiveis")
def posicoes_disponiveis(empresa_id: int, armazem_id: int, cliente_id: int,
                         db: Session = Depends(get_db),
                         usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    return [linha for linha in _disponivel(db, empresa_id, armazem_id, cliente_id)
            if linha["sacas_disponiveis"] > TOLERANCIA]


# --------------------------------------------------------------------------- #
# A guia
# --------------------------------------------------------------------------- #
class ItemIn(BaseModel):
    posicao_id: int | None = None
    sacas: float = 0
    peso: float = 0


class GuiaSaidaIn(BaseModel):
    empresa_id: int
    data: str | None = None
    armazem_id: int | None = None
    cliente_id: int | None = None
    destinatario_id: int | None = None
    destino: str | None = None
    contrato_id: int | None = None
    documento: str | None = None
    placa: str | None = None
    motorista: str | None = None
    observacao: str | None = None
    itens: list[ItemIn] = []


class MotivoIn(BaseModel):
    motivo: str | None = None


def _ficha(guia: GuiaSaida, completa: bool = False) -> dict:
    sacas = round(sum(float(i.sacas or 0) for i in guia.itens), 2)
    peso = round(sum(float(i.peso or 0) for i in guia.itens), 2)
    lotes = sorted({i.lote.codigo for i in guia.itens if i.lote})
    ficha = serializar(guia, extras={
        "armazem_nome": guia.armazem.nome if guia.armazem else "-",
        "cliente_nome": guia.cliente.nome if guia.cliente else "-",
        "destinatario_nome": guia.destinatario.nome if guia.destinatario else None,
        "contrato_numero": guia.contrato.numero if guia.contrato else None,
        "sacas": sacas, "peso": peso, "lotes": lotes,
    })
    if completa:
        ficha["itens"] = [serializar(i, extras={
            "lote_codigo": i.lote.codigo if i.lote else "-",
            "peneira": i.lote.peneira if i.lote else None,
            "padrao": i.lote.padrao if i.lote else None,
            "quadra_nome": i.posicao.quadra.nome if i.posicao and i.posicao.quadra else "-",
            "pilha": i.posicao.pilha if i.posicao else None,
        }) for i in guia.itens]
    return ficha


def _guia(db: Session, guia_id: int, usuario: Usuario) -> GuiaSaida:
    guia = db.get(GuiaSaida, guia_id)
    if not guia:
        raise HTTPException(404, "Guia de saída não encontrada.")
    validar_empresa(db, guia.empresa_id, usuario)
    return guia


def _do_cadastro(db: Session, modelo, ident, empresa_id: int, rotulo: str):
    if not ident:
        return None
    obj = db.get(modelo, ident)
    if not obj or obj.empresa_id != empresa_id:
        raise HTTPException(400, f"{rotulo} não encontrado nesta empresa.")
    return obj


def _gravar(db: Session, guia: GuiaSaida, dados: GuiaSaidaIn) -> None:
    eid = dados.empresa_id
    armazem = _do_cadastro(db, Armazem, dados.armazem_id, eid, "Armazém")
    if not armazem:
        raise HTTPException(400, "Escolha o armazém.")
    cliente = _do_cadastro(db, Parceiro, dados.cliente_id, eid, "Cliente")
    if not cliente:
        raise HTTPException(400, "Escolha o cliente (dono do café que vai sair).")
    destinatario = _do_cadastro(db, Parceiro, dados.destinatario_id, eid, "Destinatário")
    contrato = _do_cadastro(db, Contrato, dados.contrato_id, eid, "Contrato")
    if contrato and contrato.tipo not in TIPOS_DE_CONTRATO:
        raise HTTPException(400, f"O contrato {contrato.numero} é de compra — a compra é a entrada.")

    guia.empresa_id = eid
    guia.data = parse_data(dados.data) or guia.data or date.today()
    guia.armazem_id = armazem.id
    guia.cliente_id = cliente.id
    guia.destinatario_id = destinatario.id if destinatario else None
    guia.destino = _texto(dados.destino, 200)
    guia.contrato_id = contrato.id if contrato else None
    guia.documento = _texto(dados.documento, 40)
    guia.placa = (_texto(dados.placa, 10) or "").upper() or None
    guia.motorista = _texto(dados.motorista, 120)
    guia.observacao = _texto(dados.observacao, 300)

    # junta itens repetidos da mesma posição e ignora linha zerada
    por_posicao: dict[int, list[float]] = {}
    for item in dados.itens:
        sacas = max(0.0, _num(item.sacas))
        if not item.posicao_id or sacas <= 0:
            continue
        atual = por_posicao.setdefault(item.posicao_id, [0.0, 0.0])
        atual[0] += sacas
        atual[1] += max(0.0, _num(item.peso))

    guia.itens.clear()
    db.flush()
    for posicao_id, (sacas, peso) in por_posicao.items():
        posicao = db.get(LotePosicao, posicao_id)
        if not posicao or not posicao.lote or posicao.lote.empresa_id != eid:
            raise HTTPException(400, "Posição de lote não encontrada nesta empresa.")
        guia.itens.append(GuiaSaidaItem(lote_id=posicao.lote_id, posicao_id=posicao.id,
                                        sacas=round(sacas, 2), peso=round(peso, 2)))


@router.get("/guias-saida")
def listar(empresa_id: int, de: str | None = None, ate: str | None = None,
           armazem_id: int | None = None, cliente_id: int | None = None,
           status: str | None = None, busca: str | None = None,
           db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(GuiaSaida).filter(GuiaSaida.empresa_id == empresa_id)
    inicio, fim = parse_data(de), parse_data(ate)
    if inicio:
        consulta = consulta.filter(GuiaSaida.data >= inicio)
    if fim:
        consulta = consulta.filter(GuiaSaida.data <= fim)
    if armazem_id:
        consulta = consulta.filter(GuiaSaida.armazem_id == armazem_id)
    if cliente_id:
        consulta = consulta.filter(or_(GuiaSaida.cliente_id == cliente_id,
                                       GuiaSaida.destinatario_id == cliente_id))
    if status:
        consulta = consulta.filter(GuiaSaida.status == status.upper())
    else:
        consulta = consulta.filter(GuiaSaida.status != "CANCELADA")
    texto = (busca or "").strip()
    if texto:
        like = f"%{texto}%"
        filtros = [GuiaSaida.documento.ilike(like), GuiaSaida.placa.ilike(like),
                   GuiaSaida.destino.ilike(like)]
        if texto.isdigit():
            filtros.append(GuiaSaida.numero == int(texto))
        consulta = consulta.filter(or_(*filtros))
    guias = consulta.order_by(GuiaSaida.data.desc(), GuiaSaida.numero.desc()).limit(500).all()
    fichas = [_ficha(g) for g in guias]
    validas = [f for f in fichas if f["status"] != "CANCELADA"]
    return {
        "guias": fichas,
        "resumo": {
            "guias": len(validas),
            "abertas": sum(1 for f in validas if f["status"] == "ABERTA"),
            "sacas": round(sum(f["sacas"] for f in validas), 2),
            "peso_kg": round(sum(f["peso"] for f in validas), 2),
        },
    }


@router.get("/guias-saida/{guia_id}")
def ver(guia_id: int, db: Session = Depends(get_db),
        usuario: Usuario = Depends(acesso_liberado)):
    return _ficha(_guia(db, guia_id, usuario), completa=True)


@router.post("/guias-saida")
def criar(dados: GuiaSaidaIn, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    ultimo = db.query(func.max(GuiaSaida.numero)).filter(
        GuiaSaida.empresa_id == dados.empresa_id).scalar()
    guia = GuiaSaida(numero=int(ultimo or 0) + 1, status="ABERTA", usuario_id=usuario.id)
    _gravar(db, guia, dados)
    db.add(guia)
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.put("/guias-saida/{guia_id}")
def salvar(guia_id: int, dados: GuiaSaidaIn, db: Session = Depends(get_db),
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
    return _ficha(guia, completa=True)


def conferir(db: Session, guia: GuiaSaida) -> list[str]:
    """Tudo o que impede o fechamento."""
    if not guia.itens:
        return ["Escolha o lote e as posições (quadra e pilha) que vão sair."]
    problemas: list[str] = []
    saiu = saidas_por_posicao(db, guia.empresa_id, ignorar_guia_id=guia.id)
    saldos = _somar_saldos(db, guia.empresa_id)
    por_lote: dict[int, float] = defaultdict(float)
    for item in guia.itens:
        lote, pos = item.lote, item.posicao
        onde = f"lote {lote.codigo}, quadra {pos.quadra.nome if pos.quadra else '?'}" + (
            f" pilha {pos.pilha}" if pos.pilha else "")
        if lote.armazem_id != guia.armazem_id:
            problemas.append(f"O {onde} é de outro armazém.")
        if lote.depositante_id != guia.cliente_id:
            problemas.append(f"O lote {lote.codigo} não é do cliente desta guia.")
        resta = float(pos.sacas or 0) - saiu.get(pos.id, {"sacas": 0.0})["sacas"]
        if float(item.sacas) > resta + TOLERANCIA:
            problemas.append(f"No {onde} restam {_n(resta)} sacas — a guia tira {_n(float(item.sacas))}.")
        por_lote[lote.id] += float(item.sacas)
    for item in guia.itens:
        lote = item.lote
        if lote.id not in por_lote:
            continue
        chave = (lote.armazem_id, lote.depositante_id, lote.produto_id, lote.codigo.upper())
        no_saldo = saldos.get(chave, {"sacas": 0.0})["sacas"]
        if por_lote[lote.id] > no_saldo + TOLERANCIA:
            problemas.append(f"O cliente tem {_n(no_saldo)} sacas do lote {lote.codigo} no saldo "
                             f"(pode ter havido transferência) — a guia tira {_n(por_lote[lote.id])}.")
        del por_lote[lote.id]
    return problemas


def _peso_proporcional(item: GuiaSaidaItem, saiu: dict) -> None:
    """Item sem peso digitado leva o peso médio da saca daquela posição."""
    if float(item.peso or 0):
        return
    pos = item.posicao
    ja = saiu.get(pos.id, {"sacas": 0.0, "peso": 0.0})
    resta_sc = float(pos.sacas or 0) - ja["sacas"]
    resta_kg = float(pos.peso or 0) - ja["peso"]
    if resta_sc > TOLERANCIA and resta_kg > 0:
        if abs(float(item.sacas) - resta_sc) <= TOLERANCIA:
            item.peso = round(resta_kg, 2)          # tirou tudo: leva o peso que sobrou
        else:
            item.peso = round(resta_kg / resta_sc * float(item.sacas), 2)


@router.post("/guias-saida/{guia_id}/fechar")
def fechar(guia_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status != "ABERTA":
        raise HTTPException(400, f"A guia {guia.numero} já está {guia.status.lower()}.")
    problemas = conferir(db, guia)
    if problemas:
        raise HTTPException(400, "Não deu para fechar a guia: " + " ".join(problemas))
    saiu = saidas_por_posicao(db, guia.empresa_id, ignorar_guia_id=guia.id)
    por_lote: dict[int, list] = {}
    for item in guia.itens:
        _peso_proporcional(item, saiu)
        atual = por_lote.setdefault(item.lote_id, [item.lote, 0.0, 0.0])
        atual[1] += float(item.sacas)
        atual[2] += float(item.peso or 0)
    for lote, sacas, peso in por_lote.values():
        ultimo = db.query(func.max(MovimentoArmazem.numero)).filter(
            MovimentoArmazem.empresa_id == guia.empresa_id,
            MovimentoArmazem.tipo == "SAIDA").scalar()
        db.add(MovimentoArmazem(
            empresa_id=guia.empresa_id, tipo="SAIDA", numero=int(ultimo or 0) + 1,
            data=guia.data, armazem_id=guia.armazem_id, depositante_id=guia.cliente_id,
            produto_id=lote.produto_id, lote=lote.codigo, sacas=round(sacas, 2),
            peso_kg=round(peso, 2), documento=f"Guia de saída {guia.numero}",
            placa=guia.placa, motorista=guia.motorista, guia_saida_id=guia.id,
            usuario_id=usuario.id, observacao=_texto(
                f"destino: {guia.destino}" if guia.destino else "", 300)))
        db.flush()
    guia.status = "FECHADA"
    guia.fechada_em = datetime.utcnow()
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.post("/guias-saida/{guia_id}/reabrir")
def reabrir(guia_id: int, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status != "FECHADA":
        raise HTTPException(400, "Só guia fechada pode ser reaberta.")
    for m in db.query(MovimentoArmazem).filter(MovimentoArmazem.guia_saida_id == guia.id).all():
        db.delete(m)
    guia.status = "ABERTA"
    guia.fechada_em = None
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.post("/guias-saida/{guia_id}/cancelar")
def cancelar(guia_id: int, dados: MotivoIn, db: Session = Depends(get_db),
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
    return _ficha(guia)
