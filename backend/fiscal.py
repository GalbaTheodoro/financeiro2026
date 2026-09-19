"""Regras fiscais da nota: cruza o tipo do cliente com o tipo do item.

Por que existe
--------------
Antes, o imposto de cada item saía do cadastro do produto — o mesmo café levava
a mesma tributação para qualquer cliente, o que não é verdade: café cru vendido
para indústria dentro de Minas é diferido; para fora do estado tem 7% ou 12%;
para exportação é imune; para consumidor final muda de novo. Cadastrar isso no
produto obrigaria a ter um produto por situação.

Agora cada **cliente** e cada **produto** recebem um *tipo fiscal*, e a tabela
de regras cruza os dois — na mesma ideia da tabela de ICMS dos contratos, que
cruza UF de origem com UF de destino, só que com mais dimensões.

Como a regra é escolhida
------------------------
Campo em branco na regra quer dizer **qualquer um**. Uma regra só é candidata
quando nenhum campo preenchido dela conflita com a nota. Entre as candidatas
ganha a **mais específica** — a que tem mais campos preenchidos casando —, e no
empate a de maior `prioridade`, depois a mais nova.

Peso de cada campo (quanto mais específico, mais pesa):

    tipo de cliente .... 32
    tipo de item ....... 16
    CFOP ............... 8
    UF de destino ...... 4
    UF de origem ....... 2
    operação ........... 1

Assim "café cru para indústria de fora do estado" vence "café cru para
qualquer um", que por sua vez vence "qualquer item para qualquer cliente".

O **CFOP** é o quinto elemento do cruzamento: é digitado no item da nota e a
regra que exige um CFOP só serve quando ele bate. Regra sem CFOP preenchido
continua valendo para qualquer CFOP — e, se o item ainda estiver sem CFOP, o da
regra é usado como sugestão.

A tributação continua sendo responsabilidade do contribuinte e do contador: o
sistema só aplica a tabela que a empresa cadastrou.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Parceiro, Produto, RegraFiscal, TipoFiscal

# Campos que a regra manda para o item, com o nome que têm no item da nota.
CAMPOS_DA_REGRA = (
    "cfop",
    "icms_origem",
    "icms_cst",
    "icms_reducao",
    "icms_aliquota",
    "cst_pis",
    "aliquota_pis",
    "cst_cofins",
    "aliquota_cofins",
    "cst_ipi",
    "aliquota_ipi",
    "ibs_cbs_cst",
    "ibs_cbs_classe",
    "ibs_uf_aliquota",
    "ibs_mun_aliquota",
    "cbs_aliquota",
)

PESOS = {
    "tipo_cliente_id": 32,
    "tipo_item_id": 16,
    "cfop": 8,
    "uf_destino": 4,
    "uf_origem": 2,
    "operacao": 1,
}


def _uf(valor: str | None) -> str | None:
    texto = (valor or "").strip().upper()
    return texto or None


def _texto(valor: str | None) -> str | None:
    texto = (valor or "").strip().upper()
    return texto or None


def pontuar(regra: RegraFiscal, contexto: dict) -> int | None:
    """Quanto a regra casa com a nota. `None` = não serve para esta nota."""
    pontos = 0
    for campo, peso in PESOS.items():
        exigido = getattr(regra, campo, None)
        if isinstance(exigido, str):
            exigido = _texto(exigido)
        if exigido in (None, ""):
            continue                      # em branco na regra = serve para qualquer um
        atual = contexto.get(campo)
        if isinstance(atual, str):
            atual = _texto(atual)
        if campo == "cfop" and atual in (None, ""):
            # item ainda sem CFOP: a regra não é descartada, só não ganha o ponto
            continue
        if atual is None or str(atual) != str(exigido):
            return None                   # a regra exige algo que esta nota não tem
        pontos += peso
    return pontos


def escolher_regra(db: Session, empresa_id: int, contexto: dict) -> RegraFiscal | None:
    """A regra mais específica que serve para este item desta nota."""
    candidatas = (
        db.query(RegraFiscal)
        .filter(RegraFiscal.empresa_id == empresa_id, RegraFiscal.ativo.is_(True))
        .all()
    )
    melhor, melhor_nota = None, None
    for regra in candidatas:
        pontos = pontuar(regra, contexto)
        if pontos is None:
            continue
        chave = (pontos, int(regra.prioridade or 0), int(regra.id or 0))
        if melhor_nota is None or chave > melhor_nota:
            melhor, melhor_nota = regra, chave
    return melhor


def montar_contexto(db: Session, empresa, parceiro: Parceiro | None,
                    produto: Produto | None, operacao: str = "SAIDA",
                    tipo_cliente_id: int | None = None,
                    tipo_item_id: int | None = None,
                    cfop: str | None = None) -> dict:
    """Junta o que define a situação: CFOP, quem compra, o que é, de onde para onde."""
    return {
        "tipo_cliente_id": tipo_cliente_id
        or (parceiro.tipo_fiscal_id if parceiro else None),
        "tipo_item_id": tipo_item_id or (produto.tipo_fiscal_id if produto else None),
        # o CFOP do item; sem ele, o CFOP padrão do produto — que é o que o
        # item vai levar mesmo, então o cruzamento fica igual ao da nota pronta
        "cfop": _texto(cfop) or _texto(produto.cfop_padrao if produto else None),
        "uf_origem": _uf(empresa.uf if empresa else None),
        "uf_destino": _uf(parceiro.uf if parceiro else (empresa.uf if empresa else None)),
        "operacao": _texto(operacao) or "SAIDA",
    }


def valores_da_regra(regra: RegraFiscal | None) -> dict:
    """O que a regra manda aplicar, já pronto para virar campo do item.

    Texto em branco e alíquota zero **não** são mandados: assim uma regra que só
    trata do ICMS não apaga o PIS que veio do cadastro do produto.
    """
    if regra is None:
        return {}
    valores = {}
    for campo in CAMPOS_DA_REGRA:
        valor = getattr(regra, campo, None)
        if isinstance(valor, str):
            valor = valor.strip()
            if valor:
                valores[campo] = valor
        elif valor is not None and float(valor or 0) != 0:
            valores[campo] = float(valor)
    return valores


def explicar(db: Session, regra: RegraFiscal | None) -> dict | None:
    """Resumo da regra escolhida, para a tela dizer por que aquele imposto saiu."""
    if regra is None:
        return None
    nomes = {}
    for campo in ("tipo_cliente_id", "tipo_item_id"):
        identificador = getattr(regra, campo, None)
        if identificador:
            tipo = db.get(TipoFiscal, identificador)
            nomes[campo] = tipo.nome if tipo else None
    partes = []
    if nomes.get("tipo_cliente_id"):
        partes.append(f"cliente {nomes['tipo_cliente_id']}")
    if nomes.get("tipo_item_id"):
        partes.append(f"item {nomes['tipo_item_id']}")
    if regra.cfop:
        partes.append(f"CFOP {regra.cfop}")
    if regra.uf_origem or regra.uf_destino:
        partes.append(f"{regra.uf_origem or 'qualquer UF'} → {regra.uf_destino or 'qualquer UF'}")
    if regra.operacao:
        partes.append(regra.operacao.lower())
    return {
        "id": regra.id,
        "nome": regra.nome or "Regra fiscal",
        "resumo": " · ".join(partes) or "vale para qualquer cliente e qualquer item",
        "observacao": regra.observacao,
        "valores": valores_da_regra(regra),
    }


# --------------------------------------------------------------------------- #
# Tipos fiscais sugeridos, para a empresa não começar de uma tela vazia
# --------------------------------------------------------------------------- #
TIPOS_CLIENTE_PADRAO = [
    ("CONTRIB", "Contribuinte de ICMS", "Empresa inscrita, com inscrição estadual ativa."),
    ("INDUSTRIA", "Indústria", "Torrefação, cooperativa ou exportadora que industrializa."),
    ("PRODUTOR", "Produtor rural", "Produtor pessoa física ou jurídica, com inscrição de produtor."),
    ("NAOCONTRIB", "Não contribuinte", "Consumidor final e empresa sem inscrição estadual."),
    ("EXPORTACAO", "Exportação", "Saída para o exterior ou com fim específico de exportação."),
]

TIPOS_ITEM_PADRAO = [
    ("CAFECRU", "Café cru em grão", "Café em coco ou beneficiado, NCM 0901.11.10."),
    ("CAFEIND", "Café industrializado", "Torrado, moído ou solúvel."),
    ("SERVICO", "Serviço", "Corretagem, armazenagem e outros serviços."),
    ("USOCONSUMO", "Uso e consumo", "Material que não é para revenda."),
    ("IMOBILIZADO", "Imobilizado", "Bem do ativo."),
]


def criar_tipos_padrao(db: Session, empresa_id: int) -> list[TipoFiscal]:
    """Cria os tipos sugeridos que ainda não existem. Não mexe no que já está lá."""
    existentes = {
        (t.aplicacao, t.codigo)
        for t in db.query(TipoFiscal).filter(TipoFiscal.empresa_id == empresa_id).all()
    }
    criados = []
    for aplicacao, lista in (("CLIENTE", TIPOS_CLIENTE_PADRAO), ("ITEM", TIPOS_ITEM_PADRAO)):
        for codigo, nome, descricao in lista:
            if (aplicacao, codigo) in existentes:
                continue
            tipo = TipoFiscal(empresa_id=empresa_id, aplicacao=aplicacao, codigo=codigo,
                              nome=nome, descricao=descricao)
            db.add(tipo)
            criados.append(tipo)
    db.flush()
    return criados
