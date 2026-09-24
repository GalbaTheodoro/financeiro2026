"""Cupom fiscal eletrônico — NFC-e, modelo 65.

O que muda em relação à NF-e
----------------------------
A NFC-e é a mesma NF-e 4.00 por dentro: mesmos itens, mesmos impostos, mesma
assinatura, mesmo lote síncrono. O que muda é o **uso**, e daí saem as regras:

* é venda **presencial a consumidor final**, então `indPres=1`, `indFinal=1` e
  `mod=65`;
* é **só dentro do estado** (`idDest=1`). Para outro estado, ou para empresa que
  vai revender e creditar ICMS, tem de ser NF-e 55;
* o **destinatário é opcional** — a maioria dos cupons sai sem identificar
  ninguém. Quando identifica, vai só o CPF (ou CNPJ) e o nome, sem endereço;
* o cupom impresso leva um **QR Code** que o consumidor lê para conferir a venda
  no site da SEFAZ. É o `infNFeSupl`, e é o único pedaço que a NF-e não tem;
* os **webservices são outros** (em Minas, `nfce.fazenda.mg.gov.br`, não
  `nfe.fazenda.mg.gov.br`).

O QR Code
---------
Versão 2.0, emissão normal (on-line). O texto é::

    <URL da SEFAZ>?p=<chave>|2|<ambiente>|<idToken>|<hash>

onde o `hash` é o SHA-1, em hexadecimal, de tudo que vem antes do próprio hash
**com o CSC colado no fim**::

    hash = SHA1("<chave>|2|<ambiente>|<idToken>" + CSC)

O CSC é justamente o que a SEFAZ e a empresa sabem e mais ninguém: é ele que
prova que o cupom é verdadeiro. Por isso fica cifrado no banco e nunca aparece
no XML — só o hash aparece.

Fonte: Manual de Especificações Técnicas do DANFE NFC-e / QR Code, e a tabela de
web services da SEFAZ-MG (portalsped.fazenda.mg.gov.br/spedmg/nfce/web-services).
"""
from __future__ import annotations

import hashlib
import re

MODELO = "65"

# --------------------------------------------------------------------------- #
# Endereços da SEFAZ para NFC-e (são diferentes dos da NF-e)
# --------------------------------------------------------------------------- #
AUTORIZACAO = {
    "MG": {"1": "https://nfce.fazenda.mg.gov.br/nfce/services/NFeAutorizacao4",
           "2": "https://hnfce.fazenda.mg.gov.br/nfce/services/NFeAutorizacao4"},
}

EVENTO = {
    "MG": {"1": "https://nfce.fazenda.mg.gov.br/nfce/services/NFeRecepcaoEvento4",
           "2": "https://hnfce.fazenda.mg.gov.br/nfce/services/NFeRecepcaoEvento4"},
}

# Onde o QR Code manda o consumidor, e onde ele consulta digitando a chave.
QRCODE = {
    "MG": {"1": "https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml",
           "2": "https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml"},
}

CONSULTA_CHAVE = {
    "MG": {"1": "https://portalsped.fazenda.mg.gov.br/portalnfce",
           "2": "https://hportalsped.fazenda.mg.gov.br/portalnfce"},
}

# Em Minas o cancelamento do cupom tem prazo curto — bem menor que os 24 h da
# NF-e. A tela avisa antes de deixar cancelar.
MINUTOS_PARA_CANCELAR = 30


class ErroCupom(Exception):
    """Falta alguma coisa para emitir o cupom, com a frase pronta para a tela."""


def uf_atendida(uf: str) -> bool:
    return (uf or "").upper() in AUTORIZACAO


def _endereco(tabela: dict, uf: str, ambiente: str, servico: str) -> str:
    uf = (uf or "").upper()
    if uf not in tabela:
        raise ErroCupom(
            f"O cupom fiscal ainda não está ligado à SEFAZ de {uf or '(sem UF)'}. "
            f"Hoje o sistema emite cupom em: {', '.join(sorted(tabela))}. "
            "Para os outros estados, emita NF-e."
        )
    return tabela[uf][ambiente if ambiente in ("1", "2") else "2"]


