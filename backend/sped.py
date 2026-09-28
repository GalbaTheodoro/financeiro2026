"""SPED Fiscal — o arquivo da EFD ICMS/IPI, montado do que já está no sistema.

O que é
-------
A EFD ICMS/IPI (o "SPED Fiscal") é um arquivo de texto que o contribuinte
entrega mensalmente ao seu estado contando, documento por documento, tudo que
entrou e tudo que saiu. Não é um relatório: é um arquivo com leiaute fechado,
que o contador abre no **PVA** (o programa da Receita), valida, assina com o
certificado e transmite.

De onde vem cada coisa
----------------------
Nada aqui é digitado de novo. O arquivo é montado das três fontes que o AgroDock
já tem:

======================================  ==========================  =============
Fonte                                   Onde está                   Vira
======================================  ==========================  =============
Notas que a SEFAZ entregou (DF-e)       notas, origem = DFE         entradas
NF-e que a empresa emitiu (modelo 55)   notas, origem = EMITIDA     saídas
Cupons fiscais (NFC-e, modelo 65)       notas, origem = EMITIDA     saídas
Saldo do estoque                        produtos + movimentos       bloco H
======================================  ==========================  =============

Leiaute
-------
Leiaute **020** (Ato COTEPE/ICMS 01/2026), Guia Prático 3.2.3. O código da
versão sai do ano do período — arquivo de 2025 sai como 019 — porque quem gera
um mês atrasado precisa do código daquele ano, não do de hoje.

O que este módulo **não** faz
-----------------------------
* Não valida como o PVA valida. O PVA é a palavra final, e é ele que aponta o
  que falta. O que este módulo faz é a **conferência prévia** (``conferir``):
  aponta antes o que sabidamente derruba o arquivo — nota sem XML completo,
  item sem CFOP, produto sem NCM, empresa sem inscrição estadual.
* Não faz os ajustes da apuração (E111, E116, substituição tributária, saldo
  credor do mês anterior). O bloco E sai com o que dá para calcular das notas;
  o resto é do contador, no PVA.
* Não transmite. Quem assina e transmite é o contador, com o certificado dele
  ou com o da empresa, no PVA.

Simples Nacional
----------------
Empresa do Simples Nacional é, em regra, **dispensada** da EFD ICMS/IPI
(Ajuste SINIEF 2/2009) — quem apura por lá é o PGDAS-D. Alguns estados e
algumas atividades exigem de todo jeito, e contador nenhum reclama de receber
o arquivo. Então o sistema gera, mas: a apuração do bloco E sai **zerada**,
porque uma empresa do Simples não tem débito de ICMS próprio a apurar ali, e a
conferência diz isso em letras claras para ninguém achar que o número sumiu.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy.orm import Session, joinedload

from . import estoque as motor_estoque
from .models import (
    ConfigSped,
    Empresa,
    Nota,
    NotaItem,
    Parceiro,
    Produto,
)
from .utils import dinheiro, so_numeros

# --------------------------------------------------------------------------- #
# Leiaute
# --------------------------------------------------------------------------- #
# Cada Ato COTEPE de janeiro traz um código novo. A tabela guarda o que já
# existe; ano mais novo que o último conhecido usa o último (o leiaute costuma
# ser republicado sem mudar o que este módulo escreve).
VERSAO_POR_ANO: dict[int, str] = {
    2020: "014", 2021: "015", 2022: "016", 2023: "017",
    2024: "018", 2025: "019", 2026: "020",
}

# Perfil do arquivo: quanto detalhe o estado exige.
PERFIS: dict[str, str] = {
    "A": "Perfil A — detalhado, item por item (o que a maioria dos estados exige)",
    "B": "Perfil B — consolidado por totais",
    "C": "Perfil C — reduzido",
}

# Tipo do item no registro 0200.
TIPOS_DE_ITEM: dict[str, str] = {
    "00": "Mercadoria para revenda",
    "01": "Matéria-prima",
    "02": "Embalagem",
    "03": "Produto em processo",
    "04": "Produto acabado",
    "05": "Subproduto",
    "06": "Produto intermediário",
    "07": "Material de uso e consumo",
    "08": "Ativo imobilizado",
    "09": "Serviços",
    "10": "Outros insumos",
    "99": "Outras",
}

# Situação do documento (campo COD_SIT do C100).
SITUACAO_DO_DOCUMENTO: dict[str, str] = {
    "AUTORIZADA": "00",
    "CANCELADA": "02",
    "DENEGADA": "04",
    "DESCONHECIDA": "00",
}

# De/para CSOSN -> CST, para empresa do Simples Nacional.
#
# O item da nota de uma empresa do Simples leva **CSOSN** (101, 102, 500...),
# e o SPED Fiscal só conhece a tabela de **CST** (00, 20, 40, 60, 90...). Não
# existe de/para oficial, então o padrão aqui é o conservador: "90 — Outras",
# que não afirma benefício nenhum, e "60" no único caso de equivalência limpa
# (CSOSN 500 = ICMS já cobrado antes por substituição = CST 60).
#
# Quem quiser outro de/para escreve na configuração do SPED da empresa, no
# formato "101=20;102=90". O contador é quem sabe qual usar no estado dele.
CSOSN_PARA_CST: dict[str, str] = {
    "101": "90", "102": "90", "103": "90",
    "201": "90", "202": "90", "203": "90",
    "300": "90", "400": "90",
    "500": "60",
    "900": "90",
}

CSOSN = tuple(CSOSN_PARA_CST)

# Modelos de documento que este módulo escreve no bloco C.
MODELO_NFE = "55"
MODELO_CUPOM = "65"
MODELOS = (MODELO_NFE, MODELO_CUPOM)

# Regimes em que não há apuração de ICMS próprio para informar no bloco E.
CRT_DO_SIMPLES = ("1", "4")


def versao_do_layout(fim: date) -> str:
    """O código da versão do leiaute do ano do período que está sendo gerado."""
    anos = sorted(VERSAO_POR_ANO)
    ano = fim.year
    if ano in VERSAO_POR_ANO:
        return VERSAO_POR_ANO[ano]
    if ano < anos[0]:
        return VERSAO_POR_ANO[anos[0]]
    return VERSAO_POR_ANO[anos[-1]]


# --------------------------------------------------------------------------- #
# Formatação dos campos
# --------------------------------------------------------------------------- #
def _texto(valor, tamanho: int | None = None) -> str:
    """Campo de texto: sem pipe (o pipe é o separador), cortado no tamanho."""
    saida = str(valor or "").replace("|", " ").replace("\r", " ").replace("\n", " ").strip()
    return saida[:tamanho] if tamanho else saida


def _data(valor) -> str:
    """Data no formato ddmmaaaa. Vazio vira vazio."""
    if not valor:
        return ""
    if isinstance(valor, datetime):
        valor = valor.date()
    return f"{valor.day:02d}{valor.month:02d}{valor.year:04d}"


def _numero(valor, casas: int = 2, vazio_se_zero: bool = False) -> str:
    """Número no padrão do SPED: vírgula decimal, sem separador de milhar.

    Campo de valor que a tabela marca como *opcional* fica **vazio** quando é
    zero (é o que o Guia pede em vários deles); o obrigatório sai "0,00".
    """
    numero = float(valor or 0)
    if vazio_se_zero and abs(numero) < 10 ** -(casas + 1):
        return ""
    texto = f"{numero:.{casas}f}"
    return texto.replace(".", ",")


def _inteiro(valor, vazio_se_zero: bool = False) -> str:
    try:
        numero = int(valor or 0)
    except (TypeError, ValueError):
        return ""
    if vazio_se_zero and numero == 0:
        return ""
    return str(numero)


def _cst_do_sped(item_cst: str | None, origem: str | None, depara: dict) -> str:
    """CST do SPED: um dígito de origem + dois de CST.

    O item guarda a origem separada do CST (é assim que a NF-e pede). No SPED os
    dois viram um campo de três dígitos. CSOSN passa antes pelo de/para.
    """
    cst = so_numeros(item_cst)
    origem_digito = (so_numeros(origem) or "0")[:1] or "0"
    if not cst:
        return ""
    if len(cst) == 3 and cst in depara:          # CSOSN do Simples
        return origem_digito + depara[cst]
    if len(cst) == 3:                            # já veio origem + CST
        return cst
    return origem_digito + cst.zfill(2)[-2:]


def ler_depara(texto: str | None) -> dict:
    """Lê o de/para CSOSN -> CST escrito como "101=20;102=90"."""
    depara = dict(CSOSN_PARA_CST)
    for pedaco in (texto or "").replace(",", ";").split(";"):
        if "=" not in pedaco:
            continue
        csosn, cst = pedaco.split("=", 1)
        csosn = so_numeros(csosn)[:3]
        cst = so_numeros(cst)[:2]
        if csosn and cst:
            depara[csosn] = cst
    return depara


# --------------------------------------------------------------------------- #
# O arquivo em construção
# --------------------------------------------------------------------------- #
class Arquivo:
    """Junta as linhas e conta quantas de cada registro — é o que o bloco 9 pede.

    Toda linha começa e termina com pipe. As contagens são feitas na hora de
    escrever, porque no fim o arquivo precisa dizer, no 9900, quantas linhas de
    cada tipo ele tem — inclusive as linhas do próprio bloco 9.
    """

    def __init__(self) -> None:
        self.linhas: list[str] = []
        self.contagem: dict[str, int] = {}

    def escrever(self, *campos) -> None:
        registro = str(campos[0])
        self.linhas.append("|" + "|".join("" if c is None else str(c) for c in campos) + "|")
        self.contagem[registro] = self.contagem.get(registro, 0) + 1

    def quantas(self, prefixo: str) -> int:
        """Quantas linhas de um bloco — "0" conta 0000, 0005, 0150..."""
        return sum(q for reg, q in self.contagem.items() if reg.startswith(prefixo))

    def texto(self) -> str:
        return "\r\n".join(self.linhas) + "\r\n"

    def bytes(self) -> bytes:
        """O SPED pede ISO-8859-1. Caractere fora da tabela vira "?"."""
        return self.texto().encode("iso-8859-1", "replace")


# --------------------------------------------------------------------------- #
# Quais notas entram
# --------------------------------------------------------------------------- #
def _entre(valor: datetime | None, inicio: date, fim: date) -> bool:
    if not valor:
        return False
    dia = valor.date() if isinstance(valor, datetime) else valor
    return inicio <= dia <= fim


def notas_do_periodo(db: Session, empresa_id: int, inicio: date, fim: date) -> dict:
    """As notas do mês, já separadas em saídas e entradas, sem repetir chave.

    Uma nota emitida pela empresa também volta da SEFAZ na busca de documentos —
    a mesma chave apareceria duas vezes. Quem emitiu ganha: a nota de origem
    EMITIDA tem os itens e os impostos calculados, a cópia do DF-e não.
    """
    empresa = db.get(Empresa, empresa_id)
    cnpj_empresa = so_numeros(empresa.cnpj if empresa else "")

    consulta = (
        db.query(Nota)
        .options(joinedload(Nota.itens), joinedload(Nota.pagamentos))
        .filter(
            Nota.empresa_id == empresa_id,
            Nota.tipo == "NFE",
            Nota.data_emissao.isnot(None),
        )
        .order_by(Nota.data_emissao, Nota.numero)
    )

    saidas: list[Nota] = []
    entradas: list[Nota] = []
    fora: list[Nota] = []
    vistas: set[str] = set()

    todas = [n for n in consulta.all() if _entre(n.data_emissao, inicio, fim)]
    # emitidas primeiro, para a cópia do DF-e da mesma chave ser descartada
    todas.sort(key=lambda n: 0 if n.origem == "EMITIDA" else 1)

    for nota in todas:
        if (nota.modelo or MODELO_NFE) not in MODELOS:
            fora.append(nota)
            continue
        if nota.origem == "EMITIDA" and nota.status_emissao not in ("AUTORIZADA", "CANCELADA"):
            continue                      # rascunho e rejeitada não são documento fiscal
        if nota.chave in vistas:
            continue
        vistas.add(nota.chave)
        if nota.origem == "EMITIDA" or (
            cnpj_empresa and so_numeros(nota.emitente_cnpj) == cnpj_empresa
        ):
            saidas.append(nota)
        else:
            entradas.append(nota)

    saidas.sort(key=lambda n: (n.data_emissao, _inteiro(n.numero)))
    entradas.sort(key=lambda n: (n.data_emissao, _inteiro(n.numero)))
    return {"saidas": saidas, "entradas": entradas, "fora": fora, "cnpj": cnpj_empresa}


def _eh_cupom(nota: Nota) -> bool:
    return (nota.modelo or "") == MODELO_CUPOM


def _cancelada(nota: Nota) -> bool:
    return nota.situacao in ("CANCELADA", "DENEGADA") or nota.status_emissao == "CANCELADA"


def _situacao(nota: Nota) -> str:
    if nota.status_emissao == "CANCELADA" or nota.situacao == "CANCELADA":
        return "02"
    return SITUACAO_DO_DOCUMENTO.get(nota.situacao or "AUTORIZADA", "00")


# --------------------------------------------------------------------------- #
# Conferência prévia
# --------------------------------------------------------------------------- #
def conferir(db: Session, empresa_id: int, inicio: date, fim: date) -> dict:
    """O que impede (ou atrapalha) a geração, antes de gerar.

    Devolve duas listas: ``impedimentos`` — o que o PVA com certeza recusa — e
    ``avisos`` — o que sai, mas o contador vai perguntar. A tela mostra as duas
    e só libera o download quando não há impedimento.
    """
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        return {"impedimentos": ["Empresa não encontrada."], "avisos": [], "notas": {}}

    impedimentos: list[str] = []
    avisos: list[str] = []

    if not so_numeros(empresa.cnpj):
        impedimentos.append("A empresa está sem CNPJ (Cadastros → Empresas).")
    if not (empresa.inscricao_estadual or "").strip():
        impedimentos.append(
            "A empresa está sem inscrição estadual. O SPED Fiscal é da IE: sem ela o "
            "arquivo não abre no PVA.")
    if not (empresa.uf or "").strip():
        impedimentos.append("A empresa está sem UF.")
    if not so_numeros(empresa.codigo_municipio):
        impedimentos.append(
            "A empresa está sem o código do município (IBGE, 7 dígitos) — Cadastros → Empresas.")

    config = config_da_empresa(db, empresa_id)
    if not (config.contador_nome or "").strip():
        avisos.append(
            "Não há contabilista cadastrado (registro 0100). O PVA aceita o arquivo, mas o "
            "contador normalmente pede que esteja lá — preencha em SPED Fiscal → Configuração.")

    dados = notas_do_periodo(db, empresa_id, inicio, fim)
    resumos: list[dict] = []
    sem_itens: list[dict] = []
    itens_sem_cfop: list[dict] = []
    produtos_sem_ncm: set[str] = set()
    participantes_sem_documento: set[str] = set()

    for nota in dados["entradas"]:
        ficha = {
            "id": nota.id, "numero": nota.numero, "serie": nota.serie,
            "emitente": nota.emitente_nome, "chave": nota.chave,
            "data": nota.data_emissao.date().isoformat() if nota.data_emissao else "",
            "manifestacao": nota.manifestacao or "",
        }
        if nota.resumo or not nota.xml:
            resumos.append(ficha)
            continue
        if not nota.itens:
            sem_itens.append(ficha)

    for nota in dados["saidas"] + dados["entradas"]:
        if _cancelada(nota):
            continue                       # cancelada só leva o cabeçalho: não precisa de item
        for item in nota.itens:
            if not so_numeros(item.cfop):
                itens_sem_cfop.append({
                    "id": nota.id, "numero": nota.numero, "item": item.numero,
                    "descricao": item.descricao,
                })
            if not so_numeros(item.ncm):
                produtos_sem_ncm.add(item.codigo or item.descricao or "?")

    for nota in dados["entradas"]:
        if not so_numeros(nota.emitente_cnpj):
            participantes_sem_documento.add(nota.emitente_nome or f"nota {nota.numero}")
    for nota in dados["saidas"]:
        if _eh_cupom(nota):
            continue                       # cupom não leva participante no SPED
        if not so_numeros(nota.destinatario_cnpj) and not nota.parceiro_id:
            participantes_sem_documento.add(nota.destinatario_nome or f"nota {nota.numero}")

    if resumos:
        impedimentos.append(
            f"{len(resumos)} nota(s) de entrada estão no sistema só como resumo — sem itens e "
            "sem CFOP, o PVA recusa. Use o botão \"Completar as notas\" para dar ciência na "
            "SEFAZ e baixar o XML inteiro.")
    if sem_itens:
        impedimentos.append(
            f"{len(sem_itens)} nota(s) de entrada têm o XML completo mas os itens nunca foram "
            "gravados. O botão \"Completar as notas\" grava.")
    if itens_sem_cfop:
        impedimentos.append(
            f"{len(itens_sem_cfop)} item(ns) estão sem CFOP. O CFOP é a chave do registro "
            "analítico (C190): sem ele não há arquivo.")
    if produtos_sem_ncm:
        avisos.append(
            f"{len(produtos_sem_ncm)} produto(s) sem NCM. O registro 0200 sai sem a "
            "classificação fiscal e o PVA avisa.")
    if participantes_sem_documento:
        avisos.append(
            f"{len(participantes_sem_documento)} participante(s) sem CNPJ/CPF. Entram no "
            "registro 0150 sem documento, o que o PVA aponta.")
    if dados["fora"]:
        avisos.append(
            f"{len(dados['fora'])} documento(s) do período não são modelo 55 nem 65 e ficaram "
            "de fora (este arquivo cobre NF-e e cupom fiscal).")

    empresa_do_simples = (empresa.crt or "1") in CRT_DO_SIMPLES
    if empresa_do_simples:
        avisos.append(
            "A empresa está como Simples Nacional (CRT "
            f"{empresa.crt or '1'}). Quem é do Simples é, em regra, dispensado da EFD ICMS/IPI "
            "e não apura ICMS próprio — por isso o bloco E sai zerado. Os documentos saem "
            "todos; a apuração é do PGDAS-D.")

    return {
        "impedimentos": impedimentos,
        "avisos": avisos,
        "pode_gerar": not impedimentos,
        "notas": {
            "saidas": len(dados["saidas"]),
            "entradas": len(dados["entradas"]),
            "cupons": sum(1 for n in dados["saidas"] if _eh_cupom(n)),
            "canceladas": sum(1 for n in dados["saidas"] + dados["entradas"] if _cancelada(n)),
        },
        "resumos": resumos,
        "sem_itens": sem_itens,
        "itens_sem_cfop": itens_sem_cfop[:50],
        "produtos_sem_ncm": sorted(produtos_sem_ncm)[:50],
        "simples": empresa_do_simples,
        "perfil": config.perfil or "A",
        "versao": versao_do_layout(fim),
    }


# --------------------------------------------------------------------------- #
# Configuração por empresa
# --------------------------------------------------------------------------- #
def config_da_empresa(db: Session, empresa_id: int) -> ConfigSped:
    """A configuração do SPED daquela empresa, criando a linha em branco se faltar."""
    config = db.query(ConfigSped).filter(ConfigSped.empresa_id == empresa_id).first()
    if not config:
        config = ConfigSped(empresa_id=empresa_id)
        db.add(config)
        db.flush()
    return config


# --------------------------------------------------------------------------- #
# Participantes (0150) e itens (0200)
# --------------------------------------------------------------------------- #
class Participantes:
    """Junta quem apareceu nas notas do mês, um código por participante.

    O código (COD_PART) tem de ser estável: é ele que o C100 aponta. Usamos o
    CNPJ/CPF só de dígitos quando existe, porque é o que nunca muda; sem
    documento, o id do cadastro.
    """

    def __init__(self) -> None:
        self.por_codigo: dict[str, dict] = {}

    @staticmethod
    def codigo_de(documento: str | None, parceiro_id: int | None) -> str:
        documento = so_numeros(documento)
        if documento:
            return documento[:60]
        if parceiro_id:
            return f"P{parceiro_id}"
        return ""

    def registrar(self, codigo: str, dados: dict) -> str:
        if not codigo:
            return ""
        atual = self.por_codigo.setdefault(codigo, {})
        for chave, valor in dados.items():
            if valor and not atual.get(chave):
                atual[chave] = valor
        return codigo

    def do_parceiro(self, parceiro: Parceiro) -> str:
        codigo = self.codigo_de(parceiro.cpf_cnpj, parceiro.id)
        pessoa_fisica = (parceiro.pessoa or "J") == "F" or len(
            so_numeros(parceiro.cpf_cnpj)) == 11
        documento = so_numeros(parceiro.cpf_cnpj)
        return self.registrar(codigo, {
            "nome": parceiro.nome,
            "pais": so_numeros(parceiro.codigo_pais) or "1058",
            "cnpj": "" if pessoa_fisica else documento,
            "cpf": documento if pessoa_fisica else "",
            "ie": parceiro.rg_ie,
            "municipio": so_numeros(parceiro.codigo_municipio),
            "suframa": so_numeros(parceiro.inscricao_suframa),
            "logradouro": parceiro.logradouro,
            "numero": parceiro.numero,
            "complemento": parceiro.complemento,
            "bairro": parceiro.bairro,
        })

    def da_nota(self, nota: Nota, entrada: bool) -> str:
        """Quando não há cadastro: o que veio no XML já identifica o participante."""
        if entrada:
            documento, nome, ie = nota.emitente_cnpj, nota.emitente_nome, nota.emitente_ie
        else:
            documento, nome, ie = nota.destinatario_cnpj, nota.destinatario_nome, ""
        digitos = so_numeros(documento)
        codigo = self.codigo_de(documento, None)
        return self.registrar(codigo, {
            "nome": nome,
            "pais": "1058",
            "cnpj": digitos if len(digitos) != 11 else "",
            "cpf": digitos if len(digitos) == 11 else "",
            "ie": ie,
        })


class Itens:
    """Os itens (0200) e as unidades (0190) que apareceram no mês."""

    def __init__(self) -> None:
        self.por_codigo: dict[str, dict] = {}
        self.unidades: dict[str, str] = {}

    def unidade(self, sigla: str | None, nome: str | None = None) -> str:
        sigla = _texto(sigla, 6).upper()
        if sigla:
            self.unidades.setdefault(sigla, _texto(nome or sigla, 100))
        return sigla

    def registrar(self, item: NotaItem, produto: Produto | None) -> str:
        codigo = _texto(
            (produto.codigo if produto else None) or item.codigo or item.descricao, 60)
        if not codigo:
            return ""
        unidade = self.unidade(
            (produto.unidade_comercial if produto else None) or item.unidade
            or (produto.unidade.codigo if produto and produto.unidade else None))
        ficha = self.por_codigo.setdefault(codigo, {})
        novo = {
            "descricao": (produto.nome if produto else None) or item.descricao,
            "gtin": so_numeros((produto.gtin if produto else None) or item.gtin),
            "unidade": unidade,
            "tipo": (produto.tipo_item_sped if produto else None) or "00",
            "ncm": so_numeros((produto.ncm if produto else None) or item.ncm),
            "cest": so_numeros((produto.cest if produto else None) or item.cest),
            "ex_ipi": _texto((produto.ex_tipi if produto else None), 3),
            "aliquota": (produto.aliquota_icms if produto else None) or 0,
        }
        for chave, valor in novo.items():
            if valor and not ficha.get(chave):
                ficha[chave] = valor
        return codigo


# --------------------------------------------------------------------------- #
# Bloco C — os documentos
# --------------------------------------------------------------------------- #
def _indicador_de_pagamento(nota: Nota) -> str:
    """0 à vista, 1 a prazo, 2 outros, 9 sem pagamento."""
    if not float(nota.valor_total or 0):
        return "9"
    duplicatas = [p for p in nota.pagamentos if p.origem == "DUPLICATA"]
    if duplicatas:
        emissao = nota.data_emissao.date() if nota.data_emissao else None
        a_prazo = any(
            p.vencimento and emissao and p.vencimento > emissao for p in duplicatas)
        return "1" if (a_prazo or len(duplicatas) > 1) else "0"
    return "0"


def _indicador_de_frete(nota: Nota) -> str:
    modalidade = (nota.frete_modalidade or "9").strip()
    return modalidade if modalidade in ("0", "1", "2", "3", "4", "9") else "9"


class Analitico:
    """O C190: soma os itens do documento por CST + CFOP + alíquota.

    A chave dos três campos não pode repetir dentro do mesmo documento — é o que
    o PVA valida —, então a soma é feita num dicionário e escrita depois.
    """

    def __init__(self) -> None:
        self.grupos: dict[tuple[str, str, str], dict] = {}

    def somar(self, cst: str, cfop: str, aliquota, **valores) -> None:
        chave = (cst, cfop, _numero(aliquota, 2))
        grupo = self.grupos.setdefault(chave, {
            "operacao": 0.0, "base": 0.0, "icms": 0.0,
            "base_st": 0.0, "icms_st": 0.0, "reducao": 0.0, "ipi": 0.0,
        })
        for nome, valor in valores.items():
            grupo[nome] = dinheiro(grupo[nome] + float(valor or 0))

    def escrever(self, arquivo: Arquivo) -> dict:
        totais = {"icms": 0.0, "operacao": 0.0}
        for (cst, cfop, aliquota), g in sorted(self.grupos.items()):
            arquivo.escrever(
                "C190", cst, cfop, aliquota,
                _numero(g["operacao"]), _numero(g["base"]), _numero(g["icms"]),
                _numero(g["base_st"]), _numero(g["icms_st"]), _numero(g["reducao"]),
                _numero(g["ipi"]), "",
            )
            totais["icms"] = dinheiro(totais["icms"] + g["icms"])
            totais["operacao"] = dinheiro(totais["operacao"] + g["operacao"])
        return totais


def _escrever_documento(arquivo: Arquivo, nota: Nota, entrada: bool, cod_part: str,
                        itens: Itens, produtos: dict, depara: dict,
                        com_itens: bool) -> dict:
    """Escreve C100 (+ C170 quando cabe) + C190 de um documento. Devolve o ICMS."""
    cupom = _eh_cupom(nota)
    modelo = nota.modelo or MODELO_NFE
    cancelada = _cancelada(nota)

    if cancelada:
        # Documento cancelado leva só a identificação, e nenhum registro filho.
        arquivo.escrever(
            "C100", "0" if entrada else "1", "1" if entrada else "0",
            "" if cupom else cod_part, modelo, _situacao(nota),
            _texto(nota.serie, 3), _inteiro(nota.numero), _texto(nota.chave, 44),
        )
        return {"icms": 0.0, "operacao": 0.0}

    valor_total = dinheiro(nota.valor_total)
    arquivo.escrever(
        "C100",
        "0" if entrada else "1",                      # IND_OPER
        "1" if entrada else "0",                      # IND_EMIT
        "" if cupom else cod_part,                    # COD_PART
        modelo,
        _situacao(nota),
        _texto(nota.serie, 3),
        _inteiro(nota.numero),
        _texto(nota.chave, 44),
        _data(nota.data_emissao),                     # DT_DOC
        _data(nota.data_emissao) if entrada else "",  # DT_E_S
        _numero(valor_total),
        _indicador_de_pagamento(nota),
        _numero(nota.valor_desconto, vazio_se_zero=True),
        "",                                           # VL_ABAT_NT
        _numero(nota.valor_produtos),
        _indicador_de_frete(nota),
        _numero(nota.valor_frete, vazio_se_zero=True),
        "",                                           # VL_SEG
        "",                                           # VL_OUT_DA
        _numero(sum(float(i.icms_base or 0) for i in nota.itens), vazio_se_zero=True),
        _numero(nota.valor_icms, vazio_se_zero=True),
        "",                                           # VL_BC_ICMS_ST
        # O cupom (modelo 65) não leva ST, IPI, PIS nem COFINS no C100.
        "" if cupom else "",                          # VL_ICMS_ST
        "" if cupom else _numero(nota.valor_ipi, vazio_se_zero=True),
        "" if cupom else _numero(
            sum(float(i.pis_valor or 0) for i in nota.itens), vazio_se_zero=True),
        "" if cupom else _numero(
            sum(float(i.cofins_valor or 0) for i in nota.itens), vazio_se_zero=True),
        "", "",                                       # VL_PIS_ST | VL_COFINS_ST
    )

    analitico = Analitico()
    for item in nota.itens:
        produto = produtos.get(item.produto_id)
        codigo = itens.registrar(item, produto)
        cst = _cst_do_sped(item.icms_cst, item.origem_mercadoria, depara)
        cfop = so_numeros(item.cfop)[:4]
        base = dinheiro(item.icms_base)
        reducao = dinheiro(
            float(item.valor_total or 0) * float(item.icms_reducao or 0) / 100)

        if com_itens:
            arquivo.escrever(
                "C170",
                _inteiro(item.numero),
                codigo,
                _texto(item.descricao, 255),
                _numero(item.quantidade, 5),
                itens.unidade(
                    item.unidade or (produto.unidade_comercial if produto else None)),
                _numero(item.valor_total),
                _numero(item.desconto, vazio_se_zero=True),
                "1" if (produto and produto.tipo_item_sped == "09") else "0",  # IND_MOV
                cst, cfop, "",                        # COD_NAT
                _numero(base, vazio_se_zero=True),
                _numero(item.icms_aliquota, 2, vazio_se_zero=True),
                _numero(item.icms_valor, vazio_se_zero=True),
                "", "", "",                           # ST: base, alíquota, valor
                "0",                                  # IND_APUR — mensal
                _texto(item.cst_ipi, 2), "",          # CST_IPI | COD_ENQ
                "", _numero(item.aliquota_ipi, 2, vazio_se_zero=True),
                _numero(item.ipi_valor, vazio_se_zero=True),
                _texto(item.cst_pis, 2),
                _numero(item.pis_cofins_base, vazio_se_zero=True),
                _numero(item.aliquota_pis, 4, vazio_se_zero=True), "", "",
                _numero(item.pis_valor, vazio_se_zero=True),
                _texto(item.cst_cofins, 2),
                _numero(item.pis_cofins_base, vazio_se_zero=True),
                _numero(item.aliquota_cofins, 4, vazio_se_zero=True), "", "",
                _numero(item.cofins_valor, vazio_se_zero=True),
                "", "",                               # COD_CTA | VL_ABAT_NT
            )

        analitico.somar(
            cst, cfop, item.icms_aliquota,
            operacao=item.valor_total, base=base, icms=item.icms_valor,
            reducao=reducao, ipi=item.ipi_valor,
        )

    if not nota.itens:
        # Sem item (nota de entrada que ficou só com os totais): o analítico sai
        # do cabeçalho, com o CFOP da nota.
        analitico.somar(
            _cst_do_sped("90", "0", depara), so_numeros(nota.cfop)[:4], 0,
            operacao=nota.valor_total, base=0, icms=nota.valor_icms,
        )

    return analitico.escrever(arquivo)


# --------------------------------------------------------------------------- #
# A geração
# --------------------------------------------------------------------------- #
def gerar(db: Session, empresa_id: int, inicio: date, fim: date,
          perfil: str | None = None, com_inventario: bool = False,
          finalidade: str = "0") -> dict:
    """Monta o arquivo inteiro e devolve o texto, as contagens e o resumo."""
    empresa = db.get(Empresa, empresa_id)
    config = config_da_empresa(db, empresa_id)
    perfil = (perfil or config.perfil or "A").upper()[:1]
    if perfil not in PERFIS:
        perfil = "A"
    depara = ler_depara(config.csosn_para_cst)
    versao = versao_do_layout(fim)
    # Quando o item do documento (C170) é escriturado:
    #
    #   perfil A       — é o perfil detalhado; no B e no C o documento vai só pelos
    #                    totais do C190;
    #   não é cupom    — o C170 é dos modelos 01, 1B, 04 e 55. O 65 nunca leva item;
    #   é entrada      — nota de terceiro: a escrituração do item é do destinatário.
    #                    Na nota que a própria empresa emitiu o Guia manda NÃO
    #                    informar (a SEFAZ já tem o XML), salvo se a legislação do
    #                    estado exigir — daí o interruptor na configuração.
    detalhar_itens = perfil == "A"

    dados = notas_do_periodo(db, empresa_id, inicio, fim)
    produtos = {
        p.id: p for p in db.query(Produto)
        .options(joinedload(Produto.unidade))
        .filter(Produto.empresa_id == empresa_id).all()
    }
    parceiros = {
        p.id: p for p in db.query(Parceiro).filter(Parceiro.empresa_id == empresa_id).all()
    }

    arquivo = Arquivo()
    participantes = Participantes()
    itens = Itens()

    # ---------------- bloco C, montado primeiro ----------------
    # Os participantes e os itens do bloco 0 só são conhecidos depois de passar
    # pelos documentos, então o bloco C é montado num arquivo à parte e colado
    # no lugar no fim.
    bloco_c = Arquivo()
    bloco_c.escrever("C001", "0" if (dados["saidas"] or dados["entradas"]) else "1")

    icms_saidas = icms_entradas = 0.0
    valor_saidas = valor_entradas = 0.0

    for entrada, lista in ((False, dados["saidas"]), (True, dados["entradas"])):
        for nota in lista:
            cupom = _eh_cupom(nota)
            cod_part = ""
            if not cupom:
                parceiro = parceiros.get(nota.parceiro_id)
                cod_part = (participantes.do_parceiro(parceiro) if parceiro
                            else participantes.da_nota(nota, entrada))
            totais = _escrever_documento(
                bloco_c, nota, entrada, cod_part, itens, produtos, depara,
                com_itens=detalhar_itens and not cupom
                and (entrada or bool(config.itens_das_saidas)),
            )
            if entrada:
                icms_entradas = dinheiro(icms_entradas + totais["icms"])
                valor_entradas = dinheiro(valor_entradas + totais["operacao"])
            else:
                icms_saidas = dinheiro(icms_saidas + totais["icms"])
                valor_saidas = dinheiro(valor_saidas + totais["operacao"])

    # ---------------- bloco 0 ----------------
    arquivo.escrever(
        "0000", versao, finalidade, _data(inicio), _data(fim),
        _texto(empresa.razao_social, 100),
        so_numeros(empresa.cnpj), "",            # CNPJ | CPF
        _texto(empresa.uf, 2),
        _texto(empresa.inscricao_estadual, 14),
        so_numeros(empresa.codigo_municipio)[:7],
        _texto(empresa.inscricao_municipal, 14),
        "",                                            # SUFRAMA
        perfil,
        config.atividade or "1",
    )
    arquivo.escrever("0001", "0")
    arquivo.escrever(
        "0005", _texto(empresa.nome_fantasia or empresa.razao_social, 100),
        so_numeros(empresa.cep)[:8], _texto(empresa.logradouro, 60),
        _texto(empresa.numero, 10), _texto(empresa.complemento, 60),
        _texto(empresa.bairro, 60), so_numeros(empresa.telefone)[:11], "",
        _texto(empresa.email, 60),
    )
    if (config.contador_nome or "").strip():
        arquivo.escrever(
            "0100", _texto(config.contador_nome, 100),
            so_numeros(config.contador_cpf)[:11],
            _texto(config.contador_crc, 15),
            so_numeros(config.contador_cnpj)[:14],
            so_numeros(config.contador_cep)[:8],
            _texto(config.contador_logradouro, 60), _texto(config.contador_numero, 10),
            _texto(config.contador_complemento, 60), _texto(config.contador_bairro, 60),
            so_numeros(config.contador_telefone)[:11], "",
            _texto(config.contador_email, 60),
            so_numeros(config.contador_codigo_municipio)[:7],
        )

    for codigo, p in sorted(participantes.por_codigo.items()):
        arquivo.escrever(
            "0150", codigo, _texto(p.get("nome"), 100), p.get("pais") or "1058",
            p.get("cnpj", ""), p.get("cpf", ""), _texto(p.get("ie"), 14),
            (p.get("municipio") or "")[:7], p.get("suframa", ""),
            _texto(p.get("logradouro"), 60), _texto(p.get("numero"), 10),
            _texto(p.get("complemento"), 60), _texto(p.get("bairro"), 60),
        )

    for sigla, descricao in sorted(itens.unidades.items()):
        arquivo.escrever("0190", sigla, _texto(descricao, 100))

    for codigo, i in sorted(itens.por_codigo.items()):
        ncm = (i.get("ncm") or "")[:8]
        arquivo.escrever(
            "0200", codigo, _texto(i.get("descricao"), 255), i.get("gtin", ""), "",
            i.get("unidade", ""), i.get("tipo") or "00", ncm, i.get("ex_ipi", ""),
            ncm[:2],                                   # COD_GEN — gênero, do NCM
            "",                                        # COD_LST — serviço, ISS
            _numero(i.get("aliquota"), 2, vazio_se_zero=True),
            (i.get("cest") or "")[:7],
        )

    arquivo.escrever("0990", arquivo.quantas("0") + 1)

    # ---------------- bloco B — só o Distrito Federal ----------------
    if (empresa.uf or "").upper() == "DF":
        arquivo.escrever("B001", "1")
        arquivo.escrever("B990", 2)

    # ---------------- bloco C ----------------
    for linha in bloco_c.linhas:
        arquivo.linhas.append(linha)
    for registro, quantas in bloco_c.contagem.items():
        arquivo.contagem[registro] = arquivo.contagem.get(registro, 0) + quantas
    arquivo.escrever("C990", arquivo.quantas("C") + 1)

    # ---------------- bloco D — serviços, que este sistema não emite ----------
    arquivo.escrever("D001", "1")
    arquivo.escrever("D990", 2)

    # ---------------- bloco E — apuração ----------------
    do_simples = (empresa.crt or "1") in CRT_DO_SIMPLES
    debitos = 0.0 if do_simples else icms_saidas
    creditos = 0.0 if do_simples else icms_entradas
    saldo = dinheiro(debitos - creditos)
    a_recolher = saldo if saldo > 0 else 0.0
    credor = dinheiro(-saldo) if saldo < 0 else 0.0

    arquivo.escrever("E001", "0")
    arquivo.escrever("E100", _data(inicio), _data(fim))
    arquivo.escrever(
        "E110",
        _numero(debitos),        # VL_TOT_DEBITOS
        _numero(0),              # VL_AJ_DEBITOS
        _numero(0),              # VL_TOT_AJ_DEBITOS
        _numero(0),              # VL_ESTORNOS_CRED
        _numero(creditos),       # VL_TOT_CREDITOS
        _numero(0),              # VL_AJ_CREDITOS
        _numero(0),              # VL_TOT_AJ_CREDITOS
        _numero(0),              # VL_ESTORNOS_DEB
        _numero(0),              # VL_SLD_CREDOR_ANT
        _numero(abs(saldo)),     # VL_SLD_APURADO
        _numero(0),              # VL_TOT_DED
        _numero(a_recolher),     # VL_ICMS_RECOLHER
        _numero(credor),         # VL_SLD_CREDOR_TRANSPORTAR
        _numero(0),              # DEB_ESP
    )
    arquivo.escrever("E990", arquivo.quantas("E") + 1)

    # ---------------- bloco G — CIAP ----------------
    arquivo.escrever("G001", "1")
    arquivo.escrever("G990", 2)

    # ---------------- bloco H — inventário ----------------
    inventariados = 0
    if com_inventario:
        linhas_h = _inventario(db, empresa_id, fim, itens, produtos)
        arquivo.escrever("H001", "0" if linhas_h else "1")
        if linhas_h:
            arquivo.escrever("H005", _data(fim),
                             _numero(sum(l["valor"] for l in linhas_h)), "01")
            for linha in linhas_h:
                arquivo.escrever(
                    "H010", linha["codigo"], linha["unidade"],
                    _numero(linha["quantidade"], 3), _numero(linha["unitario"], 6),
                    _numero(linha["valor"]), "0", "", "", "", "",
                )
            inventariados = len(linhas_h)
        arquivo.escrever("H990", arquivo.quantas("H") + 1)
    else:
        arquivo.escrever("H001", "1")
        arquivo.escrever("H990", 2)

    # ---------------- bloco K — produção e estoque (indústria) --------------
    arquivo.escrever("K001", "1")
    arquivo.escrever("K990", 2)

    # ---------------- bloco 1 — outras informações ----------------
    arquivo.escrever("1001", "0")
    arquivo.escrever("1010", *(["N"] * 13))
    arquivo.escrever("1990", arquivo.quantas("1") + 1)

    # ---------------- bloco 9 — a contagem de tudo ----------------
    _fechar(arquivo)

    return {
        "texto": arquivo.texto(),
        "bytes": arquivo.bytes(),
        "linhas": len(arquivo.linhas),
        "contagem": dict(arquivo.contagem),   # na ordem em que aparecem
        "nome": nome_do_arquivo(empresa, inicio, fim),
        "resumo": {
            "versao": versao,
            "perfil": perfil,
            "periodo": f"{_data(inicio)} a {_data(fim)}",
            "saidas": len(dados["saidas"]),
            "entradas": len(dados["entradas"]),
            "cupons": sum(1 for n in dados["saidas"] if _eh_cupom(n)),
            "valor_saidas": valor_saidas,
            "valor_entradas": valor_entradas,
            "icms_debito": debitos,
            "icms_credito": creditos,
            "icms_a_recolher": a_recolher,
            "saldo_credor": credor,
            "participantes": len(participantes.por_codigo),
            "itens": len(itens.por_codigo),
            "inventariados": inventariados,
            "simples": do_simples,
        },
    }


def _inventario(db: Session, empresa_id: int, fim: date, itens: Itens,
                produtos: dict) -> list[dict]:
    """As linhas do H010: o que tem saldo no controle de estoque.

    O saldo é o de **agora** — o motor de estoque mantém o saldo corrente, não
    guarda foto por data. Então gerar o inventário de um mês fechado há muito
    tempo devolve o saldo de hoje, e a tela avisa isso.
    """
    linhas: list[dict] = []
    for produto in produtos.values():
        if not motor_estoque.controla(produto):
            continue
        quantidade = motor_estoque.saldo(produto)
        if not quantidade:
            continue
        unitario = float(produto.custo_medio or 0)
        codigo = _texto(produto.codigo, 60)
        unidade = itens.unidade(
            motor_estoque.unidade_do_saldo(produto) or produto.unidade_comercial)
        # o item do inventário precisa existir no 0200
        if codigo not in itens.por_codigo:
            itens.por_codigo[codigo] = {
                "descricao": produto.nome, "gtin": so_numeros(produto.gtin),
                "unidade": unidade, "tipo": produto.tipo_item_sped or "00",
                "ncm": so_numeros(produto.ncm), "cest": so_numeros(produto.cest),
                "ex_ipi": _texto(produto.ex_tipi, 3), "aliquota": produto.aliquota_icms or 0,
            }
        linhas.append({
            "codigo": codigo, "unidade": unidade, "quantidade": quantidade,
            "unitario": unitario, "valor": dinheiro(quantidade * unitario),
        })
    return sorted(linhas, key=lambda l: l["codigo"])


def _fechar(arquivo: Arquivo) -> None:
    """Escreve o bloco 9 — a lista de todos os registros do arquivo e as contagens.

    Tem uma pegadinha: o 9900 precisa contar **as próprias linhas 9900**, e o
    9990 precisa contar o 9999, que vem depois dele. Como a lista de registros
    não muda ao acrescentar o bloco 9 (9001, 9900, 9990 e 9999 são quatro tipos
    fixos), o cálculo fecha em um passo só.
    """
    # A ordem é a de aparição no arquivo (o dicionário de contagens guarda a
    # ordem em que cada registro foi escrito pela primeira vez), com o bloco 9
    # no fim. Alfabética também passaria, mas fica estranha de ler: "1001" antes
    # de "C001".
    registros = dict(arquivo.contagem)
    registros["9001"] = 1
    registros["9900"] = 0                    # entra na ordem certa, valor ajustado abaixo
    registros["9990"] = 1
    registros["9999"] = 1
    registros["9900"] = len(registros)

    arquivo.escrever("9001", "0")
    for nome, quantas in registros.items():
        arquivo.escrever("9900", nome, quantas)
    # O 9990 conta as linhas do bloco 9 **e** o 9999, que não é do bloco.
    arquivo.escrever("9990", registros["9900"] + 3)
    arquivo.escrever("9999", len(arquivo.linhas) + 1)


def nome_do_arquivo(empresa: Empresa | None, inicio: date, fim: date) -> str:
    """Nome no padrão que o contador reconhece: SPED-FISCAL-CNPJ-AAAAMM.txt."""
    cnpj = so_numeros(empresa.cnpj if empresa else "") or "SEM-CNPJ"
    return f"SPED-FISCAL-{cnpj}-{inicio.year}{inicio.month:02d}.txt"


# --------------------------------------------------------------------------- #
# Completar as notas de entrada
# --------------------------------------------------------------------------- #
def pendentes_de_completar(db: Session, empresa_id: int, inicio: date,
                           fim: date) -> dict:
    """As notas de entrada do período que ainda não estão prontas para o SPED.

    Duas situações, e o tratamento é diferente:

    * **resumo** — a SEFAZ só entregou o resumo (resNFe). Para receber o XML
      inteiro é preciso dar **ciência da operação** e buscar os documentos de
      novo. É um ato na SEFAZ, não uma conta do sistema.
    * **sem itens** — o XML completo está aqui, mas ninguém apertou Importar,
      então a nota não tem itens gravados. Isso o sistema resolve sozinho.
    """
    dados = notas_do_periodo(db, empresa_id, inicio, fim)
    resumo, sem_itens = [], []
    for nota in dados["entradas"]:
        if nota.resumo or not nota.xml:
            resumo.append(nota)
        elif not nota.itens:
            sem_itens.append(nota)
    return {"resumo": resumo, "sem_itens": sem_itens}
