"""GTA — Guia de Trânsito Animal: as tabelas, a conferência e a ficha de preparo.

Por que não existe "transmitir GTA"
-----------------------------------
A GTA não é documento fiscal eletrônico como a NF-e: é documento de defesa
sanitária animal, e **a emissão fica no sistema do estado**, fechado, onde se
entra com login pessoal:

    Minas Gerais ..... SIAPEC / IMA      (ima.mg.gov.br)
    São Paulo ........ GEDAVE            (defesaagropecuaria.sp.gov.br)
    Goiás ............ SIDAGO            (agrodefesa.go.gov.br)
    Pará ............. Sigeagro          (adepara.pa.gov.br)
    Mato Grosso ...... INDEA             (indea.mt.gov.br)

Quem emite é o **produtor** ou o **médico-veterinário habilitado**, dentro do
portal, com a senha dele.

O webservice que existe — e não serve para emitir
-------------------------------------------------
Existe, sim, um webservice federal de GTA: o **``GtaEmitidaWsService``** da
**PGA — Plataforma de Gestão Agropecuária**, do Ministério da Agricultura
(SOAP, em ``pga.agricultura.gov.br/sispga_ws/GtaEmitidaWsService?wsdl``, e
``pgahom...`` em homologação).

Só que repare no nome: GTA **emitida**. O método principal é
``gravarGtaEmitida`` — quem chama já emitiu a guia e está *registrando* isso; o
manual descreve o serviço como "mantém informações da Guia de Trânsito Animal,
sem validação das informações do destino". Nada ali gera número de guia, valida
sanidade nem autoriza trânsito.

E quem chama é o **OESA** (Órgão Executor de Sanidade Agropecuária) — o IMA em
Minas, a Adepará no Pará. O fluxo é "dos OESAs para a PGA no MAPA": o estado
prestando contas ao governo federal, não um canal para o produtor ou a
assessoria emitir.

Os métodos de consulta (``obterGtasEmitidaEstadual``, ``obterGtasEmitidaDestino``,
``obterGtasEmitidaChave``) seriam **muito úteis** aqui — dariam para a GTA o que
o DF-e dá para a nota fiscal: buscar sozinho as guias em vez de digitá-las. Mas
o credenciamento é desenhado para OESA; enquanto não houver acesso, este módulo
não fala com serviço nenhum.

Fonte: Manual do Web Service da PGA (sites.google.com/agro.gov.br/manual-ws-pga).

Então este módulo faz as duas coisas que sobram, e que são as que faltavam:

1. **Guardar e controlar** as guias dos produtores atendidos — quem mandou,
   para onde, quantos animais, até quando vale.
2. **Preparar** a digitação: a ficha de preparo é a folha com tudo já
   conferido, na ordem das telas do portal, para quem for digitar não errar
   nem ficar procurando dado.

A conferência (``conferir``) é o coração disso: ela aponta, **antes** de a
pessoa abrir o portal, o que está faltando ou o que o portal vai recusar.
"""
from __future__ import annotations

from datetime import date

# --------------------------------------------------------------------------- #
# Tabelas
# --------------------------------------------------------------------------- #
# Faixas de idade como os portais pedem — os animais não entram como um número
# só, entram separados por sexo e idade, e a soma tem de bater.
FAIXAS_BOVINO = ["0 a 12 meses", "13 a 24 meses", "25 a 36 meses", "acima de 36 meses"]
FAIXAS_SUINO = ["0 a 3 meses", "4 a 8 meses", "acima de 8 meses"]
FAIXAS_SIMPLES = ["até 12 meses", "acima de 12 meses"]

ESPECIES: dict[str, list[str]] = {
    "BOVINO": FAIXAS_BOVINO,
    "BUBALINO": FAIXAS_BOVINO,
    "EQUINO": FAIXAS_SIMPLES,
    "MUAR": FAIXAS_SIMPLES,
    "SUINO": FAIXAS_SUINO,
    "OVINO": FAIXAS_SIMPLES,
    "CAPRINO": FAIXAS_SIMPLES,
    "AVES": ["qualquer idade"],
    "ABELHAS": ["qualquer idade"],
    "PEIXES": ["qualquer idade"],
}

