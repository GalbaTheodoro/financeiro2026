"""Estrutura do DRE — ordem dos grupos e das linhas de totalização."""

# (chave, rótulo, sinal)  sinal: +1 soma, -1 subtrai
GRUPOS_DRE = [
    ("RECEITA_BRUTA", "Receita Operacional Bruta", 1),
    ("DEDUCOES", "(-) Deduções da Receita Bruta", -1),
    ("CUSTO", "(-) Custos", -1),
    ("DESPESA_PESSOAL", "(-) Despesas com Pessoal", -1),
    ("DESPESA_ADMINISTRATIVA", "(-) Despesas Administrativas", -1),
    ("DESPESA_COMERCIAL", "(-) Despesas Comerciais", -1),
    ("DESPESA_TRIBUTARIA", "(-) Despesas Tributárias", -1),
    ("RECEITA_FINANCEIRA", "(+) Receitas Financeiras", 1),
    ("DESPESA_FINANCEIRA", "(-) Despesas Financeiras", -1),
    ("OUTRAS_RECEITAS", "(+) Outras Receitas", 1),
    ("OUTRAS_DESPESAS", "(-) Outras Despesas", -1),
    ("IMPOSTO_RENDA", "(-) IRPJ e CSLL", -1),
]

# Linhas de subtotal: (rótulo, grupos acumulados até aqui)
SUBTOTAIS = [
    ("RECEITA LÍQUIDA", ["RECEITA_BRUTA", "DEDUCOES"]),
    ("LUCRO BRUTO", ["RECEITA_BRUTA", "DEDUCOES", "CUSTO"]),
    (
        "RESULTADO OPERACIONAL",
        [
            "RECEITA_BRUTA",
            "DEDUCOES",
            "CUSTO",
            "DESPESA_PESSOAL",
            "DESPESA_ADMINISTRATIVA",
            "DESPESA_COMERCIAL",
            "DESPESA_TRIBUTARIA",
        ],
    ),
    (
        "RESULTADO ANTES DO IRPJ/CSLL",
        [g for g, _, _ in GRUPOS_DRE if g != "IMPOSTO_RENDA"],
    ),
    ("RESULTADO LÍQUIDO DO PERÍODO", [g for g, _, _ in GRUPOS_DRE]),
]

SINAL = {chave: sinal for chave, _, sinal in GRUPOS_DRE}
ROTULO = {chave: rotulo for chave, rotulo, _ in GRUPOS_DRE}
