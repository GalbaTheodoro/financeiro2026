"""Modelos de entrada (validação das requisições)."""
from datetime import date

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    senha: str


class CadastroPublicoIn(BaseModel):
    """Auto-cadastro pelo site."""

    nome: str
    email: str
    senha: str
    telefone: str | None = None
    documento: str | None = None
    empresa: str | None = None
    cidade: str | None = None
    uf: str | None = None
    plano: str = "SEMESTRAL"


class EscolherPlanoIn(BaseModel):
    plano: str


class InformarPagamentoIn(BaseModel):
    observacao: str | None = None


class StatusAssinaturaIn(BaseModel):
    status: str = "ATIVA"
    plano: str | None = None
    meses: int | None = None
    horas_teste: int | None = None
    observacao: str | None = None


class ConfiguracoesIn(BaseModel):
    valores: dict[str, str | None]


class UsuarioIn(BaseModel):
    nome: str
    email: str
    senha: str | None = None
    perfil: str = "OPERADOR"
    telefone: str | None = None
    ativo: bool = True


class TrocarSenhaIn(BaseModel):
    senha_atual: str | None = None
    senha_nova: str = Field(min_length=4)


class EmpresaIn(BaseModel):
    razao_social: str
    nome_fantasia: str | None = None
    cnpj: str | None = None
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    regime_tributario: str | None = "SIMPLES NACIONAL"
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cep: str | None = None
    telefone: str | None = None
    email: str | None = None
    responsavel: str | None = None
    site: str | None = None
    logo: str | None = None             # data URL do logotipo, para a impressão
    texto_contrato: str | None = None   # cláusulas fixas impressas no contrato
    ativo: bool = True
    criar_plano_padrao: bool = True


class ParceiroIn(BaseModel):
    empresa_id: int
    tipo: str = "CLIENTE"
    pessoa: str = "J"
    nome: str
    nome_fantasia: str | None = None
    cpf_cnpj: str | None = None
    rg_ie: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cep: str | None = None
    telefone: str | None = None
    celular: str | None = None
    email: str | None = None
    contato: str | None = None
    observacao: str | None = None
    ativo: bool = True


class FormaPagamentoIn(BaseModel):
    """Onde pagar (ou receber de) um cliente/fornecedor."""

    tipo: str = "PIX"          # PIX | DEPOSITO | TED | BOLETO | DINHEIRO | CARTAO | OUTRO
    apelido: str | None = None
    banco_codigo: str | None = None
    banco_nome: str | None = None
    agencia: str | None = None
    conta: str | None = None
    tipo_conta: str | None = "CORRENTE"
    operacao: str | None = None
    pix_tipo: str | None = None
    pix_chave: str | None = None
    titular: str | None = None
    documento_titular: str | None = None
    observacao: str | None = None
    principal: bool = False
    ativo: bool = True


class BancoIn(BaseModel):
    empresa_id: int
    codigo: str | None = None
    nome: str
    codigo_banco: str | None = None
    agencia: str | None = None
    conta: str | None = None
    tipo: str = "CORRENTE"
    titular: str | None = None
    conta_contabil_id: int | None = None
    saldo_inicial: float = 0
    data_saldo_inicial: date | None = None
    ativo: bool = True


class CentroCustoIn(BaseModel):
    empresa_id: int
    codigo: str
    nome: str
    tipo: str | None = "ADMINISTRATIVO"
    pai_id: int | None = None
    aceita_lancamento: bool = True
    ativo: bool = True


class OperacaoIn(BaseModel):
    empresa_id: int
    codigo: str
    nome: str
    natureza: str = "ENTRADA"
    conta_contabil_id: int | None = None
    centro_custo_id: int | None = None
    descricao: str | None = None
    ativo: bool = True


class ContaContabilIn(BaseModel):
    empresa_id: int
    codigo: str
    nome: str
    tipo: str
    natureza: str = "D"
    analitica: bool = True
    pai_id: int | None = None
    grupo_dre: str | None = None
    saldo_inicial: float = 0
    ativo: bool = True


class ParametrosIn(BaseModel):
    empresa_id: int
    valores: dict[str, int | None]


class ItemIn(BaseModel):
    conta_contabil_id: int
    centro_custo_id: int | None = None
    operacao_id: int | None = None
    descricao: str | None = None
    valor: float


class ParcelaIn(BaseModel):
    numero: int | None = None
    data_vencimento: date
    valor: float
    observacao: str | None = None


class LancamentoIn(BaseModel):
    empresa_id: int
    tipo: str                       # RECEBER | PAGAR
    modo: str = "SIMPLES"           # SIMPLES | MULTIPLO
    numero_documento: str | None = None
    parceiro_id: int | None = None
    descricao: str
    data_emissao: date | None = None
    data_competencia: date | None = None
    valor_total: float
    operacao_id: int | None = None
    observacao: str | None = None
    itens: list[ItemIn] = []
    parcelas: list[ParcelaIn] = []
    # Geração automática de parcelas quando `parcelas` vem vazio
    num_parcelas: int = 1
    primeiro_vencimento: date | None = None
    intervalo_dias: int = 30
    periodicidade: str = "MENSAL"   # MENSAL | DIAS
    # Baixa imediata (ex.: venda/despesa paga à vista)
    baixar_agora: bool = False
    banco_id: int | None = None


class BaixaIn(BaseModel):
    banco_id: int
    data: date | None = None
    valor: float | None = None      # valor do título a abater (padrão: saldo)
    juros: float = 0
    multa: float = 0
    desconto: float = 0
    forma_pagamento: str = "DINHEIRO"
    forma_parceiro_id: int | None = None   # conta/chave do parceiro usada no pagamento
    historico: str | None = None


