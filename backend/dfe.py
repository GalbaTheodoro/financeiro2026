"""DF-e — documentos fiscais eletrônicos emitidos contra o CNPJ da empresa.

O que este arquivo faz
----------------------
1. Guarda o certificado digital A1 (arquivo .pfx) **cifrado** no banco e sabe
   abri-lo quando for falar com a SEFAZ.
2. Conversa com o webservice nacional **NFeDistribuiçãoDFe**, que entrega todos
   os documentos emitidos contra um CNPJ, em ordem, pelo NSU (número sequencial
   único). A cada consulta a SEFAZ devolve até 50 documentos compactados.
3. Lê o XML recebido (resumo ou nota completa) e devolve um dicionário simples.
4. Manifesta o destinatário (ciência, confirmação, desconhecimento e operação
   não realizada), assinando o evento com o mesmo certificado.

Sobre a assinatura do XML
-------------------------
A NF-e usa assinatura XMLDSig com SHA-1 e canonicalização C14N 1.0 (inclusiva).
Em vez de depender de uma biblioteca de canonicalização, o XML assinado é
**gerado já na forma canônica**: sem espaços entre as tags, sem tag vazia
abreviada, atributos em ordem e com o xmlns declarado no próprio elemento
assinado. É o mesmo texto que vai no envelope e que entra no cálculo do resumo.

Nada aqui depende de internet para ser testado: `ler_documento` trabalha sobre
o XML, e os testes usam arquivos gravados (testes/dados_dfe/).
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import logging
import os
import re
import ssl
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from .config import SECRET_KEY

log = logging.getLogger("financeiro")

NS = "http://www.portalfiscal.inf.br/nfe"
NS_SIG = "http://www.w3.org/2000/09/xmldsig#"
_N = f"{{{NS}}}"

# Fuso de Brasília — usado no carimbo de hora dos eventos
FUSO_BR = timezone(timedelta(hours=-3))

AMBIENTES = {"1": "Produção", "2": "Homologação"}

# Código do IBGE de cada estado (vai no cUFAutor da consulta e no cOrgao do evento)
CODIGO_UF = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
    "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}
UF_POR_CODIGO = {v: k for k, v in CODIGO_UF.items()}

# Endereços dos webservices nacionais (Ambiente Nacional — SVRS/AN)
WS = {
    "distribuicao": {
        "1": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
        "2": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    },
    "evento": {
        "1": "https://www1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
        "2": "https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
    },
}

# Manifestação do destinatário
EVENTOS = {
    "CIENCIA": ("210210", "Ciencia da Operacao", False),
    "CONFIRMADA": ("210200", "Confirmacao da Operacao", False),
    "DESCONHECIDA": ("210220", "Desconhecimento da Operacao", False),
    "NAO_REALIZADA": ("210240", "Operacao nao Realizada", True),
}
EVENTO_POR_CODIGO = {codigo: nome for nome, (codigo, _d, _j) in EVENTOS.items()}
ROTULO_EVENTO = {
    "CIENCIA": "Ciência da operação",
    "CONFIRMADA": "Confirmada",
    "DESCONHECIDA": "Desconhecida",
    "NAO_REALIZADA": "Operação não realizada",
}

# Formas de pagamento da NF-e (tag tPag)
FORMAS_PAGAMENTO = {
    "01": "Dinheiro", "02": "Cheque", "03": "Cartão de crédito", "04": "Cartão de débito",
    "05": "Crédito na loja", "10": "Vale alimentação", "11": "Vale refeição",
    "12": "Vale presente", "13": "Vale combustível", "14": "Duplicata mercantil",
    "15": "Boleto bancário", "16": "Depósito bancário", "17": "Pix (dinâmico)",
    "18": "Transferência bancária / carteira digital", "19": "Cashback",
    "20": "Pix (estático)", "21": "Crédito em loja", "22": "Pagamento eletrônico não informado",
    "90": "Sem pagamento", "99": "Outros",
}


class ErroDFe(Exception):
    """Falha esperada (certificado, rede ou recusa da SEFAZ) — vira mensagem na tela.

    `detalhe` guarda a resposta crua da SEFAZ (o envelope SOAP inteiro), para a
    tela mostrar em "detalhes técnicos" sem poluir a mensagem principal.
    """

    def __init__(self, mensagem: str, detalhe: str = ""):
        super().__init__(mensagem)
        self.detalhe = detalhe


def motivo_do_fault(resposta: str) -> str:
    """Tira a frase de dentro de um SOAP Fault.

    A SEFAZ devolve HTTP 500 com um envelope de erro; o que interessa está em
    `Reason/Text` (SOAP 1.2) ou `faultstring` (SOAP 1.1). Sem isso, a tela
    mostrava XML cortado no meio e ninguém entendia nada.
    """
    texto = (resposta or "").strip()
    if not texto:
        return ""
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError:
        # não é XML válido: devolve o texto limpo de marcação
        return re.sub(r"<[^>]+>", " ", texto).strip()[:400]
    for nome in ("Text", "faultstring", "Reason", "Detail", "detail"):
        for achado in raiz.iter():
            etiqueta = achado.tag.split("}")[-1]
            if etiqueta == nome and (achado.text or "").strip():
                return " ".join((achado.text or "").split())[:400]
    return " ".join(re.sub(r"<[^>]+>", " ", texto).split())[:400]


# --------------------------------------------------------------------------- #
# Guarda do certificado: o .pfx e a senha ficam cifrados no banco
# --------------------------------------------------------------------------- #
def _chave_cofre() -> bytes:
    return hashlib.sha256(f"agrodock-certificado::{SECRET_KEY}".encode()).digest()


def cifrar(dados: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    selado = AESGCM(_chave_cofre()).encrypt(nonce, dados, None)
    return base64.b64encode(nonce + selado).decode()


def decifrar(texto: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    bruto = base64.b64decode(texto)
    try:
        return AESGCM(_chave_cofre()).decrypt(bruto[:12], bruto[12:], None)
    except Exception:  # noqa: BLE001
        raise ErroDFe(
            "Não foi possível abrir o certificado guardado. Isso acontece quando a chave "
            "de segurança do sistema (FIN_SECRET_KEY) muda. Envie o arquivo .pfx de novo."
        ) from None


def abrir_pfx(pfx: bytes, senha: str):
    """Abre o arquivo A1 e devolve (chave privada, certificado, cadeia)."""
    from cryptography.hazmat.primitives.serialization import pkcs12

    try:
        chave, certificado, cadeia = pkcs12.load_key_and_certificates(
            pfx, (senha or "").encode()
        )
    except Exception:  # noqa: BLE001
        raise ErroDFe(
            "Não foi possível abrir o certificado. Confira se o arquivo é um A1 (.pfx ou .p12) "
            "e se a senha está correta."
        ) from None
    if chave is None or certificado is None:
        raise ErroDFe("O arquivo enviado não tem a chave privada do certificado.")
    return chave, certificado, cadeia or []


def dados_do_certificado(certificado) -> dict:
    """Titular, CNPJ e validade lidos do próprio certificado.

    Nos certificados ICP-Brasil o nome vem como "RAZÃO SOCIAL:12345678000199".
    Quando não vier, procuramos uma sequência de 14 números dentro do arquivo
    (o CNPJ fica numa extensão do padrão brasileiro).
    """
    from cryptography.hazmat.primitives import serialization

    titular = ""
    for atributo in certificado.subject:
        if atributo.oid.dotted_string == "2.5.4.3":  # commonName
            titular = str(atributo.value)

    cnpj = ""
    achado = re.search(r":(\d{14})\s*$", titular)
    if achado:
        cnpj = achado.group(1)
    else:
        bruto = certificado.public_bytes(serialization.Encoding.DER)
        for pedaco in re.findall(rb"(?<!\d)\d{14}(?!\d)", bruto):
            cnpj = pedaco.decode()
            break

    inicio = getattr(certificado, "not_valid_before_utc", None) or certificado.not_valid_before
    fim = getattr(certificado, "not_valid_after_utc", None) or certificado.not_valid_after
    return {
        "titular": titular.split(":")[0].strip() or titular,
        "cnpj": cnpj,
        "valido_de": inicio.replace(tzinfo=None),
        "valido_ate": fim.replace(tzinfo=None),
    }


def _contexto_ssl(chave, certificado, cadeia):
    """Contexto TLS com o certificado do cliente (é assim que a SEFAZ identifica a empresa).

    O par certificado/chave é gravado num arquivo temporário só de leitura para o
    dono, usado na conexão e apagado em seguida — o Python exige um arquivo aqui.
    """
    from cryptography.hazmat.primitives import serialization

    pem = certificado.public_bytes(serialization.Encoding.PEM)
    for extra in cadeia:
        pem += extra.public_bytes(serialization.Encoding.PEM)
    pem += chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    caminho = tempfile.NamedTemporaryFile(prefix="agrodock-", suffix=".pem", delete=False)
    try:
        os.chmod(caminho.name, 0o600)
        caminho.write(pem)
        caminho.close()
        contexto = ssl.create_default_context()
        # alguns servidores da SEFAZ ainda negociam TLS 1.2 com cifras antigas
        contexto.set_ciphers("DEFAULT@SECLEVEL=1")
        contexto.load_cert_chain(caminho.name)
        return contexto
    finally:
        try:
            os.unlink(caminho.name)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Conversa com a SEFAZ
# --------------------------------------------------------------------------- #
def _enviar(url: str, corpo_xml: str, acao_ns: str, contexto) -> str:
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        f"<soap12:Body>{corpo_xml}</soap12:Body></soap12:Envelope>"
    )
    requisicao = urllib.request.Request(
        url,
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": f'application/soap+xml; charset=utf-8; action="{acao_ns}"',
            "User-Agent": "AgroDock/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=45, context=contexto) as resposta:
            return resposta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        bruto = erro.read().decode("utf-8", "replace")
        motivo = motivo_do_fault(bruto)
        raise ErroDFe(
            f"A SEFAZ devolveu erro (HTTP {erro.code})"
            + (f": {motivo}" if motivo else "."),
            detalhe=f"Endereço: {url}\nAção: {acao_ns}\n\n{bruto[:4000]}",
        ) from None
    except urllib.error.URLError as erro:
        raise ErroDFe(
            f"Não foi possível falar com a SEFAZ: {erro.reason}. "
            "Tente de novo em alguns minutos."
        ) from None


# Quando o corpo do envio não casa com o WSDL, o servidor responde que não achou
# o método. Cada SEFAZ monta o WSDL de um jeito — umas esperam o <nfeDadosMsg>
# solto no corpo, outras esperam ele dentro de um invólucro com o nome da
# operação. Em vez de adivinhar por estado, o sistema tenta as duas formas.
_FALHA_DE_DESPACHO = ("despacho", "dispatch", "cannot find", "não foi possível localizar",
                      "nao foi possivel localizar", "não é possível localizar",
                      "nao e possivel localizar", "operation not found")


def corpo_servico(ns_servico: str, dados: str, envoltorio: str = "") -> list[str]:
    """As duas formas do corpo SOAP, na ordem em que valem a pena ser tentadas."""
    solto = f'<nfeDadosMsg xmlns="{ns_servico}">{dados}</nfeDadosMsg>'
    if not envoltorio:
        return [solto]
    embrulhado = (f'<{envoltorio} xmlns="{ns_servico}">'
                  f"<nfeDadosMsg>{dados}</nfeDadosMsg></{envoltorio}>")
    return [solto, embrulhado]


def _enviar_variantes(url: str, corpos: list[str], acao_ns: str, contexto) -> str:
    """Envia tentando cada formato de corpo até um ser aceito.

    Só troca de formato quando a SEFAZ reclama de não achar o método; qualquer
    outro erro sobe na hora, para não mascarar problema de verdade.
    """
    ultimo: ErroDFe | None = None
    for i, corpo in enumerate(corpos):
        try:
            return _enviar(url, corpo, acao_ns, contexto)
        except ErroDFe as erro:
            texto = str(erro).lower()
            if i + 1 < len(corpos) and any(p in texto for p in _FALHA_DE_DESPACHO):
                ultimo = erro
                continue
            raise
    raise ultimo if ultimo else ErroDFe("Não foi possível falar com a SEFAZ.")


def _busca(no, *nomes) -> str:
    """Texto do primeiro nome encontrado em qualquer nível abaixo de `no`."""
    if no is None:
        return ""
    for nome in nomes:
        achado = no.find(f".//{_N}{nome}")
        if achado is None:
            achado = no.find(f".//{nome}")
        if achado is not None and achado.text:
            return achado.text.strip()
    return ""


def _numero(texto: str) -> float:
    try:
        return round(float(texto), 6)
    except (TypeError, ValueError):
        return 0.0


def _data_hora(texto: str):
    """'2026-09-16T10:33:00-03:00' -> datetime sem fuso (hora local do documento)."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(texto[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None


