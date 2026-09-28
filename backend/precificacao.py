"""Formação do preço de venda: o markup e de onde ele sai.

O problema
----------
Quase todo mundo forma preço errado do mesmo jeito: pega o custo e soma a
margem que quer ganhar. Se o custo é 1.000 e a pessoa quer 20% de lucro, põe
1.200 — e no fim do mês descobre que não ganhou 20%, ganhou muito menos, porque
imposto, comissão e taxa de cartão saem **do preço de venda**, não do custo.

A conta certa é a do **markup divisor**. Tudo que é percentual sobre a venda —
imposto, comissão, cartão, frete, despesa fixa e o próprio lucro desejado —
entra num bolo só, e o preço é o custo dividido pelo que sobra::

    soma   = impostos + comissão + cartão + frete + despesas + lucro   (em %)
    markup = 1 / (1 - soma/100)
    preço  = custo x markup

No exemplo acima, com 20% de lucro, 10% de imposto e 5% de comissão, a soma é
35%: o markup é 1/(1-0,35) = 1,5385, e o preço é 1.538,46 — não 1.200. Vendendo
a 1.200 o lucro real seria negativo.

A vantagem dessa conta é que ela **fecha**: multiplicando cada percentual pelo
preço, cada real vai para um lugar, e o que sobra é exatamente o custo. É isso
que a tela mostra em "para onde vai cada real do preço".

O que entra e o que não entra
-----------------------------
**Entram no divisor** (saem de dentro do preço): ICMS, PIS e COFINS — ou, na
empresa do Simples Nacional, a alíquota única do DAS no lugar dos três —, mais
comissão, taxa de cartão, frete e despesa fixa, mais o lucro desejado.

**Não entra o IPI**, e não é esquecimento: o IPI é "por fora", somado ao preço e
cobrado do cliente. Ele não come a margem. Por isso o sistema mostra os dois
números — o preço e o preço com IPI —, em vez de misturar.

O custo
-------
Base do custo, nesta ordem: o **custo de compra** do cadastro (o custo de
reposição, o que custa comprar hoje) quando estiver preenchido; senão o **custo
médio** que o controle de estoque mantém. Somam-se a ele os **outros custos por
unidade** (embalagem, por exemplo), que são valor em reais e não percentual.

Um aviso honesto: o custo médio é o valor da nota de entrada. Empresa de regime
normal que se credita do ICMS da compra tem custo real menor que esse — quem
está nessa situação informa o custo líquido no campo Custo de compra.

Os dois caminhos
----------------
A tela vai nas duas direções, e o módulo também:

1. **dos percentuais para o preço** — preenche os percentuais e recebe o markup
   e o preço sugerido;
2. **do markup para o preço** — digita o markup direto (ou o preço que já
   pratica) e recebe o preço e, principalmente, **quanto de lucro sobra de
   verdade** depois de tudo. É a conta que mostra que um preço está no prejuízo.

Nada aqui grava preço sozinho: preço é decisão, não resultado de fórmula. O
sistema calcula, mostra a conta aberta e espera o "usar este preço".
"""
from __future__ import annotations

from .models import Empresa, Produto
from .utils import dinheiro

# Percentuais que saem de dentro do preço de venda — os que formam o divisor.
# A ordem é a que a tela mostra, de fora para dentro do negócio.
PERCENTUAIS: tuple[tuple[str, str], ...] = (
    ("perc_simples", "Simples Nacional (DAS)"),
    ("perc_icms", "ICMS"),
    ("perc_pis", "PIS"),
    ("perc_cofins", "COFINS"),
    ("perc_comissao", "Comissão"),
    ("perc_cartao", "Taxa de cartão"),
    ("perc_frete", "Frete"),
    ("perc_despesas", "Despesa fixa"),
    ("perc_lucro", "Lucro desejado"),
)

# Os que o usuário digita no cadastro do produto (os de imposto saem do próprio
# cadastro fiscal, ou da alíquota do Simples).
CAMPOS_DO_PRODUTO: tuple[str, ...] = (
    "markup", "custo_compra", "outros_custos",
    "perc_despesas", "perc_comissao", "perc_cartao", "perc_frete",
    "perc_lucro", "perc_simples",
)