SEXOS = {"M": "Macho", "F": "Fêmea"}

FINALIDADES = [
    "ABATE",
    "ENGORDA",
    "REPRODUCAO",
    "CRIA",
    "RECRIA",
    "EXPOSICAO",
    "LEILAO",
    "ESPORTE",
    "RETORNO",
    "QUARENTENA",
    "OUTRAS",
]

MEIOS_TRANSPORTE = ["RODOVIARIO", "A PE", "FERROVIARIO", "AQUAVIARIO", "AEREO"]

SITUACOES = ["PREPARO", "EMITIDA", "UTILIZADA", "CANCELADA", "VENCIDA"]

# Onde cada estado emite. Serve para a ficha de preparo dizer o nome certo do
# sistema e o endereço — é a primeira coisa que quem digita procura.
PORTAIS: dict[str, dict[str, str]] = {
    "MG": {"orgao": "IMA — Instituto Mineiro de Agropecuária",
           "sistema": "SIAPEC", "site": "https://sistemas.ima.mg.gov.br"},
    "SP": {"orgao": "CDA — Coordenadoria de Defesa Agropecuária",
           "sistema": "GEDAVE", "site": "https://gedave.defesaagropecuaria.sp.gov.br"},
    "GO": {"orgao": "Agrodefesa", "sistema": "SIDAGO",
           "site": "https://sidago.agrodefesa.go.gov.br"},
    "PA": {"orgao": "Adepará", "sistema": "Sigeagro",
           "site": "https://sigeagro.adepara.pa.gov.br"},
    "MT": {"orgao": "Indea-MT", "sistema": "SIGDEA/INDEA",
           "site": "https://sistemas.indea.mt.gov.br"},
    "BA": {"orgao": "ADAB", "sistema": "SIAPEC-BA", "site": "https://www.adab.ba.gov.br"},
    "ES": {"orgao": "Idaf-ES", "sistema": "SigDef", "site": "https://sistemas.idaf.es.gov.br"},
    "MS": {"orgao": "Iagro", "sistema": "e-Siapec", "site": "https://sistemas.iagro.ms.gov.br"},
    "PR": {"orgao": "Adapar", "sistema": "GTA Eletrônica",
           "site": "https://sistemas.adapar.pr.gov.br"},
    "RS": {"orgao": "SEAPDR-RS", "sistema": "SDA", "site": "https://www.agricultura.rs.gov.br"},
    "SC": {"orgao": "Cidasc", "sistema": "SIGEN+", "site": "https://sigen.cidasc.sc.gov.br"},
}

PORTAL_DESCONHECIDO = {
    "orgao": "órgão de defesa agropecuária do estado",
    "sistema": "sistema do estado",
    "site": "",
}

# Quantos dias antes do vencimento a tela já acende o aviso.
DIAS_DE_AVISO = 3


def portal(uf: str) -> dict:
    return PORTAIS.get((uf or "").upper(), PORTAL_DESCONHECIDO)


def faixas_da_especie(especie: str) -> list[str]:
    return ESPECIES.get((especie or "").upper(), FAIXAS_SIMPLES)


def tabelas() -> dict:
    """Tudo o que a tela precisa para montar os campos de escolha."""
    return {
        "especies": {nome: faixas for nome, faixas in ESPECIES.items()},
        "sexos": SEXOS,
        "finalidades": FINALIDADES,
        "meios_transporte": MEIOS_TRANSPORTE,
        "situacoes": SITUACOES,
        "portais": PORTAIS,
        "dias_de_aviso": DIAS_DE_AVISO,
    }


# --------------------------------------------------------------------------- #
# Validade
# --------------------------------------------------------------------------- #
def dias_para_vencer(guia, hoje: date | None = None) -> int | None:
    """Quantos dias faltam. Negativo = venceu. ``None`` = guia sem validade."""
    if not guia.data_validade:
        return None
    return (guia.data_validade - (hoje or date.today())).days