def consultar_distribuicao(chave, certificado, cadeia, ambiente: str, uf: str,
                           cnpj: str, ultimo_nsu: str) -> dict:
    """Pede à SEFAZ os documentos emitidos contra o CNPJ a partir do último NSU.

    Devolve ``{"cstat", "motivo", "ultimo_nsu", "max_nsu", "documentos": [...]}``.
    Cada documento traz ``{"nsu", "esquema", "xml"}`` já descompactado.
    """
    ambiente = "2" if str(ambiente) == "2" else "1"
    codigo_uf = CODIGO_UF.get((uf or "").upper(), "31")
    documento = re.sub(r"\D", "", cnpj or "")
    if len(documento) not in (11, 14):
        raise ErroDFe("O CNPJ da empresa não está preenchido corretamente no cadastro.")
    etiqueta = "CNPJ" if len(documento) == 14 else "CPF"
    dados = (
        f'<distDFeInt xmlns="{NS}" versao="1.01">'
        f"<tpAmb>{ambiente}</tpAmb><cUFAutor>{codigo_uf}</cUFAutor>"
        f"<{etiqueta}>{documento}</{etiqueta}>"
        f"<distNSU><ultNSU>{str(ultimo_nsu or '0').zfill(15)}</ultNSU></distNSU>"
        "</distDFeInt>"
    )
    corpos = corpo_servico(
        "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe",
        dados, "nfeDistDFeInteresse")
    resposta = _enviar_variantes(
        WS["distribuicao"][ambiente], list(reversed(corpos)),
        "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse",
        _contexto_ssl(chave, certificado, cadeia),
    )
    return ler_retorno_distribuicao(resposta)


