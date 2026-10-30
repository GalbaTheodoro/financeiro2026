"""WMS — Remoção: mudar o lote de lugar, com histórico.

Escolhe-se o lote; aparecem todos os locais dele (quadra + pilha) com o que
resta em cada um. Em cada local se diz quantas sacas vão e para onde (quadra
e pilha de destino) — pode ser só uma parte. Confirmar grava a remoção na
hora (não tem rascunho) e ela fica no **histórico** do lote.

* Destino no **mesmo armazém**: pode mover só uma parte de uma pilha.
* Destino em **outro armazém**: tem de ir o lote inteiro (todas as posições,
  tudo o que resta nelas) — o lote passa a ser daquele armazém e o saldo vai
  junto (``MovimentoArmazem`` REMOCAO com ``guia_remocao_id``).
* Peso vazio = peso médio da saca daquela posição (tudo = o peso que resta).
* **Estornar** desfaz a última remoção ativa do lote, se o café ainda estiver
  no destino. A remoção estornada continua no histórico, marcada.

Rotas
-----
GET  /api/wms/remocoes                     histórico das remoções (filtros)
POST /api/wms/remocoes                     faz a mudança de local
POST /api/wms/remocoes/{id}/estornar       desfaz a última do lote
GET  /api/wms/lotes/{id}/locais            o lote, os locais e o disponível
GET  /api/wms/lotes/{id}/historico         tudo o que aconteceu com o lote
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
    GuiaEntrada,
    GuiaEntradaLote,
    GuiaRemocao,
    GuiaRemocaoItem,
    GuiaSaida,
    GuiaSaidaItem,
    GuiaTransferencia,
    GuiaTransferenciaItem,
    LoteArmazem,
    LotePosicao,
    MovimentoArmazem,
    QuadraArmazem,
    Usuario,
)
from ..utils import parse_data, serializar
from .wms import TOLERANCIA, _n, _somar_saldos
from .wms_entrada import saidas_por_posicao

router = APIRouter(prefix="/api/wms", tags=["wms"],
                   dependencies=[Depends(exigir_modulo("WMS"))])


def _num(valor) -> float:
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _pilha(texto) -> str | None:
    return (str(texto or "")).strip().upper()[:20] or None


def _lugar(quadra, pilha) -> str:
    nome = quadra.nome if quadra else "?"
    return f"{nome}/{pilha}" if pilha else nome


def _lote(db: Session, lote_id: int, usuario: Usuario) -> LoteArmazem:
    lote = db.get(LoteArmazem, lote_id)
    if not lote:
        raise HTTPException(404, "Lote não encontrado.")
    validar_empresa(db, lote.empresa_id, usuario)
    return lote


def _disponivel(pos: LotePosicao, saiu: dict) -> tuple[float, float]:
    ja = saiu.get(pos.id, {"sacas": 0.0, "peso": 0.0})
    return (round(float(pos.sacas or 0) - ja["sacas"], 2),
            round(float(pos.peso or 0) - ja["peso"], 2))


# --------------------------------------------------------------------------- #
# O lote e os locais
# --------------------------------------------------------------------------- #
@router.get("/lotes/{lote_id}/locais")
def locais_do_lote(lote_id: int, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(acesso_liberado)):
    lote = _lote(db, lote_id, usuario)
    saiu = saidas_por_posicao(db, lote.empresa_id)
    posicoes = []
    for p in lote.posicoes:
        sc, kg = _disponivel(p, saiu)
        if sc <= TOLERANCIA:
            continue
        posicoes.append({"posicao_id": p.id, "quadra_id": p.quadra_id,
                         "quadra_nome": p.quadra.nome if p.quadra else "-", "pilha": p.pilha,
                         "sacas_disponiveis": sc, "peso_disponivel": kg})
    return {
        "lote": serializar(lote, extras={
            "armazem_nome": lote.armazem.nome if lote.armazem else "-",
            "depositante_nome": lote.depositante.nome if lote.depositante else "-",
        }),
        "posicoes": posicoes,
        "total_sacas": round(sum(p["sacas_disponiveis"] for p in posicoes), 2),
    }


# --------------------------------------------------------------------------- #
# Fazer a remoção
# --------------------------------------------------------------------------- #
class ItemIn(BaseModel):
    posicao_id: int | None = None
    sacas: float = 0
    peso: float = 0
    quadra_destino_id: int | None = None
    pilha_destino: str | None = None


class RemocaoIn(BaseModel):
    empresa_id: int
    lote_id: int
    data: str | None = None
    armazem_destino_id: int | None = None      # vazio = o mesmo armazém
    observacao: str | None = None
    itens: list[ItemIn] = []


def _ficha(g: GuiaRemocao) -> dict:
    return serializar(g, extras={
        "lote_codigo": g.lote.codigo if g.lote else "-",
        "depositante_nome": g.lote.depositante.nome if g.lote and g.lote.depositante else "-",
        "armazem_origem_nome": g.armazem_origem.nome if g.armazem_origem else "-",
        "armazem_destino_nome": g.armazem_destino.nome if g.armazem_destino else "-",
        "usuario_nome": g.usuario.nome if g.usuario else None,
        "sacas": round(sum(float(i.sacas or 0) for i in g.itens), 2),
        "peso": round(sum(float(i.peso or 0) for i in g.itens), 2),
        "itens": [{
            "de": _lugar(i.quadra_origem, i.pilha_origem),
            "para": _lugar(i.quadra_destino, i.pilha_destino),
            "sacas": float(i.sacas or 0), "peso": float(i.peso or 0),
        } for i in g.itens],
    })


@router.get("/remocoes")
def listar(empresa_id: int, lote_id: int | None = None, de: str | None = None,
           ate: str | None = None, armazem_id: int | None = None, busca: str | None = None,
           db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(GuiaRemocao).filter(GuiaRemocao.empresa_id == empresa_id)
    if lote_id:
        consulta = consulta.filter(GuiaRemocao.lote_id == lote_id)
    inicio, fim = parse_data(de), parse_data(ate)
    if inicio:
        consulta = consulta.filter(GuiaRemocao.data >= inicio)
    if fim:
        consulta = consulta.filter(GuiaRemocao.data <= fim)
    if armazem_id:
        consulta = consulta.filter(or_(GuiaRemocao.armazem_origem_id == armazem_id,
                                       GuiaRemocao.armazem_destino_id == armazem_id))
    texto = (busca or "").strip()
    if texto:
        consulta = consulta.join(LoteArmazem, LoteArmazem.id == GuiaRemocao.lote_id).filter(
            LoteArmazem.codigo.ilike(f"%{texto}%"))
    guias = consulta.order_by(GuiaRemocao.data.desc(), GuiaRemocao.id.desc()).limit(500).all()
    fichas = [_ficha(g) for g in guias]
    ativas = [f for f in fichas if f["status"] == "ATIVA"]
    # só a última remoção ativa de cada lote pode ser estornada
    ultimas = dict(db.query(GuiaRemocao.lote_id, func.max(GuiaRemocao.id))
                   .filter(GuiaRemocao.empresa_id == empresa_id, GuiaRemocao.status == "ATIVA")
                   .group_by(GuiaRemocao.lote_id).all())
    for f in fichas:
        f["pode_estornar"] = f["status"] == "ATIVA" and ultimas.get(f["lote_id"]) == f["id"]
    return {
        "remocoes": fichas,
        "resumo": {"remocoes": len(ativas),
                   "sacas": round(sum(f["sacas"] for f in ativas), 2),
                   "lotes": len({f["lote_id"] for f in ativas})},
    }


def _posicao_destino(db: Session, lote: LoteArmazem, quadra_id: int, pilha: str | None) -> LotePosicao:
    for p in lote.posicoes:
        if p.quadra_id == quadra_id and (p.pilha or "").upper() == (pilha or ""):
            return p
    nova = LotePosicao(quadra_id=quadra_id, pilha=pilha, sacas=0, peso=0)
    lote.posicoes.append(nova)
    db.flush()
    return nova


@router.post("/remocoes")
def remover(dados: RemocaoIn, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    lote = _lote(db, dados.lote_id, usuario)
    if lote.empresa_id != dados.empresa_id:
        raise HTTPException(400, "O lote é de outra empresa.")
    origem_armazem = lote.armazem
    destino_armazem = origem_armazem
    if dados.armazem_destino_id and dados.armazem_destino_id != lote.armazem_id:
        destino_armazem = db.get(Armazem, dados.armazem_destino_id)
        if not destino_armazem or destino_armazem.empresa_id != lote.empresa_id:
            raise HTTPException(400, "Armazém de destino não encontrado nesta empresa.")
    if not destino_armazem.ativo:
        raise HTTPException(400, f"O armazém {destino_armazem.nome} está inativo.")
    muda_armazem = destino_armazem.id != lote.armazem_id

    saiu = saidas_por_posicao(db, lote.empresa_id)
    posicoes = {p.id: p for p in lote.posicoes}
    linhas = [i for i in dados.itens if i.posicao_id and _num(i.sacas) > 0]
    if not linhas:
        raise HTTPException(400, "Diga quantas sacas mudam de local e para onde.")

    pedido_por_posicao: dict[int, float] = {}
    problemas: list[str] = []
    for i in linhas:
        pos = posicoes.get(i.posicao_id)
        if not pos:
            raise HTTPException(400, "Local não pertence a este lote.")
        pedido_por_posicao[pos.id] = pedido_por_posicao.get(pos.id, 0.0) + _num(i.sacas)
        quadra = db.get(QuadraArmazem, i.quadra_destino_id) if i.quadra_destino_id else None
        if not quadra or quadra.empresa_id != lote.empresa_id:
            problemas.append(f"Escolha a quadra de destino de {_lugar(pos.quadra, pos.pilha)}.")
            continue
        if quadra.armazem_id != destino_armazem.id:
            problemas.append(f"A quadra {quadra.nome} não é do armazém {destino_armazem.nome}.")
        if not quadra.ativo:
            problemas.append(f"A quadra {quadra.nome} está inativa.")
        if quadra.id == pos.quadra_id and _pilha(i.pilha_destino) == _pilha(pos.pilha):
            problemas.append(f"{_lugar(pos.quadra, pos.pilha)}: o destino é o mesmo local.")
    for pid, pedido in pedido_por_posicao.items():
        pos = posicoes[pid]
        resta, _ = _disponivel(pos, saiu)
        if pedido > resta + TOLERANCIA:
            problemas.append(f"Em {_lugar(pos.quadra, pos.pilha)} restam {_n(resta)} sacas — "
                             f"a remoção leva {_n(pedido)}.")
    if muda_armazem:
        faltou = []
        for pos in lote.posicoes:
            resta, _ = _disponivel(pos, saiu)
            if resta > TOLERANCIA and abs(pedido_por_posicao.get(pos.id, 0.0) - resta) > TOLERANCIA:
                faltou.append(_lugar(pos.quadra, pos.pilha))
        if faltou:
            problemas.append(
                f"Para levar o lote para outro armazém ({destino_armazem.nome}) tem de ir o lote "
                f"inteiro — falta levar tudo de: {', '.join(faltou)}.")
    if problemas:
        raise HTTPException(400, "Não deu para fazer a remoção: " + " ".join(problemas))

    ultimo = db.query(func.max(GuiaRemocao.numero)).filter(
        GuiaRemocao.empresa_id == lote.empresa_id).scalar()
    guia = GuiaRemocao(
        empresa_id=lote.empresa_id, numero=int(ultimo or 0) + 1,
        data=parse_data(dados.data) or date.today(), lote_id=lote.id,
        armazem_origem_id=lote.armazem_id, armazem_destino_id=destino_armazem.id,
        observacao=(dados.observacao or "").strip()[:300] or None, usuario_id=usuario.id)
    db.add(guia)
    restante = {pid: _disponivel(posicoes[pid], saiu) for pid in pedido_por_posicao}
    for i in linhas:
        pos = posicoes[i.posicao_id]
        sacas = _num(i.sacas)
        peso = _num(i.peso)
        resta_sc, resta_kg = restante[pos.id]
        if not peso and resta_sc > TOLERANCIA and resta_kg > 0:
            peso = round(resta_kg, 2) if abs(sacas - resta_sc) <= TOLERANCIA \
                else round(resta_kg / resta_sc * sacas, 2)
        restante[pos.id] = (round(resta_sc - sacas, 2), round(resta_kg - peso, 2))
        destino = _posicao_destino(db, lote, i.quadra_destino_id, _pilha(i.pilha_destino))
        pos.sacas = round(float(pos.sacas or 0) - sacas, 2)
        pos.peso = round(max(0.0, float(pos.peso or 0) - peso), 2)
        destino.sacas = round(float(destino.sacas or 0) + sacas, 2)
        destino.peso = round(float(destino.peso or 0) + peso, 2)
        guia.itens.append(GuiaRemocaoItem(
            posicao_origem_id=pos.id, posicao_destino_id=destino.id,
            quadra_origem_id=pos.quadra_id, pilha_origem=pos.pilha,
            quadra_destino_id=i.quadra_destino_id, pilha_destino=_pilha(i.pilha_destino),
            sacas=sacas, peso=peso))
    db.flush()

    if muda_armazem:
        chave = (lote.armazem_id, lote.depositante_id, lote.produto_id, lote.codigo.upper())
        saldo = _somar_saldos(db, lote.empresa_id).get(chave, {"sacas": 0.0, "peso_kg": 0.0})
        ultimo_mov = db.query(func.max(MovimentoArmazem.numero)).filter(
            MovimentoArmazem.empresa_id == lote.empresa_id,
            MovimentoArmazem.tipo == "REMOCAO").scalar()
        if saldo["sacas"] > TOLERANCIA:
            db.add(MovimentoArmazem(
                empresa_id=lote.empresa_id, tipo="REMOCAO", numero=int(ultimo_mov or 0) + 1,
                data=guia.data, armazem_id=lote.armazem_id, armazem_destino_id=destino_armazem.id,
                depositante_id=lote.depositante_id, produto_id=lote.produto_id, lote=lote.codigo,
                sacas=round(saldo["sacas"], 2), peso_kg=round(max(0.0, saldo["peso_kg"]), 2),
                documento=f"Remoção {guia.numero}", guia_remocao_id=guia.id,
                usuario_id=usuario.id))
        lote.armazem_id = destino_armazem.id
    db.commit()
    db.refresh(guia)
    return _ficha(guia)


@router.post("/remocoes/{guia_id}/estornar")
def estornar(guia_id: int, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    guia = db.get(GuiaRemocao, guia_id)
    if not guia:
        raise HTTPException(404, "Remoção não encontrada.")
    validar_empresa(db, guia.empresa_id, usuario)
    if guia.status != "ATIVA":
        raise HTTPException(400, "Esta remoção já foi estornada.")
    ultima = db.query(func.max(GuiaRemocao.id)).filter(
        GuiaRemocao.lote_id == guia.lote_id, GuiaRemocao.status == "ATIVA").scalar()
    if ultima != guia.id:
        raise HTTPException(400, "Só dá para estornar a última remoção do lote — estorne as "
                                 "mais novas primeiro.")
    saiu = saidas_por_posicao(db, guia.empresa_id)
    volta: dict[int, float] = {}
    for i in guia.itens:
        volta[i.posicao_destino_id] = volta.get(i.posicao_destino_id, 0.0) + float(i.sacas)
    for pid, sacas in volta.items():
        pos = db.get(LotePosicao, pid)
        resta, _ = _disponivel(pos, saiu)
        if sacas > resta + TOLERANCIA:
            raise HTTPException(400, f"Não dá para estornar: em {_lugar(pos.quadra, pos.pilha)} "
                                     f"restam {_n(resta)} sacas e a remoção levou {_n(sacas)} "
                                     "para lá (parte já saiu ou foi transferida).")
    for i in guia.itens:
        origem = db.get(LotePosicao, i.posicao_origem_id)
        destino = db.get(LotePosicao, i.posicao_destino_id)
        destino.sacas = round(float(destino.sacas or 0) - float(i.sacas), 2)
        destino.peso = round(max(0.0, float(destino.peso or 0) - float(i.peso or 0)), 2)
        origem.sacas = round(float(origem.sacas or 0) + float(i.sacas), 2)
        origem.peso = round(float(origem.peso or 0) + float(i.peso or 0), 2)
    if guia.armazem_destino_id != guia.armazem_origem_id:
        for m in db.query(MovimentoArmazem).filter(MovimentoArmazem.guia_remocao_id == guia.id):
            db.delete(m)
        guia.lote.armazem_id = guia.armazem_origem_id
    guia.status = "ESTORNADA"
    guia.estornada_em = datetime.utcnow()
    db.commit()
    db.refresh(guia)
    return _ficha(guia)


# --------------------------------------------------------------------------- #
# Histórico do lote
# --------------------------------------------------------------------------- #
def _lista_lugares(pares) -> str:
    return ", ".join(f"{lugar} {_n(sc).rstrip('0').rstrip(',')} sc" for lugar, sc in pares)


@router.get("/lotes/{lote_id}/historico")
def historico(lote_id: int, db: Session = Depends(get_db),
              usuario: Usuario = Depends(acesso_liberado)):
    """Tudo o que aconteceu com o lote, do mais antigo ao mais novo."""
    lote = _lote(db, lote_id, usuario)
    eventos: list[dict] = []

    def evento(data_ev, quando, tipo, titulo, detalhe, sacas, sinal, situacao="ATIVO"):
        eventos.append({"data": data_ev.isoformat() if data_ev else None,
                        "quando": quando.isoformat() if quando else "",
                        "tipo": tipo, "titulo": titulo, "detalhe": detalhe,
                        "sacas": round(float(sacas or 0), 2), "sinal": sinal,
                        "situacao": situacao})

    from ..models import GuiaServico, GuiaServicoDespejo

    if lote.guia_servico_id:
        gs = db.get(GuiaServico, lote.guia_servico_id)
        resultado = next((r for r in (gs.resultados if gs else []) if r.lote_gerado_id == lote.id), None)
        origens = sorted({d.lote.codigo for d in (gs.despejos if gs else []) if d.lote})
        evento(lote.data_entrada, lote.criado_em, "RESULTADO",
               f"Resultado do serviço nº {gs.numero if gs else '?'}"
               + (f" — {gs.servico}" if gs and gs.servico else ""),
               (f"dos lotes {', '.join(origens)} · " if origens else "")
               + _lista_lugares((_lugar(x.quadra, x.pilha), float(x.sacas))
                                for x in (resultado.locais if resultado else [])),
               lote.sacas, "+")
    elif lote.lote_origem_id:
        origem = db.get(LoteArmazem, lote.lote_origem_id)
        guia_t = db.get(GuiaTransferencia, lote.guia_transferencia_id) if lote.guia_transferencia_id else None
        itens = [i for i in (guia_t.itens if guia_t else []) if i.lote_novo_id == lote.id]
        evento(lote.data_entrada, lote.criado_em, "TRANSFERENCIA_RECEBIDA",
               f"Recebido por transferência do lote {origem.codigo if origem else '?'}"
               + (f" (guia de transferência nº {guia_t.numero})" if guia_t else ""),
               (f"de {guia_t.cliente.nome} · " if guia_t and guia_t.cliente else "")
               + _lista_lugares((_lugar(i.posicao.quadra, i.posicao.pilha), float(i.sacas)) for i in itens),
               lote.sacas, "+")
    else:
        guia_e = db.get(GuiaEntrada, lote.guia_id) if lote.guia_id else None
        guia_lote = db.get(GuiaEntradaLote, lote.guia_lote_id) if lote.guia_lote_id else None
        evento(lote.data_entrada, lote.criado_em, "ENTRADA",
               f"Entrada pela guia nº {guia_e.numero}" if guia_e else "Entrada",
               _lista_lugares((_lugar(x.quadra, x.pilha), float(x.sacas))
                              for x in (guia_lote.locais if guia_lote else [])),
               lote.sacas, "+")

    for guia in (db.query(GuiaRemocao).filter(GuiaRemocao.lote_id == lote.id)
                 .order_by(GuiaRemocao.id).all()):
        muda = guia.armazem_destino_id != guia.armazem_origem_id
        evento(guia.data, guia.criado_em, "REMOCAO",
               f"Remoção nº {guia.numero}" + (f" — {guia.armazem_origem.nome} → "
                                               f"{guia.armazem_destino.nome}" if muda else ""),
               "; ".join(f"{_lugar(i.quadra_origem, i.pilha_origem)} → "
                         f"{_lugar(i.quadra_destino, i.pilha_destino)}: {_n(float(i.sacas))} sc"
                         for i in guia.itens)
               + (f" · {guia.observacao}" if guia.observacao else "")
               + (f" · por {guia.usuario.nome}" if guia.usuario else ""),
               sum(float(i.sacas) for i in guia.itens), "=",
               "ESTORNADA" if guia.status == "ESTORNADA" else "ATIVO")

    saidas = (db.query(GuiaSaida).join(GuiaSaidaItem, GuiaSaidaItem.guia_id == GuiaSaida.id)
              .filter(GuiaSaidaItem.lote_id == lote.id, GuiaSaida.status == "FECHADA")
              .distinct().all())
    for guia in saidas:
        itens = [i for i in guia.itens if i.lote_id == lote.id]
        evento(guia.data, guia.fechada_em, "SAIDA",
               f"Saída pela guia nº {guia.numero}"
               + (f" — {guia.destinatario.nome}" if guia.destinatario else "")
               + (f" ({guia.destino})" if guia.destino else ""),
               _lista_lugares((_lugar(i.posicao.quadra, i.posicao.pilha), float(i.sacas)) for i in itens),
               sum(float(i.sacas) for i in itens), "-")

    transfs = (db.query(GuiaTransferencia)
               .join(GuiaTransferenciaItem, GuiaTransferenciaItem.guia_id == GuiaTransferencia.id)
               .filter(GuiaTransferenciaItem.lote_id == lote.id, GuiaTransferencia.status == "FECHADA")
               .distinct().all())
    for guia in transfs:
        itens = [i for i in guia.itens if i.lote_id == lote.id]
        novos = sorted({i.lote_novo.codigo for i in itens if i.lote_novo})
        evento(guia.data, guia.fechada_em, "TRANSFERENCIA_ENVIADA",
               f"Transferido para {guia.cliente_novo.nome if guia.cliente_novo else '?'} "
               f"(lote {', '.join(novos)}) — guia de transferência nº {guia.numero}",
               _lista_lugares((_lugar(i.posicao.quadra, i.posicao.pilha), float(i.sacas)) for i in itens),
               sum(float(i.sacas) for i in itens), "-")

    servicos = (db.query(GuiaServico)
                .join(GuiaServicoDespejo, GuiaServicoDespejo.guia_id == GuiaServico.id)
                .filter(GuiaServicoDespejo.lote_id == lote.id, GuiaServico.status == "FECHADA")
                .distinct().all())
    for guia in servicos:
        itens = [d for d in guia.despejos if d.lote_id == lote.id]
        gerados = [r.lote_gerado.codigo for r in guia.resultados if r.lote_gerado]
        evento(guia.data_fim or guia.data, guia.fechada_em, "DESPEJO",
               f"Despejado no serviço nº {guia.numero}" + (f" — {guia.servico}" if guia.servico else "")
               + (f" (gerou {', '.join(gerados)})" if gerados else ""),
               _lista_lugares((_lugar(d.posicao.quadra, d.posicao.pilha), float(d.sacas)) for d in itens),
               sum(float(d.sacas) for d in itens), "-")

    eventos.sort(key=lambda e: (e["data"] or "", e["quando"]))
    saiu = saidas_por_posicao(db, lote.empresa_id)
    return {
        "lote": {"id": lote.id, "codigo": lote.codigo,
                 "depositante_nome": lote.depositante.nome if lote.depositante else "-",
                 "armazem_nome": lote.armazem.nome if lote.armazem else "-",
                 "peneira": lote.peneira, "padrao": lote.padrao, "sacas": float(lote.sacas or 0)},
        "eventos": eventos,
        "locais_hoje": [{"lugar": _lugar(p.quadra, p.pilha), "sacas": _disponivel(p, saiu)[0]}
                        for p in lote.posicoes if _disponivel(p, saiu)[0] > TOLERANCIA],
    }
