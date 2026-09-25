"""Lançamentos financeiros — contas a receber e contas a pagar.

Lançamento SIMPLES  : uma classificação e uma parcela.
Lançamento MÚLTIPLO : rateio em várias contas/centros de custo e/ou várias parcelas.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .. import contabil
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import (
    Baixa,
    Banco,
    CentroCusto,
    ContaContabil,
    FormaPagamentoParceiro,
    Lancamento,
    LancamentoItem,
    MovimentoCaixa,
    Operacao,
    Parcela,
    Parceiro,
    Usuario,
)
from ..schemas import BaixaIn, BaixaLoteIn, LancamentoIn
from ..utils import adicionar_meses, dinheiro, parse_data, serializar, somar

# O menu deste módulo pode ser tirado de um plano (ou de um cliente) na área
# do administrador. Quem fecha a porta de verdade é a dependência abaixo:
# esconder o botão no menu não impede ninguém de chamar a rota pelo endereço.
router = APIRouter(prefix="/api", tags=["lancamentos"],
                   dependencies=[Depends(exigir_modulo("FINANCEIRO"))])

TOLERANCIA = 0.02


# --------------------------------------------------------------------------- #
# Serialização
# --------------------------------------------------------------------------- #
def item_dict(item: LancamentoItem) -> dict:
    return serializar(
        item,
        extras={
            "conta_contabil_codigo": item.conta_contabil.codigo if item.conta_contabil else None,
            "conta_contabil_nome": item.conta_contabil.nome if item.conta_contabil else None,
            "centro_custo_nome": item.centro_custo.nome if item.centro_custo else None,
            "operacao_nome": item.operacao.nome if item.operacao else None,
        },
    )


def parcela_dict(parcela: Parcela, com_lancamento: bool = False) -> dict:
    lanc = parcela.lancamento
    hoje = date.today()
    atraso = 0
    if parcela.status in ("ABERTO", "PARCIAL") and parcela.data_vencimento < hoje:
        atraso = (hoje - parcela.data_vencimento).days
    dados = serializar(
        parcela,
        extras={
            "saldo": parcela.saldo,
            "dias_atraso": atraso,
            "vencida": atraso > 0,
        },
    )
    if com_lancamento:
        dados.update(
            {
                "tipo": lanc.tipo,
                "empresa_id": lanc.empresa_id,
                "descricao": lanc.descricao,
                "numero_documento": lanc.numero_documento,
                "data_emissao": lanc.data_emissao.isoformat() if lanc.data_emissao else None,
                "data_competencia": (
                    lanc.data_competencia.isoformat() if lanc.data_competencia else None
                ),
                "parceiro_id": lanc.parceiro_id,
                "parceiro_nome": lanc.parceiro.nome if lanc.parceiro else None,
                "operacao_nome": lanc.operacao.nome if lanc.operacao else None,
                "total_parcelas": len(lanc.parcelas),
                "classificacao": ", ".join(
                    f"{i.conta_contabil.codigo} {i.conta_contabil.nome}"
                    for i in lanc.itens
                    if i.conta_contabil
                ),
                "centros_custo": ", ".join(
                    sorted({i.centro_custo.nome for i in lanc.itens if i.centro_custo})
                ),
            }
        )
    return dados


def baixa_dict(baixa: Baixa) -> dict:
    from .cadastros import resumo_forma  # evita import circular no carregamento

    return serializar(
        baixa,
        extras={
            "banco_nome": baixa.banco.nome if baixa.banco else None,
            "forma_parceiro": resumo_forma(baixa.forma_parceiro) if baixa.forma_parceiro else "",
        },
    )


def lancamento_dict(lanc: Lancamento, completo: bool = False) -> dict:
    total_baixado = somar(p.valor_baixado for p in lanc.parcelas)
    dados = serializar(
        lanc,
        extras={
            "parceiro_nome": lanc.parceiro.nome if lanc.parceiro else None,
            "operacao_nome": lanc.operacao.nome if lanc.operacao else None,
            "total_baixado": total_baixado,
            "saldo": round(dinheiro(lanc.valor_total) - total_baixado, 2),
            "qtd_parcelas": len(lanc.parcelas),
            "proximo_vencimento": min(
                (p.data_vencimento for p in lanc.parcelas if p.status in ("ABERTO", "PARCIAL")),
                default=None,
            ),
        },
    )
    if dados.get("proximo_vencimento"):
        dados["proximo_vencimento"] = str(dados["proximo_vencimento"])
    if completo:
        dados["itens"] = [item_dict(i) for i in lanc.itens]
        dados["parcelas"] = [
            dict(parcela_dict(p), baixas=[baixa_dict(b) for b in p.baixas]) for p in lanc.parcelas
        ]
    return dados


# --------------------------------------------------------------------------- #
# Regras
# --------------------------------------------------------------------------- #
def atualizar_status_lancamento(lanc: Lancamento):
    if lanc.status == "CANCELADO":
        return
    total = dinheiro(lanc.valor_total)
    baixado = somar(p.valor_baixado for p in lanc.parcelas)
    if baixado <= 0:
        lanc.status = "ABERTO"
    elif baixado + TOLERANCIA >= total:
        lanc.status = "QUITADO"
    else:
        lanc.status = "PARCIAL"


def gerar_parcelas(dados: LancamentoIn, valor_total: float) -> list[dict]:
    if dados.parcelas:
        return [
            {
                "numero": p.numero or i + 1,
                "data_vencimento": p.data_vencimento,
                "valor": dinheiro(p.valor),
                "observacao": p.observacao,
            }
            for i, p in enumerate(dados.parcelas)
        ]

    qtd = max(1, int(dados.num_parcelas or 1))
    base = dados.primeiro_vencimento or dados.data_emissao or date.today()
    valor_parcela = round(valor_total / qtd, 2)
    parcelas = []
    acumulado = 0.0
    for i in range(qtd):
        if dados.periodicidade == "DIAS":
            venc = base + timedelta(days=dados.intervalo_dias * i)
        else:
            venc = adicionar_meses(base, i)
        valor = valor_parcela if i < qtd - 1 else round(valor_total - acumulado, 2)
        acumulado += valor
        parcelas.append(
            {"numero": i + 1, "data_vencimento": venc, "valor": valor, "observacao": None}
        )
    return parcelas


def montar_itens(db: Session, dados: LancamentoIn, valor_total: float) -> list[dict]:
    itens = [i.model_dump() for i in dados.itens if dinheiro(i.valor) > 0]
    if not itens:
        if not dados.operacao_id:
            raise HTTPException(
                400, "Informe ao menos uma classificação (conta contábil) ou uma operação."
            )
        operacao = db.get(Operacao, dados.operacao_id)
        if not operacao or not operacao.conta_contabil_id:
            raise HTTPException(
                400,
                "A operação selecionada não tem conta contábil vinculada. "
                "Informe a classificação manualmente.",
            )
        itens = [
            {
                "conta_contabil_id": operacao.conta_contabil_id,
                "centro_custo_id": operacao.centro_custo_id,
                "operacao_id": operacao.id,
                "descricao": dados.descricao,
                "valor": valor_total,
            }
        ]
    soma = somar(i["valor"] for i in itens)
    if abs(soma - valor_total) > TOLERANCIA:
        raise HTTPException(
            400,
            f"A soma do rateio (R$ {soma:,.2f}) é diferente do valor do lançamento "
            f"(R$ {valor_total:,.2f}).",
        )
    for item in itens:
        conta = db.get(ContaContabil, item["conta_contabil_id"])
        if not conta or conta.empresa_id != dados.empresa_id:
            raise HTTPException(400, "Conta contábil inválida no rateio.")
        if not conta.analitica:
            raise HTTPException(
                400, f"A conta {conta.codigo} é sintética e não aceita lançamentos."
            )
    return itens


# --------------------------------------------------------------------------- #
# Endpoints — lançamentos
# --------------------------------------------------------------------------- #
@router.post("/lancamentos")
def criar_lancamento(
    dados: LancamentoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    validar_empresa(db, dados.empresa_id)
    if dados.tipo not in ("RECEBER", "PAGAR"):
        raise HTTPException(400, "Tipo deve ser RECEBER ou PAGAR")

    valor_total = dinheiro(dados.valor_total)
    if valor_total <= 0:
        raise HTTPException(400, "Informe um valor maior que zero")

    emissao = dados.data_emissao or date.today()
    competencia = dados.data_competencia or emissao
    itens = montar_itens(db, dados, valor_total)
    parcelas = gerar_parcelas(dados, valor_total)

    soma_parcelas = somar(p["valor"] for p in parcelas)
    if abs(soma_parcelas - valor_total) > TOLERANCIA:
        raise HTTPException(
            400,
            f"A soma das parcelas (R$ {soma_parcelas:,.2f}) é diferente do valor do "
            f"lançamento (R$ {valor_total:,.2f}).",
        )

    lanc = Lancamento(
        empresa_id=dados.empresa_id,
        tipo=dados.tipo,
        modo="MULTIPLO" if (len(itens) > 1 or len(parcelas) > 1) else "SIMPLES",
        numero_documento=dados.numero_documento,
        parceiro_id=dados.parceiro_id,
        descricao=dados.descricao,
        data_emissao=emissao,
        data_competencia=competencia,
        valor_total=valor_total,
        operacao_id=dados.operacao_id,
        observacao=dados.observacao,
        usuario_id=usuario.id,
    )
    db.add(lanc)
    db.flush()

    for item in itens:
        db.add(LancamentoItem(lancamento_id=lanc.id, **item))
    for p in parcelas:
        db.add(Parcela(lancamento_id=lanc.id, **p))
    db.flush()
    db.refresh(lanc)

    contabil.contabilizar_lancamento(db, lanc)

    if dados.baixar_agora:
        if not dados.banco_id:
            raise HTTPException(400, "Informe a conta bancária para a baixa imediata.")
        for parcela in lanc.parcelas:
            _executar_baixa(
                db,
                parcela,
                BaixaIn(
                    banco_id=dados.banco_id,
                    data=emissao,
                    valor=parcela.valor,
                    historico=f"{lanc.descricao} (baixa automática)",
                ),
                usuario,
            )

    atualizar_status_lancamento(lanc)
    db.commit()
    db.refresh(lanc)
    return lancamento_dict(lanc, completo=True)


@router.get("/lancamentos")
def listar_lancamentos(
    empresa_id: int,
    tipo: str | None = None,
    status: str | None = None,
    parceiro_id: int | None = None,
    operacao_id: int | None = None,
    de: str | None = None,
    ate: str | None = None,
    campo_data: str = "data_emissao",
    q: str | None = None,
    limite: int = 500,
    db: Session = Depends(get_db),
    _=Depends(acesso_liberado),
):
    query = (
        db.query(Lancamento)
        .options(joinedload(Lancamento.parcelas), joinedload(Lancamento.itens))
        .filter(Lancamento.empresa_id == empresa_id)
    )
    if tipo:
        query = query.filter(Lancamento.tipo == tipo)
    if status:
        query = query.filter(Lancamento.status == status)
    if parceiro_id:
        query = query.filter(Lancamento.parceiro_id == parceiro_id)
    if operacao_id:
        query = query.filter(Lancamento.operacao_id == operacao_id)
    coluna = getattr(Lancamento, campo_data, Lancamento.data_emissao)
    if de:
        query = query.filter(coluna >= parse_data(de))
    if ate:
        query = query.filter(coluna <= parse_data(ate))
    if q:
        termo = f"%{q.strip()}%"
        query = query.filter(
            or_(Lancamento.descricao.ilike(termo), Lancamento.numero_documento.ilike(termo))
        )
    lancamentos = query.order_by(Lancamento.data_emissao.desc(), Lancamento.id.desc()).limit(
        limite
    ).all()
    return [lancamento_dict(l) for l in lancamentos]


@router.get("/lancamentos/{lancamento_id}")
def obter_lancamento(lancamento_id: int, db: Session = Depends(get_db), _=Depends(acesso_liberado)):
    lanc = db.get(Lancamento, lancamento_id)
    if not lanc:
        raise HTTPException(404, "Lançamento não encontrado")
    return lancamento_dict(lanc, completo=True)


@router.delete("/lancamentos/{lancamento_id}")
def excluir_lancamento(
    lancamento_id: int, db: Session = Depends(get_db), _=Depends(acesso_liberado)
):
    lanc = db.get(Lancamento, lancamento_id)
    if not lanc:
        raise HTTPException(404, "Lançamento não encontrado")
    if any(p.baixas for p in lanc.parcelas):
        raise HTTPException(
            400, "Existem baixas neste lançamento. Estorne as baixas antes de excluir."
        )
    contabil.estornar(db, "LANCAMENTO", lanc.id)
    db.delete(lanc)
    db.commit()
    return {"ok": True}


@router.post("/lancamentos/{lancamento_id}/cancelar")
def cancelar_lancamento(
    lancamento_id: int, db: Session = Depends(get_db), _=Depends(acesso_liberado)
):
    lanc = db.get(Lancamento, lancamento_id)
    if not lanc:
        raise HTTPException(404, "Lançamento não encontrado")
    if any(p.baixas for p in lanc.parcelas):
        raise HTTPException(400, "Estorne as baixas antes de cancelar o lançamento.")
    lanc.status = "CANCELADO"
    for p in lanc.parcelas:
        p.status = "CANCELADO"
    contabil.estornar(db, "LANCAMENTO", lanc.id)
    db.commit()
    return lancamento_dict(lanc, completo=True)


# --------------------------------------------------------------------------- #
# Endpoints — parcelas e baixas
# --------------------------------------------------------------------------- #
@router.get("/parcelas")
def listar_parcelas(
    empresa_id: int,
    tipo: str | None = None,
    situacao: str = "ABERTAS",  # ABERTAS | PAGAS | VENCIDAS | TODAS
    parceiro_id: int | None = None,
    banco_id: int | None = None,
    de: str | None = None,
    ate: str | None = None,
    q: str | None = None,
    limite: int = 1000,
    db: Session = Depends(get_db),
    _=Depends(acesso_liberado),
):
    query = (
        db.query(Parcela)
        .join(Lancamento)
        .options(joinedload(Parcela.lancamento).joinedload(Lancamento.itens))
        .filter(Lancamento.empresa_id == empresa_id)
    )
    if tipo:
        query = query.filter(Lancamento.tipo == tipo)
    if parceiro_id:
        query = query.filter(Lancamento.parceiro_id == parceiro_id)
    if de:
        query = query.filter(Parcela.data_vencimento >= parse_data(de))
    if ate:
        query = query.filter(Parcela.data_vencimento <= parse_data(ate))
    if q:
        termo = f"%{q.strip()}%"
        query = query.filter(
            or_(Lancamento.descricao.ilike(termo), Lancamento.numero_documento.ilike(termo))
        )
    if situacao == "ABERTAS":
        query = query.filter(Parcela.status.in_(("ABERTO", "PARCIAL")))
    elif situacao == "PAGAS":
        query = query.filter(Parcela.status == "PAGO")
    elif situacao == "VENCIDAS":
        query = query.filter(
            Parcela.status.in_(("ABERTO", "PARCIAL")), Parcela.data_vencimento < date.today()
        )
    parcelas = (
        query.order_by(Parcela.data_vencimento, Parcela.id).limit(limite).all()
    )
    return [parcela_dict(p, com_lancamento=True) for p in parcelas]


@router.get("/parcelas/{parcela_id}")
def obter_parcela(parcela_id: int, db: Session = Depends(get_db), _=Depends(acesso_liberado)):
    parcela = db.get(Parcela, parcela_id)
    if not parcela:
        raise HTTPException(404, "Parcela não encontrada")
    dados = parcela_dict(parcela, com_lancamento=True)
    dados["baixas"] = [baixa_dict(b) for b in parcela.baixas]
    return dados


def _executar_baixa(db: Session, parcela: Parcela, dados: BaixaIn, usuario: Usuario) -> Baixa:
    lanc = parcela.lancamento
    if parcela.status == "CANCELADO":
        raise HTTPException(400, "Parcela cancelada não pode ser baixada.")
    banco = db.get(Banco, dados.banco_id)
    if not banco or banco.empresa_id != lanc.empresa_id:
        raise HTTPException(400, "Conta bancária inválida.")

    saldo = parcela.saldo
    valor = dinheiro(dados.valor if dados.valor is not None else saldo)
    if valor <= 0:
        raise HTTPException(400, "Valor da baixa deve ser maior que zero.")
    if valor > saldo + TOLERANCIA:
        raise HTTPException(
            400, f"Valor informado (R$ {valor:,.2f}) maior que o saldo da parcela (R$ {saldo:,.2f})."
        )

    juros = dinheiro(dados.juros)
    multa = dinheiro(dados.multa)
    desconto = dinheiro(dados.desconto)
    if desconto > valor:
        raise HTTPException(400, "O desconto não pode ser maior que o valor baixado.")
    liquido = round(valor - desconto + juros + multa, 2)
    data_baixa = dados.data or date.today()

    forma_parceiro = None
    if dados.forma_parceiro_id:
        forma_parceiro = db.get(FormaPagamentoParceiro, dados.forma_parceiro_id)
        if not forma_parceiro or forma_parceiro.parceiro_id != lanc.parceiro_id:
            raise HTTPException(
                400, "A forma de pagamento escolhida não pertence a este cliente/fornecedor."
            )

    baixa = Baixa(
        empresa_id=lanc.empresa_id,
        parcela_id=parcela.id,
        banco_id=banco.id,
        data=data_baixa,
        valor=valor,
        juros=juros,
        multa=multa,
        desconto=desconto,
        valor_liquido=liquido,
        forma_pagamento=dados.forma_pagamento,
        forma_parceiro_id=forma_parceiro.id if forma_parceiro else None,
        historico=dados.historico or f"{lanc.descricao} - parcela {parcela.numero}",
        usuario_id=usuario.id,
    )
    db.add(baixa)
    db.flush()

    parcela.valor_baixado = round(dinheiro(parcela.valor_baixado) + valor, 2)
    parcela.juros_multa = round(dinheiro(parcela.juros_multa) + juros + multa, 2)
    parcela.desconto = round(dinheiro(parcela.desconto) + desconto, 2)
    parcela.data_ultima_baixa = data_baixa
    parcela.status = "PAGO" if parcela.saldo <= TOLERANCIA else "PARCIAL"

    item = lanc.itens[0] if lanc.itens else None
    db.add(
        MovimentoCaixa(
            empresa_id=lanc.empresa_id,
            banco_id=banco.id,
            data=data_baixa,
            tipo="E" if lanc.tipo == "RECEBER" else "S",
            valor=liquido,
            historico=baixa.historico,
            origem="BAIXA",
            origem_id=baixa.id,
            conta_contabil_id=item.conta_contabil_id if item else None,
            centro_custo_id=item.centro_custo_id if item else None,
            operacao_id=lanc.operacao_id,
            parceiro_id=lanc.parceiro_id,
            documento=lanc.numero_documento,
            usuario_id=usuario.id,
        )
    )
    db.refresh(baixa)
    contabil.contabilizar_baixa(db, baixa)
    atualizar_status_lancamento(lanc)
    return baixa


@router.post("/parcelas/{parcela_id}/baixar")
def baixar_parcela(
    parcela_id: int,
    dados: BaixaIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    parcela = db.get(Parcela, parcela_id)
    if not parcela:
        raise HTTPException(404, "Parcela não encontrada")
    baixa = _executar_baixa(db, parcela, dados, usuario)
    db.commit()
    db.refresh(parcela)
    return {"baixa": baixa_dict(baixa), "parcela": parcela_dict(parcela, com_lancamento=True)}


@router.post("/parcelas/baixar-lote")
def baixar_lote(
    dados: BaixaLoteIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    resultado = []
    for parcela_id in dados.parcela_ids:
        parcela = db.get(Parcela, parcela_id)
        if not parcela or parcela.status in ("PAGO", "CANCELADO"):
            continue
        baixa = _executar_baixa(
            db,
            parcela,
            BaixaIn(
                banco_id=dados.banco_id,
                data=dados.data,
                forma_pagamento=dados.forma_pagamento,
                historico=dados.historico,
            ),
            usuario,
        )
        resultado.append(baixa.id)
    db.commit()
    return {"baixas": resultado, "quantidade": len(resultado)}


@router.delete("/baixas/{baixa_id}")
def estornar_baixa(baixa_id: int, db: Session = Depends(get_db), _=Depends(acesso_liberado)):
    baixa = db.get(Baixa, baixa_id)
    if not baixa:
        raise HTTPException(404, "Baixa não encontrada")
    parcela = baixa.parcela
    parcela.valor_baixado = round(dinheiro(parcela.valor_baixado) - dinheiro(baixa.valor), 2)
    parcela.juros_multa = round(
        dinheiro(parcela.juros_multa) - dinheiro(baixa.juros) - dinheiro(baixa.multa), 2
    )
    parcela.desconto = round(dinheiro(parcela.desconto) - dinheiro(baixa.desconto), 2)
    if parcela.valor_baixado <= TOLERANCIA:
        parcela.valor_baixado = 0
        parcela.status = "ABERTO"
        parcela.data_ultima_baixa = None
    else:
        parcela.status = "PARCIAL"

    db.query(MovimentoCaixa).filter(
        MovimentoCaixa.origem == "BAIXA", MovimentoCaixa.origem_id == baixa.id
    ).delete(synchronize_session=False)
    contabil.estornar(db, "BAIXA", baixa.id)
    db.delete(baixa)
    db.flush()
    atualizar_status_lancamento(parcela.lancamento)
    db.commit()
    return {"ok": True}


@router.get("/baixas")
def listar_baixas(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    tipo: str | None = None,
    banco_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(acesso_liberado),
):
    query = (
        db.query(Baixa)
        .join(Parcela)
        .join(Lancamento)
        .filter(Baixa.empresa_id == empresa_id)
    )
    if de:
        query = query.filter(Baixa.data >= parse_data(de))
    if ate:
        query = query.filter(Baixa.data <= parse_data(ate))
    if tipo:
        query = query.filter(Lancamento.tipo == tipo)
    if banco_id:
        query = query.filter(Baixa.banco_id == banco_id)
    baixas = query.order_by(Baixa.data.desc(), Baixa.id.desc()).all()
    return [
        dict(
            baixa_dict(b),
            tipo=b.parcela.lancamento.tipo,
            descricao=b.parcela.lancamento.descricao,
            parceiro_nome=(
                b.parcela.lancamento.parceiro.nome if b.parcela.lancamento.parceiro else None
            ),
            numero_parcela=b.parcela.numero,
        )
        for b in baixas
    ]