def url_autorizacao(uf: str, ambiente: str) -> str:
    return _endereco(AUTORIZACAO, uf, ambiente, "autorização")


def url_evento(uf: str, ambiente: str) -> str:
    return _endereco(EVENTO, uf, ambiente, "evento")


def url_consulta_chave(uf: str, ambiente: str) -> str:
    return _endereco(CONSULTA_CHAVE, uf, ambiente, "consulta")


# --------------------------------------------------------------------------- #
# O QR Code
# --------------------------------------------------------------------------- #
def texto_qrcode(chave: str, ambiente: str, csc: str, csc_id: str, uf: str) -> str:
    """O texto que vai dentro do QR Code impresso no cupom.

    Só para emissão normal (on-line), que é a que este sistema faz. A emissão em
    contingência tem outro formato, com data, valor e digest — fica para quando
    houver contingência.
    """
    chave = re.sub(r"\D", "", chave or "")
    if len(chave) != 44:
        raise ErroCupom("A chave de acesso do cupom saiu fora do padrão (44 números).")
    if not (csc or "").strip():
        raise ErroCupom(
            "Falta o CSC da empresa. É o código que a SEFAZ dá para assinar o QR Code do "
            "cupom — sem ele a SEFAZ recusa. Peça no portal da SEFAZ do seu estado (em "
            "Minas, no SIARE) e cadastre em Cadastros > Cupom fiscal."
        )
    identificador = re.sub(r"\D", "", str(csc_id or ""))
    if not identificador:
        raise ErroCupom(
            "Falta o número de identificação do CSC (o idToken, de 1 a 6 dígitos). "
            "Ele vem junto com o CSC no portal da SEFAZ."
        )
    identificador = str(int(identificador))          # sem zeros à esquerda
    dados = f"{chave}|2|{ambiente}|{identificador}"
    # o CSC entra só aqui, no cálculo — nunca no texto que é impresso
    assinatura = hashlib.sha1(f"{dados}{csc.strip()}".encode()).hexdigest().upper()
    return f"{_endereco(QRCODE, uf, ambiente, 'QR Code')}?p={dados}|{assinatura}"


def bloco_suplementar(chave: str, ambiente: str, csc: str, csc_id: str, uf: str) -> str:
    """`infNFeSupl` — o QR Code e o endereço de consulta, que só o cupom tem.

    Entra **entre** o `infNFe` e a assinatura, nessa ordem exata (é o que o
    schema manda).
    """
    from .emissao import _tag

    qr = texto_qrcode(chave, ambiente, csc, csc_id, uf)
    return ("<infNFeSupl>"
            + _tag("qrCode", qr, True)
            + _tag("urlChave", url_consulta_chave(uf, ambiente), True)
            + "</infNFeSupl>")


# --------------------------------------------------------------------------- #
# O CSC guardado
# --------------------------------------------------------------------------- #
def csc_do_ambiente(config, ambiente: str) -> tuple[str, str]:
    """Devolve (CSC, idToken) já decifrados, do ambiente pedido.

    Cada ambiente tem o seu: o CSC de homologação não vale em produção.
    """
    from .correio import decifrar

    if config is None:
        raise ErroCupom(
            "Esta empresa ainda não tem o cupom fiscal configurado — falta o CSC, o "
            "código que a SEFAZ dá para assinar o QR Code. Cadastre em "
            "Cadastros > Cupom fiscal."
        )
    if ambiente == "1":
        guardado, identificador = config.csc_producao, config.csc_id_producao
        onde = "de produção"
    else:
        guardado, identificador = config.csc_homologacao, config.csc_id_homologacao
        onde = "de homologação"
    if not guardado:
        raise ErroCupom(
            f"Falta o CSC {onde} desta empresa. Cada ambiente tem o seu código — "
            "cadastre em Cadastros > Cupom fiscal."
        )
    return decifrar(guardado), identificador or ""
