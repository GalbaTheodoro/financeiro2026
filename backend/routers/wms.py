"""WMS / Armazém: o café que a empresa guarda para os depositantes.

O menu tem cinco telas, e todas gravam na mesma tabela (``MovimentoArmazem``),
cada uma com o seu ``tipo``:

=================  ========================================================
Tela               O que faz no saldo
=================  ========================================================
Entrada            + no armazém / depositante / produto / lote
Saídas             - no armazém / depositante / produto / lote
Serviços           nada: registra o serviço feito no lote e o valor cobrado
Transferências     - no depositante de origem, + no de destino (mesmo armazém)
Remoção            - no armazém de origem, + no de destino (mesmo depositante)
=================  ========================================================

O saldo nunca é digitado: é a soma dos lançamentos ativos. Saída,
transferência e remoção são recusadas quando passam do que o depositante tem
naquele armazém e lote — e o cancelamento também, se desfazer uma entrada
deixaria o saldo negativo.

Rotas
-----
GET  /api/wms/armazens                  lista dos armazéns
POST /api/wms/armazens                  novo armazém
PUT  /api/wms/armazens/{id}             alterar armazém
GET  /api/wms/movimentos?tipo=ENTRADA   lançamentos de uma tela
POST /api/wms/movimentos                novo lançamento (entrada, saída e transferência
                                        são pelas guias — wms_entrada/saida/transferencia.py)
POST /api/wms/movimentos/{id}/cancelar  cancela (com motivo)
GET  /api/wms/saldos                    saldo por armazém, depositante, produto e lote

Só o Plano 4 tem este módulo (``WMS`` em planos.py) — a porta é fechada aqui
pelo ``exigir_modulo``, não só pelo menu.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import Armazem, MovimentoArmazem, Parceiro, Produto, Usuario
from ..utils import parse_data, serializar

router = APIRouter(prefix="/api/wms", tags=["wms"],
                   dependencies=[Depends(exigir_modulo("WMS"))])

TIPOS = {
    "ENTRADA": "Entrada",
    "SAIDA": "Saída",
    "SERVICO": "Serviço",
    "TRANSFERENCIA": "Transferência",
    "REMOCAO": "Remoção",
}

# serviços mais comuns num armazém de café — a tela sugere, mas aceita outro
SERVICOS = ("Armazenagem", "Recepção / descarga", "Pesagem", "Rebenefício",
            "Padronização / liga", "Catação", "Ensaque", "Sacaria", "Expedição / carga",
            "Amostragem", "Classificação")

TOLERANCIA = 0.005


# --------------------------------------------------------------------------- #
# Armazéns
# --------------------------------------------------------------------------- #
class ArmazemIn(BaseModel):
    empresa_id: int
    nome: str
    cidade: str | None = None
    uf: str | None = None
    capacidade_sacas: float = 0
    observacao: str | None = None
    ativo: bool = True


def _armazem(db: Session, armazem_id: int | None, empresa_id: int,
             rotulo: str = "o armazém") -> Armazem:
    armazem = db.get(Armazem, armazem_id) if armazem_id else None
    if not armazem or armazem.empresa_id != empresa_id:
        raise HTTPException(400, f"Escolha {rotulo}.")
    return armazem


@router.get("/armazens")
def listar_armazens(empresa_id: int, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    armazens = (db.query(Armazem).filter(Armazem.empresa_id == empresa_id)
                .order_by(Armazem.nome).all())
    saldos = _somar_saldos(db, empresa_id)
    ocupado: dict[int, float] = defaultdict(float)
    for (armazem_id, _dep, _prod, _lote), valores in saldos.items():
        ocupado[armazem_id] += valores["sacas"]
    saida = []
    for a in armazens:
        sacas = round(ocupado.get(a.id, 0.0), 2)
        cap = float(a.capacidade_sacas or 0)
        saida.append(serializar(a, extras={
            "sacas_guardadas": sacas,
            "ocupacao": round(sacas / cap * 100, 1) if cap else None,
        }))
    return saida


@router.post("/armazens")
def criar_armazem(dados: ArmazemIn, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    nome = (dados.nome or "").strip()
    if not nome:
        raise HTTPException(400, "Dê um nome ao armazém.")
    armazem = Armazem(empresa_id=dados.empresa_id, nome=nome[:120],
                      cidade=(dados.cidade or "").strip()[:80] or None,
                      uf=(dados.uf or "").strip().upper()[:2] or None,
                      capacidade_sacas=max(0.0, float(dados.capacidade_sacas or 0)),
                      observacao=(dados.observacao or "").strip()[:300] or None,
                      ativo=dados.ativo)
    db.add(armazem)
    db.commit()
    db.refresh(armazem)
    return serializar(armazem)


@router.put("/armazens/{armazem_id}")
def alterar_armazem(armazem_id: int, dados: ArmazemIn, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    armazem = db.get(Armazem, armazem_id)
    if not armazem or armazem.empresa_id != dados.empresa_id:
        raise HTTPException(404, "Armazém não encontrado nesta empresa.")
    nome = (dados.nome or "").strip()
    if not nome:
        raise HTTPException(400, "Dê um nome ao armazém.")
    armazem.nome = nome[:120]
    armazem.cidade = (dados.cidade or "").strip()[:80] or None
    armazem.uf = (dados.uf or "").strip().upper()[:2] or None
    armazem.capacidade_sacas = max(0.0, float(dados.capacidade_sacas or 0))
    armazem.observacao = (dados.observacao or "").strip()[:300] or None
    armazem.ativo = dados.ativo
    db.commit()
    db.refresh(armazem)
    return serializar(armazem)


# --------------------------------------------------------------------------- #
# Saldo: a soma dos lançamentos ativos
# --------------------------------------------------------------------------- #
Chave = tuple  # (armazem_id, depositante_id, produto_id, lote)


def _lote(texto: str | None) -> str:
    return (texto or "").strip().upper()[:40]


def _somar_saldos(db: Session, empresa_id: int,
                  ignorar_id: int | None = None) -> dict[Chave, dict]:
    """Saldo por (armazém, depositante, produto, lote).

    ``ignorar_id`` tira um lançamento da conta — é assim que o cancelamento
    confere se o saldo aguenta ficar sem ele.
    """
    consulta = db.query(MovimentoArmazem).filter(
        MovimentoArmazem.empresa_id == empresa_id,
        MovimentoArmazem.status == "ATIVO",
        MovimentoArmazem.tipo != "SERVICO",
    )
    if ignorar_id:
        consulta = consulta.filter(MovimentoArmazem.id != ignorar_id)
    saldos: dict[Chave, dict] = defaultdict(lambda: {"sacas": 0.0, "peso_kg": 0.0})

    def somar(chave, sinal, m):
        saldos[chave]["sacas"] += sinal * float(m.sacas or 0)
        saldos[chave]["peso_kg"] += sinal * float(m.peso_kg or 0)

    for m in consulta.all():
        lote = _lote(m.lote)
        origem = (m.armazem_id, m.depositante_id, m.produto_id, lote)
        if m.tipo == "ENTRADA":
            somar(origem, +1, m)
        elif m.tipo == "SAIDA":
            somar(origem, -1, m)
        elif m.tipo == "TRANSFERENCIA":
            somar(origem, -1, m)
            # pela guia de transferência o lote ganha código novo no novo dono ("1/1T")
            destino = _lote(m.lote_destino) or lote
            somar((m.armazem_id, m.depositante_destino_id, m.produto_id, destino), +1, m)
        elif m.tipo == "REMOCAO":
            somar(origem, -1, m)
            somar((m.armazem_destino_id, m.depositante_id, m.produto_id, lote), +1, m)
    return saldos


def _negativos(saldos: dict[Chave, dict]) -> list[Chave]:
    return [c for c, v in saldos.items() if v["sacas"] < -TOLERANCIA]


@router.get("/saldos")
def saldos(empresa_id: int, armazem_id: int | None = None,
           depositante_id: int | None = None, produto_id: int | None = None,
           db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    somados = _somar_saldos(db, empresa_id)
    armazens = {a.id: a.nome for a in db.query(Armazem).filter(Armazem.empresa_id == empresa_id)}
    ids_dep = {c[1] for c in somados}
    ids_prod = {c[2] for c in somados if c[2]}
    depositantes = {p.id: p.nome for p in db.query(Parceiro).filter(Parceiro.id.in_(ids_dep or [0]))}
    produtos = {p.id: p.nome for p in db.query(Produto).filter(Produto.id.in_(ids_prod or [0]))}

    linhas = []
    for (a_id, d_id, p_id, lote), v in somados.items():
        if abs(v["sacas"]) < TOLERANCIA and abs(v["peso_kg"]) < TOLERANCIA:
            continue
        if armazem_id and a_id != armazem_id:
            continue
        if depositante_id and d_id != depositante_id:
            continue
        if produto_id and p_id != produto_id:
            continue
        linhas.append({
            "armazem_id": a_id, "armazem_nome": armazens.get(a_id, "-"),
            "depositante_id": d_id, "depositante_nome": depositantes.get(d_id, "-"),
            "produto_id": p_id, "produto_nome": produtos.get(p_id, "") if p_id else "",
            "lote": lote, "sacas": round(v["sacas"], 2), "peso_kg": round(v["peso_kg"], 2),
        })
    linhas.sort(key=lambda l: (l["armazem_nome"], l["depositante_nome"],
                               l["produto_nome"], l["lote"]))
    return {
        "saldos": linhas,
        "total_sacas": round(sum(l["sacas"] for l in linhas), 2),
        "total_peso_kg": round(sum(l["peso_kg"] for l in linhas), 2),
    }


# --------------------------------------------------------------------------- #
# Lançamentos
# --------------------------------------------------------------------------- #
class MovimentoIn(BaseModel):
    empresa_id: int
    tipo: str
    data: str | None = None
    armazem_id: int | None = None
    armazem_destino_id: int | None = None
    depositante_id: int | None = None
    depositante_destino_id: int | None = None
    produto_id: int | None = None
    lote: str | None = None
    sacas: float = 0
    peso_kg: float = 0
    documento: str | None = None
    placa: str | None = None
    motorista: str | None = None
    servico: str | None = None
    valor: float = 0
    observacao: str | None = None


class CancelarIn(BaseModel):
    motivo: str | None = None


def _depositante(db: Session, parceiro_id: int | None, empresa_id: int,
                 rotulo: str = "o depositante") -> Parceiro:
    parceiro = db.get(Parceiro, parceiro_id) if parceiro_id else None
    if not parceiro or parceiro.empresa_id != empresa_id:
        raise HTTPException(400, f"Escolha {rotulo}.")
    return parceiro


def _n(valor: float) -> str:
    """1234.5 -> "1.234,50" (o jeito que a frase de erro mostra as sacas)."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _texto(valor: str | None, limite: int) -> str | None:
    return (valor or "").strip()[:limite] or None


