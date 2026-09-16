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
    """Mercadoria negociada nos contratos."""

    __tablename__ = "produtos"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_produto_codigo"),)

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(20), nullable=False)
    nome = Column(String(120), nullable=False)
    unidade_id = Column(Integer, ForeignKey("unidades.id"))
    embalagem = Column(String(40))
    descricao = Column(String(200))
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    unidade = relationship("Unidade")


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

    comprador_id = Column(Integer, ForeignKey("parceiros.id"), nullable=False, index=True)
    vendedor_id = Column(Integer, ForeignKey("parceiros.id"), nullable=False, index=True)
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
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    criado_em = Column(DateTime, default=datetime.utcnow)

    comprador = relationship("Parceiro", foreign_keys=[comprador_id])
    vendedor = relationship("Parceiro", foreign_keys=[vendedor_id])
    representante = relationship("Usuario", foreign_keys=[representante_id])
    produto_ref = relationship("Produto")
    modalidade_ref = relationship("ModalidadeContrato")
    unidade_ref = relationship("Unidade")
    conta_contabil = relationship("ContaContabil")
    centro_custo = relationship("CentroCusto")
    operacao = relationship("Operacao")


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
