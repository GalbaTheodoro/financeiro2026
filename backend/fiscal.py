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
    # ICMS
    "icms_cst",
    "icms_base",          # % do valor do item que entra na base
    "icms_reducao",
    "icms_aliquota",
    # PIS e COFINS
    "cst_pis",
    "cst_cofins",
    "pis_cofins_base",
    "pis_cofins_reducao",
    "aliquota_pis",
    "aliquota_cofins",
    "cst_ipi",
    "aliquota_ipi",
    # IBS e CBS
    "ibs_cbs_cst",
    "ibs_cbs_classe",
    "ibs_cbs_base",
    "ibs_cbs_reducao_base",
    "ibs_cbs_reducao_aliquota",
    "cbs_aliquota",
    "ibs_uf_aliquota",
    "ibs_mun_aliquota",
)

# Percentuais de base: 100 é o normal e não precisa ser mandado para o item.
_BASES_PADRAO = {"icms_base": 100.0, "pis_cofins_base": 100.0, "ibs_cbs_base": 100.0}

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

    **Zero é zero.** Todo número da regra é mandado como está — base 0%, alíquota
    0% ou redução 0% são decisões da legislação cadastrada, não campos vazios. Só
    texto em branco (CST, cClassTrib, CFOP) fica de fora, porque aí não há o que
    aplicar. Quando não existe regra nenhuma, este dicionário volta vazio e a
    conta cai nos padrões — é o único caso em que padrão entra.
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
        elif valor is not None:
            valores[campo] = float(valor)
    # base nunca fica sem número: regra antiga sem a coluna vale pelo valor inteiro
    for campo, padrao in _BASES_PADRAO.items():
        if valores.get(campo) is None:
            valores[campo] = padrao
    return valores


# --------------------------------------------------------------------------- #
# A conta: percentual de base -> base em reais -> imposto
# --------------------------------------------------------------------------- #
# ICMS que não destaca valor: isento, não tributado, diferido e já cobrado por ST
ICMS_SEM_VALOR = ("40", "41", "50", "51", "60")
# CSOSN do Simples Nacional que também não destacam ICMS
CSOSN_SEM_VALOR = ("102", "103", "300", "400", "500")


def _num(*candidatos, padrao: float = 0.0) -> float:
    """O primeiro número que veio preenchido; senão o padrão."""
    for valor in candidatos:
        if valor is not None and valor != "":
            return float(valor)
    return float(padrao)


def _primeiro_texto(*candidatos) -> str | None:
    for valor in candidatos:
        if valor is None:
            continue
        texto = str(valor).strip()
        if texto:
            return texto
    return None


def _montar_base(total: float, percentual: float, reducao: float,
                 digitada) -> tuple[float, float]:
    """Base cheia e base depois da redução.

    A regra diz **quanto do valor do item entra na base** (100% é o normal) e
    **quanto dessa base é reduzido**. Quando a tela digita a base em reais, ela
    já é a base final — a redução não é aplicada de novo em cima.
    """
    if digitada is not None and digitada != "":
        base = round(float(digitada), 2)
        return base, base
    cheia = round(total * float(percentual or 0) / 100, 2)
    if not reducao:
        return cheia, cheia
    return cheia, round(cheia * (1 - float(reducao) / 100), 2)


