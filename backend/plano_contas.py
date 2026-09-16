"""Plano de contas padrão brasileiro e parâmetros contábeis da empresa."""
from sqlalchemy.orm import Session

from .models import CentroCusto, ContaContabil, Operacao, Parametro

# (codigo, nome, tipo, natureza, analitica, grupo_dre)
A, S = True, False
PLANO_PADRAO = [
    # ---------------------------------------------------------------- ATIVO
    ("1", "ATIVO", "ATIVO", "D", S, None),
    ("1.1", "ATIVO CIRCULANTE", "ATIVO", "D", S, None),
    ("1.1.01", "DISPONIVEL", "ATIVO", "D", S, None),
    ("1.1.01.001", "Caixa Geral", "ATIVO", "D", A, None),
    ("1.1.01.002", "Bancos Conta Movimento", "ATIVO", "D", A, None),
    ("1.1.01.003", "Aplicacoes Financeiras", "ATIVO", "D", A, None),
    ("1.1.02", "CREDITOS", "ATIVO", "D", S, None),
    ("1.1.02.001", "Clientes a Receber", "ATIVO", "D", A, None),
    ("1.1.02.002", "Adiantamentos a Fornecedores", "ATIVO", "D", A, None),
    ("1.1.02.003", "Impostos a Recuperar", "ATIVO", "D", A, None),
    ("1.1.02.004", "Outros Creditos", "ATIVO", "D", A, None),
    ("1.1.03", "ESTOQUES", "ATIVO", "D", S, None),
    ("1.1.03.001", "Mercadorias para Revenda", "ATIVO", "D", A, None),
    ("1.1.03.002", "Materia Prima e Insumos", "ATIVO", "D", A, None),
    ("1.2", "ATIVO NAO CIRCULANTE", "ATIVO", "D", S, None),
    ("1.2.01", "IMOBILIZADO", "ATIVO", "D", S, None),
    ("1.2.01.001", "Moveis e Utensilios", "ATIVO", "D", A, None),
    ("1.2.01.002", "Maquinas e Equipamentos", "ATIVO", "D", A, None),
    ("1.2.01.003", "Veiculos", "ATIVO", "D", A, None),
    ("1.2.01.004", "Computadores e Perifericos", "ATIVO", "D", A, None),
    ("1.2.02", "DEPRECIACAO ACUMULADA", "ATIVO", "C", S, None),
    ("1.2.02.001", "(-) Depreciacao Acumulada", "ATIVO", "C", A, None),
    # -------------------------------------------------------------- PASSIVO
    ("2", "PASSIVO", "PASSIVO", "C", S, None),
    ("2.1", "PASSIVO CIRCULANTE", "PASSIVO", "C", S, None),
    ("2.1.01", "FORNECEDORES", "PASSIVO", "C", S, None),
    ("2.1.01.001", "Fornecedores a Pagar", "PASSIVO", "C", A, None),
    ("2.1.02", "OBRIGACOES TRABALHISTAS", "PASSIVO", "C", S, None),
    ("2.1.02.001", "Salarios a Pagar", "PASSIVO", "C", A, None),
    ("2.1.02.002", "INSS a Recolher", "PASSIVO", "C", A, None),
    ("2.1.02.003", "FGTS a Recolher", "PASSIVO", "C", A, None),
    ("2.1.02.004", "Provisao de Ferias e 13o Salario", "PASSIVO", "C", A, None),
    ("2.1.03", "OBRIGACOES TRIBUTARIAS", "PASSIVO", "C", S, None),
    ("2.1.03.001", "Simples Nacional a Recolher", "PASSIVO", "C", A, None),
    ("2.1.03.002", "ICMS a Recolher", "PASSIVO", "C", A, None),
    ("2.1.03.003", "ISS a Recolher", "PASSIVO", "C", A, None),
    ("2.1.03.004", "IRPJ e CSLL a Recolher", "PASSIVO", "C", A, None),
    ("2.1.04", "EMPRESTIMOS E FINANCIAMENTOS", "PASSIVO", "C", S, None),
    ("2.1.04.001", "Emprestimos Bancarios", "PASSIVO", "C", A, None),
    ("2.1.04.002", "Financiamentos", "PASSIVO", "C", A, None),
    ("2.1.05", "OUTRAS OBRIGACOES", "PASSIVO", "C", S, None),
    ("2.1.05.001", "Contas a Pagar Diversas", "PASSIVO", "C", A, None),
    ("2.1.05.002", "Adiantamento de Clientes", "PASSIVO", "C", A, None),
    ("2.3", "PATRIMONIO LIQUIDO", "PATRIMONIO_LIQUIDO", "C", S, None),
    ("2.3.01", "CAPITAL", "PATRIMONIO_LIQUIDO", "C", S, None),
    ("2.3.01.001", "Capital Social Integralizado", "PATRIMONIO_LIQUIDO", "C", A, None),
    ("2.3.01.002", "Saldos de Abertura", "PATRIMONIO_LIQUIDO", "C", A, None),
    ("2.3.02", "RESULTADOS ACUMULADOS", "PATRIMONIO_LIQUIDO", "C", S, None),
    ("2.3.02.001", "Lucros ou Prejuizos Acumulados", "PATRIMONIO_LIQUIDO", "C", A, None),
    # ------------------------------------------------------------- RECEITAS
    ("3", "RECEITAS", "RECEITA", "C", S, None),
    ("3.1", "RECEITA OPERACIONAL BRUTA", "RECEITA", "C", S, None),
    ("3.1.01.001", "Receita de Venda de Mercadorias", "RECEITA", "C", A, "RECEITA_BRUTA"),
    ("3.1.01.002", "Receita de Prestacao de Servicos", "RECEITA", "C", A, "RECEITA_BRUTA"),
    ("3.1.01.003", "Receita de Assessoria e Consultoria", "RECEITA", "C", A, "RECEITA_BRUTA"),
    ("3.1.01.004", "Receita de Corretagem e Comissoes", "RECEITA", "C", A, "RECEITA_BRUTA"),
    ("3.2", "DEDUCOES DA RECEITA BRUTA", "RECEITA", "D", S, None),
    ("3.2.01.001", "(-) Simples Nacional sobre Vendas", "RECEITA", "D", A, "DEDUCOES"),
    ("3.2.01.002", "(-) ICMS sobre Vendas", "RECEITA", "D", A, "DEDUCOES"),
    ("3.2.01.003", "(-) ISS sobre Servicos", "RECEITA", "D", A, "DEDUCOES"),
    ("3.2.01.004", "(-) PIS e COFINS sobre Faturamento", "RECEITA", "D", A, "DEDUCOES"),
    ("3.2.01.005", "(-) Devolucoes e Cancelamentos", "RECEITA", "D", A, "DEDUCOES"),
    ("3.3", "RECEITAS FINANCEIRAS", "RECEITA", "C", S, None),
    ("3.3.01.001", "Juros Recebidos", "RECEITA", "C", A, "RECEITA_FINANCEIRA"),
    ("3.3.01.002", "Rendimentos de Aplicacoes", "RECEITA", "C", A, "RECEITA_FINANCEIRA"),
    ("3.3.01.003", "Descontos Obtidos", "RECEITA", "C", A, "RECEITA_FINANCEIRA"),
    ("3.4", "OUTRAS RECEITAS", "RECEITA", "C", S, None),
    ("3.4.01.001", "Outras Receitas Operacionais", "RECEITA", "C", A, "OUTRAS_RECEITAS"),
    ("3.4.01.002", "Receitas Nao Operacionais", "RECEITA", "C", A, "OUTRAS_RECEITAS"),
    # ----------------------------------------------------- CUSTOS E DESPESAS
    ("4", "CUSTOS E DESPESAS", "DESPESA", "D", S, None),
    ("4.1", "CUSTOS", "CUSTO", "D", S, None),
    ("4.1.01.001", "Custo das Mercadorias Vendidas", "CUSTO", "D", A, "CUSTO"),
    ("4.1.01.002", "Custo dos Servicos Prestados", "CUSTO", "D", A, "CUSTO"),
    ("4.1.01.003", "Materia Prima Aplicada", "CUSTO", "D", A, "CUSTO"),
    ("4.1.01.004", "Mao de Obra Direta", "CUSTO", "D", A, "CUSTO"),
    ("4.2", "DESPESAS COM PESSOAL", "DESPESA", "D", S, None),
    ("4.2.01.001", "Salarios e Ordenados", "DESPESA", "D", A, "DESPESA_PESSOAL"),
    ("4.2.01.002", "Pro-Labore", "DESPESA", "D", A, "DESPESA_PESSOAL"),
    ("4.2.01.003", "Encargos Sociais (INSS/FGTS)", "DESPESA", "D", A, "DESPESA_PESSOAL"),
    ("4.2.01.004", "Ferias e 13o Salario", "DESPESA", "D", A, "DESPESA_PESSOAL"),
    ("4.2.01.005", "Vale Transporte e Alimentacao", "DESPESA", "D", A, "DESPESA_PESSOAL"),
    ("4.2.01.006", "Rescisoes Trabalhistas", "DESPESA", "D", A, "DESPESA_PESSOAL"),
    ("4.3", "DESPESAS ADMINISTRATIVAS", "DESPESA", "D", S, None),
    ("4.3.01.001", "Aluguel e Condominio", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.002", "Energia Eletrica", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.003", "Agua e Esgoto", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.004", "Telefone e Internet", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.005", "Material de Escritorio", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.006", "Honorarios Contabeis", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.007", "Honorarios Advocaticios e Consultorias", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.008", "Softwares e Assinaturas", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.009", "Manutencao e Conservacao", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.010", "Seguros", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.011", "Combustivel e Transporte", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.3.01.012", "Despesas Administrativas Diversas", "DESPESA", "D", A, "DESPESA_ADMINISTRATIVA"),
    ("4.4", "DESPESAS COMERCIAIS", "DESPESA", "D", S, None),
    ("4.4.01.001", "Comissoes sobre Vendas", "DESPESA", "D", A, "DESPESA_COMERCIAL"),
    ("4.4.01.002", "Publicidade e Marketing", "DESPESA", "D", A, "DESPESA_COMERCIAL"),
    ("4.4.01.003", "Fretes e Entregas", "DESPESA", "D", A, "DESPESA_COMERCIAL"),
    ("4.4.01.004", "Viagens e Representacoes", "DESPESA", "D", A, "DESPESA_COMERCIAL"),
    ("4.5", "DESPESAS FINANCEIRAS", "DESPESA", "D", S, None),
    ("4.5.01.001", "Juros Pagos", "DESPESA", "D", A, "DESPESA_FINANCEIRA"),
    ("4.5.01.002", "Multas e Encargos", "DESPESA", "D", A, "DESPESA_FINANCEIRA"),
    ("4.5.01.003", "Tarifas Bancarias", "DESPESA", "D", A, "DESPESA_FINANCEIRA"),
    ("4.5.01.004", "Descontos Concedidos", "DESPESA", "D", A, "DESPESA_FINANCEIRA"),
    ("4.5.01.005", "IOF e Despesas Bancarias", "DESPESA", "D", A, "DESPESA_FINANCEIRA"),
    ("4.6", "DESPESAS TRIBUTARIAS", "DESPESA", "D", S, None),
    ("4.6.01.001", "IPTU, IPVA e Taxas", "DESPESA", "D", A, "DESPESA_TRIBUTARIA"),
    ("4.6.01.002", "Contribuicoes e Anuidades", "DESPESA", "D", A, "DESPESA_TRIBUTARIA"),
    ("4.7", "IMPOSTOS SOBRE O LUCRO", "DESPESA", "D", S, None),
    ("4.7.01.001", "IRPJ", "DESPESA", "D", A, "IMPOSTO_RENDA"),
    ("4.7.01.002", "CSLL", "DESPESA", "D", A, "IMPOSTO_RENDA"),
    ("4.8", "OUTRAS DESPESAS", "DESPESA", "D", S, None),
    ("4.8.01.001", "Depreciacao e Amortizacao", "DESPESA", "D", A, "OUTRAS_DESPESAS"),
    ("4.8.01.002", "Despesas Nao Operacionais", "DESPESA", "D", A, "OUTRAS_DESPESAS"),
]

PARAMETROS_PADRAO = {
    "conta_clientes": "1.1.02.001",
    "conta_comissao": "3.1.01.004",
    "conta_fornecedores": "2.1.01.001",
    "conta_caixa_padrao": "1.1.01.001",
    "conta_banco_padrao": "1.1.01.002",
    "conta_juros_recebidos": "3.3.01.001",
    "conta_descontos_obtidos": "3.3.01.003",
    "conta_juros_pagos": "4.5.01.001",
    "conta_multas_pagas": "4.5.01.002",
    "conta_descontos_concedidos": "4.5.01.004",
    "conta_saldo_abertura": "2.3.01.002",
    "conta_resultado_acumulado": "2.3.02.001",
}

CENTROS_CUSTO_PADRAO = [
    ("001", "Administrativo", "ADMINISTRATIVO"),
    ("002", "Comercial / Vendas", "COMERCIAL"),
    ("003", "Operacional", "OPERACIONAL"),
    ("004", "Financeiro", "ADMINISTRATIVO"),
    ("005", "Diretoria", "ADMINISTRATIVO"),
]

# (codigo, nome, natureza, codigo_conta_contabil)
OPERACOES_PADRAO = [
    ("001", "Venda de Mercadorias", "ENTRADA", "3.1.01.001"),
    ("002", "Prestacao de Servicos", "ENTRADA", "3.1.01.002"),
    ("003", "Honorarios de Assessoria", "ENTRADA", "3.1.01.003"),
    ("004", "Recebimento de Juros", "ENTRADA", "3.3.01.001"),
    ("005", "Outras Receitas", "ENTRADA", "3.4.01.001"),
    ("006", "Corretagem / Comissao de Contrato", "ENTRADA", "3.1.01.004"),
    ("101", "Compra de Mercadorias", "SAIDA", "4.1.01.001"),
    ("102", "Folha de Pagamento", "SAIDA", "4.2.01.001"),
    ("103", "Pro-Labore", "SAIDA", "4.2.01.002"),
    ("104", "Encargos Sociais", "SAIDA", "4.2.01.003"),
    ("105", "Aluguel", "SAIDA", "4.3.01.001"),
    ("106", "Contas de Consumo (agua/luz/telefone)", "SAIDA", "4.3.01.002"),
    ("107", "Honorarios Contabeis", "SAIDA", "4.3.01.006"),
    ("108", "Despesas Administrativas", "SAIDA", "4.3.01.012"),
    ("109", "Marketing e Publicidade", "SAIDA", "4.4.01.002"),
    ("110", "Tarifas e Despesas Bancarias", "SAIDA", "4.5.01.003"),
    ("111", "Impostos e Taxas", "SAIDA", "4.6.01.001"),
    ("112", "Emprestimos e Financiamentos", "SAIDA", "2.1.04.001"),
]


def criar_plano_padrao(db: Session, empresa_id: int) -> int:
    """Cria o plano de contas padrão para a empresa (ignora códigos já existentes)."""
    existentes = {
        c.codigo: c
        for c in db.query(ContaContabil).filter(ContaContabil.empresa_id == empresa_id).all()
    }
    criadas = 0
    for codigo, nome, tipo, natureza, analitica, grupo in PLANO_PADRAO:
        if codigo in existentes:
            continue
        pai_codigo = ".".join(codigo.split(".")[:-1])
        pai = existentes.get(pai_codigo)
        # contas analíticas de 4 níveis penduram no nível 2 quando não há nível 3
        while pai is None and pai_codigo.count("."):
            pai_codigo = ".".join(pai_codigo.split(".")[:-1])
            pai = existentes.get(pai_codigo)
        conta = ContaContabil(
            empresa_id=empresa_id,
            codigo=codigo,
            nome=nome,
            tipo=tipo,
            natureza=natureza,
            analitica=analitica,
            nivel=codigo.count(".") + 1,
            pai_id=pai.id if pai else None,
            grupo_dre=grupo,
        )
        db.add(conta)
        db.flush()
        existentes[codigo] = conta
        criadas += 1
    db.flush()
    _criar_parametros(db, empresa_id, existentes)
    return criadas


def _criar_parametros(db: Session, empresa_id: int, contas: dict):
    atuais = {
        p.chave: p for p in db.query(Parametro).filter(Parametro.empresa_id == empresa_id).all()
    }
    for chave, codigo in PARAMETROS_PADRAO.items():
        conta = contas.get(codigo)
        if not conta:
            continue
        if chave in atuais:
            if not atuais[chave].valor:
                atuais[chave].valor = str(conta.id)
        else:
            db.add(Parametro(empresa_id=empresa_id, chave=chave, valor=str(conta.id)))
    db.flush()


def criar_centros_custo_padrao(db: Session, empresa_id: int) -> int:
    existentes = {
        c.codigo for c in db.query(CentroCusto).filter(CentroCusto.empresa_id == empresa_id).all()
    }
    criados = 0
    for codigo, nome, tipo in CENTROS_CUSTO_PADRAO:
        if codigo in existentes:
            continue
        db.add(CentroCusto(empresa_id=empresa_id, codigo=codigo, nome=nome, tipo=tipo))
        criados += 1
    db.flush()
    return criados


def criar_operacoes_padrao(db: Session, empresa_id: int) -> int:
    contas = {
        c.codigo: c
        for c in db.query(ContaContabil).filter(ContaContabil.empresa_id == empresa_id).all()
    }
    existentes = {
        o.codigo for o in db.query(Operacao).filter(Operacao.empresa_id == empresa_id).all()
    }
    criadas = 0
    for codigo, nome, natureza, conta_codigo in OPERACOES_PADRAO:
        if codigo in existentes:
            continue
        conta = contas.get(conta_codigo)
        db.add(
            Operacao(
                empresa_id=empresa_id,
                codigo=codigo,
                nome=nome,
                natureza=natureza,
                conta_contabil_id=conta.id if conta else None,
            )
        )
        criadas += 1
    db.flush()
    return criadas


def parametro_conta(db: Session, empresa_id: int, chave: str) -> int | None:
    p = (
        db.query(Parametro)
        .filter(Parametro.empresa_id == empresa_id, Parametro.chave == chave)
        .first()
    )
    if p and p.valor:
        try:
            return int(p.valor)
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------- #
# Cadastros usados nos contratos de intermediação
# --------------------------------------------------------------------------- #
# (codigo, nome, peso em quilos de uma unidade)
UNIDADES_PADRAO = [
    ("SC", "Saca de 60 kg", 60),
    ("SC50", "Saca de 50 kg", 50),
    ("TON", "Tonelada", 1000),
    ("KG", "Quilograma", 1),
    ("AR", "Arroba", 15),
    ("UN", "Unidade", 0),
    ("LT", "Litro", 0),
]

# (codigo, nome, descricao)
MODALIDADES_PADRAO = [
    ("001", "DISPONIVEL", "Mercadoria pronta para retirada"),
    ("002", "FUTURO", "Entrega em data futura"),
    ("003", "A FIXAR", "Preco a ser fixado depois"),
    ("004", "CIF", "Frete por conta do vendedor"),
    ("005", "FOB", "Frete por conta do comprador"),
]

# (codigo, nome, codigo da unidade, embalagem)
PRODUTOS_PADRAO = [
    ("001", "CAFE ARABICA", "SC", "A GRANEL"),
    ("002", "CAFE CONILON / ROBUSTA", "SC", "A GRANEL"),
    ("003", "SOJA", "SC", "A GRANEL"),
    ("004", "MILHO", "SC", "A GRANEL"),
    ("005", "BOI GORDO", "AR", ""),
]


def criar_unidades_padrao(db: Session, empresa_id: int) -> int:
    from .models import Unidade

    existentes = {
        u.codigo for u in db.query(Unidade).filter(Unidade.empresa_id == empresa_id).all()
    }
    criadas = 0
    for codigo, nome, peso in UNIDADES_PADRAO:
        if codigo in existentes:
            continue
        db.add(Unidade(empresa_id=empresa_id, codigo=codigo, nome=nome, peso_conversao=peso))
        criadas += 1
    db.flush()
    return criadas


def criar_modalidades_padrao(db: Session, empresa_id: int) -> int:
    from .models import ModalidadeContrato

    existentes = {
        m.codigo
        for m in db.query(ModalidadeContrato)
        .filter(ModalidadeContrato.empresa_id == empresa_id)
        .all()
    }
    criadas = 0
    for codigo, nome, descricao in MODALIDADES_PADRAO:
        if codigo in existentes:
            continue
        db.add(
            ModalidadeContrato(
                empresa_id=empresa_id, codigo=codigo, nome=nome, descricao=descricao
            )
        )
        criadas += 1
    db.flush()
    return criadas


def criar_produtos_padrao(db: Session, empresa_id: int) -> int:
    from .models import Produto, Unidade

    unidades = {
        u.codigo: u for u in db.query(Unidade).filter(Unidade.empresa_id == empresa_id).all()
    }
    existentes = {
        p.codigo for p in db.query(Produto).filter(Produto.empresa_id == empresa_id).all()
    }
    criados = 0
    for codigo, nome, unidade_codigo, embalagem in PRODUTOS_PADRAO:
        if codigo in existentes:
            continue
        unidade = unidades.get(unidade_codigo)
        db.add(
            Produto(
                empresa_id=empresa_id,
                codigo=codigo,
                nome=nome,
                unidade_id=unidade.id if unidade else None,
                embalagem=embalagem,
            )
        )
        criados += 1
    db.flush()
    return criados


def criar_cadastros_contrato_padrao(db: Session, empresa_id: int) -> dict:
    """Unidades, modalidades e produtos padrão, na ordem certa de dependência."""
    unidades = criar_unidades_padrao(db, empresa_id)
    modalidades = criar_modalidades_padrao(db, empresa_id)
    produtos = criar_produtos_padrao(db, empresa_id)
    return {"unidades": unidades, "modalidades": modalidades, "produtos": produtos}
