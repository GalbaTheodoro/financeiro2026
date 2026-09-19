"""Emissão de NF-e (modelo 55) — montar, assinar, transmitir e cancelar.

O caminho de uma nota emitida pelo AgroDock
-------------------------------------------
1. **Rascunho** — a nota é montada na tela (ou a partir de um contrato de venda).
   Rascunho não gasta numeração e pode ser editado à vontade.
2. **Transmitir** — o sistema pega o próximo número da série, monta a chave de
   acesso, gera o XML no layout 4.00, assina com o certificado A1 e envia para o
   webservice da SEFAZ do estado da empresa, em **lote síncrono** (indSinc=1):
   a resposta já traz autorizado ou rejeitado, sem precisar consultar recibo.
3. **Autorizada** — o sistema guarda o `nfeProc` (NF-e + protocolo), que é o XML
   que vale para o contador e de onde sai a DANFE.
4. **Cancelar** — evento 110111 com justificativa (mínimo 15 letras), dentro do
   prazo legal (em regra 24 horas da autorização).

Responsabilidade fiscal
-----------------------
O sistema monta a nota com os dados dos cadastros: CFOP, CST/CSOSN, NCM e
alíquotas vêm do **produto** e o regime vem da **empresa**. Conferir se essa
tributação está certa para cada operação é do contribuinte e do seu contador —
o AgroDock não decide tributação por conta própria.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime

from . import dfe as motor

NS = motor.NS
_N = f"{{{NS}}}"
VERSAO = "4.00"
VERSAO_SISTEMA = "AgroDock 1.0"

# --------------------------------------------------------------------------- #
# Endereços dos webservices de autorização, por estado
#
# Os estados que não têm servidor próprio usam o SVRS (Sefaz Virtual do RS) ou o
# SVAN. Só estes dois mais MG, SP, PR, BA, GO, MT, MS, CE, PE, AM e RS emitem por
# conta própria — o resto cai no SVRS.
# --------------------------------------------------------------------------- #
_SVRS = {
    "1": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
    "2": "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
}
_SVRS_EVENTO = {
    "1": "https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
    "2": "https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
}

AUTORIZACAO = {
    "MG": {"1": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
           "2": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4"},
    "SP": {"1": "https://nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
           "2": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx"},
    "PR": {"1": "https://nfe.sefa.pr.gov.br/nfe/NFeAutorizacao4",
           "2": "https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeAutorizacao4"},
    "RS": {"1": "https://nfe.sefazrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
           "2": "https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx"},
    "GO": {"1": "https://nfe.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
           "2": "https://homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4"},
    "MT": {"1": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeAutorizacao4",
           "2": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeAutorizacao4"},
    "MS": {"1": "https://nfe.sefaz.ms.gov.br/ws/NFeAutorizacao4",
           "2": "https://hom.nfe.sefaz.ms.gov.br/ws/NFeAutorizacao4"},
    "BA": {"1": "https://nfe.sefaz.ba.gov.br/webservices/NFeAutorizacao4/NFeAutorizacao4.asmx",
           "2": "https://hnfe.sefaz.ba.gov.br/webservices/NFeAutorizacao4/NFeAutorizacao4.asmx"},
    "PE": {"1": "https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeAutorizacao4",
           "2": "https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeAutorizacao4"},
    "CE": {"1": "https://nfe.sefaz.ce.gov.br/nfe4/services/NFeAutorizacao4",
           "2": "https://nfeh.sefaz.ce.gov.br/nfe4/services/NFeAutorizacao4"},
    "AM": {"1": "https://nfe.sefaz.am.gov.br/services2/services/NfeAutorizacao4",
           "2": "https://homnfe.sefaz.am.gov.br/services2/services/NfeAutorizacao4"},
}

EVENTO = {
    "MG": {"1": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4",
           "2": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4"},
    "SP": {"1": "https://nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx",
           "2": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx"},
    "PR": {"1": "https://nfe.sefa.pr.gov.br/nfe/NFeRecepcaoEvento4",
           "2": "https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeRecepcaoEvento4"},
    "RS": {"1": "https://nfe.sefazrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
           "2": "https://nfe-homologacao.sefazrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx"},
    "GO": {"1": "https://nfe.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4",
           "2": "https://homolog.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4"},
    "MT": {"1": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/RecepcaoEvento4",
           "2": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/RecepcaoEvento4"},
    "MS": {"1": "https://nfe.sefaz.ms.gov.br/ws/NFeRecepcaoEvento4",
           "2": "https://hom.nfe.sefaz.ms.gov.br/ws/NFeRecepcaoEvento4"},
    "BA": {"1": "https://nfe.sefaz.ba.gov.br/webservices/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
           "2": "https://hnfe.sefaz.ba.gov.br/webservices/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"},
    "PE": {"1": "https://nfe.sefaz.pe.gov.br/nfe-service/services/RecepcaoEvento4",
           "2": "https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/RecepcaoEvento4"},
    "CE": {"1": "https://nfe.sefaz.ce.gov.br/nfe4/services/NFeRecepcaoEvento4",
           "2": "https://nfeh.sefaz.ce.gov.br/nfe4/services/NFeRecepcaoEvento4"},
    "AM": {"1": "https://nfe.sefaz.am.gov.br/services2/services/RecepcaoEvento4",
           "2": "https://homnfe.sefaz.am.gov.br/services2/services/RecepcaoEvento4"},
}

# Regimes (CRT) e o que cada um usa no ICMS do item
CRT = {
    "1": "Simples Nacional",
    "2": "Simples Nacional — excesso de sublimite",
    "3": "Regime normal (presumido ou real)",
    "4": "MEI",
}
# no Simples o item leva CSOSN; no regime normal, CST
CSOSN_PADRAO = "102"   # tributada pelo Simples, sem permissão de crédito
CST_PADRAO = "00"      # tributada integralmente

FINALIDADES = {"1": "Normal", "2": "Complementar", "3": "Ajuste", "4": "Devolução"}
MODALIDADES_FRETE = {
    "0": "Por conta do emitente", "1": "Por conta do destinatário",
    "2": "Por conta de terceiros", "3": "Transporte próprio do emitente",
    "4": "Transporte próprio do destinatário", "9": "Sem transporte",
}


class ErroEmissao(Exception):
    """Falha esperada ao emitir — vira mensagem na tela."""


# --------------------------------------------------------------------------- #
# Pedaços de XML
# --------------------------------------------------------------------------- #
def _t(valor) -> str:
    """Texto de uma tag, com os caracteres especiais escapados."""
    return (str(valor if valor is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _tag(nome: str, valor, obrigatorio: bool = False) -> str:
    """<nome>valor</nome> — some quando o valor está vazio e não é obrigatório."""
    texto = _t(valor).strip()
    if not texto and not obrigatorio:
        return ""
    return f"<{nome}>{texto}</{nome}>"


def _num(valor, casas: int = 2) -> str:
    return f"{float(valor or 0):.{casas}f}"


def _limpar(valor, tamanho: int | None = None) -> str:
    """Tira acento e caractere estranho — a SEFAZ recusa caractere fora do padrão."""
    import unicodedata

    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\x20-\x7E]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:tamanho] if tamanho else texto


def digito_chave(chave43: str) -> str:
    """Dígito verificador da chave de acesso (módulo 11, pesos de 2 a 9)."""
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(c) * pesos[i % 8] for i, c in enumerate(reversed(chave43)))
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def montar_chave(uf: str, emissao: datetime, cnpj: str, modelo: str, serie: str,
                 numero: int, codigo: int, tipo_emissao: str = "1") -> str:
    """Os 44 números da chave de acesso."""
    base = (
        motor.CODIGO_UF.get((uf or "").upper(), "31")
        + emissao.strftime("%y%m")
        + motor.so_numeros(cnpj).zfill(14)
        + str(modelo).zfill(2)
        + str(serie).zfill(3)
        + str(numero).zfill(9)
        + str(tipo_emissao)
        + str(codigo).zfill(8)
    )
    return base + digito_chave(base)


def codigo_numerico(numero: int, serie: str) -> int:
    """cNF — número aleatório da nota. Usamos algo estável e diferente de nNF."""
    import hashlib

    semente = hashlib.sha256(f"{serie}-{numero}-agrodock".encode()).hexdigest()
    return int(semente[:8], 16) % 100_000_000


# --------------------------------------------------------------------------- #
# Blocos da NF-e
# --------------------------------------------------------------------------- #
def _ide(empresa, nota, chave: str, numero: int, serie: str, codigo: int,
         emissao: datetime) -> str:
    destino = "1"  # 1 interna, 2 interestadual, 3 exterior
    uf_destino = (nota["destinatario_uf"] or empresa.uf or "").upper()
    if uf_destino and uf_destino != (empresa.uf or "").upper():
        destino = "2"
    return (
        "<ide>"
        + _tag("cUF", motor.CODIGO_UF.get((empresa.uf or "MG").upper(), "31"), True)
        + _tag("cNF", str(codigo).zfill(8), True)
        + _tag("natOp", _limpar(nota["natureza_operacao"] or "VENDA", 60), True)
        + _tag("mod", "55", True)
        + _tag("serie", str(int(serie)), True)
        + _tag("nNF", numero, True)
        + _tag("dhEmi", emissao.isoformat(), True)
        + _tag("tpNF", nota["tipo_operacao"] or "1", True)
        + _tag("idDest", destino, True)
        + _tag("cMunFG", empresa.codigo_municipio or "3106200", True)
        + _tag("tpImp", "1", True)        # DANFE retrato
        + _tag("tpEmis", "1", True)       # emissão normal
        + _tag("cDV", chave[-1], True)
        + _tag("tpAmb", nota["ambiente"], True)
        + _tag("finNFe", nota["finalidade"] or "1", True)
        + _tag("indFinal", nota["consumidor_final"] or "0", True)
        + _tag("indPres", nota["presenca"] or "9", True)
        + _tag("procEmi", "0", True)
        + _tag("verProc", VERSAO_SISTEMA, True)
        + "</ide>"
    )


def _emit(empresa) -> str:
    if not motor.so_numeros(empresa.cnpj):
        raise ErroEmissao("Preencha o CNPJ da empresa em Cadastros > Empresas.")
    if not (empresa.inscricao_estadual or "").strip():
        raise ErroEmissao("Preencha a inscrição estadual da empresa em Cadastros > Empresas.")
    if not (empresa.codigo_municipio or "").strip():
        raise ErroEmissao(
            "Preencha o código do município (IBGE) da empresa em Cadastros > Empresas.")
    return (
        "<emit>"
        + _tag("CNPJ", motor.so_numeros(empresa.cnpj), True)
        + _tag("xNome", _limpar(empresa.razao_social, 60), True)
        + _tag("xFant", _limpar(empresa.nome_fantasia, 60))
        + "<enderEmit>"
        + _tag("xLgr", _limpar(empresa.logradouro or "SEM ENDERECO", 60), True)
        + _tag("nro", _limpar(empresa.numero or "S/N", 60), True)
        + _tag("xCpl", _limpar(empresa.complemento, 60))
        + _tag("xBairro", _limpar(empresa.bairro or "CENTRO", 60), True)
        + _tag("cMun", empresa.codigo_municipio, True)
        + _tag("xMun", _limpar(empresa.cidade, 60), True)
        + _tag("UF", (empresa.uf or "").upper(), True)
        + _tag("CEP", motor.so_numeros(empresa.cep), True)
        + _tag("cPais", empresa.codigo_pais or "1058", True)
        + _tag("xPais", _limpar(empresa.pais or "BRASIL", 60), True)
        + _tag("fone", motor.so_numeros(empresa.telefone))
        + "</enderEmit>"
        + _tag("IE", motor.so_numeros(empresa.inscricao_estadual) or "ISENTO", True)
        + _tag("CRT", empresa.crt or "1", True)
        + "</emit>"
    )


def _dest(parceiro, ambiente: str) -> str:
    """Destinatário. Em homologação o nome é obrigatoriamente o aviso da SEFAZ."""
    if parceiro is None:
        raise ErroEmissao("Escolha o cliente da nota.")
    documento = motor.so_numeros(parceiro.cpf_cnpj)
    if len(documento) not in (11, 14):
        raise ErroEmissao(
            f"O CPF/CNPJ de {parceiro.nome} está incompleto — a SEFAZ não aceita a nota assim.")
    if not (parceiro.codigo_municipio or "").strip():
        raise ErroEmissao(
            f"Falta o código do município (IBGE) no cadastro de {parceiro.nome}.")

    nome = ("NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
            if ambiente == "2" else _limpar(parceiro.nome, 60))
    indicador = parceiro.indicador_ie or "9"
    inscricao = motor.so_numeros(parceiro.rg_ie)
    if indicador == "1" and not inscricao:
        raise ErroEmissao(
            f"{parceiro.nome} está marcado como contribuinte de ICMS mas está sem inscrição "
            "estadual. Corrija o cadastro.")
    return (
        "<dest>"
        + _tag("CNPJ" if len(documento) == 14 else "CPF", documento, True)
        + _tag("xNome", nome, True)
        + "<enderDest>"
        + _tag("xLgr", _limpar(parceiro.logradouro or "SEM ENDERECO", 60), True)
        + _tag("nro", _limpar(parceiro.numero or "S/N", 60), True)
        + _tag("xCpl", _limpar(parceiro.complemento, 60))
        + _tag("xBairro", _limpar(parceiro.bairro or "CENTRO", 60), True)
        + _tag("cMun", parceiro.codigo_municipio, True)
        + _tag("xMun", _limpar(parceiro.cidade, 60), True)
        + _tag("UF", (parceiro.uf or "").upper(), True)
        + _tag("CEP", motor.so_numeros(parceiro.cep))
        + _tag("cPais", parceiro.codigo_pais or "1058")
        + _tag("xPais", _limpar(parceiro.pais or "BRASIL", 60))
        + _tag("fone", motor.so_numeros(parceiro.telefone or parceiro.celular))
        + "</enderDest>"
        + _tag("indIEDest", indicador, True)
        + (_tag("IE", inscricao) if indicador == "1" else "")
        + _tag("email", _limpar(parceiro.email, 60))
        + "</dest>"
    )


def _icms_do_item(item, crt: str) -> str:
    """Bloco de ICMS conforme o regime da empresa e o CST/CSOSN do produto."""
    origem = item.origem_mercadoria or "0"
    base = float(item.icms_base or 0)
    aliquota = float(item.icms_aliquota or 0)
    valor = float(item.icms_valor or 0)
    reducao = float(item.icms_reducao or 0)

    if crt in ("1", "4"):  # Simples Nacional
        csosn = (item.icms_cst or CSOSN_PADRAO).zfill(3)
        if csosn == "101":
            corpo = (_tag("orig", origem, True) + _tag("CSOSN", csosn, True)
                     + _tag("pCredSN", _num(aliquota, 4), True)
                     + _tag("vCredICMSSN", _num(valor), True))
            return f"<ICMS><ICMSSN101>{corpo}</ICMSSN101></ICMS>"
        if csosn == "900":
            corpo = (_tag("orig", origem, True) + _tag("CSOSN", csosn, True)
                     + _tag("modBC", "3", True) + _tag("vBC", _num(base), True)
                     + _tag("pICMS", _num(aliquota, 4), True) + _tag("vICMS", _num(valor), True))
            return f"<ICMS><ICMSSN900>{corpo}</ICMSSN900></ICMS>"
        corpo = _tag("orig", origem, True) + _tag("CSOSN", csosn, True)
        return f"<ICMS><ICMSSN102>{corpo}</ICMSSN102></ICMS>"

    cst = (item.icms_cst or CST_PADRAO).zfill(2)[:2]
    if cst == "00":
        corpo = (_tag("orig", origem, True) + _tag("CST", cst, True) + _tag("modBC", "3", True)
                 + _tag("vBC", _num(base), True) + _tag("pICMS", _num(aliquota, 4), True)
                 + _tag("vICMS", _num(valor), True))
        return f"<ICMS><ICMS00>{corpo}</ICMS00></ICMS>"
    if cst == "20":
        corpo = (_tag("orig", origem, True) + _tag("CST", cst, True) + _tag("modBC", "3", True)
                 + _tag("pRedBC", _num(reducao, 4), True) + _tag("vBC", _num(base), True)
                 + _tag("pICMS", _num(aliquota, 4), True) + _tag("vICMS", _num(valor), True))
        return f"<ICMS><ICMS20>{corpo}</ICMS20></ICMS>"
    if cst == "51":  # diferimento — muito usado no café em MG
        corpo = (_tag("orig", origem, True) + _tag("CST", cst, True) + _tag("modBC", "3", True)
                 + _tag("vBC", _num(base), True) + _tag("pICMS", _num(aliquota, 4), True)
                 + _tag("vICMSOp", _num(base * aliquota / 100), True)
                 + _tag("pDif", "100.0000", True)
                 + _tag("vICMSDif", _num(base * aliquota / 100), True)
                 + _tag("vICMS", "0.00", True))
        return f"<ICMS><ICMS51>{corpo}</ICMS51></ICMS>"
    if cst == "60":
        corpo = _tag("orig", origem, True) + _tag("CST", cst, True)
        return f"<ICMS><ICMS60>{corpo}</ICMS60></ICMS>"
    # 40 isenta, 41 não tributada, 50 suspensão
    corpo = _tag("orig", origem, True) + _tag("CST", cst, True)
    return f"<ICMS><ICMS40>{corpo}</ICMS40></ICMS>"


def _pis_cofins(item, crt: str) -> str:
    """PIS e COFINS. No Simples o normal é CST 49 (outras operações) com valor zero."""
    def bloco(nome, cst, aliquota, valor, base):
        cst = (cst or ("49" if crt in ("1", "4") else "01")).zfill(2)
        if cst in ("01", "02"):
            corpo = (_tag("CST", cst, True) + _tag("vBC", _num(base), True)
                     + _tag(f"p{nome}", _num(aliquota, 4), True)
                     + _tag(f"v{nome}", _num(valor), True))
            return f"<{nome}><{nome}Aliq>{corpo}</{nome}Aliq></{nome}>"
        if cst in ("04", "05", "06", "07", "08", "09"):
            corpo = _tag("CST", cst, True)
            return f"<{nome}><{nome}NT>{corpo}</{nome}NT></{nome}>"
        corpo = (_tag("CST", cst, True) + _tag("vBC", _num(base), True)
                 + _tag(f"p{nome}", _num(aliquota, 4), True)
                 + _tag(f"v{nome}", _num(valor), True))
        return f"<{nome}><{nome}Outr>{corpo}</{nome}Outr></{nome}>"

    total = float(item.valor_total or 0)
    return (bloco("PIS", item.cst_pis, item.aliquota_pis, item.pis_valor,
                  total if float(item.aliquota_pis or 0) else 0)
            + bloco("COFINS", item.cst_cofins, item.aliquota_cofins, item.cofins_valor,
                    total if float(item.aliquota_cofins or 0) else 0))


def _det(item, numero: int, crt: str, ambiente: str) -> str:
    if not (item.ncm or "").strip():
        raise ErroEmissao(
            f"O item {item.descricao} está sem NCM. Preencha em Cadastros > Produtos.")
    if not (item.cfop or "").strip():
        raise ErroEmissao(f"O item {item.descricao} está sem CFOP.")
    descricao = ("NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
                 if ambiente == "2" and numero == 1 else _limpar(item.descricao, 120))
    gtin = (item.gtin or "").strip() or "SEM GTIN"
    unidade = _limpar(item.unidade or "UN", 6) or "UN"
    prod = (
        "<prod>"
        + _tag("cProd", _limpar(item.codigo or numero, 60), True)
        + _tag("cEAN", gtin, True)
        + _tag("xProd", descricao, True)
        + _tag("NCM", motor.so_numeros(item.ncm)[:8], True)
        + _tag("CEST", motor.so_numeros(item.cest)[:7] if item.cest else "")
        + _tag("CFOP", motor.so_numeros(item.cfop)[:4], True)
        + _tag("uCom", unidade, True)
        + _tag("qCom", _num(item.quantidade, 4), True)
        + _tag("vUnCom", _num(item.valor_unitario, 10), True)
        + _tag("vProd", _num(item.valor_total), True)
        + _tag("cEANTrib", gtin, True)
        + _tag("uTrib", unidade, True)
        + _tag("qTrib", _num(item.quantidade, 4), True)
        + _tag("vUnTrib", _num(item.valor_unitario, 10), True)
        + (_tag("vFrete", _num(item.frete)) if float(item.frete or 0) else "")
        + (_tag("vDesc", _num(item.desconto)) if float(item.desconto or 0) else "")
        + _tag("indTot", "1", True)
        + "</prod>"
    )
    imposto = "<imposto>" + _icms_do_item(item, crt) + _pis_cofins(item, crt) + "</imposto>"
    return f'<det nItem="{numero}">{prod}{imposto}</det>'


def _total(itens, frete: float = 0, desconto: float = 0) -> tuple[str, float]:
    produtos = sum(float(i.valor_total or 0) for i in itens)
    icms = sum(float(i.icms_valor or 0) for i in itens)
    base_icms = sum(float(i.icms_base or 0) for i in itens)
    ipi = sum(float(i.ipi_valor or 0) for i in itens)
    pis = sum(float(i.pis_valor or 0) for i in itens)
    cofins = sum(float(i.cofins_valor or 0) for i in itens)
    descontos = desconto + sum(float(i.desconto or 0) for i in itens)
    fretes = frete + sum(float(i.frete or 0) for i in itens)
    total = round(produtos + fretes + ipi - descontos, 2)
    corpo = (
        "<ICMSTot>"
        + _tag("vBC", _num(base_icms), True) + _tag("vICMS", _num(icms), True)
        + _tag("vICMSDeson", "0.00", True) + _tag("vFCP", "0.00", True)
        + _tag("vBCST", "0.00", True) + _tag("vST", "0.00", True)
        + _tag("vFCPST", "0.00", True) + _tag("vFCPSTRet", "0.00", True)
        + _tag("vProd", _num(produtos), True) + _tag("vFrete", _num(fretes), True)
        + _tag("vSeg", "0.00", True) + _tag("vDesc", _num(descontos), True)
        + _tag("vII", "0.00", True) + _tag("vIPI", _num(ipi), True)
        + _tag("vIPIDevol", "0.00", True) + _tag("vPIS", _num(pis), True)
        + _tag("vCOFINS", _num(cofins), True) + _tag("vOutro", "0.00", True)
        + _tag("vNF", _num(total), True)
        + "</ICMSTot>"
    )
    return f"<total>{corpo}</total>", total


def _transp(nota, transportadora) -> str:
    modalidade = nota["frete_modalidade"] or "9"
    partes = [_tag("modFrete", modalidade, True)]
    if transportadora is not None:
        documento = motor.so_numeros(transportadora.cpf_cnpj)
        partes.append(
            "<transporta>"
            + (_tag("CNPJ" if len(documento) == 14 else "CPF", documento) if documento else "")
            + _tag("xNome", _limpar(transportadora.nome, 60))
            + _tag("IE", motor.so_numeros(transportadora.rg_ie))
            + _tag("xEnder", _limpar(transportadora.logradouro, 60))
            + _tag("xMun", _limpar(transportadora.cidade, 60))
            + _tag("UF", (transportadora.uf or "").upper())
            + "</transporta>"
        )
    if nota["placa_veiculo"]:
        partes.append(
            "<veicTransp>"
            + _tag("placa", re.sub(r"[^A-Za-z0-9]", "", nota["placa_veiculo"]).upper()[:7], True)
            + _tag("UF", (nota["uf_veiculo"] or "").upper(), True)
            + "</veicTransp>"
        )
    if nota["volumes"] or float(nota["peso_bruto"] or 0):
        partes.append(
            "<vol>"
            + _tag("qVol", nota["volumes"] or "")
            + _tag("esp", _limpar(nota["especie_volume"], 60))
            + (_tag("pesoL", _num(nota["peso_liquido"], 3)) if float(nota["peso_liquido"] or 0) else "")
            + (_tag("pesoB", _num(nota["peso_bruto"], 3)) if float(nota["peso_bruto"] or 0) else "")
            + "</vol>"
        )
    return "<transp>" + "".join(partes) + "</transp>"


def _cobranca(duplicatas, total: float) -> str:
    if not duplicatas:
        return ""
    soma = sum(float(d.valor or 0) for d in duplicatas)
    partes = [
        "<fat>" + _tag("nFat", "1", True) + _tag("vOrig", _num(soma), True)
        + _tag("vDesc", "0.00", True) + _tag("vLiq", _num(soma), True) + "</fat>"
    ]
    for numero, dup in enumerate(duplicatas, start=1):
        partes.append(
            "<dup>"
            + _tag("nDup", str(dup.numero or numero).zfill(3), True)
            + _tag("dVenc", dup.vencimento.isoformat() if dup.vencimento else "", True)
            + _tag("vDup", _num(dup.valor), True)
            + "</dup>"
        )
    return "<cobr>" + "".join(partes) + "</cobr>"


def _pagamento(pagamentos, total: float) -> str:
    formas = [p for p in pagamentos if p.origem == "PAGAMENTO"] or None
    if formas is None:
        corpo = ("<detPag>" + _tag("indPag", "1", True) + _tag("tPag", "15", True)
                 + _tag("vPag", _num(total), True) + "</detPag>")
        return f"<pag>{corpo}</pag>"
    partes = []
    for forma in formas:
        partes.append(
            "<detPag>"
            + _tag("indPag", "1", True)
            + _tag("tPag", (forma.codigo or "99").zfill(2), True)
            + _tag("vPag", _num(forma.valor), True)
            + "</detPag>"
        )
    return "<pag>" + "".join(partes) + "</pag>"


# --------------------------------------------------------------------------- #
# XML completo
# --------------------------------------------------------------------------- #
def montar_nfe(empresa, nota: dict, itens, parceiro, transportadora,
               duplicatas, pagamentos, numero: int, serie: str,
               emissao: datetime | None = None) -> tuple[str, str, float]:
    """Monta o <NFe> sem assinatura. Devolve (xml, chave, valor total)."""
    if not itens:
        raise ErroEmissao("A nota está sem itens.")
    emissao = emissao or datetime.now(motor.FUSO_BR).replace(microsecond=0)
    if emissao.tzinfo is None:
        emissao = emissao.replace(tzinfo=motor.FUSO_BR)
    ambiente = nota["ambiente"]
    crt = empresa.crt or "1"

    codigo = codigo_numerico(numero, serie)
    chave = montar_chave(empresa.uf, emissao, empresa.cnpj, "55", serie, numero, codigo)

    corpo_itens = "".join(
        _det(item, i, crt, ambiente) for i, item in enumerate(itens, start=1))
    bloco_total, total = _total(itens)

    complementares = _limpar(nota["informacoes_complementares"], 5000)
    inf_adic = ""
    if complementares:
        inf_adic = "<infAdic>" + _tag("infCpl", complementares, True) + "</infAdic>"

    inf = (
        f'<infNFe xmlns="{NS}" Id="NFe{chave}" versao="{VERSAO}">'
        + _ide(empresa, nota, chave, numero, serie, codigo, emissao)
        + _emit(empresa)
        + _dest(parceiro, ambiente)
        + corpo_itens
        + bloco_total
        + _transp(nota, transportadora)
        + _cobranca(duplicatas, total)
        + _pagamento(pagamentos, total)
        + inf_adic
        + "</infNFe>"
    )
    return inf, chave, total


def assinar_nfe(inf_nfe: str, chave_privada, certificado) -> str:
    """<NFe> com a assinatura digital (mesmo padrão do evento: SHA-1 + C14N)."""
    assinatura = motor.assinar(inf_nfe, chave_privada, certificado)
    return f'<NFe xmlns="{NS}">{inf_nfe}{assinatura}</NFe>'


def montar_lote(nfe_assinada: str, lote: int = 1) -> str:
    """Lote **síncrono**: a SEFAZ responde já com o resultado, sem consultar recibo."""
    return (
        f'<enviNFe xmlns="{NS}" versao="{VERSAO}">'
        + _tag("idLote", lote, True)
        + _tag("indSinc", "1", True)
        + nfe_assinada
        + "</enviNFe>"
    )


# --------------------------------------------------------------------------- #
# Transmissão
# --------------------------------------------------------------------------- #
def _endereco(tabela: dict, uf: str, ambiente: str) -> str:
    uf = (uf or "").upper()
    if uf in tabela:
        return tabela[uf][ambiente]
    return (_SVRS if tabela is AUTORIZACAO else _SVRS_EVENTO)[ambiente]


def transmitir(chave_privada, certificado, cadeia, uf: str, ambiente: str,
               nfe_assinada: str, lote: int = 1) -> dict:
    """Envia a nota para a SEFAZ e traduz a resposta."""
    url = _endereco(AUTORIZACAO, uf, ambiente)
    corpo = (
        '<nfeAutorizacaoLote xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">'
        f"<nfeDadosMsg>{montar_lote(nfe_assinada, lote)}</nfeDadosMsg></nfeAutorizacaoLote>"
    )
    try:
        resposta = motor._enviar(
            url, corpo,
            "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4/nfeAutorizacaoLote",
            motor._contexto_ssl(chave_privada, certificado, cadeia),
        )
    except motor.ErroDFe as erro:
        raise ErroEmissao(str(erro)) from None
    return ler_retorno_autorizacao(resposta, nfe_assinada)


def ler_retorno_autorizacao(resposta: str, nfe_assinada: str = "") -> dict:
    """Separa o retorno da autorização (usado também nos testes, com XML gravado).

    100 = autorizado. 150 = autorizado fora de prazo. 110/301/302 = denegado.
    Qualquer outro é rejeição, e o motivo vem em `mensagem`.
    """
    try:
        raiz = ET.fromstring(resposta)
    except ET.ParseError:
        raise ErroEmissao("A SEFAZ respondeu algo que o sistema não entendeu.") from None

    protocolo = raiz.find(f".//{_N}protNFe")
    info = protocolo.find(f"{_N}infProt") if protocolo is not None else None
    codigo = motor._busca(info, "cStat") or motor._busca(raiz, "cStat")
    mensagem = motor._busca(info, "xMotivo") or motor._busca(raiz, "xMotivo")
    autorizada = codigo in ("100", "150")

    proc = ""
    if autorizada and nfe_assinada and protocolo is not None:
        bruto = ET.tostring(protocolo, encoding="unicode")
        bruto = bruto.replace(f'xmlns:ns0="{NS}"', "").replace("ns0:", "")
        if "xmlns=" not in bruto:
            bruto = bruto.replace("<protNFe", f'<protNFe xmlns="{NS}"', 1)
        proc = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<nfeProc xmlns="{NS}" versao="{VERSAO}">{nfe_assinada}{bruto}</nfeProc>'
        )
    return {
        "autorizada": autorizada,
        "denegada": codigo in ("110", "301", "302", "303"),
        "codigo": codigo,
        "mensagem": mensagem,
        "protocolo": motor._busca(info, "nProt"),
        "autorizada_em": motor._data_hora(motor._busca(info, "dhRecbto")),
        "recibo": motor._busca(raiz, "nRec"),
        "xml": proc,
    }


def cancelar(chave_privada, certificado, cadeia, uf: str, ambiente: str, chave_nfe: str,
             cnpj: str, protocolo: str, justificativa: str, sequencia: int = 1) -> dict:
    """Evento 110111 — cancelamento da NF-e autorizada."""
    justificativa = (justificativa or "").strip()
    if len(justificativa) < 15:
        raise ErroEmissao("A justificativa do cancelamento precisa ter 15 letras ou mais.")
    if not protocolo:
        raise ErroEmissao("Só dá para cancelar uma nota que a SEFAZ autorizou.")

    momento = datetime.now(motor.FUSO_BR).replace(microsecond=0)
    identificador = f"ID110111{motor.so_numeros(chave_nfe)}{sequencia:02d}"
    orgao = motor.CODIGO_UF.get((uf or "").upper(), "31")
    inf = (
        f'<infEvento xmlns="{NS}" Id="{identificador}">'
        f"<cOrgao>{orgao}</cOrgao><tpAmb>{ambiente}</tpAmb>"
        f"<CNPJ>{motor.so_numeros(cnpj)}</CNPJ><chNFe>{motor.so_numeros(chave_nfe)}</chNFe>"
        f"<dhEvento>{momento.isoformat()}</dhEvento>"
        f"<tpEvento>110111</tpEvento><nSeqEvento>{sequencia}</nSeqEvento>"
        f"<verEvento>1.00</verEvento>"
        f'<detEvento versao="1.00"><descEvento>Cancelamento</descEvento>'
        f"<nProt>{motor.so_numeros(protocolo)}</nProt>"
        f"<xJust>{_t(_limpar(justificativa, 255))}</xJust></detEvento>"
        "</infEvento>"
    )
    envelope = motor.montar_envelope_evento(
        inf, motor.assinar(inf, chave_privada, certificado))
    corpo = (
        '<nfeRecepcaoEventoNF xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">'
        f"<nfeDadosMsg>{envelope}</nfeDadosMsg></nfeRecepcaoEventoNF>"
    )
    try:
        resposta = motor._enviar(
            _endereco(EVENTO, uf, ambiente), corpo,
            "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4/nfeRecepcaoEvento",
            motor._contexto_ssl(chave_privada, certificado, cadeia),
        )
    except motor.ErroDFe as erro:
        raise ErroEmissao(str(erro)) from None
    retorno = motor.ler_retorno_evento(resposta, envelope)
    # 135 registrado, 155 registrado fora de prazo
    retorno["ok"] = retorno["cstat"] in ("135", "155")
    return retorno