# Simples Nacional: CRT 1 (Simples) e 4 (MEI).
CRT_DO_SIMPLES = ("1", "4")

# Acima disto a conta não existe: não há preço que pague 100% de percentuais.
LIMITE_SOMA = 99.99


def _p(valor) -> float:
    """Percentual: nunca negativo, arredondado em 4 casas."""
    return round(max(float(valor or 0), 0.0) + 1e-9, 4)


def _r(valor) -> float:
    return dinheiro(valor)


def empresa_do_simples(empresa: Empresa | None) -> bool:
    return bool(empresa) and (empresa.crt or "1") in CRT_DO_SIMPLES


def estado_do_produto(produto: Produto, empresa: Empresa | None) -> dict:
    """Os números com que a tela abre: o que está gravado no produto.

    Os impostos vêm do cadastro fiscal do produto; na empresa do Simples eles
    não valem, e quem entra é a alíquota do DAS.
    """
    simples = empresa_do_simples(empresa)
    return {
        "produto_id": produto.id,
        "nome": produto.nome,
        "codigo": produto.codigo,
        "simples": simples,
        "crt": (empresa.crt if empresa else "1") or "1",
        "custo_medio": _r(produto.custo_medio),
        "custo_compra": _r(produto.custo_compra),
        "outros_custos": _r(produto.outros_custos),
        "preco_atual": _r(produto.preco_venda),
        "markup": _p(produto.markup),
        # impostos: os do cadastro fiscal, zerados quando a empresa é do Simples
        "perc_icms": 0.0 if simples else _p(produto.aliquota_icms),
        "perc_pis": 0.0 if simples else _p(produto.aliquota_pis),
        "perc_cofins": 0.0 if simples else _p(produto.aliquota_cofins),
        "perc_ipi": _p(produto.aliquota_ipi),
        "perc_simples": _p(produto.perc_simples) if simples else 0.0,
        "perc_despesas": _p(produto.perc_despesas),
        "perc_comissao": _p(produto.perc_comissao),
        "perc_cartao": _p(produto.perc_cartao),
        "perc_frete": _p(produto.perc_frete),
        "perc_lucro": _p(produto.perc_lucro),
    }


def custo_da_base(entrada: dict) -> dict:
    """Qual custo a conta usa, e por quê — a tela mostra os dois números."""
    compra = _r(entrada.get("custo_compra"))
    medio = _r(entrada.get("custo_medio"))
    outros = _r(entrada.get("outros_custos"))
    if compra > 0:
        base, origem = compra, "custo de compra (reposição)"
    else:
        base, origem = medio, "custo médio do estoque"
    return {
        "custo_compra": compra,
        "custo_medio": medio,
        "outros_custos": outros,
        "base": base,
        "origem": origem,
        "custo_total": _r(base + outros),
    }