def ler_retorno_distribuicao(resposta: str) -> dict:
    """Separa o retorno da SEFAZ (também usado nos testes, com XML gravado)."""
    try:
        raiz = ET.fromstring(resposta)
    except ET.ParseError:
        raise ErroDFe("A SEFAZ respondeu algo que o sistema não entendeu.") from None
    retorno = raiz.find(f".//{_N}retDistDFeInt")
    if retorno is None:
        retorno = raiz.find(".//retDistDFeInt")
    if retorno is None:
        retorno = raiz
    documentos = []
    for zip_ in retorno.findall(f".//{_N}docZip") or retorno.findall(".//docZip"):
        try:
            xml = gzip.decompress(base64.b64decode(zip_.text or "")).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            log.warning("Documento do DF-e veio ilegível (NSU %s)", zip_.get("NSU"))
            continue
        documentos.append({
            "nsu": (zip_.get("NSU") or "").zfill(15),
            "esquema": zip_.get("schema") or "",
            "xml": xml,
        })
    return {
        "cstat": _busca(retorno, "cStat"),
        "motivo": _busca(retorno, "xMotivo"),
        "ultimo_nsu": (_busca(retorno, "ultNSU") or "").zfill(15),
        "max_nsu": (_busca(retorno, "maxNSU") or "").zfill(15),
        "documentos": documentos,
    }


