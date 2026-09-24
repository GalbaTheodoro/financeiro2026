"""Os planos de assinatura e o que cada um libera.

A ideia
-------
Antes existia **um sistema só**, vendido por 6 ou 12 meses. Agora o que muda de
um plano para outro não é o prazo: é **o que a conta pode usar**. O prazo
continua existindo, mas é uma segunda escolha dentro do mesmo plano.

Então o plano tem duas partes, e o código guarda as duas juntas::

    P3_ANUAL  =  Plano 3  +  12 meses

Os quatro planos:

=========  ==========================================  ==========  =========
Plano      Além do contrato, financeiro e NF-e         Semestral   Anual
=========  ==========================================  ==========  =========
Plano 1    —                                             399,90     699,90
Plano 2    Cupom fiscal eletrônico                       459,90     859,90
Plano 3    GTA — Guia de Trânsito Animal                 519,90     969,90
Plano 4    Cupom fiscal **e** GTA                        579,90   1.069,90
=========  ==========================================  ==========  =========

Os valores acima são só o **padrão de fábrica**: o administrador do site muda
cada um deles em *Configurações do site → Planos e teste*, e é o que estiver
guardado lá que vale.

Como o sistema barra o que não foi contratado
---------------------------------------------
Cada plano tem uma lista de **módulos**. Cada módulo tem uma lista de **rotas**
do menu. Daí saem as duas barreiras, e as duas são necessárias:

* no **servidor**, `exigir_modulo` (em `deps.py`) recusa a chamada com a frase
  dizendo qual plano tem aquilo — porque esconder botão não é segurança;
* na **tela**, o menu simplesmente não mostra o que a conta não tem.

Contas antigas
--------------
Quem assinou quando existia só ``SEMESTRAL``/``ANUAL`` contratou o sistema
inteiro do jeito que ele era. Então esses dois códigos valem como **Plano 4**:
ninguém perde nada numa atualização.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Os módulos
# --------------------------------------------------------------------------- #
# codigo -> (nome curto, frase da página inicial)
MODULOS: dict[str, tuple[str, str]] = {
    "CONTRATOS": (
        "Contrato de assessoria",
        "Contratos de corretagem, compra e venda, com comissão dos dois lados e "
        "impressão em PDF.",
    ),
    "FINANCEIRO": (
        "Financeiro",
        "Contas a receber e a pagar, caixa e bancos, DRE, balancete e relatórios.",
    ),
    "NFE": (
        "Emissão de NF-e",
        "NF-e 4.00 assinada e transmitida à SEFAZ, DANFE, envio por e-mail e busca "
        "dos documentos emitidos contra o CNPJ.",
    ),
    "CUPOM": (
        "Cupom fiscal eletrônico",
        "NFC-e modelo 65 para venda no balcão, com QR Code e impressão em 80 mm.",
    ),
    "GTA": (
        "GTA — Guia de Trânsito Animal",
        "Controle das guias dos produtores, aviso de validade e ficha de preparo "
        "para o portal do estado.",
    ),
}

# O que todo plano tem.
BASE: tuple[str, ...] = ("CONTRATOS", "FINANCEIRO", "NFE")

# Rotas do menu que cada módulo libera. O que não está aqui é de todo mundo
# (cadastros, minha assinatura e a área do administrador).
ROTAS: dict[str, tuple[str, ...]] = {
    "CONTRATOS": ("/contratos",),
    "FINANCEIRO": ("/painel", "/receber", "/pagar", "/caixa", "/relatorios"),
    "NFE": ("/notas", "/dfe"),
    "CUPOM": ("/cupom",),
    "GTA": ("/gta",),
}

# --------------------------------------------------------------------------- #
# Os quatro planos
# --------------------------------------------------------------------------- #
NIVEIS: list[dict] = [
    {"nivel": 1, "nome": "Plano 1", "extras": (),
     "semestral": 399.90, "anual": 699.90,
     "para": "Quem trabalha com contrato, financeiro e nota fiscal."},
    {"nivel": 2, "nome": "Plano 2", "extras": ("CUPOM",),
     "semestral": 459.90, "anual": 859.90,
     "para": "Quem também vende no balcão e precisa do cupom fiscal."},
    {"nivel": 3, "nome": "Plano 3", "extras": ("GTA",),
     "semestral": 519.90, "anual": 969.90,
     "para": "Quem atende produtor de gado e controla as guias de trânsito."},
    {"nivel": 4, "nome": "Plano 4", "extras": ("CUPOM", "GTA"),
     "semestral": 579.90, "anual": 1069.90,
     "para": "O sistema inteiro: balcão e trânsito animal juntos."},
]

PERIODOS: dict[str, str] = {"SEMESTRAL": "Semestral", "ANUAL": "Anual"}

# Contas de antes dos planos separados: contrataram o sistema inteiro.
NIVEL_DAS_CONTAS_ANTIGAS = 4
NIVEL_PADRAO = 1


def modulos_do_nivel(nivel: int) -> tuple[str, ...]:
    for plano in NIVEIS:
        if plano["nivel"] == nivel:
            return BASE + tuple(plano["extras"])
    return BASE


def nome_do_nivel(nivel: int) -> str:
    for plano in NIVEIS:
        if plano["nivel"] == nivel:
            return plano["nome"]
    return f"Plano {nivel}"


def todos_os_modulos() -> list[str]:
    return list(MODULOS)


# --------------------------------------------------------------------------- #
# O código do plano: "P3_ANUAL"
# --------------------------------------------------------------------------- #
def codigo(nivel: int, periodo: str) -> str:
    periodo = (periodo or "SEMESTRAL").upper()
    return f"P{nivel}_{periodo if periodo in PERIODOS else 'SEMESTRAL'}"


def separar(codigo_plano: str) -> tuple[int, str]:
    """Devolve (nível, período) de qualquer código, inclusive os antigos.

    ``SEMESTRAL`` e ``ANUAL`` sozinhos são de antes dos planos separados: valem
    como o plano completo, para nenhuma conta antiga perder o que já usava.
    """
    texto = (codigo_plano or "").strip().upper()
    if texto in PERIODOS:
        return NIVEL_DAS_CONTAS_ANTIGAS, texto
    if texto.startswith("P") and "_" in texto:
        marca, periodo = texto.split("_", 1)
        try:
            nivel = int(marca[1:])
        except ValueError:
            nivel = NIVEL_PADRAO
        if not any(p["nivel"] == nivel for p in NIVEIS):
            nivel = NIVEL_PADRAO
        return nivel, (periodo if periodo in PERIODOS else "SEMESTRAL")
    return NIVEL_PADRAO, "SEMESTRAL"


def modulos_do_plano(codigo_plano: str) -> tuple[str, ...]:
    nivel, _ = separar(codigo_plano)
    return modulos_do_nivel(nivel)


def rotas_dos_modulos(modulos) -> list[str]:
    """As rotas do menu liberadas por esses módulos."""
    liberadas: list[str] = []
    for modulo in modulos:
        liberadas.extend(ROTAS.get(modulo, ()))
    return liberadas


def modulo_da_rota(rota: str) -> str:
    """Qual módulo manda nessa rota. Vazio = rota de todo mundo."""
    for modulo, rotas in ROTAS.items():
        if rota in rotas:
            return modulo
    return ""


def planos_com(modulo: str) -> list[str]:
    """Os nomes dos planos que incluem esse módulo — para a frase do bloqueio."""
    return [p["nome"] for p in NIVEIS if modulo in modulos_do_nivel(p["nivel"])]


def frase_de_bloqueio(modulo: str) -> str:
    """O que a tela mostra quando a conta pede uma coisa que não contratou."""
    nome = MODULOS.get(modulo, (modulo, ""))[0]
    quais = planos_com(modulo)
    if not quais:
        return f"{nome} não está disponível no seu plano."
    lista = quais[0] if len(quais) == 1 else f"{', '.join(quais[:-1])} e {quais[-1]}"
    return (f"{nome} não faz parte do seu plano. Está no {lista}. "
            "Para mudar, vá em Minha Assinatura.")


# --------------------------------------------------------------------------- #
# Configurações: uma chave de preço para cada plano e prazo
# --------------------------------------------------------------------------- #
def chave_do_valor(nivel: int, periodo: str) -> str:
    return f"plano{nivel}_{(periodo or 'semestral').lower()}_valor"


def configuracoes_de_preco() -> dict[str, tuple[str, str, bool]]:
    """As oito chaves de preço, no formato do CONFIGURACOES_PADRAO."""
    saida: dict[str, tuple[str, str, bool]] = {}
    for plano in NIVEIS:
        for periodo, rotulo in (("semestral", "semestral"), ("anual", "anual")):
            saida[chave_do_valor(plano["nivel"], periodo)] = (
                f"{plano[periodo]:.2f}",
                f"Valor do {plano['nome']} {rotulo} (R$)",
                True,
            )
    return saida


def chaves_de_preco() -> list[str]:
    return [chave_do_valor(p["nivel"], periodo)
            for p in NIVEIS for periodo in ("semestral", "anual")]
