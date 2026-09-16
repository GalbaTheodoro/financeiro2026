"""Motor contábil — gera as partidas dobradas de cada evento financeiro.

Toda movimentação do sistema (título lançado, baixa, movimento de caixa,
transferência, saldo inicial) grava um par débito/crédito na tabela `partidas`.
O balancete e o DRE são calculados exclusivamente a partir dela, o que garante
que débitos e créditos sempre fechem.
"""
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Banco, ContaContabil, Partida
from .plano_contas import parametro_conta
from .utils import dinheiro


# --------------------------------------------------------------------------- #
# Infra
# --------------------------------------------------------------------------- #
def lancar(
    db: Session,
    *,
    empresa_id: int,
    data: date,
    competencia: date,
    historico: str,
    debito_id: int,
    credito_id: int,
    valor: float,
    origem: str,
    origem_id: int,
    centro_custo_id: int | None = None,
    operacao_id: int | None = None,
    parceiro_id: int | None = None,
):
    valor = dinheiro(valor)
    if valor <= 0:
        return None
    if not debito_id or not credito_id:
        raise HTTPException(
            400,
            "Não foi possível gerar a contabilização: verifique as contas contábeis "
            "padrão em Cadastros > Parâmetros.",
        )
    p = Partida(
        empresa_id=empresa_id,
        data=data,
        competencia=competencia or data,
        historico=historico[:250],
        conta_debito_id=debito_id,
        conta_credito_id=credito_id,
        valor=valor,
        centro_custo_id=centro_custo_id,
        operacao_id=operacao_id,
        parceiro_id=parceiro_id,
        origem=origem,
        origem_id=origem_id,
    )
    db.add(p)
    return p


def estornar(db: Session, origem: str, origem_id: int):
    """Remove todas as partidas geradas por um documento."""
    db.query(Partida).filter(Partida.origem == origem, Partida.origem_id == origem_id).delete(
        synchronize_session=False
    )


def conta_do_banco(db: Session, banco: Banco) -> int:
    if banco.conta_contabil_id:
        return banco.conta_contabil_id
    chave = "conta_caixa_padrao" if banco.tipo == "CAIXA" else "conta_banco_padrao"
    conta = parametro_conta(db, banco.empresa_id, chave)
    if not conta:
        raise HTTPException(
            400,
            f"A conta '{banco.nome}' não tem conta contábil vinculada e não há "
            "conta padrão configurada.",
        )
    return conta


def _param(db: Session, empresa_id: int, chave: str) -> int:
    conta = parametro_conta(db, empresa_id, chave)
    if not conta:
        raise HTTPException(400, f"Parâmetro contábil '{chave}' não configurado para a empresa.")
    return conta


# --------------------------------------------------------------------------- #
# Eventos
# --------------------------------------------------------------------------- #
def contabilizar_lancamento(db: Session, lancamento):
    """Título a receber:  D Clientes        / C Receita (por item de rateio)
    Título a pagar:      D Despesa/Custo   / C Fornecedores
    """
    estornar(db, "LANCAMENTO", lancamento.id)
    if lancamento.status == "CANCELADO":
        return

    if lancamento.tipo == "RECEBER":
        contrapartida = _param(db, lancamento.empresa_id, "conta_clientes")
    else:
        contrapartida = _param(db, lancamento.empresa_id, "conta_fornecedores")

    for item in lancamento.itens:
        historico = f"{lancamento.descricao} - {item.descricao or ''}".strip(" -")
        if lancamento.tipo == "RECEBER":
            debito, credito = contrapartida, item.conta_contabil_id
        else:
            debito, credito = item.conta_contabil_id, contrapartida
        lancar(
            db,
            empresa_id=lancamento.empresa_id,
            data=lancamento.data_emissao,
            competencia=lancamento.data_competencia,
            historico=historico,
            debito_id=debito,
            credito_id=credito,
            valor=item.valor,
            origem="LANCAMENTO",
            origem_id=lancamento.id,
            centro_custo_id=item.centro_custo_id,
            operacao_id=item.operacao_id or lancamento.operacao_id,
            parceiro_id=lancamento.parceiro_id,
        )