def situacao_mostrada(guia, hoje: date | None = None) -> str:
    """A situação que a tela mostra — a guardada, corrigida pela data.

    Uma guia EMITIDA que passou da validade aparece como VENCIDA sem ninguém
    precisar marcar nada. Cancelada e utilizada não mudam: já acabaram.
    """
    situacao = (guia.situacao or "PREPARO").upper()
    if situacao != "EMITIDA":
        return situacao
    faltam = dias_para_vencer(guia, hoje)
    if faltam is not None and faltam < 0:
        return "VENCIDA"
    return situacao


def aviso_de_validade(guia, hoje: date | None = None) -> str:
    """A frase do aviso, em português de gente. Em branco = nada a avisar."""
    if (guia.situacao or "").upper() != "EMITIDA":
        return ""
    faltam = dias_para_vencer(guia, hoje)
    if faltam is None:
        return ""
    if faltam < 0:
        dias = abs(faltam)
        return (f"Esta guia venceu há {dias} dia{'s' if dias > 1 else ''}. "
                "Se a carga ainda não andou, é preciso emitir outra no portal.")
    if faltam == 0:
        return "Esta guia vence hoje — a carga tem de sair hoje."
    if faltam <= DIAS_DE_AVISO:
        return f"Faltam {faltam} dia{'s' if faltam > 1 else ''} para esta guia vencer."
    return ""


# --------------------------------------------------------------------------- #
# Conferência — o que o portal vai cobrar
# --------------------------------------------------------------------------- #
def _vazio(valor) -> bool:
    return not (str(valor or "").strip())


def conferir(guia, hoje: date | None = None) -> list[str]:
    """O que falta ou está errado, **antes** de abrir o portal.

    Devolve as frases prontas para a tela. Lista vazia = pode digitar.
    """
    faltas: list[str] = []

    if _vazio(guia.especie):
        faltas.append("Falta a espécie dos animais (bovino, suíno, equino...).")
    if _vazio(guia.finalidade):
        faltas.append("Falta a finalidade do transporte (abate, engorda, reprodução...). "
                      "O portal pede isso na primeira tela.")

    for lado, nome in (("origem", "origem"), ("destino", "destino")):
        if _vazio(getattr(guia, f"{lado}_nome")):
            faltas.append(f"Falta o nome do produtor de {nome}.")
        if _vazio(getattr(guia, f"{lado}_propriedade")):
            faltas.append(f"Falta o nome da propriedade de {nome} — "
                          "o portal procura a propriedade, não a pessoa.")
        if _vazio(getattr(guia, f"{lado}_inscricao")):
            faltas.append(f"Falta a inscrição estadual da propriedade de {nome}. "
                          "É por ela que o portal acha o cadastro.")
        if _vazio(getattr(guia, f"{lado}_municipio")) or _vazio(getattr(guia, f"{lado}_uf")):
            faltas.append(f"Falta o município e o estado de {nome}.")

    categorias = list(getattr(guia, "categorias", None) or [])
    soma = sum(int(c.quantidade or 0) for c in categorias)
    if not categorias or soma <= 0:
        faltas.append("Falta dizer quantos animais vão, separados por sexo e idade. "
                      "O portal não aceita um número só.")
    elif int(guia.quantidade or 0) != soma:
        faltas.append(f"A quantidade total da guia ({int(guia.quantidade or 0)}) não bate "
                      f"com a soma das categorias ({soma}).")

    faixas = faixas_da_especie(guia.especie)
    for categoria in categorias:
        if (categoria.sexo or "").upper() not in SEXOS:
            faltas.append("Uma categoria está sem o sexo do animal (macho ou fêmea).")
        if categoria.faixa and faixas and categoria.faixa not in faixas:
            faltas.append(
                f"A faixa de idade “{categoria.faixa}” não é uma das que o portal usa "
                f"para {(guia.especie or '').lower()}: {', '.join(faixas)}.")

    origem_uf = (guia.origem_uf or "").upper()
    destino_uf = (guia.destino_uf or "").upper()
    if origem_uf and destino_uf and origem_uf != destino_uf:
        faltas.append(f"O trânsito é de {origem_uf} para {destino_uf} — guia interestadual. "
                      "O portal vai exigir os exames sanitários em dia e, em geral, "
                      "a assinatura do médico-veterinário.")
        if _vazio(guia.veterinario) or _vazio(guia.crmv):
            faltas.append("Falta o médico-veterinário e o CRMV — sem eles a guia "
                          "interestadual não sai.")

    if (guia.meio_transporte or "RODOVIARIO").upper() == "RODOVIARIO" \
            and _vazio(guia.placa):
        faltas.append("Falta a placa do caminhão. No transporte rodoviário o portal pede.")

    if (guia.situacao or "").upper() == "EMITIDA":
        if _vazio(guia.numero):
            faltas.append("A guia está marcada como emitida mas está sem número.")
        if not guia.data_validade:
            faltas.append("A guia está marcada como emitida mas está sem a data de validade.")

    return faltas


