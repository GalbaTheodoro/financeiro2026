"""Análise de vendas: o que vendeu, para quem, a que custo e com que margem.

O que este módulo responde
--------------------------
Perguntas de dono de negócio, não de contador: quanto vendi, quem são meus
melhores clientes, que produto sai mais, qual dá mais margem, quanto está
parado no estoque. O DRE e o balancete continuam em Relatórios — eles vêm dos
lançamentos e das partidas; **isto aqui vem das vendas e do estoque**, que é
outra fonte e outra pergunta.

De onde vêm as vendas
---------------------
De duas fontes, somadas sem contar nada em dobro:

* **documentos fiscais** — os itens das NF-e (modelo 55) e dos cupons (65) que a
  empresa emitiu e a SEFAZ autorizou. Cancelada não conta;
* **vendas sem documento** — os itens dos pedidos finalizados que ainda não têm
  nota (o "emitir depois"). Venda feita é venda feita, e deixar de fora
  esconderia faturamento de verdade.

O que impede a contagem em dobro é o vínculo: quando a nota daquele pedido sai,
o pedido passa a ter ``nota_id`` e **só a nota conta**. O pedido sem nota conta
sozinho.

De onde vem o custo
-------------------
Na ordem, e a ordem importa porque muda o número:

1. o **movimento de estoque** daquela venda — é o custo médio no momento em que
   a mercadoria saiu, que é o custo certo da operação e não muda depois;
2. o **custo de compra** do cadastro, quando o produto não controla estoque;
3. o **custo médio de hoje**, como último recurso.

Produto sem custo nenhum entra na venda mas **fica marcado**: sem isso a margem
apareceria inflada, o que é pior que aparecer incompleta. Os relatórios contam
quantos são e quanto de faturamento está sem custo.

Uma palavra sobre "lucro"
-------------------------
O que este módulo chama de lucro é a **margem bruta**: receita menos o custo da
mercadoria vendida. Não é o lucro da empresa — desse ainda saem despesa fixa,
salário, aluguel e imposto, e quem responde por ele é o DRE. Os títulos da tela
dizem "margem bruta" justamente para ninguém confundir os dois.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from .models import (
    CategoriaProduto,
    MarcaProduto,
    MovimentoEstoque,
    Nota,
    NotaItem,
    Parceiro,
    Pedido,
    PedidoItem,
    Produto,
)
from .utils import dinheiro

# Modelos de documento que são venda da empresa.
MODELOS_DE_VENDA = ("55", "65")

# De onde o custo saiu, para a tela poder dizer.
ORIGENS_DO_CUSTO = {
    "MOVIMENTO": "custo médio no momento da venda",
    "COMPRA": "custo de compra do cadastro",
    "MEDIO": "custo médio de hoje",
    "SEM": "sem custo conhecido",
}

# Padrão de "parado": dias sem sair do estoque. A tela deixa mudar.
DIAS_PARADO = 60


def _q(valor) -> float:
    return round(float(valor or 0) + 1e-9, 4)


# --------------------------------------------------------------------------- #
# As linhas de venda
# --------------------------------------------------------------------------- #
def _custos_por_item(db: Session, empresa_id: int, inicio: date, fim: date) -> dict:
    """O custo que o estoque registrou em cada item vendido no período.

    Duas chaves diferentes porque as duas origens são diferentes: a venda com
    documento prende o movimento ao item da nota, a venda de balcão que baixou
    pelo pedido prende ao item do pedido.
    """
    movimentos = (
        db.query(MovimentoEstoque)
        .filter(
            MovimentoEstoque.empresa_id == empresa_id,
            MovimentoEstoque.origem.in_(("SAIDA", "CUPOM", "PEDIDO")),
            MovimentoEstoque.data >= inicio,
            MovimentoEstoque.data <= fim,
        )
        .all()
    )
    por_nota: dict[int, float] = {}
    por_pedido: dict[int, float] = {}
    for m in movimentos:
        if m.nota_item_id:
            por_nota[m.nota_item_id] = dinheiro(por_nota.get(m.nota_item_id, 0)
                                                + float(m.custo_total or 0))
        elif m.pedido_item_id:
            por_pedido[m.pedido_item_id] = dinheiro(por_pedido.get(m.pedido_item_id, 0)
                                                    + float(m.custo_total or 0))
    return {"nota": por_nota, "pedido": por_pedido}


def _custo_do_produto(produto: Produto | None, quantidade: float) -> tuple[float, str]:
    """O custo quando o estoque não registrou nada — e de onde ele saiu."""
    if produto is None:
        return 0.0, "SEM"
    compra = float(produto.custo_compra or 0)
    if compra > 0:
        return dinheiro(compra * quantidade), "COMPRA"
    medio = float(produto.custo_medio or 0)
    if medio > 0:
        return dinheiro(medio * quantidade), "MEDIO"
    return 0.0, "SEM"


def linhas_de_venda(db: Session, empresa_id: int, inicio: date, fim: date) -> list[dict]:
    """Uma linha por item vendido no período, com receita, custo e margem."""
    custos = _custos_por_item(db, empresa_id, inicio, fim)
    produtos = {p.id: p for p in db.query(Produto)
                .options(joinedload(Produto.categoria), joinedload(Produto.marca))
                .filter(Produto.empresa_id == empresa_id).all()}
    parceiros = {p.id: p for p in db.query(Parceiro)
                 .filter(Parceiro.empresa_id == empresa_id).all()}

    linhas: list[dict] = []

    def acrescentar(*, dia, documento, tipo, parceiro_id, cliente, item_id,
                    produto_id, descricao, quantidade, unidade, receita, custo_pronto):
        produto = produtos.get(produto_id)
        quantidade = _q(quantidade)
        receita = dinheiro(receita)
        if custo_pronto is not None:
            custo, origem = dinheiro(custo_pronto), "MOVIMENTO"
        else:
            custo, origem = _custo_do_produto(produto, quantidade)
        categoria = produto.categoria.nome if produto and produto.categoria else "Sem categoria"
        marca = produto.marca.nome if produto and produto.marca else "Sem marca"
        parceiro = parceiros.get(parceiro_id)
        linhas.append({
            "data": dia.isoformat() if dia else "",
            "documento": documento,
            "tipo": tipo,
            "parceiro_id": parceiro_id,
            "cliente": (parceiro.nome if parceiro else None) or cliente or "Consumidor não identificado",
            "item_id": item_id,
            "produto_id": produto_id,
            "produto": (produto.nome if produto else None) or descricao or "-",
            "codigo": produto.codigo if produto else "",
            "categoria": categoria,
            "marca": marca,
            "quantidade": quantidade,
            "unidade": unidade or (produto.unidade_comercial if produto else "") or "",
            "receita": receita,
            "custo": custo,
            "origem_custo": origem,
            "margem": dinheiro(receita - custo),
        })

    # ---- 1. os documentos fiscais ----
    notas = (
        db.query(Nota)
        .options(joinedload(Nota.itens))
        .filter(
            Nota.empresa_id == empresa_id,
            Nota.origem == "EMITIDA",
            Nota.status_emissao == "AUTORIZADA",
            Nota.situacao != "CANCELADA",
        )
        .all()
    )
    for nota in notas:
        if (nota.modelo or "55") not in MODELOS_DE_VENDA:
            continue
        dia = nota.data_emissao.date() if nota.data_emissao else None
        if dia is None or not (inicio <= dia <= fim):
            continue
        rotulo = "Cupom" if (nota.modelo or "") == "65" else "NF-e"
        numero = f"{rotulo} {nota.numero or ''}".strip()
        for item in nota.itens:
            acrescentar(
                dia=dia, documento=numero, tipo=rotulo, parceiro_id=nota.parceiro_id,
                cliente=nota.destinatario_nome, item_id=item.id,
                produto_id=item.produto_id, descricao=item.descricao,
                quantidade=item.quantidade, unidade=item.unidade,
                receita=item.valor_total,
                custo_pronto=custos["nota"].get(item.id),
            )

    # ---- 2. as vendas que ainda não viraram documento ----
    pedidos = (
        db.query(Pedido)
        .options(joinedload(Pedido.itens))
        .filter(
            Pedido.empresa_id == empresa_id,
            Pedido.situacao == "FINALIZADO",
            Pedido.nota_id.is_(None),          # com nota, quem conta é a nota
        )
        .all()
    )
    for pedido in pedidos:
        dia = pedido.data
        if dia is None or not (inicio <= dia <= fim):
            continue
        # o desconto do pedido é do total: rateia entre os itens, senão a
        # receita do relatório não bate com o que o cliente pagou
        produtos_valor = sum(float(i.valor_total or 0) for i in pedido.itens) or 1.0
        desconto = float(pedido.desconto or 0)
        sobra = dinheiro(desconto)
        for posicao, item in enumerate(pedido.itens):
            parte = (dinheiro(float(item.valor_total or 0) / produtos_valor * desconto)
                     if posicao < len(pedido.itens) - 1 else sobra)
            sobra = dinheiro(sobra - parte)
            acrescentar(
                dia=dia, documento=f"Pedido {pedido.numero}", tipo="Sem documento",
                parceiro_id=pedido.parceiro_id, cliente=pedido.cliente_nome,
                item_id=item.id, produto_id=item.produto_id, descricao=item.descricao,
                quantidade=item.quantidade, unidade=item.unidade,
                receita=dinheiro(float(item.valor_total or 0) - parte),
                custo_pronto=custos["pedido"].get(item.id),
            )

    linhas.sort(key=lambda l: (l["data"], l["documento"]))
    return linhas


# --------------------------------------------------------------------------- #
# Agrupamentos
# --------------------------------------------------------------------------- #
def _vazio() -> dict:
    return {"receita": 0.0, "custo": 0.0, "margem": 0.0, "quantidade": 0.0,
            "itens": 0, "documentos": set(), "sem_custo": 0}


def _fechar(grupo: dict, extras: dict) -> dict:
    receita = grupo["receita"]
    return {
        **extras,
        "receita": receita,
        "custo": grupo["custo"],
        "margem": grupo["margem"],
        "margem_percentual": round(grupo["margem"] / receita * 100, 2) if receita else 0.0,
        "quantidade": _q(grupo["quantidade"]),
        "itens": grupo["itens"],
        "documentos": len(grupo["documentos"]),
        "sem_custo": grupo["sem_custo"],
        "ticket_medio": dinheiro(receita / len(grupo["documentos"])) if grupo["documentos"] else 0.0,
    }


def _somar(grupo: dict, linha: dict) -> None:
    grupo["receita"] = dinheiro(grupo["receita"] + linha["receita"])
    grupo["custo"] = dinheiro(grupo["custo"] + linha["custo"])
    grupo["margem"] = dinheiro(grupo["margem"] + linha["margem"])
    grupo["quantidade"] = _q(grupo["quantidade"] + linha["quantidade"])
    grupo["itens"] += 1
    grupo["documentos"].add(linha["documento"])
    if linha["origem_custo"] == "SEM":
        grupo["sem_custo"] += 1


def agrupar(linhas: list[dict], chave: str, rotulos: tuple[str, ...] = ()) -> list[dict]:
    """Soma as linhas por um campo, devolvendo a lista ordenada por receita."""
    grupos: dict = defaultdict(_vazio)
    extras: dict = {}
    for linha in linhas:
        valor = linha[chave]
        _somar(grupos[valor], linha)
        if valor not in extras:
            extras[valor] = {chave: valor, **{r: linha.get(r) for r in rotulos}}
    saida = [_fechar(g, extras[valor]) for valor, g in grupos.items()]
    saida.sort(key=lambda x: x["receita"], reverse=True)
    return saida


def totais(linhas: list[dict]) -> dict:
    grupo = _vazio()
    for linha in linhas:
        _somar(grupo, linha)
    fechado = _fechar(grupo, {})
    fechado["receita_sem_custo"] = dinheiro(
        sum(l["receita"] for l in linhas if l["origem_custo"] == "SEM"))
    return fechado


def evolucao(linhas: list[dict], inicio: date, fim: date) -> list[dict]:
    """Faturamento e margem por dia ou por mês, conforme o tamanho do período.

    Até uns dois meses a leitura por dia funciona; mais que isso viram tantas
    colunas que o gráfico não diz mais nada, e a conta passa a ser mensal.
    """
    por_mes = (fim - inicio).days > 62
    grupos: dict = defaultdict(_vazio)
    for linha in linhas:
        if not linha["data"]:
            continue
        chave = linha["data"][:7] if por_mes else linha["data"]
        _somar(grupos[chave], linha)

    MESES = ("jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez")
    saida = []
    for chave in sorted(grupos):
        if por_mes:
            ano, mes = chave.split("-")
            rotulo = f"{MESES[int(mes) - 1]}/{ano[2:]}"
        else:
            rotulo = f"{chave[8:10]}/{chave[5:7]}"
        g = grupos[chave]
        saida.append({"periodo": rotulo, "chave": chave,
                      "receita": g["receita"], "margem": g["margem"],
                      "custo": g["custo"], "documentos": len(g["documentos"])})
    return saida


# --------------------------------------------------------------------------- #
# Estoque parado
# --------------------------------------------------------------------------- #
def parados(db: Session, empresa_id: int, dias: int = DIAS_PARADO) -> dict:
    """Produtos com saldo que não saem há mais de N dias — e quanto está parado.

    Só entram produtos que controlam estoque e têm saldo: produto zerado não
    está parado, está acabado.
    """
    hoje = date.today()
    limite = hoje - timedelta(days=max(int(dias or 0), 0))

    saidas = (
        db.query(MovimentoEstoque.produto_id,
                 MovimentoEstoque.data)
        .filter(MovimentoEstoque.empresa_id == empresa_id,
                MovimentoEstoque.tipo == "S",
                MovimentoEstoque.origem != "ESTORNO")
        .all()
    )
    ultima: dict[int, date] = {}
    for produto_id, dia in saidas:
        if dia and (produto_id not in ultima or dia > ultima[produto_id]):
            ultima[produto_id] = dia

    linhas = []
    for produto in (db.query(Produto)
                    .options(joinedload(Produto.categoria), joinedload(Produto.marca))
                    .filter(Produto.empresa_id == empresa_id,
                            Produto.controla_estoque.is_(True))
                    .order_by(Produto.codigo).all()):
        saldo = _q(produto.estoque_atual)
        if saldo <= 0:
            continue
        saiu_em = ultima.get(produto.id)
        if saiu_em and saiu_em > limite:
            continue                          # ainda tem giro
        valor = dinheiro(saldo * float(produto.custo_medio or 0))
        linhas.append({
            "produto_id": produto.id,
            "codigo": produto.codigo,
            "produto": produto.nome,
            "categoria": produto.categoria.nome if produto.categoria else "Sem categoria",
            "marca": produto.marca.nome if produto.marca else "Sem marca",
            "saldo": saldo,
            "unidade": produto.estoque_unidade or produto.unidade_comercial or "",
            "custo_medio": round(float(produto.custo_medio or 0), 6),
            "valor": valor,
            "ultima_saida": saiu_em.isoformat() if saiu_em else None,
            "dias_parado": (hoje - saiu_em).days if saiu_em else None,
        })

    linhas.sort(key=lambda l: l["valor"], reverse=True)
    return {
        "dias": int(dias or 0),
        "linhas": linhas,
        "valor_total": dinheiro(sum(l["valor"] for l in linhas)),
        "produtos": len(linhas),
        "nunca_vendidos": sum(1 for l in linhas if l["ultima_saida"] is None),
    }
