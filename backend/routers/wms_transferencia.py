"""WMS — Guia de transferência: o café muda de dono sem sair do lugar.

A guia tem dois níveis::

    Guia (cabeçalho)   data, número, armazém, cliente (dono atual),
                       cliente novo, documento, observação
      └ Item           lote + posição (quadra e pilha), sacas e peso —
                       pode ser só uma parte

Ao **FECHAR**, o sistema confere (como na saída) que cada posição tem as
sacas e que o cliente tem o lote no saldo, e então, para **cada lote de
origem**, gera um **lote novo** do cliente novo:

* código = código do lote de origem + "T" ("1/1" -> "1/1T"). Se esse código
  já existir na empresa, "1/1T2", "1/1T3"... — nunca fica lote repetido;
* mesmo produto, peneira, padrão, unidade e valor por saca do lote de origem;
* as posições do lote novo são as mesmas quadras e pilhas, com as sacas
  transferidas; a posição de origem perde essas sacas;
* no saldo, um ``MovimentoArmazem`` TRANSFERENCIA tira do lote de origem do
  cliente e põe no lote novo do cliente novo (``lote_destino``).

**Reabrir** apaga os lotes novos e o movimento — só se nada saiu dos lotes
novos (nem guia de saída, nem outra transferência). **Cancelar** só aberta.

Rotas
-----
GET  /api/wms/guias-transferencia                lista
GET  /api/wms/guias-transferencia/{id}           a guia completa
POST /api/wms/guias-transferencia                nova (aberta)
PUT  /api/wms/guias-transferencia/{id}           salvar a guia aberta
POST /api/wms/guias-transferencia/{id}/fechar    fecha e gera os lotes novos
POST /api/wms/guias-transferencia/{id}/reabrir   volta para aberta
POST /api/wms/guias-transferencia/{id}/cancelar  cancela a guia aberta

As posições disponíveis do cliente vêm de ``/api/wms/posicoes-disponiveis``
(em wms_saida.py), a mesma lista da guia de saída.
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
    GuiaSaida,
    GuiaSaidaItem,
    GuiaTransferencia,
    GuiaTransferenciaItem,
    LoteArmazem,
    LotePosicao,
    MovimentoArmazem,
    Parceiro,
    Usuario,
)
from ..utils import parse_data, serializar
from .wms import TOLERANCIA, _n, _negativos, _somar_saldos
from .wms_entrada import desligar_amostras, religar_amostra, saidas_por_posicao

router = APIRouter(prefix="/api/wms", tags=["wms"],
                   dependencies=[Depends(exigir_modulo("WMS"))])


def _num(valor) -> float:
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _texto(valor, limite: int) -> str | None:
    return (str(valor or "")).strip()[:limite] or None


class ItemIn(BaseModel):
    posicao_id: int | None = None
    sacas: float = 0
    peso: float = 0


class GuiaTransferenciaIn(BaseModel):
    empresa_id: int
    data: str | None = None
    armazem_id: int | None = None
    cliente_id: int | None = None
    cliente_novo_id: int | None = None
    documento: str | None = None
    observacao: str | None = None
    itens: list[ItemIn] = []


class MotivoIn(BaseModel):
    motivo: str | None = None


def codigo_livre(db: Session, empresa_id: int, origem: str, usados: set[str] | None = None) -> str:
    """O código do lote novo: origem + "T"; se já existir, "T2", "T3"..."""
    existentes = {c.upper() for (c,) in db.query(LoteArmazem.codigo).filter(
        LoteArmazem.empresa_id == empresa_id, LoteArmazem.codigo.like(f"{origem}T%"))}
    existentes |= {u.upper() for u in (usados or set())}
    candidato = f"{origem}T"
    seq = 2
    while candidato.upper() in existentes:
        candidato = f"{origem}T{seq}"
        seq += 1
    return candidato[:40]


def _ficha(guia: GuiaTransferencia, completa: bool = False) -> dict:
    sacas = round(sum(float(i.sacas or 0) for i in guia.itens), 2)
    peso = round(sum(float(i.peso or 0) for i in guia.itens), 2)
    ficha = serializar(guia, extras={
        "armazem_nome": guia.armazem.nome if guia.armazem else "-",
        "cliente_nome": guia.cliente.nome if guia.cliente else "-",
        "cliente_novo_nome": guia.cliente_novo.nome if guia.cliente_novo else "-",
        "sacas": sacas, "peso": peso,
        "lotes": sorted({i.lote.codigo for i in guia.itens if i.lote}),
        "lotes_novos": sorted({i.lote_novo.codigo for i in guia.itens if i.lote_novo}),
    })
    if completa:
        ficha["itens"] = [serializar(i, extras={
            "lote_codigo": i.lote.codigo if i.lote else "-",
            "lote_novo_codigo": i.lote_novo.codigo if i.lote_novo else None,
            "peneira": i.lote.peneira if i.lote else None,
            "padrao": i.lote.padrao if i.lote else None,
            "quadra_nome": i.posicao.quadra.nome if i.posicao and i.posicao.quadra else "-",
            "pilha": i.posicao.pilha if i.posicao else None,
        }) for i in guia.itens]
    return ficha


def _guia(db: Session, guia_id: int, usuario: Usuario) -> GuiaTransferencia:
    guia = db.get(GuiaTransferencia, guia_id)
    if not guia:
        raise HTTPException(404, "Guia de transferência não encontrada.")
    validar_empresa(db, guia.empresa_id, usuario)
    return guia


def _do_cadastro(db: Session, modelo, ident, empresa_id: int, rotulo: str):
    if not ident:
        return None
    obj = db.get(modelo, ident)
    if not obj or obj.empresa_id != empresa_id:
        raise HTTPException(400, f"{rotulo} não encontrado nesta empresa.")
    return obj


def _gravar(db: Session, guia: GuiaTransferencia, dados: GuiaTransferenciaIn) -> None:
    eid = dados.empresa_id
    armazem = _do_cadastro(db, Armazem, dados.armazem_id, eid, "Armazém")
    if not armazem:
        raise HTTPException(400, "Escolha o armazém.")
    cliente = _do_cadastro(db, Parceiro, dados.cliente_id, eid, "Cliente")
    if not cliente:
        raise HTTPException(400, "Escolha o cliente (dono atual do café).")
    novo = _do_cadastro(db, Parceiro, dados.cliente_novo_id, eid, "Cliente novo")
    if not novo:
        raise HTTPException(400, "Escolha o cliente novo (quem passa a ser o dono).")
    if novo.id == cliente.id:
        raise HTTPException(400, "O cliente novo é o mesmo cliente de origem.")

    guia.empresa_id = eid
    guia.data = parse_data(dados.data) or guia.data or date.today()
    guia.armazem_id = armazem.id
    guia.cliente_id = cliente.id
    guia.cliente_novo_id = novo.id
    guia.documento = _texto(dados.documento, 40)
    guia.observacao = _texto(dados.observacao, 300)

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
        guia.itens.append(GuiaTransferenciaItem(lote_id=posicao.lote_id, posicao_id=posicao.id,
                                                sacas=round(sacas, 2), peso=round(peso, 2)))


@router.get("/guias-transferencia")
def listar(empresa_id: int, de: str | None = None, ate: str | None = None,
           armazem_id: int | None = None, cliente_id: int | None = None,
           status: str | None = None, busca: str | None = None,
           db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(GuiaTransferencia).filter(GuiaTransferencia.empresa_id == empresa_id)
    inicio, fim = parse_data(de), parse_data(ate)
    if inicio:
        consulta = consulta.filter(GuiaTransferencia.data >= inicio)
    if fim:
        consulta = consulta.filter(GuiaTransferencia.data <= fim)
    if armazem_id:
        consulta = consulta.filter(GuiaTransferencia.armazem_id == armazem_id)
    if cliente_id:
        consulta = consulta.filter(or_(GuiaTransferencia.cliente_id == cliente_id,
                                       GuiaTransferencia.cliente_novo_id == cliente_id))
    if status:
        consulta = consulta.filter(GuiaTransferencia.status == status.upper())
    else:
        consulta = consulta.filter(GuiaTransferencia.status != "CANCELADA")
    texto = (busca or "").strip()
    if texto:
        filtros = [GuiaTransferencia.documento.ilike(f"%{texto}%")]
        if texto.isdigit():
            filtros.append(GuiaTransferencia.numero == int(texto))
        consulta = consulta.filter(or_(*filtros))
    guias = consulta.order_by(GuiaTransferencia.data.desc(),
                              GuiaTransferencia.numero.desc()).limit(500).all()
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


@router.get("/guias-transferencia/{guia_id}")
def ver(guia_id: int, db: Session = Depends(get_db),
        usuario: Usuario = Depends(acesso_liberado)):
    return _ficha(_guia(db, guia_id, usuario), completa=True)


@router.post("/guias-transferencia")
def criar(dados: GuiaTransferenciaIn, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    ultimo = db.query(func.max(GuiaTransferencia.numero)).filter(
        GuiaTransferencia.empresa_id == dados.empresa_id).scalar()
    guia = GuiaTransferencia(numero=int(ultimo or 0) + 1, status="ABERTA", usuario_id=usuario.id)
    _gravar(db, guia, dados)
    db.add(guia)
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.put("/guias-transferencia/{guia_id}")
def salvar(guia_id: int, dados: GuiaTransferenciaIn, db: Session = Depends(get_db),
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


def conferir(db: Session, guia: GuiaTransferencia) -> list[str]:
    if not guia.itens:
        return ["Escolha o lote e as posições (quadra e pilha) que vão mudar de dono."]
    if guia.cliente_novo_id == guia.cliente_id:
        return ["O cliente novo é o mesmo cliente de origem."]
    problemas: list[str] = []
    saiu = saidas_por_posicao(db, guia.empresa_id, ignorar_transferencia_id=guia.id)
    saldos = _somar_saldos(db, guia.empresa_id)
    por_lote: dict[int, list] = {}
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
            problemas.append(f"No {onde} restam {_n(resta)} sacas — a guia transfere "
                             f"{_n(float(item.sacas))}.")
        por_lote.setdefault(lote.id, [lote, 0.0])[1] += float(item.sacas)
    for lote, sacas in por_lote.values():
        chave = (lote.armazem_id, lote.depositante_id, lote.produto_id, lote.codigo.upper())
        no_saldo = saldos.get(chave, {"sacas": 0.0})["sacas"]
        if sacas > no_saldo + TOLERANCIA:
            problemas.append(f"O cliente tem {_n(no_saldo)} sacas do lote {lote.codigo} no saldo "
                             f"— a guia transfere {_n(sacas)}.")
    return problemas


def _peso_do_item(item: GuiaTransferenciaItem, saiu: dict) -> None:
    """Item sem peso digitado leva o peso médio da saca daquela posição."""
    if float(item.peso or 0):
        return
    pos = item.posicao
    ja = saiu.get(pos.id, {"sacas": 0.0, "peso": 0.0})
    resta_sc = float(pos.sacas or 0) - ja["sacas"]
    resta_kg = float(pos.peso or 0) - ja["peso"]
    if resta_sc > TOLERANCIA and resta_kg > 0:
        if abs(float(item.sacas) - resta_sc) <= TOLERANCIA:
            item.peso = round(resta_kg, 2)
        else:
            item.peso = round(resta_kg / resta_sc * float(item.sacas), 2)


@router.post("/guias-transferencia/{guia_id}/fechar")
def fechar(guia_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status != "ABERTA":
        raise HTTPException(400, f"A guia {guia.numero} já está {guia.status.lower()}.")
    problemas = conferir(db, guia)
    if problemas:
        raise HTTPException(400, "Não deu para fechar a guia: " + " ".join(problemas))

    saiu = saidas_por_posicao(db, guia.empresa_id, ignorar_transferencia_id=guia.id)
    grupos: dict[int, list[GuiaTransferenciaItem]] = defaultdict(list)
    for item in guia.itens:
        _peso_do_item(item, saiu)
        grupos[item.lote_id].append(item)

    usados: set[str] = set()
    for itens in grupos.values():
        origem = itens[0].lote
        codigo = codigo_livre(db, guia.empresa_id, origem.codigo, usados)
        usados.add(codigo)
        sacas = round(sum(float(i.sacas) for i in itens), 2)
        peso = round(sum(float(i.peso or 0) for i in itens), 2)
        novo = LoteArmazem(
            empresa_id=guia.empresa_id, guia_id=origem.guia_id, codigo=codigo,
            data_entrada=guia.data, armazem_id=guia.armazem_id,
            depositante_id=guia.cliente_novo_id, produto_id=origem.produto_id,
            peneira=origem.peneira, padrao=origem.padrao, sacas=sacas, peso=peso,
            unidade_id=origem.unidade_id, valor_unitario=origem.valor_unitario,
            valor_total=round(sacas * float(origem.valor_unitario or 0), 2),
            lote_origem_id=origem.id, guia_transferencia_id=guia.id,
        )
        for i in itens:
            novo.posicoes.append(LotePosicao(quadra_id=i.posicao.quadra_id, pilha=i.posicao.pilha,
                                             sacas=i.sacas, peso=i.peso))
        db.add(novo)
        db.flush()
        religar_amostra(db, novo)
        for i in itens:
            i.lote_novo_id = novo.id
        ultimo = db.query(func.max(MovimentoArmazem.numero)).filter(
            MovimentoArmazem.empresa_id == guia.empresa_id,
            MovimentoArmazem.tipo == "TRANSFERENCIA").scalar()
        db.add(MovimentoArmazem(
            empresa_id=guia.empresa_id, tipo="TRANSFERENCIA", numero=int(ultimo or 0) + 1,
            data=guia.data, armazem_id=guia.armazem_id, depositante_id=guia.cliente_id,
            depositante_destino_id=guia.cliente_novo_id, produto_id=origem.produto_id,
            lote=origem.codigo, lote_destino=codigo, sacas=sacas, peso_kg=peso,
            documento=guia.documento or f"Guia de transferência {guia.numero}",
            guia_transferencia_id=guia.id, usuario_id=usuario.id,
            observacao=f"lote {origem.codigo} -> {codigo}"))
        db.flush()
    guia.status = "FECHADA"
    guia.fechada_em = datetime.utcnow()
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.post("/guias-transferencia/{guia_id}/reabrir")
def reabrir(guia_id: int, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status != "FECHADA":
        raise HTTPException(400, "Só guia fechada pode ser reaberta.")
    novos = db.query(LoteArmazem).filter(LoteArmazem.guia_transferencia_id == guia.id).all()
    ids = [l.id for l in novos] or [0]
    em_saida = (db.query(GuiaSaida.numero)
                .join(GuiaSaidaItem, GuiaSaidaItem.guia_id == GuiaSaida.id)
                .filter(GuiaSaidaItem.lote_id.in_(ids), GuiaSaida.status != "CANCELADA")
                .distinct().all())
    em_transf = (db.query(GuiaTransferencia.numero)
                 .join(GuiaTransferenciaItem, GuiaTransferenciaItem.guia_id == GuiaTransferencia.id)
                 .filter(GuiaTransferenciaItem.lote_id.in_(ids),
                         GuiaTransferencia.status != "CANCELADA")
                 .distinct().all())
    from ..models import GuiaRemocao

    removidos = db.query(GuiaRemocao.numero).filter(
        GuiaRemocao.lote_id.in_(ids), GuiaRemocao.status == "ATIVA").all()
    if removidos:
        raise HTTPException(
            400, f"Não dá para reabrir a guia {guia.numero}: os lotes novos dela mudaram de local "
                 f"(remoção {', '.join(str(n[0]) for n in removidos)}). Estorne a remoção primeiro.")
    from ..models import GuiaServico, GuiaServicoDespejo

    em_servico = (db.query(GuiaServico.numero)
                  .join(GuiaServicoDespejo, GuiaServicoDespejo.guia_id == GuiaServico.id)
                  .filter(GuiaServicoDespejo.lote_id.in_(ids), GuiaServico.status != "CANCELADA")
                  .distinct().all())
    if em_servico:
        raise HTTPException(
            400, f"Não dá para reabrir a guia {guia.numero}: os lotes novos dela estão na(s) guia(s) "
                 f"de serviço {', '.join(str(n[0]) for n in em_servico)}.")
    if em_saida or em_transf:
        onde = [f"guia de saída {n[0]}" for n in em_saida] + \
               [f"guia de transferência {n[0]}" for n in em_transf]
        raise HTTPException(
            400, f"Não dá para reabrir a guia {guia.numero}: os lotes novos dela já estão na "
                 f"{', '.join(onde)}. Reabra e tire os itens (ou cancele) essas guias primeiro.")
    movimentos = db.query(MovimentoArmazem).filter(
        MovimentoArmazem.guia_transferencia_id == guia.id).all()
    saldos = _somar_saldos(db, guia.empresa_id)
    for m in movimentos:      # sem a transferência, o lote novo ficaria negativo?
        chave = (m.armazem_id, m.depositante_destino_id, m.produto_id, (m.lote_destino or "").upper())
        if chave in saldos:
            saldos[chave]["sacas"] -= float(m.sacas or 0)
    if _negativos(saldos):
        raise HTTPException(400, f"Não dá para reabrir a guia {guia.numero}: parte dos lotes "
                                 "novos já foi removida para outro armazém.")
    for m in movimentos:
        db.delete(m)
    for item in guia.itens:
        item.lote_novo_id = None
    db.flush()
    desligar_amostras(db, [l.id for l in novos])
    for lote in novos:
        db.delete(lote)
    guia.status = "ABERTA"
    guia.fechada_em = None
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.post("/guias-transferencia/{guia_id}/cancelar")
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