def contabilizar_baixa(db: Session, baixa):
    """Recebimento:
        D Banco                  / C Clientes          (valor - desconto)
        D Descontos Concedidos   / C Clientes          (desconto)
        D Banco                  / C Juros Recebidos   (juros + multa)

    Pagamento:
        D Fornecedores           / C Banco             (valor - desconto)
        D Fornecedores           / C Descontos Obtidos (desconto)
        D Juros Pagos            / C Banco             (juros)
        D Multas Pagas           / C Banco             (multa)
    """
    estornar(db, "BAIXA", baixa.id)

    parcela = baixa.parcela
    lancamento = parcela.lancamento
    banco = db.get(Banco, baixa.banco_id)
    conta_banco = conta_do_banco(db, banco)
    empresa_id = baixa.empresa_id
    hist = baixa.historico or f"{lancamento.descricao} - parcela {parcela.numero}"
    item_principal = lancamento.itens[0] if lancamento.itens else None
    cc = item_principal.centro_custo_id if item_principal else None

    comum = dict(
        empresa_id=empresa_id,
        data=baixa.data,
        competencia=baixa.data,
        origem="BAIXA",
        origem_id=baixa.id,
        centro_custo_id=cc,
        operacao_id=lancamento.operacao_id,
        parceiro_id=lancamento.parceiro_id,
    )
    valor = dinheiro(baixa.valor)
    desconto = dinheiro(baixa.desconto)
    juros = dinheiro(baixa.juros)
    multa = dinheiro(baixa.multa)

    if lancamento.tipo == "RECEBER":
        clientes = _param(db, empresa_id, "conta_clientes")
        lancar(db, historico=hist, debito_id=conta_banco, credito_id=clientes,
               valor=valor - desconto, **comum)
        if desconto:
            lancar(db, historico=f"Desconto concedido - {hist}",
                   debito_id=_param(db, empresa_id, "conta_descontos_concedidos"),
                   credito_id=clientes, valor=desconto, **comum)
        if juros + multa:
            lancar(db, historico=f"Juros/multa recebidos - {hist}", debito_id=conta_banco,
                   credito_id=_param(db, empresa_id, "conta_juros_recebidos"),
                   valor=juros + multa, **comum)
    else:
        fornecedores = _param(db, empresa_id, "conta_fornecedores")
        lancar(db, historico=hist, debito_id=fornecedores, credito_id=conta_banco,
               valor=valor - desconto, **comum)
        if desconto:
            lancar(db, historico=f"Desconto obtido - {hist}", debito_id=fornecedores,
                   credito_id=_param(db, empresa_id, "conta_descontos_obtidos"),
                   valor=desconto, **comum)
        if juros:
            lancar(db, historico=f"Juros pagos - {hist}",
                   debito_id=_param(db, empresa_id, "conta_juros_pagos"),
                   credito_id=conta_banco, valor=juros, **comum)
        if multa:
            lancar(db, historico=f"Multa paga - {hist}",
                   debito_id=_param(db, empresa_id, "conta_multas_pagas"),
                   credito_id=conta_banco, valor=multa, **comum)


def contabilizar_movimento_caixa(db: Session, mov, conta_contrapartida_id: int | None = None):
    """Movimento avulso de caixa/banco ou transferência entre contas."""
    estornar(db, "CAIXA", mov.id)
    banco = db.get(Banco, mov.banco_id)
    conta_banco = conta_do_banco(db, banco)
    contra = conta_contrapartida_id or mov.conta_contabil_id
    if not contra:
        raise HTTPException(400, "Informe a conta contábil do movimento.")
    if mov.tipo == "E":
        debito, credito = conta_banco, contra
    else:
        debito, credito = contra, conta_banco
    lancar(
        db,
        empresa_id=mov.empresa_id,
        data=mov.data,
        competencia=mov.data,
        historico=mov.historico,
        debito_id=debito,
        credito_id=credito,
        valor=mov.valor,
        origem="CAIXA",
        origem_id=mov.id,
        centro_custo_id=mov.centro_custo_id,
        operacao_id=mov.operacao_id,
        parceiro_id=mov.parceiro_id,
    )


def contabilizar_saldo_inicial_banco(db: Session, banco: Banco):
    """D Conta do banco / C Saldos de Abertura."""
    estornar(db, "ABERTURA_BANCO", banco.id)
    if not banco.saldo_inicial:
        return
    conta_banco = conta_do_banco(db, banco)
    abertura = _param(db, banco.empresa_id, "conta_saldo_abertura")
    data = banco.data_saldo_inicial or date.today()
    valor = dinheiro(banco.saldo_inicial)
    if valor >= 0:
        debito, credito = conta_banco, abertura
    else:
        debito, credito = abertura, conta_banco
        valor = abs(valor)
    lancar(
        db,
        empresa_id=banco.empresa_id,
        data=data,
        competencia=data,
        historico=f"Saldo inicial - {banco.nome}",
        debito_id=debito,
        credito_id=credito,
        valor=valor,
        origem="ABERTURA_BANCO",
        origem_id=banco.id,
    )


def contabilizar_saldo_inicial_conta(db: Session, conta: ContaContabil):
    """Saldo de abertura informado direto numa conta contábil (exceto bancos,
    que usam o saldo inicial do próprio cadastro de banco)."""
    estornar(db, "ABERTURA_CONTA", conta.id)
    if not conta.saldo_inicial:
        return
    abertura = _param(db, conta.empresa_id, "conta_saldo_abertura")
    if abertura == conta.id:
        return
    data = date(date.today().year, 1, 1)
    valor = dinheiro(conta.saldo_inicial)
    devedora = conta.natureza == "D"
    if (valor >= 0 and devedora) or (valor < 0 and not devedora):
        debito, credito = conta.id, abertura
    else:
        debito, credito = abertura, conta.id
    lancar(
        db,
        empresa_id=conta.empresa_id,
        data=data,
        competencia=data,
        historico=f"Saldo de abertura - {conta.codigo} {conta.nome}",
        debito_id=debito,
        credito_id=credito,
        valor=abs(valor),
        origem="ABERTURA_CONTA",
        origem_id=conta.id,
    )