# --------------------------------------------------------------------------- #
# A ficha de preparo
# --------------------------------------------------------------------------- #
def ficha_preparo(guia, empresa=None, hoje: date | None = None) -> dict:
    """A folha para levar ao portal: tudo conferido, na ordem das telas.

    A tela (e a impressão) só desenham o que vem daqui — a ordem dos blocos é a
    ordem em que o portal pergunta, de propósito.
    """
    uf = (guia.uf_emissora or guia.origem_uf or (empresa.uf if empresa else "") or "").upper()
    onde = portal(uf)
    categorias = list(getattr(guia, "categorias", None) or [])
    return {
        "portal": {"uf": uf, **onde},
        "faltas": conferir(guia, hoje),
        "blocos": [
            {"titulo": "1. Origem — de onde os animais saem",
             "linhas": [
                 ("Produtor", guia.origem_nome),
                 ("CPF/CNPJ", guia.origem_documento),
                 ("Propriedade", guia.origem_propriedade),
                 ("Inscrição estadual", guia.origem_inscricao),
                 ("Município/UF", _municipio(guia.origem_municipio, guia.origem_uf)),
             ]},
            {"titulo": "2. Destino — para onde vão",
             "linhas": [
                 ("Produtor", guia.destino_nome),
                 ("CPF/CNPJ", guia.destino_documento),
                 ("Propriedade", guia.destino_propriedade),
                 ("Inscrição estadual", guia.destino_inscricao),
                 ("Município/UF", _municipio(guia.destino_municipio, guia.destino_uf)),
             ]},
            {"titulo": "3. Os animais",
             "linhas": [
                 ("Espécie", guia.especie),
                 ("Finalidade", guia.finalidade),
                 ("Total de animais", str(int(guia.quantidade or 0))),
             ],
             "categorias": [
                 {"sexo": SEXOS.get((c.sexo or "").upper(), c.sexo or ""),
                  "faixa": c.faixa,
                  "quantidade": int(c.quantidade or 0),
                  "observacao": c.observacao or ""}
                 for c in categorias
             ]},
            {"titulo": "4. Transporte",
             "linhas": [
                 ("Meio", guia.meio_transporte or "RODOVIARIO"),
                 ("Transportador", guia.transportador),
                 ("Placa", guia.placa),
             ]},
            {"titulo": "5. Responsável técnico",
             "linhas": [
                 ("Médico-veterinário", guia.veterinario),
                 ("CRMV", guia.crmv),
             ]},
            {"titulo": "6. Depois de emitir, volte e anote aqui",
             "linhas": [
                 ("Número da GTA", guia.numero or "____________________"),
                 ("Série", guia.serie or "________"),
                 ("Data de emissão", _data(guia.data_emissao) or "____/____/________"),
                 ("Validade", _data(guia.data_validade) or "____/____/________"),
             ]},
        ],
        "observacao": guia.observacao or "",
    }


def _municipio(municipio, uf) -> str:
    municipio = (municipio or "").strip()
    uf = (uf or "").strip().upper()
    if municipio and uf:
        return f"{municipio}/{uf}"
    return municipio or uf


def _data(valor) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""
