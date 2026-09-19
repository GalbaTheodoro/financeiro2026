"""Tabela de classificação tributária do IBS/CBS (cClassTrib).

De onde vem
-----------
Informe Técnico 2025.002 (RFB e Comitê Gestor do IBS). Cada CST do IBS/CBS tem
uma lista de códigos de seis dígitos que dizem **por qual regra** aquela situação
é tributada — é o `cClassTrib` que vai no item da NF-e.

O que está aqui
---------------
Os códigos usados no dia a dia de quem negocia café e presta serviço, para dar
para escolher numa lista em vez de decorar número. **Não é a tabela inteira** (a
oficial passa de cento e sessenta códigos e muda a cada versão do informe): por
isso o campo continua aceitando qualquer código digitado à mão, e quem confirma
a classificação certa de cada operação é o contador.
"""
from __future__ import annotations

# (CST, cClassTrib, descrição)
TABELA: tuple[tuple[str, str, str], ...] = (
    # ---- 000 tributação integral
    ("000", "000001", "Situações tributadas integralmente pelo IBS e pela CBS"),
    ("000", "000002", "Exploração de via (pedágio)"),
    ("000", "000003", "Regime automotivo — projetos incentivados (art. 311)"),
    ("000", "000004", "Regime automotivo — projetos incentivados (art. 312)"),
    ("000", "000005", "Operação com EAC destinado à mistura com gasolina A"),
    # ---- 200 alíquota reduzida
    ("200", "200001", "Transporte de bens até zonas de processamento de exportação"),
    ("200", "200002", "Fornecimento a produtor rural não contribuinte ou transportador autônomo"),
    ("200", "200003", "Produtos destinados à alimentação humana (Anexo I da LC 214/2025)"),
    ("200", "200004", "Dispositivos médicos (Anexo XII)"),
    ("200", "200009", "Medicamentos registrados na Anvisa"),
    ("200", "200028", "Serviços de educação (Anexo II)"),
    ("200", "200029", "Serviços de saúde humana (Anexo III)"),
    ("200", "200032", "Medicamentos registrados na Anvisa"),
    ("200", "200047", "Bares e restaurantes"),
    ("200", "200052", "Serviços de profissões intelectuais de natureza científica, literária ou artística"),
    # ---- 400 isenção
    ("400", "400001", "Serviços de transporte público coletivo"),
    ("400", "400002", "Transporte público com medição por quilômetro rodado"),
    # ---- 410 imunidade e não incidência
    ("410", "410001", "Bonificações quando constam do próprio documento fiscal"),
    ("410", "410002", "Transferências entre estabelecimentos do mesmo contribuinte"),
    ("410", "410003", "Doações sem contraprestação em benefício do doador"),
    ("410", "410004", "Exportações de bens e de serviços"),
    ("410", "410005", "Fornecimentos realizados pela União, Estados e Municípios"),
    ("410", "410014", "Fornecimento por produtor rural não contribuinte"),
    ("410", "410030", "Estorno de crédito por perecimento, deterioração ou extravio"),
    # ---- 510 diferimento
    ("510", "510001", "Operações com energia elétrica sujeitas a diferimento"),
    # ---- 550 suspensão
    ("550", "550001", "Exportações de bens materiais"),
    ("550", "550014", "Zona de processamento de exportação"),
    ("550", "550021", "Industrialização destinada a exportação"),
    # ---- 620 tributação monofásica
    ("620", "620001", "Tributação monofásica sobre combustíveis"),
    ("620", "620002", "Tributação monofásica com responsabilidade de retenção"),
    ("620", "620006", "Tributação monofásica sobre combustíveis cobrada anteriormente"),
)

# Nome de cada CST do IBS/CBS, para a tela agrupar a lista
CST_IBS_CBS = {
    "000": "Tributação integral",
    "200": "Alíquota reduzida",
    "400": "Isenção",
    "410": "Imunidade e não incidência",
    "510": "Diferimento",
    "550": "Suspensão",
    "620": "Tributação monofásica",
}


def _sem_acento(texto: str) -> str:
    acentos = "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ"
    limpos = "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC"
    return texto.translate(str.maketrans(acentos, limpos))


def buscar(termo: str = "", cst: str = "") -> list[dict]:
    """Procura por código, por CST ou por palavra da descrição."""
    procura = _sem_acento((termo or "").strip().lower())
    filtro_cst = (cst or "").strip()
    achados = []
    for codigo_cst, codigo, descricao in TABELA:
        if filtro_cst and codigo_cst != filtro_cst:
            continue
        if procura and procura not in codigo and procura not in _sem_acento(descricao.lower()):
            continue
        achados.append({
            "cst": codigo_cst,
            "cst_nome": CST_IBS_CBS.get(codigo_cst, ""),
            "codigo": codigo,
            "descricao": descricao,
        })
    return achados


def descricao_de(codigo: str) -> str | None:
    """A descrição de um código, quando ele está na tabela resumida."""
    alvo = (codigo or "").strip()
    for _cst, valor, descricao in TABELA:
        if valor == alvo:
            return descricao
    return None
