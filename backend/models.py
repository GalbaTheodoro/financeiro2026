"""Modelo de dados do sistema financeiro.

Estrutura geral
---------------
Cadastros ......... Usuario, Empresa, Parceiro (cliente/fornecedor), Banco (conta
                    bancária/caixa), CentroCusto, Operacao, ContaContabil
Movimento ......... Lancamento (título) -> LancamentoItem (rateio) -> Parcela -> Baixa
Caixa ............. MovimentoCaixa (extrato de cada conta bancária/caixa)
Contabilidade ..... Partida (partidas dobradas geradas automaticamente, base do
                    balancete e do DRE)
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Float,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def _dinheiro(**kw):
    return Column(Numeric(15, 2, asdecimal=False), nullable=False, default=0, **kw)


# --------------------------------------------------------------------------- #
# Cadastros
# --------------------------------------------------------------------------- #
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    nome = Column(String(120), nullable=False)
    email = Column(String(160), nullable=False, unique=True, index=True)
    senha_hash = Column(String(255), nullable=False)
    # MASTER = dono do sistema (vê todas as contas e confirma os pagamentos)
    perfil = Column(String(20), nullable=False, default="ADMIN")  # MASTER | ADMIN | OPERADOR | CONSULTA
    telefone = Column(String(30))
    documento = Column(String(20))
    empresa_id = Column(Integer, index=True)  # empresa principal (sem FK: evita ciclo com empresas.dono_id)
    ativo = Column(Boolean, nullable=False, default=True)
    # último dia em que o usuário pode entrar (definido pelo administrador do site);
    # vazio = sem data limite
    acesso_ate = Column(Date)
    # bloqueado pelo administrador do site: o admin da empresa não consegue reativar
    bloqueado_admin = Column(Boolean, nullable=False, default=False)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Empresa(Base):
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True)
    razao_social = Column(String(160), nullable=False)
    nome_fantasia = Column(String(160))
    cnpj = Column(String(20))
    inscricao_estadual = Column(String(30))
    inscricao_municipal = Column(String(30))
    regime_tributario = Column(String(40), default="SIMPLES NACIONAL")
    logradouro = Column(String(160))
    numero = Column(String(20))
    complemento = Column(String(80))
    bairro = Column(String(80))
    cidade = Column(String(80))
    uf = Column(String(2))
    cep = Column(String(12))
    telefone = Column(String(30))
    email = Column(String(160))
    responsavel = Column(String(120))
    site = Column(String(160))
    # Logotipo em data URL (data:image/png;base64,...) usado na impressão do contrato
    logo = Column(Text)
    # Texto fixo impresso no rodapé do contrato (cláusulas gerais, foro...)
    texto_contrato = Column(Text)

    # ---- dados exigidos para EMITIR nota fiscal ----
    codigo_municipio = Column(String(7))     # código do IBGE da cidade da empresa
    codigo_pais = Column(String(4), default="1058")
    pais = Column(String(60), default="BRASIL")
    # CRT: 1 Simples Nacional | 2 Simples com excesso | 3 Regime normal | 4 MEI
    crt = Column(String(1), default="1")
    cnae = Column(String(10))
    # texto fixo que entra em "Informações complementares" de toda nota emitida
    texto_nota = Column(Text)

    # Usuário assinante dono desta empresa (isolamento entre contas)
    dono_id = Column(Integer, index=True)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Parceiro(Base):
    """Cliente e/ou fornecedor."""

    __tablename__ = "parceiros"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    tipo = Column(String(12), nullable=False, default="CLIENTE")  # CLIENTE | FORNECEDOR | AMBOS
    pessoa = Column(String(1), nullable=False, default="J")  # F | J
    nome = Column(String(160), nullable=False)
    nome_fantasia = Column(String(160))
    cpf_cnpj = Column(String(20))
    rg_ie = Column(String(30))
    logradouro = Column(String(160))
    numero = Column(String(20))
    complemento = Column(String(80))
    bairro = Column(String(80))
    cidade = Column(String(80))
    uf = Column(String(2))
    cep = Column(String(12))
    telefone = Column(String(30))
    celular = Column(String(30))
    email = Column(String(160))
    contato = Column(String(120))
    observacao = Column(Text)

    # ---- dados fiscais (NF-e) ----
    # 1 = contribuinte de ICMS, 2 = isento inscrito, 9 = não contribuinte
    indicador_ie = Column(String(1), default="9")
    inscricao_municipal = Column(String(30))
    inscricao_suframa = Column(String(20))
    codigo_municipio = Column(String(7))     # código do IBGE do município
    codigo_pais = Column(String(4), default="1058")
    pais = Column(String(60), default="BRASIL")
    regime_tributario = Column(String(40))   # SIMPLES NACIONAL, LUCRO PRESUMIDO...
    # classificação usada para achar a regra fiscal da nota (ver TipoFiscal)
    tipo_fiscal_id = Column(Integer, ForeignKey("tipos_fiscais.id"), index=True)

    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    empresa = relationship("Empresa")
    formas_pagamento = relationship(
        "FormaPagamentoParceiro",
        back_populates="parceiro",
        cascade="all, delete-orphan",
        order_by="FormaPagamentoParceiro.principal.desc()",
    )


class FormaPagamentoParceiro(Base):
    """Onde pagar (ou receber de) um cliente/fornecedor.

    Um mesmo parceiro pode ter várias: chave Pix, conta em bancos diferentes,
    boleto, dinheiro. Uma delas fica marcada como principal e é a sugerida na
    hora de dar baixa no título.
    """

    __tablename__ = "parceiro_formas_pagamento"

    id = Column(Integer, primary_key=True)
    parceiro_id = Column(
        Integer, ForeignKey("parceiros.id", ondelete="CASCADE"), nullable=False, index=True
    )
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    # PIX | DEPOSITO | TED | BOLETO | DINHEIRO | CARTAO | OUTRO
    tipo = Column(String(15), nullable=False, default="PIX")
    apelido = Column(String(80))            # ex.: "Conta principal", "Banco do sócio"
    # dados bancários
    banco_codigo = Column(String(10))
    banco_nome = Column(String(80))
    agencia = Column(String(20))
    conta = Column(String(30))
    tipo_conta = Column(String(20), default="CORRENTE")  # CORRENTE | POUPANCA | PAGAMENTO
    operacao = Column(String(10))           # usado pela Caixa Econômica (001, 013...)
    # chave Pix
    pix_tipo = Column(String(15))           # CPF | CNPJ | EMAIL | TELEFONE | ALEATORIA
    pix_chave = Column(String(160))
    # titular (pode ser diferente do cadastro)
    titular = Column(String(160))
    documento_titular = Column(String(20))
    observacao = Column(String(300))
    principal = Column(Boolean, nullable=False, default=False)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    parceiro = relationship("Parceiro", back_populates="formas_pagamento")


class ContaContabil(Base):
    """Plano de contas. Contas sintéticas agrupam; analíticas recebem lançamento."""

    __tablename__ = "contas_contabeis"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_conta_codigo"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(30), nullable=False, index=True)
    nome = Column(String(160), nullable=False)
    # ATIVO | PASSIVO | PATRIMONIO_LIQUIDO | RECEITA | CUSTO | DESPESA
    tipo = Column(String(25), nullable=False)
    natureza = Column(String(1), nullable=False, default="D")  # D (devedora) | C (credora)
    analitica = Column(Boolean, nullable=False, default=True)
    nivel = Column(Integer, nullable=False, default=1)
    pai_id = Column(Integer, ForeignKey("contas_contabeis.id"))
    # Agrupamento usado na montagem do DRE (ver backend/dre_estrutura.py)
    grupo_dre = Column(String(40))
    saldo_inicial = _dinheiro()
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    pai = relationship("ContaContabil", remote_side=[id])


class Banco(Base):
    """Conta bancária, caixa ou aplicação — onde o dinheiro entra e sai."""

    __tablename__ = "bancos"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(20))
    nome = Column(String(120), nullable=False)
    codigo_banco = Column(String(10))  # 001, 341, 237...
    agencia = Column(String(20))
    conta = Column(String(30))
    tipo = Column(String(20), nullable=False, default="CORRENTE")  # CAIXA | CORRENTE | POUPANCA | APLICACAO | CARTAO
    titular = Column(String(160))
    conta_contabil_id = Column(Integer, ForeignKey("contas_contabeis.id"))
    saldo_inicial = _dinheiro()
    data_saldo_inicial = Column(Date, default=date.today)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    conta_contabil = relationship("ContaContabil")


class CentroCusto(Base):
    __tablename__ = "centros_custo"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_cc_codigo"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(20), nullable=False)
    nome = Column(String(120), nullable=False)
    tipo = Column(String(30), default="ADMINISTRATIVO")
    pai_id = Column(Integer, ForeignKey("centros_custo.id"))
    aceita_lancamento = Column(Boolean, nullable=False, default=True)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Operacao(Base):
    """Natureza da movimentação: venda, compra, salário, empréstimo, etc."""

    __tablename__ = "operacoes"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_operacao_codigo"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(20), nullable=False)
    nome = Column(String(120), nullable=False)
    natureza = Column(String(10), nullable=False, default="ENTRADA")  # ENTRADA | SAIDA | AMBAS
    # Classificação sugerida ao usar a operação num lançamento
    conta_contabil_id = Column(Integer, ForeignKey("contas_contabeis.id"))
    centro_custo_id = Column(Integer, ForeignKey("centros_custo.id"))
    descricao = Column(Text)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    conta_contabil = relationship("ContaContabil")
    centro_custo = relationship("CentroCusto")


class Assinatura(Base):
    """Assinatura do sistema (SaaS).

    Fluxo: cadastro pelo site -> TESTE por 48 horas -> assinante paga o Pix e
    informa o pagamento (AGUARDANDO) -> administrador confirma o recebimento e
    libera o acesso (ATIVA) até a data de vencimento do plano.
    """

    __tablename__ = "assinaturas"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    empresa_id = Column(Integer, index=True)
    plano = Column(String(15), nullable=False, default="SEMESTRAL")  # SEMESTRAL | ANUAL
    valor = Column(Numeric(15, 2, asdecimal=False), nullable=False, default=0)
    # TESTE | AGUARDANDO | ATIVA | EXPIRADA | CANCELADA | BLOQUEADA
    status = Column(String(15), nullable=False, default="TESTE", index=True)
    teste_inicio = Column(DateTime, default=datetime.utcnow)
    teste_fim = Column(DateTime)
    data_inicio = Column(Date)
    data_fim = Column(Date)
    # pacotes de usuários extras (cada pacote libera N usuários além dos inclusos)
    pacotes_usuarios = Column(Integer, nullable=False, default=0)
    pacotes_solicitados = Column(Integer, nullable=False, default=0)
    # limite de usuários definido à mão pelo administrador do site (vazio = padrão
    # do plano: usuários inclusos + pacotes)
    limite_usuarios = Column(Integer)
    pagamento_informado_em = Column(DateTime)
    pagamento_observacao = Column(String(300))
    pix_identificador = Column(String(40))
    confirmado_em = Column(DateTime)
    confirmado_por_id = Column(Integer, ForeignKey("usuarios.id"))
    observacao_admin = Column(Text)
    criado_em = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", foreign_keys=[usuario_id])


class CacheExterno(Base):
    """Dados buscados na internet (ex.: cotações do café), guardados para não
    consultar as fontes a cada visita."""

    __tablename__ = "cache_externo"

    chave = Column(String(60), primary_key=True)
    conteudo = Column(Text)
    atualizado_em = Column(DateTime)


class CotacaoHistorico(Base):
    """Histórico diário das cotações do painel "Mercado do Café".

    grupo ... série de onde veio: ny, londres, b3, cepea, moedas, fisico_6_7,
              fisico_6_duro, cereja, conilon_es, agnocafe
    item .... contrato ("Dezembro/26"), praça ("Patrocínio/MG (Expocaccer)") ou
              descrição ("Patrocínio · Safra 25/26 15%")
    cidade .. cidade normalizada, para o filtro por cidade (vazio nas bolsas)
    """

    __tablename__ = "cotacao_historico"
    __table_args__ = (UniqueConstraint("grupo", "item", "data", name="uq_cotacao_hist"),)

    id = Column(Integer, primary_key=True)
    grupo = Column(String(30), nullable=False, index=True)
    item = Column(String(140), nullable=False)
    cidade = Column(String(80), index=True)
    data = Column(Date, nullable=False, index=True)
    valor = Column(Float, nullable=False)
    variacao = Column(Float)
    tipo_variacao = Column(String(10))
    atualizado_em = Column(DateTime, default=datetime.utcnow)


class Configuracao(Base):
    """Configurações gerais do sistema (chave Pix, valores dos planos, contatos)."""

    __tablename__ = "configuracoes"

    id = Column(Integer, primary_key=True)
    chave = Column(String(60), nullable=False, unique=True, index=True)
    valor = Column(Text)
    descricao = Column(String(200))
    publica = Column(Boolean, nullable=False, default=False)


class Parametro(Base):
    """Contas contábeis padrão usadas pelo motor contábil, por empresa."""

    __tablename__ = "parametros"
    __table_args__ = (UniqueConstraint("empresa_id", "chave", name="uq_parametro"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    chave = Column(String(60), nullable=False)
    valor = Column(String(120))


# --------------------------------------------------------------------------- #
# Movimento — contas a pagar e a receber
# --------------------------------------------------------------------------- #
class Lancamento(Base):
    """Título a pagar ou a receber.

    modo = SIMPLES  -> um item de classificação e uma parcela
    modo = MULTIPLO -> vários itens (rateio) e/ou várias parcelas
    """

    __tablename__ = "lancamentos"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    tipo = Column(String(10), nullable=False, index=True)  # RECEBER | PAGAR
    modo = Column(String(10), nullable=False, default="SIMPLES")  # SIMPLES | MULTIPLO
    numero_documento = Column(String(40))
    parceiro_id = Column(Integer, ForeignKey("parceiros.id"), index=True)
    descricao = Column(String(200), nullable=False)
    data_emissao = Column(Date, nullable=False, default=date.today)
    data_competencia = Column(Date, nullable=False, default=date.today)
    valor_total = _dinheiro()
    operacao_id = Column(Integer, ForeignKey("operacoes.id"))
    observacao = Column(Text)
    status = Column(String(15), nullable=False, default="ABERTO")  # ABERTO | PARCIAL | QUITADO | CANCELADO
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    criado_em = Column(DateTime, default=datetime.utcnow)

    parceiro = relationship("Parceiro")
    operacao = relationship("Operacao")
    itens = relationship(
        "LancamentoItem", back_populates="lancamento", cascade="all, delete-orphan"
    )
    parcelas = relationship(
        "Parcela",
        back_populates="lancamento",
        cascade="all, delete-orphan",
        order_by="Parcela.numero",
    )


class LancamentoItem(Base):
    """Rateio do título entre contas contábeis / centros de custo / operações."""

    __tablename__ = "lancamento_itens"

    id = Column(Integer, primary_key=True)
    lancamento_id = Column(
        Integer, ForeignKey("lancamentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conta_contabil_id = Column(Integer, ForeignKey("contas_contabeis.id"), nullable=False)
    centro_custo_id = Column(Integer, ForeignKey("centros_custo.id"))
    operacao_id = Column(Integer, ForeignKey("operacoes.id"))
    descricao = Column(String(200))
    valor = _dinheiro()

    lancamento = relationship("Lancamento", back_populates="itens")
    conta_contabil = relationship("ContaContabil")
    centro_custo = relationship("CentroCusto")
    operacao = relationship("Operacao")


class Parcela(Base):
    __tablename__ = "parcelas"

    id = Column(Integer, primary_key=True)
    lancamento_id = Column(
        Integer, ForeignKey("lancamentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero = Column(Integer, nullable=False, default=1)
    data_vencimento = Column(Date, nullable=False, index=True)
    valor = _dinheiro()
    valor_baixado = _dinheiro()
    juros_multa = _dinheiro()
    desconto = _dinheiro()
    status = Column(String(15), nullable=False, default="ABERTO")  # ABERTO | PARCIAL | PAGO | CANCELADO
    data_ultima_baixa = Column(Date)
    observacao = Column(String(200))

    lancamento = relationship("Lancamento", back_populates="parcelas")
    baixas = relationship("Baixa", back_populates="parcela", cascade="all, delete-orphan")

    @property
    def saldo(self) -> float:
        return round((self.valor or 0) - (self.valor_baixado or 0), 2)


class Baixa(Base):
    """Recebimento ou pagamento (total ou parcial) de uma parcela."""

    __tablename__ = "baixas"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    parcela_id = Column(
        Integer, ForeignKey("parcelas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    banco_id = Column(Integer, ForeignKey("bancos.id"), nullable=False)
    data = Column(Date, nullable=False, default=date.today, index=True)
    valor = _dinheiro()          # valor abatido do título
    juros = _dinheiro()
    multa = _dinheiro()
    desconto = _dinheiro()
    valor_liquido = _dinheiro()  # valor efetivamente movimentado no banco
    forma_pagamento = Column(String(30), default="DINHEIRO")
    # qual conta/chave do parceiro foi usada (quando informada)
    forma_parceiro_id = Column(Integer, ForeignKey("parceiro_formas_pagamento.id"))
    historico = Column(String(200))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    criado_em = Column(DateTime, default=datetime.utcnow)

    parcela = relationship("Parcela", back_populates="baixas")
    banco = relationship("Banco")
    forma_parceiro = relationship("FormaPagamentoParceiro")


# --------------------------------------------------------------------------- #
# Cadastros usados nos contratos
# --------------------------------------------------------------------------- #
class Unidade(Base):
    """Unidade de medida negociada (saca, tonelada, arroba...).

    `peso_conversao` é quantos quilos vale uma unidade — permite calcular o
    peso total do contrato e comparar negócios em unidades diferentes.
    """

    __tablename__ = "unidades"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_unidade_codigo"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(20), nullable=False)
    nome = Column(String(80), nullable=False)
    peso_conversao = Column(Numeric(15, 4, asdecimal=False), nullable=False, default=0)
    observacao = Column(String(200))
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class ModalidadeContrato(Base):
    """Modalidade do contrato (disponível, futuro, a fixar, CIF, FOB...)."""

    __tablename__ = "modalidades_contrato"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_modalidade_codigo"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(20), nullable=False)
    nome = Column(String(80), nullable=False)
    descricao = Column(String(200))
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Produto(Base):
    """Mercadoria negociada nos contratos.

    Os campos fiscais são os que a nota fiscal eletrônica exige de cada item.
    Ficam em branco enquanto o produto for usado só em contrato; ao importar o
    XML de uma nota, o sistema oferece preencher o cadastro com o que veio nela.
    """

    __tablename__ = "produtos"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_produto_codigo"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(20), nullable=False)
    nome = Column(String(120), nullable=False)
    unidade_id = Column(Integer, ForeignKey("unidades.id"))
    embalagem = Column(String(40))
    descricao = Column(String(200))

    # ---- dados fiscais (NF-e) ----
    ncm = Column(String(10))                 # classificação fiscal, 8 dígitos
    cest = Column(String(9))                 # substituição tributária
    ex_tipi = Column(String(3))
    cfop_padrao = Column(String(5))          # CFOP sugerido na emissão
    origem = Column(String(1), default="0")  # 0 nacional, 1 importação direta...
    unidade_comercial = Column(String(6))    # uCom: SC, KG, TON
    unidade_tributavel = Column(String(6))   # uTrib (normalmente igual à comercial)
    gtin = Column(String(14))                # código de barras (antigo EAN)
    gtin_tributavel = Column(String(14))
    cst_icms = Column(String(3))             # CST (normal) ou CSOSN (Simples)
    aliquota_icms = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    reducao_base_icms = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cst_ipi = Column(String(2))
    aliquota_ipi = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cst_pis = Column(String(2))
    aliquota_pis = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cst_cofins = Column(String(2))
    aliquota_cofins = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    peso_liquido = Column(Numeric(15, 4, asdecimal=False), nullable=False, default=0)
    peso_bruto = Column(Numeric(15, 4, asdecimal=False), nullable=False, default=0)
    codigo_beneficio = Column(String(10))    # cBenef (MG e outros estados)
    observacao_fiscal = Column(String(300))
    # classificação usada para achar a regra fiscal da nota (ver TipoFiscal)
    tipo_fiscal_id = Column(Integer, ForeignKey("tipos_fiscais.id"), index=True)

    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    unidade = relationship("Unidade")


class AliquotaIcms(Base):
    """Tabela de ICMS usada nos contratos: UF do vendedor x UF do comprador.

    `produto_id` vazio = vale para qualquer produto. Uma linha específica do
    produto tem prioridade sobre a linha geral do mesmo par de estados.
    """

    __tablename__ = "aliquotas_icms"
    __table_args__ = (
        UniqueConstraint("empresa_id", "uf_origem", "uf_destino", "produto_id", name="uq_aliquota_icms"),
    )

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    uf_origem = Column(String(2), nullable=False)    # estado do vendedor
    uf_destino = Column(String(2), nullable=False)   # estado do comprador
    produto_id = Column(Integer, ForeignKey("produtos.id"))
    aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    observacao = Column(String(200))
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    produto = relationship("Produto")


# --------------------------------------------------------------------------- #
# Regras fiscais da nota: tipo de cliente x tipo de item
# --------------------------------------------------------------------------- #
class TipoFiscal(Base):
    """Classificação fiscal, usada dos dois lados do cruzamento.

    `aplicacao` diz de quem é o tipo: **CLIENTE** (contribuinte de dentro do
    estado, produtor rural, exportação, consumidor final...) ou **ITEM** (café
    cru em grão, café torrado, serviço, uso e consumo...). É esse par que a
    regra fiscal cruza para achar o imposto certo de cada item da nota.
    """

    __tablename__ = "tipos_fiscais"
    __table_args__ = (
        UniqueConstraint("empresa_id", "aplicacao", "codigo", name="uq_tipo_fiscal"),
    )

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    aplicacao = Column(String(8), nullable=False, default="ITEM")   # CLIENTE | ITEM
    codigo = Column(String(20), nullable=False)
    nome = Column(String(120), nullable=False)
    descricao = Column(String(300))
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class RegraFiscal(Base):
    """Uma linha da tabela de impostos da nota.

    Campo em branco quer dizer **qualquer um**: uma regra só com o tipo de item
    preenchido vale para todo cliente. Quando mais de uma linha serve, ganha a
    mais específica (a que tem mais campos preenchidos casando com a nota) e,
    em caso de empate, a de maior `prioridade`.
    """

    __tablename__ = "regras_fiscais"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    nome = Column(String(120))
    tipo_cliente_id = Column(Integer, ForeignKey("tipos_fiscais.id"), index=True)
    tipo_item_id = Column(Integer, ForeignKey("tipos_fiscais.id"), index=True)
    uf_origem = Column(String(2))        # em branco = qualquer estado de saída
    uf_destino = Column(String(2))       # em branco = qualquer estado de destino
    operacao = Column(String(7))         # SAIDA | ENTRADA | em branco = as duas
    # ---- o que a regra manda aplicar no item ----
    # As "bases" são percentuais do valor do item: 100 = o valor inteiro entra na
    # base. A redução é aplicada depois, sobre essa base.
    cfop = Column(String(5))
    icms_origem = Column(String(1))
    # ICMS
    icms_cst = Column(String(3))         # CST (regime normal) ou CSOSN (Simples)
    icms_base = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=100)
    icms_reducao = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    icms_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    # PIS e COFINS (um CST só para os dois, como na prática)
    cst_pis = Column(String(2))
    cst_cofins = Column(String(2))
    pis_cofins_base = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=100)
    pis_cofins_reducao = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    aliquota_pis = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    aliquota_cofins = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cst_ipi = Column(String(2))
    aliquota_ipi = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    # IBS e CBS (reforma tributária)
    ibs_cbs_cst = Column(String(3))
    ibs_cbs_classe = Column(String(6))   # cClassTrib
    ibs_cbs_base = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=100)
    ibs_cbs_reducao_base = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    ibs_cbs_reducao_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cbs_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    ibs_uf_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    ibs_mun_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    prioridade = Column(Integer, nullable=False, default=0)
    observacao = Column(String(300))
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    tipo_cliente = relationship("TipoFiscal", foreign_keys=[tipo_cliente_id])
    tipo_item = relationship("TipoFiscal", foreign_keys=[tipo_item_id])


# --------------------------------------------------------------------------- #
# Contratos de intermediação (corretagem)
# --------------------------------------------------------------------------- #
class Contrato(Base):
    """Contrato de compra e venda intermediado pela assessoria.

    Registra o negócio entre um comprador e um vendedor e a corretagem cobrada
    de cada lado (em percentual sobre o valor negociado ou em valor fixo).
    A partir dele o sistema gera as contas a receber das comissões.
    """

    __tablename__ = "contratos"
    __table_args__ = (UniqueConstraint("empresa_id", "numero", name="uq_contrato_numero"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    numero = Column(String(30), nullable=False, index=True)
    data = Column(Date, nullable=False, default=date.today)
    # CORRETAGEM = a empresa só intermedeia (comissão dos dois lados)
    # COMPRA     = a empresa compra (conta a pagar do fornecedor)
    # VENDA      = a empresa vende (conta a receber do cliente)
    tipo = Column(String(12), nullable=False, default="CORRETAGEM", index=True)

    # na compra o comprador é a própria empresa (comprador_id vazio);
    # na venda o vendedor é a própria empresa (vendedor_id vazio)
    comprador_id = Column(Integer, ForeignKey("parceiros.id"), index=True)
    vendedor_id = Column(Integer, ForeignKey("parceiros.id"), index=True)
    corretor = Column(String(160))
    # representante da equipe que fechou o negócio (usuário da empresa)
    representante_id = Column(Integer, ForeignKey("usuarios.id"), index=True)

    # objeto do contrato — os textos ficam gravados junto para o histórico
    produto_id = Column(Integer, ForeignKey("produtos.id"))
    modalidade_id = Column(Integer, ForeignKey("modalidades_contrato.id"))
    unidade_id = Column(Integer, ForeignKey("unidades.id"))
    produto = Column(String(120), default="CAFÉ")
    modalidade = Column(String(40))          # DISPONÍVEL, FUTURO...
    embalagem = Column(String(40))           # A GRANEL, SACARIA...
    unidade = Column(String(20), default="SACA")
    peso_total = Column(Numeric(15, 3, asdecimal=False), nullable=False, default=0)
    quantidade = Column(Numeric(15, 3, asdecimal=False), nullable=False, default=0)
    preco_unitario = Column(Numeric(15, 4, asdecimal=False), nullable=False, default=0)
    diferencial = Column(Numeric(15, 4, asdecimal=False), nullable=False, default=0)
    valor_total = Column(Numeric(15, 2, asdecimal=False), nullable=False, default=0)

    local_coleta = Column(String(200))
    local_descarga = Column(String(200))
    numero_compra = Column(String(40))
    numero_venda = Column(String(40))
    data_embarque = Column(Date)
    data_pagamento = Column(Date)

    # corretagem de cada lado
    comissao_comprador_percentual = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    comissao_comprador_valor = Column(Numeric(15, 2, asdecimal=False), nullable=False, default=0)
    comissao_vendedor_percentual = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    comissao_vendedor_valor = Column(Numeric(15, 2, asdecimal=False), nullable=False, default=0)

    # agente que intermediou a compra/venda (opcional): a comissão dele vira
    # conta a pagar da empresa
    agente_id = Column(Integer, ForeignKey("parceiros.id"), index=True)
    agente_percentual = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    agente_valor = Column(Numeric(15, 2, asdecimal=False), nullable=False, default=0)

    # ICMS (informativo: não altera o valor negociado nem a corretagem)
    # icms_manual = False -> o percentual vem da tabela de ICMS (UF vendedor x UF comprador)
    icms_uf_origem = Column(String(2))
    icms_uf_destino = Column(String(2))
    icms_percentual = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    icms_valor = Column(Numeric(15, 2, asdecimal=False), nullable=False, default=0)
    icms_manual = Column(Boolean, nullable=False, default=False)

    # classificação usada nas contas a receber geradas
    conta_contabil_id = Column(Integer, ForeignKey("contas_contabeis.id"))
    centro_custo_id = Column(Integer, ForeignKey("centros_custo.id"))
    operacao_id = Column(Integer, ForeignKey("operacoes.id"))

    observacao = Column(Text)
    # ABERTO | FECHADO_A_RECEBER | RECEBIDO_PARCIAL | RECEBIDO_TOTAL | CANCELADO
    # (calculado a partir das baixas das comissões — ver routers/contratos.py)
    status = Column(String(20), nullable=False, default="ABERTO")
    lancamento_comprador_id = Column(Integer, ForeignKey("lancamentos.id"))
    lancamento_vendedor_id = Column(Integer, ForeignKey("lancamentos.id"))
    # compra/venda: título da mercadoria e título da comissão do agente
    lancamento_mercadoria_id = Column(Integer, ForeignKey("lancamentos.id"))
    lancamento_agente_id = Column(Integer, ForeignKey("lancamentos.id"))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    criado_em = Column(DateTime, default=datetime.utcnow)

    comprador = relationship("Parceiro", foreign_keys=[comprador_id])
    vendedor = relationship("Parceiro", foreign_keys=[vendedor_id])
    agente = relationship("Parceiro", foreign_keys=[agente_id])
    representante = relationship("Usuario", foreign_keys=[representante_id])
    produto_ref = relationship("Produto")
    modalidade_ref = relationship("ModalidadeContrato")
    unidade_ref = relationship("Unidade")
    conta_contabil = relationship("ContaContabil")
    centro_custo = relationship("CentroCusto")
    operacao = relationship("Operacao")


# --------------------------------------------------------------------------- #
# DF-e — documentos fiscais eletrônicos emitidos contra o CNPJ da empresa
# --------------------------------------------------------------------------- #
class ConfigCupom(Base):
    """O que a empresa precisa para emitir **cupom fiscal** (NFC-e, modelo 65).

    O cupom leva um QR Code que o consumidor lê para conferir a venda no site da
    SEFAZ. Esse QR Code é assinado com o **CSC** (Código de Segurança do
    Contribuinte), um código que a empresa pede no portal da SEFAZ do seu estado
    — em Minas, no SIARE. Sem CSC nenhum cupom é aceito.

    O CSC vem **junto com um número de identificação** (o `idToken`, de 1 a 6
    dígitos), e os dois entram no QR Code. Cada ambiente tem o seu: o CSC de
    homologação não funciona em produção e vice-versa — por isso os dois ficam
    guardados aqui, e a emissão pega o do ambiente da vez.

    O CSC fica **cifrado** no banco (AES-GCM com chave derivada de
    FIN_SECRET_KEY, igual ao certificado digital) e nenhuma rota o devolve.
    """

    __tablename__ = "config_cupom"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False,
                        unique=True, index=True)
    csc_homologacao = Column(Text)             # cifrado
    csc_id_homologacao = Column(String(6))
    csc_producao = Column(Text)                # cifrado
    csc_id_producao = Column(String(6))
    serie = Column(String(3), nullable=False, default="1")
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow)


class ConfigEmail(Base):
    """Como a empresa envia e-mail pelo sistema (servidor SMTP do e-mail dela).

    O sistema não tem servidor de e-mail próprio: ele usa a conta da empresa —
    a mesma do Gmail, do Outlook ou do provedor do domínio. Por isso precisa do
    servidor, da porta e da senha daquela conta.

    A **senha fica cifrada** no banco (AES-GCM com chave derivada de
    FIN_SECRET_KEY, igual ao certificado digital) e nenhuma rota a devolve: a
    tela mostra só se existe senha guardada.
    """

    __tablename__ = "config_email"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False,
                        unique=True, index=True)
    servidor = Column(String(160))                 # smtp.gmail.com, mail.dominio...
    porta = Column(Integer, nullable=False, default=587)
    seguranca = Column(String(8), nullable=False, default="TLS")   # TLS | SSL | NENHUMA
    usuario = Column(String(160))                  # quase sempre o próprio e-mail
    senha = Column(Text)                           # cifrada
    remetente_nome = Column(String(120))           # o nome que aparece para quem recebe
    remetente_email = Column(String(160))
    responder_para = Column(String(160))           # para onde vai a resposta do cliente
    email_contador = Column(String(160))           # cópia para o contador
    copia_empresa = Column(Boolean, nullable=False, default=True)
    enviar_ao_autorizar = Column(Boolean, nullable=False, default=True)
    assunto = Column(String(200))                  # aceita {numero} e {empresa}
    texto = Column(Text)                           # corpo do e-mail
    ativo = Column(Boolean, nullable=False, default=True)
    ultimo_envio_em = Column(DateTime)
    ultimo_erro = Column(String(300))
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow)


class CertificadoDigital(Base):
    """Certificado digital A1 (arquivo .pfx) usado para falar com a SEFAZ.

    O arquivo e a senha ficam **cifrados** no banco (AES-GCM com chave derivada
    de FIN_SECRET_KEY — ver backend/dfe.py). Nenhuma rota devolve o conteúdo
    nem a senha: a tela mostra só o titular, o CNPJ e a validade.
    """

    __tablename__ = "certificados_digitais"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, unique=True, index=True)
    arquivo_nome = Column(String(160))
    conteudo = Column(Text, nullable=False)   # .pfx cifrado (base64)
    senha = Column(Text, nullable=False)      # senha cifrada (base64)
    titular = Column(String(200))
    cnpj = Column(String(20))
    valido_de = Column(DateTime)
    valido_ate = Column(DateTime)
    ambiente = Column(String(1), nullable=False, default="1")  # 1 produção | 2 homologação
    uf_autor = Column(String(2))
    # controle da distribuição: a SEFAZ entrega os documentos a partir do último
    # NSU já recebido (número sequencial único, 15 dígitos)
    ultimo_nsu = Column(String(15), nullable=False, default="000000000000000")
    max_nsu = Column(String(15))
    ultima_consulta = Column(DateTime)
    ultima_mensagem = Column(String(300))
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow)


class SerieNota(Base):
    """Numeração das notas que a empresa emite.

    Cada série tem sua própria sequência. O número só é gasto quando a nota é
    transmitida — rascunho não consome numeração, para não abrir buraco na
    sequência se o usuário desistir.
    """

    __tablename__ = "series_nota"
    __table_args__ = (
        UniqueConstraint("empresa_id", "modelo", "serie", "ambiente", name="uq_serie_nota"),
    )

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    modelo = Column(String(2), nullable=False, default="55")
    serie = Column(String(3), nullable=False, default="1")
    ambiente = Column(String(1), nullable=False, default="2")  # 1 produção | 2 homologação
    proximo_numero = Column(Integer, nullable=False, default=1)
    descricao = Column(String(80))
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Nota(Base):
    """Documento fiscal: o que a SEFAZ entregou **e** o que a empresa emite.

    `origem` separa os dois mundos:
      DFE     — veio da SEFAZ (ou de um XML recebido). Só leitura.
      EMITIDA — a empresa está emitindo. Passa por RASCUNHO -> AUTORIZADA.

    `resumo` = True quando a SEFAZ entregou só o resumo (resNFe). O XML completo
    (procNFe) costuma chegar depois que o destinatário dá ciência da operação.
    """

    __tablename__ = "notas"
    __table_args__ = (UniqueConstraint("empresa_id", "chave", name="uq_nota_chave"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    # rascunho ainda não tem chave: fica um código provisório "RASCUNHO-<id>"
    chave = Column(String(44), nullable=False, index=True)
    nsu = Column(String(15), index=True)
    esquema = Column(String(40))              # resNFe_v1.01, procNFe_v4.00...
    tipo = Column(String(10), nullable=False, default="NFE")  # NFE | EVENTO | OUTRO
    resumo = Column(Boolean, nullable=False, default=True)

    modelo = Column(String(2))
    serie = Column(String(3))
    numero = Column(String(9))
    data_emissao = Column(DateTime, index=True)
    natureza_operacao = Column(String(120))
    # 0 = entrada (a empresa recebeu), 1 = saída (a empresa emitiu)
    tipo_operacao = Column(String(1))
    finalidade = Column(String(1))

    emitente_cnpj = Column(String(20), index=True)
    emitente_nome = Column(String(200))
    emitente_ie = Column(String(30))
    emitente_uf = Column(String(2))
    destinatario_cnpj = Column(String(20))
    destinatario_nome = Column(String(200))

    valor_total = _dinheiro()
    valor_produtos = _dinheiro()
    valor_icms = _dinheiro()
    valor_ipi = _dinheiro()
    valor_frete = _dinheiro()
    valor_desconto = _dinheiro()

    protocolo = Column(String(20))
    data_autorizacao = Column(DateTime)
    # AUTORIZADA | CANCELADA | DENEGADA | DESCONHECIDA
    situacao = Column(String(15), nullable=False, default="AUTORIZADA")

    # manifestação do destinatário
    # (vazio) | CIENCIA | CONFIRMADA | DESCONHECIDA | NAO_REALIZADA
    manifestacao = Column(String(15))
    manifestacao_em = Column(DateTime)
    manifestacao_protocolo = Column(String(20))
    manifestacao_justificativa = Column(String(255))

    xml = Column(Text)
    importada = Column(Boolean, nullable=False, default=False)
    importada_em = Column(DateTime)
    parceiro_id = Column(Integer, ForeignKey("parceiros.id"), index=True)

    # faturamento: o título (conta a pagar ou a receber) gerado a partir da nota.
    # Desfaturar apaga o título e limpa estes campos — só no AgroDock, a nota na
    # SEFAZ não é tocada.
    lancamento_id = Column(Integer, ForeignKey("lancamentos.id"))
    faturada_em = Column(DateTime)
    faturada_por_id = Column(Integer, ForeignKey("usuarios.id"))
    faturamento_observacao = Column(String(300))

    # ---- emissão (só nas notas que a empresa emite) ----
    origem = Column(String(8), nullable=False, default="DFE", index=True)  # DFE | EMITIDA
    # RASCUNHO | ENVIADA | AUTORIZADA | REJEITADA | CANCELADA
    status_emissao = Column(String(12), index=True)
    ambiente = Column(String(1))              # 1 produção | 2 homologação
    contrato_id = Column(Integer, ForeignKey("contratos.id"), index=True)
    cfop = Column(String(5))
    codigo_sefaz = Column(String(5))          # cStat do retorno
    mensagem_sefaz = Column(String(300))      # xMotivo do retorno
    recibo = Column(String(20))
    enviada_em = Column(DateTime)
    # transporte
    frete_modalidade = Column(String(1), default="9")  # 0 emitente, 1 destinatário... 9 sem frete
    transportadora_id = Column(Integer, ForeignKey("parceiros.id"))
    placa_veiculo = Column(String(8))
    uf_veiculo = Column(String(2))
    volumes = Column(Integer)
    especie_volume = Column(String(30))
    peso_liquido = Column(Numeric(15, 3, asdecimal=False), nullable=False, default=0)
    peso_bruto = Column(Numeric(15, 3, asdecimal=False), nullable=False, default=0)
    informacoes_complementares = Column(Text)
    # cancelamento
    cancelamento_justificativa = Column(String(255))
    cancelamento_protocolo = Column(String(20))
    cancelada_em = Column(DateTime)
    # cupom fiscal (modelo 65): o consumidor é opcional e não tem cadastro —
    # quem pede "CPF na nota" informa só o documento, e o troco vai no XML
    consumidor_documento = Column(String(20))
    consumidor_nome = Column(String(60))
    troco = _dinheiro()
    # envio do XML e da DANFE por e-mail para o cliente
    email_enviado_em = Column(DateTime)
    email_destinatarios = Column(String(400))
    email_erro = Column(String(300))

    observacao = Column(Text)
    criado_em = Column(DateTime, default=datetime.utcnow)

    parceiro = relationship("Parceiro", foreign_keys=[parceiro_id])
    transportadora = relationship("Parceiro", foreign_keys=[transportadora_id])
    contrato = relationship("Contrato")
    itens = relationship(
        "NotaItem", back_populates="nota", cascade="all, delete-orphan",
        order_by="NotaItem.numero",
    )
    pagamentos = relationship(
        "NotaPagamento", back_populates="nota", cascade="all, delete-orphan",
        order_by="NotaPagamento.id",
    )


class NotaItem(Base):
    """Produto/serviço de uma nota (tag <det> do XML)."""

    __tablename__ = "nota_itens"

    id = Column(Integer, primary_key=True)
    nota_id = Column(Integer, ForeignKey("notas.id", ondelete="CASCADE"), nullable=False, index=True)
    numero = Column(Integer, nullable=False, default=1)
    codigo = Column(String(60))
    gtin = Column(String(14))
    descricao = Column(String(200), nullable=False)
    ncm = Column(String(10))
    cest = Column(String(9))
    cfop = Column(String(5))
    unidade = Column(String(10))
    quantidade = Column(Numeric(15, 4, asdecimal=False), nullable=False, default=0)
    valor_unitario = Column(Numeric(15, 6, asdecimal=False), nullable=False, default=0)
    valor_total = _dinheiro()
    desconto = _dinheiro()
    frete = _dinheiro()
    icms_cst = Column(String(3))
    icms_base = _dinheiro()
    icms_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    icms_valor = _dinheiro()
    ipi_valor = _dinheiro()
    pis_valor = _dinheiro()
    cofins_valor = _dinheiro()
    # usados na emissão (na nota recebida ficam como vieram no XML)
    origem_mercadoria = Column(String(1), default="0")
    icms_reducao = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cst_ipi = Column(String(2))
    aliquota_ipi = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cst_pis = Column(String(2))
    aliquota_pis = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cst_cofins = Column(String(2))
    aliquota_cofins = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    # Reforma tributária (NT 2025.002): IBS estadual, IBS municipal e CBS.
    # Em 2026 as alíquotas são de teste (IBS 0,1% e CBS 0,9%) e o cálculo é
    # informativo. Simples Nacional só passa a destacar em 2027.
    pis_cofins_base = _dinheiro()             # vBC do PIS e da COFINS
    ibs_cbs_cst = Column(String(3))
    ibs_cbs_classe = Column(String(6))        # cClassTrib
    ibs_cbs_base = _dinheiro()
    ibs_cbs_reducao_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    ibs_uf_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    ibs_uf_valor = _dinheiro()
    ibs_mun_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    ibs_mun_valor = _dinheiro()
    cbs_aliquota = Column(Numeric(9, 4, asdecimal=False), nullable=False, default=0)
    cbs_valor = _dinheiro()
    # Quais campos de imposto foram digitados à mão nesta linha, separados por
    # vírgula. Os que não estão aqui saem da regra fiscal a cada gravação — assim,
    # corrigir a tabela de regras conserta os rascunhos que ainda não foram
    # transmitidos, sem apagar o que alguém digitou de propósito.
    campos_manuais = Column(String(400))
    # produto do cadastro ligado a este item (preenchido na importação)
    produto_id = Column(Integer, ForeignKey("produtos.id"), index=True)

    nota = relationship("Nota", back_populates="itens")
    produto = relationship("Produto")


class NotaPagamento(Base):
    """Forma de pagamento (<detPag>) ou duplicata (<dup>) da nota."""

    __tablename__ = "nota_pagamentos"

    id = Column(Integer, primary_key=True)
    nota_id = Column(Integer, ForeignKey("notas.id", ondelete="CASCADE"), nullable=False, index=True)
    origem = Column(String(12), nullable=False, default="PAGAMENTO")  # PAGAMENTO | DUPLICATA
    codigo = Column(String(2))            # tPag: 01 dinheiro, 03 cartão, 15 boleto, 17 Pix...
    descricao = Column(String(80))
    numero = Column(String(60))           # número da duplicata
    vencimento = Column(Date, index=True)
    valor = _dinheiro()
    troco = _dinheiro()
    bandeira = Column(String(30))
    cnpj_credenciadora = Column(String(20))
    autorizacao = Column(String(40))

    nota = relationship("Nota", back_populates="pagamentos")


# --------------------------------------------------------------------------- #
# Caixa
# --------------------------------------------------------------------------- #
class MovimentoCaixa(Base):
    """Extrato de cada conta bancária/caixa.

    origem = BAIXA | AVULSO | TRANSFERENCIA | SALDO_INICIAL
    """

    __tablename__ = "movimentos_caixa"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    banco_id = Column(Integer, ForeignKey("bancos.id"), nullable=False, index=True)
    data = Column(Date, nullable=False, default=date.today, index=True)
    tipo = Column(String(1), nullable=False)  # E (entrada) | S (saída)
    valor = _dinheiro()
    historico = Column(String(200), nullable=False)
    origem = Column(String(20), nullable=False, default="AVULSO")
    origem_id = Column(Integer)
    conta_contabil_id = Column(Integer, ForeignKey("contas_contabeis.id"))
    centro_custo_id = Column(Integer, ForeignKey("centros_custo.id"))
    operacao_id = Column(Integer, ForeignKey("operacoes.id"))
    parceiro_id = Column(Integer, ForeignKey("parceiros.id"))
    documento = Column(String(40))
    conciliado = Column(Boolean, nullable=False, default=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    criado_em = Column(DateTime, default=datetime.utcnow)

    banco = relationship("Banco")
    conta_contabil = relationship("ContaContabil")
    centro_custo = relationship("CentroCusto")
    operacao = relationship("Operacao")
    parceiro = relationship("Parceiro")


# --------------------------------------------------------------------------- #
# Contabilidade
# --------------------------------------------------------------------------- #
class Partida(Base):
    """Partida dobrada gerada automaticamente por cada evento financeiro.

    É a base do balancete e do DRE. `origem`/`origem_id` permitem estornar
    todas as partidas de um documento quando ele é excluído.
    """

    __tablename__ = "partidas"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    data = Column(Date, nullable=False, index=True)
    competencia = Column(Date, nullable=False, index=True)
    historico = Column(String(250), nullable=False)
    conta_debito_id = Column(Integer, ForeignKey("contas_contabeis.id"), nullable=False, index=True)
    conta_credito_id = Column(Integer, ForeignKey("contas_contabeis.id"), nullable=False, index=True)
    valor = _dinheiro()
    centro_custo_id = Column(Integer, ForeignKey("centros_custo.id"))
    operacao_id = Column(Integer, ForeignKey("operacoes.id"))
    parceiro_id = Column(Integer, ForeignKey("parceiros.id"))
    origem = Column(String(20), nullable=False)  # LANCAMENTO | BAIXA | CAIXA | ABERTURA
    origem_id = Column(Integer, index=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    conta_debito = relationship("ContaContabil", foreign_keys=[conta_debito_id])
    conta_credito = relationship("ContaContabil", foreign_keys=[conta_credito_id])