class BaixaLoteIn(BaseModel):
    parcela_ids: list[int]
    banco_id: int
    data: date | None = None
    forma_pagamento: str = "DINHEIRO"
    historico: str | None = None


class UnidadeIn(BaseModel):
    """Unidade de medida negociada."""

    empresa_id: int
    codigo: str
    nome: str
    peso_conversao: float = 0      # quantos quilos vale uma unidade
    observacao: str | None = None
    ativo: bool = True


class ModalidadeIn(BaseModel):
    empresa_id: int
    codigo: str
    nome: str
    descricao: str | None = None
    ativo: bool = True


class ProdutoIn(BaseModel):
    empresa_id: int
    codigo: str
    nome: str
    unidade_id: int | None = None
    embalagem: str | None = None
    descricao: str | None = None
    ativo: bool = True


class AliquotaIcmsIn(BaseModel):
    """Linha da tabela de ICMS: UF do vendedor x UF do comprador (x produto)."""

    empresa_id: int
    uf_origem: str
    uf_destino: str
    produto_id: int | None = None    # vazio = todos os produtos
    aliquota: float = 0
    observacao: str | None = None
    ativo: bool = True


class GerarIcmsPadraoIn(BaseModel):
    """Gera as alíquotas interestaduais de referência a partir de um estado."""

    empresa_id: int
    uf_origem: str
    aliquota_interna: float | None = None   # opcional: operação dentro do próprio estado
    substituir: bool = False                # True = sobrescreve as linhas gerais já existentes


class PacotesUsuariosIn(BaseModel):
    """Pedido de pacotes de usuários extras."""

    quantidade: int = 1


class ContratoIn(BaseModel):
    """Contrato de compra e venda intermediado (corretagem)."""

    empresa_id: int
    tipo: str = "CORRETAGEM"          # CORRETAGEM | COMPRA | VENDA
    numero: str | None = None        # em branco = numeração automática
    data: date | None = None
    # na compra o comprador é a empresa; na venda o vendedor é a empresa
    comprador_id: int | None = None
    vendedor_id: int | None = None
    agente_id: int | None = None          # quem intermediou (opcional)
    agente_percentual: float = 0
    agente_valor: float | None = None     # em branco = calculado pelo percentual
    corretor: str | None = None
    representante_id: int | None = None
    produto_id: int | None = None
    modalidade_id: int | None = None
    unidade_id: int | None = None
    produto: str | None = "CAFÉ"
    modalidade: str | None = None
    embalagem: str | None = None
    unidade: str | None = "SACA"
    quantidade: float = 0
    preco_unitario: float = 0
    diferencial: float = 0
    valor_total: float | None = None      # em branco = quantidade x (preço + diferencial)
    local_coleta: str | None = None
    local_descarga: str | None = None
    numero_compra: str | None = None
    numero_venda: str | None = None
    data_embarque: date | None = None
    data_pagamento: date | None = None
    comissao_comprador_percentual: float = 0
    comissao_comprador_valor: float | None = None   # em branco = calculado pelo percentual
    comissao_vendedor_percentual: float = 0
    comissao_vendedor_valor: float | None = None
    icms_percentual: float | None = None   # usado só quando icms_manual = True
    icms_manual: bool = False              # False = alíquota da tabela de ICMS
    conta_contabil_id: int | None = None
    centro_custo_id: int | None = None
    operacao_id: int | None = None
    observacao: str | None = None


class GerarRecebiveisIn(BaseModel):
    """Opções da geração dos títulos do contrato.

    Corretagem: contas a receber das comissões do comprador e do vendedor.
    Compra: conta a pagar do fornecedor (mercadoria) e do agente.
    Venda: conta a receber do cliente (mercadoria) e conta a pagar do agente.
    """

    vencimento: date | None = None        # padrão: data de pagamento do contrato
    num_parcelas: int = 1
    periodicidade: str = "MENSAL"         # MENSAL | DIAS
    intervalo_dias: int = 30
    gerar_comprador: bool = True
    gerar_vendedor: bool = True
    gerar_mercadoria: bool = True         # compra/venda
    gerar_agente: bool = True             # comissão do agente
    vencimento_agente: date | None = None  # padrão: o mesmo da mercadoria
    num_parcelas_agente: int = 1


class MovimentoCaixaIn(BaseModel):
    empresa_id: int
    banco_id: int
    data: date | None = None
    tipo: str                       # E | S
    valor: float
    historico: str
    conta_contabil_id: int
    centro_custo_id: int | None = None
    operacao_id: int | None = None
    parceiro_id: int | None = None
    documento: str | None = None


class TransferenciaIn(BaseModel):
    empresa_id: int
    banco_origem_id: int
    banco_destino_id: int
    data: date | None = None
    valor: float
    historico: str | None = None


# --------------------------------------------------------------------------- #
# Administração do site: acesso das empresas e dos usuários
# --------------------------------------------------------------------------- #
class AcessoEmpresaIn(BaseModel):
    """LIBERAR = acesso até a data `ate` (depois disso bloqueia sozinho);
    BLOQUEAR = bloqueia agora."""

    acao: str = "LIBERAR"
    ate: date | None = None
    observacao: str | None = None


class LimiteUsuariosIn(BaseModel):
    """Número de usuários da empresa. Vazio/0 volta ao padrão do plano."""

    limite: int | None = None


class AcessoUsuarioIn(BaseModel):
    ativo: bool = True
    acesso_ate: date | None = None
