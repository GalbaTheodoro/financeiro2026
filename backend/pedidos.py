"""Orçamento e pedido de venda — as contas e as regras.

O que é
-------
O pedido é o documento que existe **antes** da nota: o carrinho montado na tela
de balcão, guardado com número, para reabrir, imprimir e finalizar depois.

A finalização não reimplementa nada. O pedido vira uma NF-e (55) ou um cupom
(65) pelos mesmos caminhos que já existiam no sistema, e as parcelas do "a
prazo" viram as **duplicatas** da nota — que é de onde o faturamento já tirava as
contas a receber. Ver ``routers/pedidos.py``.

As parcelas
-----------
Dividir dinheiro em partes iguais quase nunca dá exato: 100,00 em 3 vezes dá
33,333... O sistema arredonda cada parcela em centavos e **joga a sobra na
primeira**, não na última. É de propósito: o cliente prefere que a diferença de
centavos apareça na parcela que ele paga hoje, e quem confere o título vê a
soma bater com o total do pedido na primeira linha.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from .models import Pedido, PedidoItem
from .utils import adicionar_meses, dinheiro

TIPOS = {"ORCAMENTO": "Orçamento", "PEDIDO": "Pedido"}
SITUACOES = {"ABERTO": "Aberto", "FINALIZADO": "Finalizado", "CANCELADO": "Cancelado"}
CONDICOES = {"VISTA": "À vista", "PRAZO": "A prazo"}
DOCUMENTOS = {"NFE": "Nota fiscal (NF-e)", "CUPOM": "Cupom fiscal (NFC-e)"}
MAX_PARCELAS = 36


class ErroPedido(Exception):
    """Falha esperada — a frase já é a que vai para a tela."""


# --------------------------------------------------------------------------- #
# Numeração
# --------------------------------------------------------------------------- #
def proximo_numero(db: Session, empresa_id: int) -> str:
    """Sequência por empresa, com seis dígitos. Orçamento e pedido compartilham.

    Compartilhar é intencional: o orçamento 000012 aprovado vira o pedido 000012,
    e o cliente continua falando do mesmo número.
    """
    maior = (
        db.query(func.max(func.cast(Pedido.numero, Integer)))
        .filter(Pedido.empresa_id == empresa_id)
        .scalar()
    )
    return str(int(maior or 0) + 1).zfill(6)


# --------------------------------------------------------------------------- #
# Totais
# --------------------------------------------------------------------------- #
def total_do_item(quantidade: float, valor_unitario: float, desconto: float = 0) -> float:
    return dinheiro(max(float(quantidade or 0) * float(valor_unitario or 0)
                        - float(desconto or 0), 0))


def recalcular(pedido: Pedido) -> Pedido:
    """Refaz os totais a partir dos itens. É a única conta de valor do pedido."""
    produtos = 0.0
    for item in pedido.itens:
        item.valor_total = total_do_item(item.quantidade, item.valor_unitario, item.desconto)
        produtos += item.valor_total
    pedido.valor_produtos = dinheiro(produtos)
    desconto = min(float(pedido.desconto or 0), pedido.valor_produtos)
    pedido.desconto = dinheiro(desconto)
    pedido.valor_total = dinheiro(pedido.valor_produtos - pedido.desconto)
    return pedido


# --------------------------------------------------------------------------- #
# Parcelas
# --------------------------------------------------------------------------- #
def datas_das_parcelas(quantidade: int, primeiro: date, intervalo_dias: int = 30) -> list[date]:
    """Os vencimentos. Intervalo 30 anda de mês em mês, não de 30 em 30 dias.

    Quem vende a prazo fala em "30/60/90", e quem paga espera o mesmo dia do mês
    seguinte. Somar 30 dias faria a parcela de março cair no dia 2 de abril.
    """
    if intervalo_dias == 30:
        return [adicionar_meses(primeiro, mes) for mes in range(quantidade)]
    return [primeiro + timedelta(days=intervalo_dias * i) for i in range(quantidade)]


def dividir(total: float, quantidade: int) -> list[float]:
    """Divide em partes iguais e joga a sobra dos centavos na primeira parcela."""
    quantidade = max(1, int(quantidade or 1))
    total = dinheiro(total)
    parte = dinheiro(total / quantidade)
    valores = [parte] * quantidade
    valores[0] = dinheiro(total - parte * (quantidade - 1))
    return valores


def montar_parcelas(total: float, quantidade: int, primeiro: date,
                    intervalo_dias: int = 30) -> list[dict]:
    """[{numero, vencimento, valor}] — o que a tela mostra e o que vira duplicata."""
    quantidade = max(1, int(quantidade or 1))
    if quantidade > MAX_PARCELAS:
        raise ErroPedido(f"O máximo são {MAX_PARCELAS} parcelas.")
    if total <= 0:
        raise ErroPedido("Não dá para parcelar um pedido sem valor.")
    valores = dividir(total, quantidade)
    datas = datas_das_parcelas(quantidade, primeiro, intervalo_dias)
    return [
        {"numero": str(i + 1).zfill(3), "vencimento": datas[i], "valor": valores[i]}
        for i in range(quantidade)
    ]


# --------------------------------------------------------------------------- #
# Fechar a venda
# --------------------------------------------------------------------------- #
def concluir(db: Session, pedido: Pedido, nota, condicao: str, quantidade: int,
             primeiro: date, intervalo_dias: int, documento: str,
             forma_pagamento: str | None, usuario) -> str:
    """O que acontece **depois** que o documento fiscal saiu autorizado.

    Fica separado da emissão de propósito: emitir depende da SEFAZ e de
    certificado, e esta parte aqui — marcar o pedido e gerar as contas a receber
    — é dinheiro do cliente e precisa ser testável sozinha.

    À vista não gera título: o dinheiro já entrou. A prazo vira conta a receber
    pelas duplicatas que a nota já carrega, pelo mesmo `faturar` de sempre.
    """
    from .notas import faturar as faturar_nota
    from .schemas import FaturarNotaIn

    pedido.nota_id = nota.id
    pedido.condicao = condicao
    pedido.forma_pagamento = forma_pagamento
    pedido.parcelas = quantidade
    pedido.intervalo_dias = int(intervalo_dias or 30)
    pedido.primeiro_vencimento = primeiro if condicao == "PRAZO" else None
    pedido.documento = documento
    pedido.situacao = "FINALIZADO"
    pedido.finalizado_em = datetime.utcnow()

    mensagem = f"Pedido nº {pedido.numero} finalizado."
    if condicao == "PRAZO":
        lancamento = faturar_nota(db, nota, FaturarNotaIn(
            empresa_id=pedido.empresa_id, tipo_titulo="RECEBER",
            parceiro_id=pedido.parceiro_id,
            observacao=f"Pedido nº {pedido.numero}"), usuario)
        pedido.lancamento_id = lancamento.id
        mensagem += (f" Conta a receber gerada em {quantidade} parcela(s), "
                     f"a primeira em {primeiro.strftime('%d/%m/%Y')}.")
    else:
        mensagem += " À vista: nada foi lançado em contas a receber."
    db.flush()
    return mensagem


# --------------------------------------------------------------------------- #
# Serialização
# --------------------------------------------------------------------------- #
def item_dict(item: PedidoItem) -> dict:
    return {
        "id": item.id,
        "produto_id": item.produto_id,
        "descricao": item.descricao,
        "unidade": item.unidade or "",
        "quantidade": float(item.quantidade or 0),
        "valor_unitario": float(item.valor_unitario or 0),
        "desconto": float(item.desconto or 0),
        "valor_total": float(item.valor_total or 0),
    }


def ficha(db: Session, pedido: Pedido) -> dict:
    from .models import Lancamento, Nota

    nota = db.get(Nota, pedido.nota_id) if pedido.nota_id else None
    lancamento = db.get(Lancamento, pedido.lancamento_id) if pedido.lancamento_id else None
    return {
        "id": pedido.id,
        "numero": pedido.numero,
        "tipo": pedido.tipo,
        "tipo_rotulo": TIPOS.get(pedido.tipo, pedido.tipo),
        "situacao": pedido.situacao,
        "situacao_rotulo": SITUACOES.get(pedido.situacao, pedido.situacao),
        "data": pedido.data.isoformat() if pedido.data else None,
        "validade": pedido.validade.isoformat() if pedido.validade else None,
        "parceiro_id": pedido.parceiro_id,
        "parceiro_nome": pedido.parceiro.nome if pedido.parceiro else None,
        "cliente_nome": pedido.cliente_nome or "",
        "cliente_documento": pedido.cliente_documento or "",
        "observacao": pedido.observacao or "",
        "desconto": float(pedido.desconto or 0),
        "valor_produtos": float(pedido.valor_produtos or 0),
        "valor_total": float(pedido.valor_total or 0),
        "condicao": pedido.condicao,
        "condicao_rotulo": CONDICOES.get(pedido.condicao or "", ""),
        "forma_pagamento": pedido.forma_pagamento,
        "parcelas": int(pedido.parcelas or 1),
        "intervalo_dias": int(pedido.intervalo_dias or 30),
        "primeiro_vencimento": (pedido.primeiro_vencimento.isoformat()
                                if pedido.primeiro_vencimento else None),
        "documento": pedido.documento,
        "documento_rotulo": DOCUMENTOS.get(pedido.documento or "", ""),
        "nota_id": pedido.nota_id,
        "nota_numero": nota.numero if nota else None,
        "nota_situacao": nota.status_emissao if nota else None,
        "lancamento_id": pedido.lancamento_id,
        "lancamento_numero": lancamento.numero if lancamento else None,
        "itens": [item_dict(i) for i in pedido.itens],
        "finalizado_em": (pedido.finalizado_em.isoformat(timespec="seconds")
                          if pedido.finalizado_em else None),
        "criado_em": (pedido.criado_em.isoformat(timespec="seconds")
                      if pedido.criado_em else None),
    }


def resumo(pedido: Pedido) -> dict:
    """A linha da lista — mais enxuta que a ficha, sem os itens."""
    return {
        "id": pedido.id,
        "numero": pedido.numero,
        "tipo": pedido.tipo,
        "tipo_rotulo": TIPOS.get(pedido.tipo, pedido.tipo),
        "situacao": pedido.situacao,
        "situacao_rotulo": SITUACOES.get(pedido.situacao, pedido.situacao),
        "data": pedido.data.isoformat() if pedido.data else None,
        "validade": pedido.validade.isoformat() if pedido.validade else None,
        "cliente": (pedido.parceiro.nome if pedido.parceiro
                    else (pedido.cliente_nome or "Consumidor não identificado")),
        "itens": len(pedido.itens),
        "valor_total": float(pedido.valor_total or 0),
        "condicao_rotulo": CONDICOES.get(pedido.condicao or "", ""),
        "documento_rotulo": DOCUMENTOS.get(pedido.documento or "", ""),
        "parcelas": int(pedido.parcelas or 1),
        "nota_id": pedido.nota_id,
        "lancamento_id": pedido.lancamento_id,
    }