def _ficha(m: MovimentoArmazem) -> dict:
    return serializar(m, extras={
        "tipo_nome": TIPOS.get(m.tipo, m.tipo),
        "armazem_nome": m.armazem.nome if m.armazem else "-",
        "armazem_destino_nome": m.armazem_destino.nome if m.armazem_destino else None,
        "depositante_nome": m.depositante.nome if m.depositante else "-",
        "depositante_destino_nome": m.depositante_destino.nome if m.depositante_destino else None,
        "produto_nome": m.produto.nome if m.produto else None,
    })


@router.get("/movimentos")
def listar(empresa_id: int, tipo: str, de: str | None = None, ate: str | None = None,
           armazem_id: int | None = None, depositante_id: int | None = None,
           busca: str | None = None, mostrar_cancelados: bool = False,
           db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    tipo = (tipo or "").upper()
    if tipo not in TIPOS:
        raise HTTPException(400, "Tipo de lançamento desconhecido.")
    consulta = db.query(MovimentoArmazem).filter(
        MovimentoArmazem.empresa_id == empresa_id, MovimentoArmazem.tipo == tipo)
    inicio, fim = parse_data(de), parse_data(ate)
    if inicio:
        consulta = consulta.filter(MovimentoArmazem.data >= inicio)
    if fim:
        consulta = consulta.filter(MovimentoArmazem.data <= fim)
    if armazem_id:
        consulta = consulta.filter(or_(MovimentoArmazem.armazem_id == armazem_id,
                                       MovimentoArmazem.armazem_destino_id == armazem_id))
    if depositante_id:
        consulta = consulta.filter(or_(MovimentoArmazem.depositante_id == depositante_id,
                                       MovimentoArmazem.depositante_destino_id == depositante_id))
    if not mostrar_cancelados:
        consulta = consulta.filter(MovimentoArmazem.status == "ATIVO")
    texto = (busca or "").strip()
    if texto:
        like = f"%{texto}%"
        consulta = consulta.filter(or_(MovimentoArmazem.lote.ilike(like),
                                       MovimentoArmazem.documento.ilike(like),
                                       MovimentoArmazem.placa.ilike(like),
                                       MovimentoArmazem.servico.ilike(like)))
    linhas = consulta.order_by(MovimentoArmazem.data.desc(),
                               MovimentoArmazem.id.desc()).limit(500).all()
    ativos = [m for m in linhas if m.status == "ATIVO"]
    return {
        "movimentos": [_ficha(m) for m in linhas],
        "resumo": {
            "lancamentos": len(ativos),
            "sacas": round(sum(float(m.sacas or 0) for m in ativos), 2),
            "peso_kg": round(sum(float(m.peso_kg or 0) for m in ativos), 2),
            "valor": round(sum(float(m.valor or 0) for m in ativos), 2),
        },
        "servicos": list(SERVICOS),
    }


@router.post("/movimentos")
def lancar(dados: MovimentoIn, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    eid = dados.empresa_id
    tipo = (dados.tipo or "").upper()
    if tipo not in TIPOS:
        raise HTTPException(400, "Tipo de lançamento desconhecido.")
    if tipo == "ENTRADA":
        raise HTTPException(
            400, "A entrada agora é feita pela guia de entrada (tela Entrada > Nova guia): "
                 "é ela que gera os lotes e as posições no armazém.")
    if tipo == "TRANSFERENCIA":
        raise HTTPException(
            400, "A transferência agora é feita pela guia de transferência (tela "
                 "Transferências > Nova guia): ela gera o lote novo do novo dono.")
    if tipo == "SAIDA":
        raise HTTPException(
            400, "A saída agora é feita pela guia de saída (tela Saídas > Nova guia): "
                 "é nela que se escolhe o lote e a quadra/pilha de onde o café sai.")

    armazem = _armazem(db, dados.armazem_id, eid,
                       "o armazém de origem" if tipo == "REMOCAO" else "o armazém")
    if not armazem.ativo:
        raise HTTPException(400, f"O armazém {armazem.nome} está inativo.")
    depositante = _depositante(
        db, dados.depositante_id, eid,
        "o depositante de origem" if tipo == "TRANSFERENCIA" else "o depositante")
    produto = None
    if dados.produto_id:
        produto = db.get(Produto, dados.produto_id)
        if not produto or produto.empresa_id != eid:
            raise HTTPException(400, "Produto não encontrado nesta empresa.")

    sacas = round(float(dados.sacas or 0), 2)
    peso = round(float(dados.peso_kg or 0), 2)
    if sacas < 0 or peso < 0:
        raise HTTPException(400, "Sacas e peso não podem ser negativos.")
    if tipo != "SERVICO" and sacas <= 0:
        raise HTTPException(400, "Informe a quantidade de sacas.")

    movimento = MovimentoArmazem(
        empresa_id=eid, tipo=tipo, data=parse_data(dados.data) or date.today(),
        armazem_id=armazem.id, depositante_id=depositante.id,
        produto_id=produto.id if produto else None, lote=_lote(dados.lote) or None,
        sacas=sacas, peso_kg=peso,
        documento=_texto(dados.documento, 40), placa=(_texto(dados.placa, 10) or "").upper() or None,
        motorista=_texto(dados.motorista, 120), observacao=_texto(dados.observacao, 300),
        usuario_id=usuario.id,
    )

    if tipo == "SERVICO":
        servico = _texto(dados.servico, 80)
        if not servico:
            raise HTTPException(400, "Diga qual foi o serviço (ex.: rebenefício, ensaque).")
        movimento.servico = servico
        movimento.valor = round(max(0.0, float(dados.valor or 0)), 2)
    elif tipo == "TRANSFERENCIA":
        destino = _depositante(db, dados.depositante_destino_id, eid, "o depositante de destino")
        if destino.id == depositante.id:
            raise HTTPException(400, "Origem e destino da transferência são o mesmo depositante.")
        movimento.depositante_destino_id = destino.id
    elif tipo == "REMOCAO":
        destino = _armazem(db, dados.armazem_destino_id, eid, "o armazém de destino")
        if destino.id == armazem.id:
            raise HTTPException(400, "Origem e destino da remoção são o mesmo armazém.")
        if not destino.ativo:
            raise HTTPException(400, f"O armazém {destino.nome} está inativo.")
        movimento.armazem_destino_id = destino.id

    # o que tira do saldo precisa caber no saldo
    if tipo in ("SAIDA", "TRANSFERENCIA", "REMOCAO"):
        chave = (armazem.id, depositante.id, movimento.produto_id, _lote(movimento.lote))
        no_lote = _somar_saldos(db, eid).get(chave, {"sacas": 0.0, "peso_kg": 0.0})
        disponivel = no_lote["sacas"]
        if sacas > disponivel + TOLERANCIA:
            lote = f" no lote {movimento.lote}" if movimento.lote else ""
            raise HTTPException(
                400, f"{depositante.nome} tem {_n(disponivel)} sacas em {armazem.nome}{lote}"
                     f" — não dá para tirar {_n(sacas)}.")
        # sem peso digitado, sai o peso médio da saca daquele lote — senão o
        # saldo ficaria com sacas de um lado e quilos sobrando do outro
        if not peso and disponivel > TOLERANCIA and no_lote["peso_kg"] > 0:
            movimento.peso_kg = round(no_lote["peso_kg"] / disponivel * sacas, 2)

    ultimo = db.query(func.max(MovimentoArmazem.numero)).filter(
        MovimentoArmazem.empresa_id == eid, MovimentoArmazem.tipo == tipo).scalar()
    movimento.numero = int(ultimo or 0) + 1
    db.add(movimento)
    db.commit()
    db.refresh(movimento)
    return _ficha(movimento)


@router.post("/movimentos/{movimento_id}/cancelar")
def cancelar(movimento_id: int, dados: CancelarIn, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    movimento = db.get(MovimentoArmazem, movimento_id)
    if not movimento:
        raise HTTPException(404, "Lançamento não encontrado.")
    validar_empresa(db, movimento.empresa_id, usuario)
    if movimento.status == "CANCELADO":
        raise HTTPException(400, "Este lançamento já está cancelado.")
    if movimento.guia_transferencia_id:
        raise HTTPException(400, "Esta transferência veio de uma guia de transferência: para "
                                 "desfazer, reabra a guia na tela Transferências.")
    if movimento.guia_saida_id:
        raise HTTPException(400, "Esta saída veio de uma guia de saída: para desfazer, "
                                 "reabra ou cancele a guia na tela Saídas.")
    if movimento.guia_entrada_id:
        raise HTTPException(400, "Esta entrada veio de uma guia de entrada: para desfazer, "
                                 "reabra ou cancele a guia na tela Entrada.")
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise HTTPException(400, "Escreva o motivo do cancelamento.")
    if movimento.tipo != "SERVICO":
        negativos = _negativos(_somar_saldos(db, movimento.empresa_id, ignorar_id=movimento.id))
        if negativos:
            raise HTTPException(
                400, "Não dá para cancelar: parte deste café já saiu, foi transferida ou "
                     "removida. Cancele primeiro esses lançamentos.")
    movimento.status = "CANCELADO"
    obs = f"Cancelado: {motivo}"
    movimento.observacao = (f"{movimento.observacao} | {obs}" if movimento.observacao
                            else obs)[:300]
    db.commit()
    db.refresh(movimento)
    return _ficha(movimento)
