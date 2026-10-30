"""WMS — Guia de serviço: liga, rebenefício, catação, padronização...

A guia tem três partes::

    Cabeçalho   número, data, data de início, data de fim, armazém, cliente,
                serviço (liga, rebenefício...), produto, valor cobrado,
                observação
    Despejo     de que lotes e posições (quadra + pilha) sai o café que entra
                no serviço — vários lotes, e pode ser só uma parte de cada
    Resultado   os lotes que saem do serviço — um ou vários — com peneira,
                padrão, sacas, peso e os locais (quadra, pilha) onde ficaram

Enquanto está **ABERTA** é rascunho. Ao **FECHAR**, o sistema confere:

* cada posição do despejo tem as sacas e o cliente tem o lote no saldo;
* todo lote do despejo é do cliente e do armazém da guia;
* há pelo menos um lote resultado, e os locais de cada um somam as sacas dele
  (local sem peso recebe a parte proporcional);

e então:

* o despejo sai das pilhas e do saldo (``MovimentoArmazem`` DESPEJO por lote);
* cada resultado vira um ``LoteArmazem`` do cliente, código "S<nº>/<seq>"
  ("S7/1", "S7/2"; se já existir, "S7/1-2"...), com as posições, e entra no
  saldo (``MovimentoArmazem`` RESULTADO);
* resultado sem peso digitado recebe o peso do despejo, dividido pelas sacas.

A **quebra** (despejo − resultado) é só mostrada: rebenefício e catação perdem
peso, e é isso que se quer enxergar.

**Reabrir** desfaz, se nenhum lote resultado foi usado (saída, transferência,
outro serviço, remoção). **Cancelar** só vale para guia aberta.

Rotas
-----
GET  /api/wms/guias-servico                 lista
GET  /api/wms/guias-servico/{id}            a guia completa
POST /api/wms/guias-servico                 nova (aberta)
PUT  /api/wms/guias-servico/{id}            salvar a guia aberta
POST /api/wms/guias-servico/{id}/fechar     fecha: despeja e gera os lotes
POST /api/wms/guias-servico/{id}/reabrir    volta para aberta
POST /api/wms/guias-servico/{id}/cancelar   cancela a guia aberta

As posições do cliente vêm de ``/api/wms/posicoes-disponiveis`` (wms_saida.py).
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
    GuiaRemocao,
    GuiaSaida,
    GuiaSaidaItem,
    GuiaServico,
    GuiaServicoDespejo,
    GuiaServicoResultado,
    GuiaServicoResultadoLocal,
    GuiaTransferencia,
    GuiaTransferenciaItem,
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
from .wms import SERVICOS, TOLERANCIA, _n, _negativos, _somar_saldos
from .wms_entrada import desligar_amostras, religar_amostra, saidas_por_posicao

router = APIRouter(prefix="/api/wms", tags=["wms"],
                   dependencies=[Depends(exigir_modulo("WMS"))])

# serviços que mexem no café (a guia sugere; aceita outro)
TIPOS_DE_SERVICO = ("Liga / padronização", "Rebenefício", "Catação", "Ventilação",
                    "Peneiramento", "Secagem", "Ensaque", "Reensaque", "Blend")


def _num(valor) -> float:
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _texto(valor, limite: int) -> str | None:
    return (str(valor or "")).strip()[:limite] or None


# --------------------------------------------------------------------------- #
# Entrada de dados
# --------------------------------------------------------------------------- #
class DespejoIn(BaseModel):
    posicao_id: int | None = None
    sacas: float = 0
    peso: float = 0


class LocalIn(BaseModel):
    quadra_id: int | None = None
    pilha: str | None = None
    sacas: float = 0
    peso: float = 0


class ResultadoIn(BaseModel):
    peneira: str | None = None
    padrao: str | None = None
    sacas: float = 0
    peso: float = 0
    unidade_id: int | None = None
    locais: list[LocalIn] = []


class GuiaServicoIn(BaseModel):
    empresa_id: int
    data: str | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    armazem_id: int | None = None
    cliente_id: int | None = None
    servico: str | None = None
    produto_id: int | None = None
    valor: float = 0
    observacao: str | None = None
    despejos: list[DespejoIn] = []
    resultados: list[ResultadoIn] = []


class MotivoIn(BaseModel):
    motivo: str | None = None


# --------------------------------------------------------------------------- #
# Ficha
# --------------------------------------------------------------------------- #
def _lugar(quadra, pilha) -> str:
    nome = quadra.nome if quadra else "?"
    return f"{nome}/{pilha}" if pilha else nome


def _ficha(g: GuiaServico, completa: bool = False) -> dict:
    sacas_d = round(sum(float(d.sacas or 0) for d in g.despejos), 2)
    peso_d = round(sum(float(d.peso or 0) for d in g.despejos), 2)
    sacas_r = round(sum(float(r.sacas or 0) for r in g.resultados), 2)
    peso_r = round(sum(float(r.peso or 0) for r in g.resultados), 2)
    ficha = serializar(g, extras={
        "armazem_nome": g.armazem.nome if g.armazem else "-",
        "cliente_nome": g.cliente.nome if g.cliente else "-",
        "produto_nome": g.produto.nome if g.produto else None,
        "despejo_sacas": sacas_d, "despejo_peso": peso_d,
        "resultado_sacas": sacas_r, "resultado_peso": peso_r,
        "quebra_sacas": round(sacas_d - sacas_r, 2),
        "quebra_peso": round(peso_d - peso_r, 2) if peso_d and peso_r else None,
        "lotes_despejo": sorted({d.lote.codigo for d in g.despejos if d.lote}),
        "lotes_resultado": [r.lote_gerado.codigo for r in g.resultados if r.lote_gerado],
    })
    if completa:
        ficha["despejos"] = [serializar(d, extras={
            "lote_codigo": d.lote.codigo if d.lote else "-",
            "peneira": d.lote.peneira if d.lote else None,
            "padrao": d.lote.padrao if d.lote else None,
            "quadra_nome": d.posicao.quadra.nome if d.posicao and d.posicao.quadra else "-",
            "pilha": d.posicao.pilha if d.posicao else None,
        }) for d in g.despejos]
        ficha["resultados"] = [serializar(r, extras={
            "codigo": r.lote_gerado.codigo if r.lote_gerado else None,
            "unidade_codigo": r.unidade.codigo if r.unidade else None,
            "locais": [serializar(x, extras={"quadra_nome": x.quadra.nome if x.quadra else "-"})
                       for x in r.locais],
        }) for r in g.resultados]
    return ficha


def _guia(db: Session, guia_id: int, usuario: Usuario) -> GuiaServico:
    guia = db.get(GuiaServico, guia_id)
    if not guia:
        raise HTTPException(404, "Guia de serviço não encontrada.")
    validar_empresa(db, guia.empresa_id, usuario)
    return guia


def _do_cadastro(db: Session, modelo, ident, empresa_id: int, rotulo: str):
    if not ident:
        return None
    obj = db.get(modelo, ident)
    if not obj or obj.empresa_id != empresa_id:
        raise HTTPException(400, f"{rotulo} não encontrado nesta empresa.")
    return obj


def _gravar(db: Session, guia: GuiaServico, dados: GuiaServicoIn) -> None:
    eid = dados.empresa_id
    armazem = _do_cadastro(db, Armazem, dados.armazem_id, eid, "Armazém")
    if not armazem:
        raise HTTPException(400, "Escolha o armazém.")
    cliente = _do_cadastro(db, Parceiro, dados.cliente_id, eid, "Cliente")
    if not cliente:
        raise HTTPException(400, "Escolha o cliente (dono do café).")
    produto = _do_cadastro(db, Produto, dados.produto_id, eid, "Produto")
    inicio, fim = parse_data(dados.data_inicio), parse_data(dados.data_fim)
    if inicio and fim and fim < inicio:
        raise HTTPException(400, "A data de fim é antes da data de início.")

    guia.empresa_id = eid
    guia.data = parse_data(dados.data) or guia.data or date.today()
    guia.data_inicio = inicio
    guia.data_fim = fim
    guia.armazem_id = armazem.id
    guia.cliente_id = cliente.id
    guia.servico = _texto(dados.servico, 80)
    guia.produto_id = produto.id if produto else None
    guia.valor = max(0.0, _num(dados.valor))
    guia.observacao = _texto(dados.observacao, 500)

    # despejo: junta repetidos da mesma posição, ignora linha zerada
    por_posicao: dict[int, list[float]] = {}
    for d in dados.despejos:
        sacas = max(0.0, _num(d.sacas))
        if not d.posicao_id or sacas <= 0:
            continue
        atual = por_posicao.setdefault(d.posicao_id, [0.0, 0.0])
        atual[0] += sacas
        atual[1] += max(0.0, _num(d.peso))
    guia.despejos.clear()
    guia.resultados.clear()
    db.flush()
    for posicao_id, (sacas, peso) in por_posicao.items():
        pos = db.get(LotePosicao, posicao_id)
        if not pos or not pos.lote or pos.lote.empresa_id != eid:
            raise HTTPException(400, "Posição de lote não encontrada nesta empresa.")
        guia.despejos.append(GuiaServicoDespejo(lote_id=pos.lote_id, posicao_id=pos.id,
                                                sacas=round(sacas, 2), peso=round(peso, 2)))

    quadras = {q.id: q for q in db.query(QuadraArmazem).filter(QuadraArmazem.empresa_id == eid)}
    seq = 0
    for r in dados.resultados:
        locais = [x for x in r.locais if x.quadra_id or _num(x.sacas)]
        if not _num(r.sacas) and not locais and not (r.peneira or r.padrao):
            continue                                  # lote em branco
        seq += 1
        unidade = _do_cadastro(db, Unidade, r.unidade_id, eid, "Unidade")
        resultado = GuiaServicoResultado(
            sequencia=seq, peneira=_texto(r.peneira, 20), padrao=_texto(r.padrao, 60),
            sacas=max(0.0, _num(r.sacas)), peso=max(0.0, _num(r.peso)),
            unidade_id=unidade.id if unidade else None)
        for x in locais:
            quadra = quadras.get(x.quadra_id or 0)
            if not quadra:
                raise HTTPException(400, f"Resultado {seq}: escolha a quadra.")
            resultado.locais.append(GuiaServicoResultadoLocal(
                quadra_id=quadra.id, pilha=(_texto(x.pilha, 20) or "").upper() or None,
                sacas=max(0.0, _num(x.sacas)), peso=max(0.0, _num(x.peso))))
        guia.resultados.append(resultado)


# --------------------------------------------------------------------------- #
# Lista e CRUD
# --------------------------------------------------------------------------- #
@router.get("/guias-servico")
def listar(empresa_id: int, de: str | None = None, ate: str | None = None,
           armazem_id: int | None = None, cliente_id: int | None = None,
           status: str | None = None, busca: str | None = None,
           db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(GuiaServico).filter(GuiaServico.empresa_id == empresa_id)
    inicio, fim = parse_data(de), parse_data(ate)
    if inicio:
        consulta = consulta.filter(GuiaServico.data >= inicio)
    if fim:
        consulta = consulta.filter(GuiaServico.data <= fim)
    if armazem_id:
        consulta = consulta.filter(GuiaServico.armazem_id == armazem_id)
    if cliente_id:
        consulta = consulta.filter(GuiaServico.cliente_id == cliente_id)
    if status:
        consulta = consulta.filter(GuiaServico.status == status.upper())
    else:
        consulta = consulta.filter(GuiaServico.status != "CANCELADA")
    texto = (busca or "").strip()
    if texto:
        filtros = [GuiaServico.servico.ilike(f"%{texto}%"), GuiaServico.observacao.ilike(f"%{texto}%")]
        if texto.isdigit():
            filtros.append(GuiaServico.numero == int(texto))
        consulta = consulta.filter(or_(*filtros))
    guias = consulta.order_by(GuiaServico.data.desc(), GuiaServico.numero.desc()).limit(500).all()
    fichas = [_ficha(g) for g in guias]
    validas = [f for f in fichas if f["status"] != "CANCELADA"]
    fechadas = [f for f in validas if f["status"] == "FECHADA"]
    return {
        "guias": fichas,
        "resumo": {
            "guias": len(validas),
            "abertas": sum(1 for f in validas if f["status"] == "ABERTA"),
            "despejo_sacas": round(sum(f["despejo_sacas"] for f in fechadas), 2),
            "resultado_sacas": round(sum(f["resultado_sacas"] for f in fechadas), 2),
            "valor": round(sum(float(f["valor"] or 0) for f in validas), 2),
        },
        "servicos": list(TIPOS_DE_SERVICO) + [s for s in SERVICOS if s not in TIPOS_DE_SERVICO],
    }


@router.get("/guias-servico/{guia_id}")
def ver(guia_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    return _ficha(_guia(db, guia_id, usuario), completa=True)


@router.post("/guias-servico")
def criar(dados: GuiaServicoIn, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    ultimo = db.query(func.max(GuiaServico.numero)).filter(
        GuiaServico.empresa_id == dados.empresa_id).scalar()
    guia = GuiaServico(numero=int(ultimo or 0) + 1, status="ABERTA", usuario_id=usuario.id)
    _gravar(db, guia, dados)
    db.add(guia)
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.put("/guias-servico/{guia_id}")
def salvar(guia_id: int, dados: GuiaServicoIn, db: Session = Depends(get_db),
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


# --------------------------------------------------------------------------- #
# Fechar, reabrir, cancelar
# --------------------------------------------------------------------------- #
def conferir(db: Session, guia: GuiaServico) -> list[str]:
    problemas: list[str] = []
    if not guia.despejos:
        problemas.append("Escolha o que é despejado no serviço (lote, quadra e pilha).")
    if not any(float(r.sacas or 0) > 0 for r in guia.resultados):
        problemas.append("Diga o resultado: o(s) lote(s) que saem do serviço, com as sacas.")
    saiu = saidas_por_posicao(db, guia.empresa_id, ignorar_servico_id=guia.id)
    saldos = _somar_saldos(db, guia.empresa_id)
    por_lote: dict[int, list] = {}
    for d in guia.despejos:
        lote, pos = d.lote, d.posicao
        onde = f"lote {lote.codigo}, quadra {pos.quadra.nome if pos.quadra else '?'}" + (
            f" pilha {pos.pilha}" if pos.pilha else "")
        if lote.armazem_id != guia.armazem_id:
            problemas.append(f"O {onde} é de outro armazém.")
        if lote.depositante_id != guia.cliente_id:
            problemas.append(f"O lote {lote.codigo} não é do cliente desta guia.")
        resta = float(pos.sacas or 0) - saiu.get(pos.id, {"sacas": 0.0})["sacas"]
        if float(d.sacas) > resta + TOLERANCIA:
            problemas.append(f"No {onde} restam {_n(resta)} sacas — o despejo leva {_n(float(d.sacas))}.")
        por_lote.setdefault(lote.id, [lote, 0.0])[1] += float(d.sacas)
    for lote, sacas in por_lote.values():
        chave = (lote.armazem_id, lote.depositante_id, lote.produto_id, lote.codigo.upper())
        no_saldo = saldos.get(chave, {"sacas": 0.0})["sacas"]
        if sacas > no_saldo + TOLERANCIA:
            problemas.append(f"O cliente tem {_n(no_saldo)} sacas do lote {lote.codigo} no saldo "
                             f"— o despejo leva {_n(sacas)}.")
    for r in guia.resultados:
        nome = f"Resultado {r.sequencia}"
        if float(r.sacas or 0) <= 0:
            problemas.append(f"{nome}: informe as sacas.")
            continue
        if not r.locais:
            problemas.append(f"{nome}: diga em que quadra ele ficou.")
            continue
        soma = sum(float(x.sacas or 0) for x in r.locais)
        if abs(soma - float(r.sacas)) > TOLERANCIA * 2:
            problemas.append(f"{nome}: os locais somam {_n(soma)} sacas e o lote tem {_n(float(r.sacas))}.")
        soma_kg = sum(float(x.peso or 0) for x in r.locais)
        if soma_kg and float(r.peso or 0) and abs(soma_kg - float(r.peso)) > TOLERANCIA * 2:
            problemas.append(f"{nome}: os locais somam {_n(soma_kg)} kg e o lote tem {_n(float(r.peso))} kg.")
        for x in r.locais:
            if x.quadra and x.quadra.armazem_id != guia.armazem_id:
                problemas.append(f"{nome}: a quadra {x.quadra.nome} é de outro armazém.")
            if float(x.sacas or 0) <= 0:
                problemas.append(f"{nome}: o local na quadra {x.quadra.nome if x.quadra else '?'} está sem sacas.")
    return problemas


def _codigo_resultado(db: Session, empresa_id: int, numero: int, seq: int, usados: set[str]) -> str:
    base = f"S{numero}/{seq}"
    existentes = {c.upper() for (c,) in db.query(LoteArmazem.codigo).filter(
        LoteArmazem.empresa_id == empresa_id, LoteArmazem.codigo.like(f"{base}%"))} | usados
    codigo, n = base, 2
    while codigo.upper() in existentes:
        codigo = f"{base}-{n}"
        n += 1
    return codigo


def _peso_do_despejo(d: GuiaServicoDespejo, saiu: dict) -> None:
    if float(d.peso or 0):
        return
    pos = d.posicao
    ja = saiu.get(pos.id, {"sacas": 0.0, "peso": 0.0})
    resta_sc = float(pos.sacas or 0) - ja["sacas"]
    resta_kg = float(pos.peso or 0) - ja["peso"]
    if resta_sc > TOLERANCIA and resta_kg > 0:
        d.peso = round(resta_kg, 2) if abs(float(d.sacas) - resta_sc) <= TOLERANCIA \
            else round(resta_kg / resta_sc * float(d.sacas), 2)


def _distribuir(total: float, partes: list, campo_sacas="sacas", campo_peso="peso") -> None:
    """Põe o ``total`` de peso nas partes sem peso, proporcional às sacas."""
    sem = [p for p in partes if not float(getattr(p, campo_peso) or 0)]
    if not sem or total <= 0:
        return
    sacas = sum(float(getattr(p, campo_sacas) or 0) for p in sem)
    if sacas <= 0:
        return
    restante = round(total, 2)
    for i, p in enumerate(sem):
        if i == len(sem) - 1:
            setattr(p, campo_peso, round(restante, 2))
        else:
            v = round(total * float(getattr(p, campo_sacas) or 0) / sacas, 2)
            setattr(p, campo_peso, v)
            restante = round(restante - v, 2)


def _proximo(db: Session, empresa_id: int, tipo: str) -> int:
    ultimo = db.query(func.max(MovimentoArmazem.numero)).filter(
        MovimentoArmazem.empresa_id == empresa_id, MovimentoArmazem.tipo == tipo).scalar()
    return int(ultimo or 0) + 1


@router.post("/guias-servico/{guia_id}/fechar")
def fechar(guia_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status != "ABERTA":
        raise HTTPException(400, f"A guia {guia.numero} já está {guia.status.lower()}.")
    problemas = conferir(db, guia)
    if problemas:
        raise HTTPException(400, "Não deu para fechar a guia: " + " ".join(problemas))

    # despejo: peso, saída do saldo por lote
    saiu = saidas_por_posicao(db, guia.empresa_id, ignorar_servico_id=guia.id)
    por_lote: dict[int, list] = {}
    for d in guia.despejos:
        _peso_do_despejo(d, saiu)
        atual = por_lote.setdefault(d.lote_id, [d.lote, 0.0, 0.0])
        atual[1] += float(d.sacas)
        atual[2] += float(d.peso or 0)
    peso_despejo = round(sum(v[2] for v in por_lote.values()), 2)
    for lote, sacas, peso in por_lote.values():
        db.add(MovimentoArmazem(
            empresa_id=guia.empresa_id, tipo="DESPEJO", numero=_proximo(db, guia.empresa_id, "DESPEJO"),
            data=guia.data_fim or guia.data, armazem_id=guia.armazem_id,
            depositante_id=guia.cliente_id, produto_id=lote.produto_id, lote=lote.codigo,
            sacas=round(sacas, 2), peso_kg=round(peso, 2),
            documento=f"Guia de serviço {guia.numero}", guia_servico_id=guia.id,
            usuario_id=usuario.id, servico=guia.servico,
            observacao=_texto(f"{guia.servico or 'serviço'} — despejo", 300)))
        db.flush()

    # resultado: peso que falta vem do despejo (menos o que já foi digitado)
    resultados = [r for r in guia.resultados if float(r.sacas or 0) > 0]
    digitado = sum(float(r.peso or 0) for r in resultados)
    _distribuir(max(0.0, peso_despejo - digitado), resultados)
    produto_id = guia.produto_id or next((l.produto_id for l, _, _ in por_lote.values()), None)
    unidade_padrao = next((l.unidade_id for l, _, _ in por_lote.values() if l.unidade_id), None)
    usados: set[str] = set()
    for r in resultados:
        _distribuir(float(r.peso or 0), r.locais)
        codigo = _codigo_resultado(db, guia.empresa_id, guia.numero, r.sequencia, usados)
        usados.add(codigo.upper())
        lote = LoteArmazem(
            empresa_id=guia.empresa_id, guia_id=None, codigo=codigo,
            data_entrada=guia.data_fim or guia.data, armazem_id=guia.armazem_id,
            depositante_id=guia.cliente_id, produto_id=produto_id,
            peneira=r.peneira, padrao=r.padrao, sacas=r.sacas, peso=r.peso,
            unidade_id=r.unidade_id or unidade_padrao, guia_servico_id=guia.id)
        for x in r.locais:
            lote.posicoes.append(LotePosicao(quadra_id=x.quadra_id, pilha=x.pilha,
                                             sacas=x.sacas, peso=x.peso))
        db.add(lote)
        db.flush()
        religar_amostra(db, lote)
        r.lote_gerado_id = lote.id
        db.add(MovimentoArmazem(
            empresa_id=guia.empresa_id, tipo="RESULTADO", numero=_proximo(db, guia.empresa_id, "RESULTADO"),
            data=guia.data_fim or guia.data, armazem_id=guia.armazem_id,
            depositante_id=guia.cliente_id, produto_id=produto_id, lote=codigo,
            sacas=r.sacas, peso_kg=r.peso, documento=f"Guia de serviço {guia.numero}",
            guia_servico_id=guia.id, usuario_id=usuario.id, servico=guia.servico,
            observacao=_texto(" · ".join(filter(None, [
                guia.servico or "", f"peneira {r.peneira}" if r.peneira else "", r.padrao or ""])), 300)))
        db.flush()
    if not guia.data_fim:
        guia.data_fim = date.today()
    guia.status = "FECHADA"
    guia.fechada_em = datetime.utcnow()
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.post("/guias-servico/{guia_id}/reabrir")
def reabrir(guia_id: int, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    guia = _guia(db, guia_id, usuario)
    if guia.status != "FECHADA":
        raise HTTPException(400, "Só guia fechada pode ser reaberta.")
    novos = db.query(LoteArmazem).filter(LoteArmazem.guia_servico_id == guia.id).all()
    ids = [l.id for l in novos] or [0]
    usos = []
    usos += [f"guia de saída {n}" for (n,) in db.query(GuiaSaida.numero)
             .join(GuiaSaidaItem, GuiaSaidaItem.guia_id == GuiaSaida.id)
             .filter(GuiaSaidaItem.lote_id.in_(ids), GuiaSaida.status != "CANCELADA").distinct()]
    usos += [f"guia de transferência {n}" for (n,) in db.query(GuiaTransferencia.numero)
             .join(GuiaTransferenciaItem, GuiaTransferenciaItem.guia_id == GuiaTransferencia.id)
             .filter(GuiaTransferenciaItem.lote_id.in_(ids), GuiaTransferencia.status != "CANCELADA").distinct()]
    usos += [f"guia de serviço {n}" for (n,) in db.query(GuiaServico.numero)
             .join(GuiaServicoDespejo, GuiaServicoDespejo.guia_id == GuiaServico.id)
             .filter(GuiaServicoDespejo.lote_id.in_(ids), GuiaServico.status != "CANCELADA",
                     GuiaServico.id != guia.id).distinct()]
    usos += [f"remoção {n}" for (n,) in db.query(GuiaRemocao.numero)
             .filter(GuiaRemocao.lote_id.in_(ids), GuiaRemocao.status == "ATIVA")]
    if usos:
        raise HTTPException(
            400, f"Não dá para reabrir a guia {guia.numero}: os lotes resultado já estão na "
                 f"{', '.join(usos)}. Desfaça isso primeiro.")
    movimentos = db.query(MovimentoArmazem).filter(MovimentoArmazem.guia_servico_id == guia.id).all()
    saldos = _somar_saldos(db, guia.empresa_id)
    for m in movimentos:
        chave = (m.armazem_id, m.depositante_id, m.produto_id, (m.lote or "").upper())
        if m.tipo == "RESULTADO" and chave in saldos:
            saldos[chave]["sacas"] -= float(m.sacas or 0)
    if _negativos(saldos):
        raise HTTPException(400, f"Não dá para reabrir a guia {guia.numero}: parte dos lotes "
                                 "resultado já foi movimentada.")
    for m in movimentos:
        db.delete(m)
    for r in guia.resultados:
        r.lote_gerado_id = None
    db.flush()
    desligar_amostras(db, [l.id for l in novos])
    for lote in novos:
        db.delete(lote)
    guia.status = "ABERTA"
    guia.fechada_em = None
    db.commit()
    db.refresh(guia)
    return _ficha(guia, completa=True)


@router.post("/guias-servico/{guia_id}/cancelar")
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
    guia.observacao = (f"{guia.observacao} | {obs}" if guia.observacao else obs)[:500]
    db.commit()
    db.refresh(guia)
    return _ficha(guia)