def calcular(entrada: dict) -> dict:
    """A conta inteira, com a composição aberta e os avisos.

    ``entrada`` aceita os percentuais, o custo e, opcionalmente:

    * ``markup`` — quando vem preenchido, manda: o preço passa a ser
      custo x markup, e o lucro vira o que **sobra** depois de tudo (pode dar
      negativo, e é justamente isso que precisa aparecer);
    * ``preco_atual`` — o preço praticado hoje, para a tela comparar.

    Nunca levanta erro: uma conta impossível volta como aviso, porque quem está
    formando preço precisa ver o que digitou, não uma tela vermelha.
    """
    custo = custo_da_base(entrada)
    custo_total = custo["custo_total"]
    ipi = _p(entrada.get("perc_ipi"))

    percentuais = [
        {"campo": campo, "rotulo": rotulo, "valor": _p(entrada.get(campo))}
        for campo, rotulo in PERCENTUAIS
    ]
    soma = round(sum(p["valor"] for p in percentuais) + 1e-9, 4)
    avisos: list[str] = []

    # --- markup digitado à mão manda na conta ------------------------------
    markup_digitado = _p(entrada.get("markup"))
    usar_digitado = markup_digitado > 0

    if soma > LIMITE_SOMA and not usar_digitado:
        avisos.append(
            f"Os percentuais somam {_texto(soma)}% do preço de venda. Não existe preço "
            "que pague isso e ainda cubra o custo — reduza o lucro desejado ou as "
            "despesas.")
        markup = 0.0
        preco = 0.0
    elif usar_digitado:
        markup = markup_digitado
        preco = _r(custo_total * markup)
    else:
        markup = round(1 / (1 - soma / 100), 4)
        preco = _r(custo_total * markup)

    if custo_total <= 0:
        avisos.append(
            "O custo está zerado. Informe o custo de compra, ou lance a entrada da "
            "mercadoria para o estoque calcular o custo médio — sem custo não há preço "
            "a formar.")

    # --- para onde vai cada real do preço ---------------------------------
    composicao = []
    total_percentuais = 0.0
    for p in percentuais:
        if p["campo"] == "perc_lucro":
            continue                      # o lucro entra no fim, como resíduo
        valor = _r(preco * p["valor"] / 100)
        total_percentuais = _r(total_percentuais + valor)
        if p["valor"]:
            composicao.append({"rotulo": p["rotulo"], "percentual": p["valor"],
                               "valor": valor})

    lucro_valor = _r(preco - custo_total - total_percentuais)
    lucro_percentual = round(lucro_valor / preco * 100, 2) if preco else 0.0

    composicao.insert(0, {"rotulo": "Custo da mercadoria", "valor": custo_total,
                          "percentual": round(custo_total / preco * 100, 2) if preco else 0.0})
    composicao.append({"rotulo": "Lucro", "valor": lucro_valor,
                       "percentual": lucro_percentual})

    if usar_digitado and lucro_valor < 0:
        avisos.append(
            f"Com este markup o preço fica {_moeda(preco)} e a venda dá prejuízo de "
            f"{_moeda(-lucro_valor)} por unidade: os percentuais e o custo já passam do "
            "preço. Suba o markup ou reveja os custos.")

    # --- o preço que já é praticado ---------------------------------------
    atual = None
    preco_atual = _r(entrada.get("preco_atual"))
    if preco_atual > 0:
        gasto = _r(sum(preco_atual * p["valor"] / 100
                       for p in percentuais if p["campo"] != "perc_lucro"))
        sobra = _r(preco_atual - custo_total - gasto)
        atual = {
            "preco": preco_atual,
            "markup": round(preco_atual / custo_total, 4) if custo_total else 0.0,
            "lucro_valor": sobra,
            "lucro_percentual": round(sobra / preco_atual * 100, 2),
            "diferenca": _r(preco - preco_atual) if preco else 0.0,
        }
        if sobra < 0:
            avisos.append(
                f"O preço praticado hoje ({_moeda(preco_atual)}) dá prejuízo de "
                f"{_moeda(-sobra)} por unidade depois de custo, impostos e despesas.")
        elif preco and preco_atual < preco:
            avisos.append(
                f"O preço praticado ({_moeda(preco_atual)}) está {_moeda(preco - preco_atual)} "
                f"abaixo do sugerido ({_moeda(preco)}) — dá lucro, mas menos que o desejado.")

    return {
        "custo": custo,
        "percentuais": percentuais,
        "soma": soma,
        "markup": markup,
        "markup_digitado": usar_digitado,
        "preco": preco,
        "perc_ipi": ipi,
        # o IPI é por fora: soma ao preço e é cobrado do cliente, não come margem
        "preco_com_ipi": _r(preco * (1 + ipi / 100)) if ipi else preco,
        "composicao": composicao,
        "lucro_valor": lucro_valor,
        "lucro_percentual": lucro_percentual,
        "atual": atual,
        "avisos": avisos,
    }


def _texto(valor: float) -> str:
    """Percentual sem casas inúteis: 35 em vez de 35,0000."""
    if abs(valor - round(valor)) < 0.0001:
        return str(int(round(valor)))
    return f"{valor:.2f}".replace(".", ",")


def _moeda(valor: float) -> str:
    return f"R$ {float(valor or 0):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