def calcular(valores: dict | None, total: float, digitado: dict | None = None) -> dict:
    """Faz a conta de um item: percentual de base → base em reais → imposto.

    É a **mesma** função que a emissão usa para gravar o item e que a tela de
    regras usa para mostrar a conta enquanto a pessoa digita — assim o que se vê
    na tabela é exatamente o que vai sair na nota.

    * `valores` é o que `valores_da_regra()` devolveu;
    * `digitado` são os campos que a tela mandou preenchidos, que vencem a regra.

    **Zero é zero**: base 0%, alíquota 0% ou redução 0% vindas da regra valem
    como estão. Os padrões de IBS/CBS só entram quando `valores` vem vazio — ou
    seja, quando nenhuma regra serviu para o item.
    """
    from . import emissao as nfe          # só para as alíquotas de teste de 2026

    r = valores or {}
    d = {k: v for k, v in (digitado or {}).items() if v is not None and v != ""}
    total = round(float(total or 0), 2)

    def numero(campo, padrao=0.0):
        return _num(d.get(campo), r.get(campo), padrao=padrao)

    def texto(campo):
        return _primeiro_texto(d.get(campo), r.get(campo))

    # ------------------------------------------------------------------- ICMS
    perc_icms = _num(r.get("icms_base"), padrao=100.0)
    red_icms = numero("icms_reducao")
    cheia_icms, base_icms = _montar_base(total, perc_icms, red_icms, d.get("icms_base"))
    cst_icms = texto("icms_cst") or ""
    aliq_icms = numero("icms_aliquota")
    if d.get("icms_valor") is not None:
        icms = round(float(d["icms_valor"]), 2)
    elif cst_icms[:2] in ICMS_SEM_VALOR or cst_icms.zfill(3) in CSOSN_SEM_VALOR:
        icms = 0.0                        # diferido, isento, ST: não destaca
    else:
        icms = round(base_icms * aliq_icms / 100, 2)

    # --------------------------------------------------------- PIS, COFINS, IPI
    perc_pc = _num(r.get("pis_cofins_base"), padrao=100.0)
    red_pc = numero("pis_cofins_reducao")
    cheia_pc, base_pc = _montar_base(total, perc_pc, red_pc, d.get("pis_cofins_base"))
    aliq_pis = numero("aliquota_pis")
    aliq_cofins = numero("aliquota_cofins")
    pis = (round(float(d["pis_valor"]), 2) if d.get("pis_valor") is not None
           else round(base_pc * aliq_pis / 100, 2))
    cofins = (round(float(d["cofins_valor"]), 2) if d.get("cofins_valor") is not None
              else round(base_pc * aliq_cofins / 100, 2))
    aliq_ipi = numero("aliquota_ipi")
    ipi = (round(float(d["ipi_valor"]), 2) if d.get("ipi_valor") is not None
           else round(total * aliq_ipi / 100, 2))

    # --------------------------------------------------- IBS e CBS (reforma)
    perc_ibs = _num(r.get("ibs_cbs_base"), padrao=100.0)
    red_ibs = numero("ibs_cbs_reducao_base")
    cheia_ibs, base_ibs = _montar_base(total, perc_ibs, red_ibs, d.get("ibs_cbs_base"))
    # redutor de alíquota da reforma: desconta das três alíquotas de uma vez
    red_aliq = numero("ibs_cbs_reducao_aliquota")
    fator = 1 - red_aliq / 100
    aliq_ibs_uf = round(numero("ibs_uf_aliquota", nfe.IBS_UF_PADRAO) * fator, 4)
    aliq_ibs_mun = round(numero("ibs_mun_aliquota", nfe.IBS_MUN_PADRAO) * fator, 4)
    aliq_cbs = round(numero("cbs_aliquota", nfe.CBS_PADRAO) * fator, 4)
    ibs_uf = (round(float(d["ibs_uf_valor"]), 2) if d.get("ibs_uf_valor") is not None
              else round(base_ibs * aliq_ibs_uf / 100, 2))
    ibs_mun = (round(float(d["ibs_mun_valor"]), 2) if d.get("ibs_mun_valor") is not None
               else round(base_ibs * aliq_ibs_mun / 100, 2))
    cbs = (round(float(d["cbs_valor"]), 2) if d.get("cbs_valor") is not None
           else round(base_ibs * aliq_cbs / 100, 2))

    return {
        "valor_item": total,
        "icms": {
            "cst": cst_icms or None,
            "percentual_base": perc_icms, "reducao": red_icms,
            "base_cheia": cheia_icms, "base": base_icms,
            "aliquota": aliq_icms, "valor": icms,
        },
        "pis_cofins": {
            "cst_pis": texto("cst_pis"), "cst_cofins": texto("cst_cofins"),
            "percentual_base": perc_pc, "reducao": red_pc,
            "base_cheia": cheia_pc, "base": base_pc,
            "aliquota_pis": aliq_pis, "valor_pis": pis,
            "aliquota_cofins": aliq_cofins, "valor_cofins": cofins,
        },
        "ipi": {
            "cst": texto("cst_ipi"), "base": total,
            "aliquota": aliq_ipi, "valor": ipi,
        },
        "ibs_cbs": {
            "cst": texto("ibs_cbs_cst"), "classe": texto("ibs_cbs_classe"),
            "percentual_base": perc_ibs, "reducao": red_ibs,
            "base_cheia": cheia_ibs, "base": base_ibs,
            "reducao_aliquota": red_aliq,
            "aliquota_cbs": aliq_cbs, "valor_cbs": cbs,
            "aliquota_ibs_uf": aliq_ibs_uf, "valor_ibs_uf": ibs_uf,
            "aliquota_ibs_mun": aliq_ibs_mun, "valor_ibs_mun": ibs_mun,
        },
        "total_impostos": round(icms + pis + cofins + ipi + cbs + ibs_uf + ibs_mun, 2),
    }


def calcular_da_regra(regra: RegraFiscal | None, total: float,
                      digitado: dict | None = None) -> dict:
    """Atalho: pega os valores da regra e já faz a conta."""
    return calcular(valores_da_regra(regra), total, digitado)


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


# Alíquotas usadas **só quando não existe regra nenhuma** para o item. Em 2026 a
# reforma está em fase de teste (IBS 0,1% e CBS 0,9%). Havendo regra, o que ela
# disser é o que vale — inclusive zero.
def padroes_sem_regra() -> dict:
    from . import emissao as nfe

    return {
        "ibs_uf_aliquota": nfe.IBS_UF_PADRAO,
        "ibs_mun_aliquota": nfe.IBS_MUN_PADRAO,
        "cbs_aliquota": nfe.CBS_PADRAO,
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