# --------------------------------------------------------------------------- #
# Leitura do XML recebido
# --------------------------------------------------------------------------- #
def ler_documento(xml: str, esquema: str = "") -> dict | None:
    """Traduz o XML de um documento do DF-e num dicionário.

    Atende os quatro formatos que a SEFAZ entrega: resumo da nota (resNFe), nota
    completa (nfeProc/NFe), resumo de evento (resEvento) e evento completo
    (procEventoNFe).
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:
        return None
    marca = raiz.tag.split("}")[-1]

    if marca in ("nfeProc", "NFe"):
        return _ler_nfe(raiz, xml, esquema)
    if marca == "resNFe":
        return _ler_resumo(raiz, xml, esquema)
    if marca in ("procEventoNFe", "resEvento", "evento"):
        return _ler_evento(raiz, xml, esquema)
    return None


def _ler_resumo(raiz, xml: str, esquema: str) -> dict:
    situacao = {"1": "AUTORIZADA", "2": "DENEGADA", "3": "CANCELADA"}
    chave = _busca(raiz, "chNFe")
    return {
        "tipo": "NFE",
        "resumo": True,
        "esquema": esquema or "resNFe",
        "chave": chave,
        "modelo": chave[20:22] if len(chave) == 44 else "",
        "serie": str(int(chave[22:25])) if len(chave) == 44 and chave[22:25].isdigit() else "",
        "numero": str(int(chave[25:34])) if len(chave) == 44 and chave[25:34].isdigit() else "",
        "emitente_cnpj": _busca(raiz, "CNPJ", "CPF"),
        "emitente_nome": _busca(raiz, "xNome"),
        "emitente_ie": _busca(raiz, "IE"),
        "emitente_uf": UF_POR_CODIGO.get(chave[:2], "") if len(chave) == 44 else "",
        "data_emissao": _data_hora(_busca(raiz, "dhEmi")),
        "tipo_operacao": _busca(raiz, "tpNF"),
        "valor_total": _numero(_busca(raiz, "vNF")),
        "protocolo": _busca(raiz, "nProt"),
        "data_autorizacao": _data_hora(_busca(raiz, "dhRecbto")),
        "situacao": situacao.get(_busca(raiz, "cSitNFe"), "AUTORIZADA"),
        "xml": xml,
        "itens": [],
        "pagamentos": [],
    }


def _ler_nfe(raiz, xml: str, esquema: str) -> dict:
    inf = raiz.find(f".//{_N}infNFe")
    if inf is None:
        return _ler_resumo(raiz, xml, esquema)
    ide = inf.find(f"{_N}ide")
    emit = inf.find(f"{_N}emit")
    dest = inf.find(f"{_N}dest")
    total = inf.find(f".//{_N}ICMSTot")
    chave = (inf.get("Id") or "").replace("NFe", "")
    protocolo = raiz.find(f".//{_N}infProt")

    dados = {
        "tipo": "NFE",
        "resumo": False,
        "esquema": esquema or "procNFe",
        "chave": chave,
        "modelo": _busca(ide, "mod"),
        "serie": _busca(ide, "serie"),
        "numero": _busca(ide, "nNF"),
        "data_emissao": _data_hora(_busca(ide, "dhEmi") or _busca(ide, "dEmi")),
        "natureza_operacao": _busca(ide, "natOp"),
        "tipo_operacao": _busca(ide, "tpNF"),
        "finalidade": _busca(ide, "finNFe"),
        "emitente_cnpj": _busca(emit, "CNPJ", "CPF"),
        "emitente_nome": _busca(emit, "xNome"),
        "emitente_ie": _busca(emit, "IE"),
        "emitente_uf": _busca(emit, "UF"),
        "destinatario_cnpj": _busca(dest, "CNPJ", "CPF"),
        "destinatario_nome": _busca(dest, "xNome"),
        "valor_total": _numero(_busca(total, "vNF")),
        "valor_produtos": _numero(_busca(total, "vProd")),
        "valor_icms": _numero(_busca(total, "vICMS")),
        "valor_ipi": _numero(_busca(total, "vIPI")),
        "valor_frete": _numero(_busca(total, "vFrete")),
        "valor_desconto": _numero(_busca(total, "vDesc")),
        "protocolo": _busca(protocolo, "nProt"),
        "data_autorizacao": _data_hora(_busca(protocolo, "dhRecbto")),
        "situacao": "AUTORIZADA",
        "xml": xml,
        "itens": [],
        "pagamentos": [],
    }
    if _busca(protocolo, "cStat") in ("110", "301", "302", "303"):
        dados["situacao"] = "DENEGADA"

    for det in inf.findall(f"{_N}det"):
        prod = det.find(f"{_N}prod")
        imposto = det.find(f"{_N}imposto")
        icms = imposto.find(f".//{_N}ICMS") if imposto is not None else None
        dados["itens"].append({
            "numero": int(det.get("nItem") or len(dados["itens"]) + 1),
            "codigo": _busca(prod, "cProd"),
            "gtin": _limpar_gtin(_busca(prod, "cEAN")),
            "descricao": _busca(prod, "xProd"),
            "ncm": _busca(prod, "NCM"),
            "cest": _busca(prod, "CEST"),
            "cfop": _busca(prod, "CFOP"),
            "unidade": _busca(prod, "uCom"),
            "quantidade": _numero(_busca(prod, "qCom")),
            "valor_unitario": _numero(_busca(prod, "vUnCom")),
            "valor_total": _numero(_busca(prod, "vProd")),
            "desconto": _numero(_busca(prod, "vDesc")),
            "frete": _numero(_busca(prod, "vFrete")),
            "icms_cst": _busca(icms, "CST", "CSOSN"),
            "icms_base": _numero(_busca(icms, "vBC")),
            "icms_aliquota": _numero(_busca(icms, "pICMS")),
            "icms_valor": _numero(_busca(icms, "vICMS")),
            "ipi_valor": _numero(_busca(imposto.find(f"{_N}IPI") if imposto is not None else None, "vIPI")),
            "pis_valor": _numero(_busca(imposto.find(f"{_N}PIS") if imposto is not None else None, "vPIS")),
            "cofins_valor": _numero(_busca(imposto.find(f"{_N}COFINS") if imposto is not None else None, "vCOFINS")),
        })

    for pagamento in inf.findall(f".//{_N}detPag"):
        codigo = _busca(pagamento, "tPag")
        cartao = pagamento.find(f"{_N}card")
        dados["pagamentos"].append({
            "origem": "PAGAMENTO",
            "codigo": codigo,
            "descricao": _busca(pagamento, "xPag") or FORMAS_PAGAMENTO.get(codigo, "Outros"),
            "valor": _numero(_busca(pagamento, "vPag")),
            "troco": _numero(_busca(inf.find(f".//{_N}pag"), "vTroco")),
            "bandeira": _busca(cartao, "tBand"),
            "cnpj_credenciadora": _busca(cartao, "CNPJ"),
            "autorizacao": _busca(cartao, "cAut"),
        })
    for duplicata in inf.findall(f".//{_N}dup"):
        dados["pagamentos"].append({
            "origem": "DUPLICATA",
            "codigo": "14",
            "descricao": "Duplicata",
            "numero": _busca(duplicata, "nDup"),
            "vencimento": _busca(duplicata, "dVenc"),
            "valor": _numero(_busca(duplicata, "vDup")),
        })
    return dados


def _limpar_gtin(valor: str) -> str:
    return "" if (valor or "").upper() in ("SEM GTIN", "SEM EAN") else (valor or "")


def _ler_evento(raiz, xml: str, esquema: str) -> dict:
    codigo = _busca(raiz, "tpEvento")
    return {
        "tipo": "EVENTO",
        "resumo": esquema.startswith("resEvento"),
        "esquema": esquema or "procEventoNFe",
        "chave": _busca(raiz, "chNFe"),
        "codigo_evento": codigo,
        "descricao_evento": _busca(raiz, "xEvento", "descEvento"),
        "sequencia_evento": _busca(raiz, "nSeqEvento"),
        "data_evento": _data_hora(_busca(raiz, "dhEvento")),
        "protocolo": _busca(raiz, "nProt"),
        "emitente_cnpj": _busca(raiz, "CNPJ", "CPF"),
        "xml": xml,
        "itens": [],
        "pagamentos": [],
    }


# --------------------------------------------------------------------------- #
# Manifestação do destinatário (evento assinado)
# --------------------------------------------------------------------------- #
def _escapar_texto(valor: str) -> str:
    return (valor or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escapar_atributo(valor: str) -> str:
    return (_escapar_texto(valor).replace('"', "&quot;")
            .replace("\t", "&#x9;").replace("\n", "&#xA;").replace("\r", "&#xD;"))


def montar_inf_evento(chave_nfe: str, cnpj: str, tipo: str, ambiente: str,
                      sequencia: int = 1, justificativa: str = "",
                      quando: datetime | None = None) -> str:
    """Monta o <infEvento> já na forma canônica (é esse texto que será assinado)."""
    codigo, descricao, exige_justificativa = EVENTOS[tipo]
    documento = re.sub(r"\D", "", cnpj or "")
    chave_nfe = re.sub(r"\D", "", chave_nfe or "")
    if len(chave_nfe) != 44:
        raise ErroDFe("A chave da nota precisa ter 44 números.")
    if exige_justificativa and len(justificativa.strip()) < 15:
        raise ErroDFe("Para 'Operação não realizada' escreva uma justificativa com 15 letras ou mais.")
    # mesma regra do dhEmi: sem fuso é UTC (o servidor roda em UTC e o banco
    # guarda assim), então converte-se — etiquetar jogaria o evento 3h à frente
    momento = quando or datetime.now(FUSO_BR)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    momento = min(momento.astimezone(FUSO_BR),
                  datetime.now(FUSO_BR)).replace(microsecond=0)
    identificador = f"ID{codigo}{chave_nfe}{sequencia:02d}"
    detalhe = f"<descEvento>{descricao}</descEvento>"
    if exige_justificativa or (justificativa.strip() and tipo == "DESCONHECIDA"):
        detalhe += f"<xJust>{_escapar_texto(justificativa.strip())}</xJust>"
    return (
        f'<infEvento xmlns="{NS}" Id="{_escapar_atributo(identificador)}">'
        f"<cOrgao>91</cOrgao><tpAmb>{ambiente}</tpAmb>"
        f"<CNPJ>{documento}</CNPJ><chNFe>{chave_nfe}</chNFe>"
        f"<dhEvento>{momento.isoformat()}</dhEvento>"
        f"<tpEvento>{codigo}</tpEvento><nSeqEvento>{sequencia}</nSeqEvento>"
        f"<verEvento>1.00</verEvento>"
        f'<detEvento versao="1.00">{detalhe}</detEvento>'
        "</infEvento>"
    )


def assinar(inf_evento: str, chave_privada, certificado) -> str:
    """Assinatura XMLDSig do <infEvento>, no formato que a NF-e exige."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    identificador = re.search(r'Id="([^"]+)"', inf_evento).group(1)
    resumo = base64.b64encode(hashlib.sha1(inf_evento.encode("utf-8")).digest()).decode()
    c14n = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
    assinado = (
        f'<SignedInfo xmlns="{NS_SIG}">'
        f'<CanonicalizationMethod Algorithm="{c14n}"></CanonicalizationMethod>'
        f'<SignatureMethod Algorithm="{NS_SIG}rsa-sha1"></SignatureMethod>'
        f'<Reference URI="#{identificador}"><Transforms>'
        f'<Transform Algorithm="{NS_SIG}enveloped-signature"></Transform>'
        f'<Transform Algorithm="{c14n}"></Transform>'
        "</Transforms>"
        f'<DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"></DigestMethod>'
        f"<DigestValue>{resumo}</DigestValue></Reference></SignedInfo>"
    )
    assinatura = base64.b64encode(
        chave_privada.sign(assinado.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
    ).decode()
    publico = base64.b64encode(
        certificado.public_bytes(serialization.Encoding.DER)
    ).decode()
    return (
        f'<Signature xmlns="{NS_SIG}">{assinado}'
        f"<SignatureValue>{assinatura}</SignatureValue>"
        f"<KeyInfo><X509Data><X509Certificate>{publico}</X509Certificate></X509Data></KeyInfo>"
        "</Signature>"
    )


def montar_envelope_evento(inf_evento: str, assinatura: str) -> str:
    return (
        f'<envEvento xmlns="{NS}" versao="1.00"><idLote>1</idLote>'
        f'<evento xmlns="{NS}" versao="1.00">{inf_evento}{assinatura}</evento></envEvento>'
    )


def manifestar(chave_privada, certificado, cadeia, ambiente: str, chave_nfe: str,
               cnpj: str, tipo: str, justificativa: str = "", sequencia: int = 1) -> dict:
    """Envia a manifestação do destinatário. Devolve o retorno já traduzido."""
    if tipo not in EVENTOS:
        raise ErroDFe("Tipo de manifestação desconhecido.")
    ambiente = "2" if str(ambiente) == "2" else "1"
    inf = montar_inf_evento(chave_nfe, cnpj, tipo, ambiente, sequencia, justificativa)
    envelope = montar_envelope_evento(inf, assinar(inf, chave_privada, certificado))
    corpos = corpo_servico(
        "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4",
        envelope, "nfeRecepcaoEventoNF")
    resposta = _enviar_variantes(
        WS["evento"][ambiente], corpos,
        "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4/nfeRecepcaoEvento",
        _contexto_ssl(chave_privada, certificado, cadeia),
    )
    return ler_retorno_evento(resposta, envelope)


def ler_retorno_evento(resposta: str, envelope: str = "") -> dict:
    """Lê o retorno da manifestação (usado também nos testes, com XML gravado).

    Códigos que valem como aceite: 135 (registrado), 136 (registrado fora de
    prazo) e 573 (evento já registrado antes).
    """
    try:
        raiz = ET.fromstring(resposta)
    except ET.ParseError:
        raise ErroDFe("A SEFAZ respondeu algo que o sistema não entendeu.") from None
    retorno = raiz.find(f".//{_N}retEnvEvento")
    if retorno is None:
        retorno = raiz
    item = retorno.find(f".//{_N}infEvento")
    codigo = _busca(item, "cStat") or _busca(retorno, "cStat")
    motivo = _busca(item, "xMotivo") or _busca(retorno, "xMotivo")
    return {
        "ok": codigo in ("135", "136", "573"),
        "cstat": codigo,
        "motivo": motivo,
        "protocolo": _busca(item, "nProt"),
        "registrado_em": _data_hora(_busca(item, "dhRegEvento")),
        "envelope": envelope,
    }


# --------------------------------------------------------------------------- #
# Ajudas usadas pelas rotas
# --------------------------------------------------------------------------- #
def so_numeros(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def formatar_documento(valor: str | None) -> str:
    """CNPJ 12345678000199 -> 12.345.678/0001-99 (e CPF no formato dele)."""
    numero = so_numeros(valor)
    if len(numero) == 14:
        return f"{numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]}"
    if len(numero) == 11:
        return f"{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}"
    return valor or ""


def formatar_chave(chave: str | None) -> str:
    numero = so_numeros(chave)
    return " ".join(numero[i:i + 4] for i in range(0, len(numero), 4)) if numero else ""


def uf_da_chave(chave: str | None) -> str:
    numero = so_numeros(chave)
    return UF_POR_CODIGO.get(numero[:2], "") if len(numero) == 44 else ""
