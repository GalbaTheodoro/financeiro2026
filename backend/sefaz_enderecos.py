"""Endereços dos webservices da SEFAZ, por estado — e editáveis pela tela.

Por que isto existe
-------------------
Os endereços da SEFAZ **mudam**. Goiás trocou a URL do QR Code da NFC-e em 2025
(Informe Técnico 2025.003, de http para https, com host novo); a Paraíba, Santa
Catarina e outras já fizeram o mesmo antes. Quando isso acontece com um endereço
chumbado no código, o cupom do cliente para de sair no balcão e ele fica esperando
uma nova versão do sistema.

Então o desenho é: o código traz o **padrão de fábrica**, e quem manda é o que
estiver gravado na tabela. O administrador do site corrige um endereço na tela em
trinta segundos, sem republicar nada.

A regra da recusa
-----------------
Endereço em branco **não vira palpite**. Sem a URL do QR Code não há como montar o
`infNFeSupl`, e um QR Code errado é pior que não emitir: a SEFAZ devolve a rejeição
395, ou pior — autoriza e o consumidor não consegue conferir a compra. Por isso
``exigir`` levanta erro com a frase dizendo exatamente o que falta e onde preencher.

De onde vieram os padrões
-------------------------
Cada linha leva uma ``fonte``, que a tela mostra, porque a confiança não é a mesma:

* ``MG`` — em uso desde o começo, cupom emitido de verdade;
* ``SP`` — conferido no portal da SEFAZ-SP (portal.fazenda.sp.gov.br, serviços da
  NFC-e → WebServices);
* ``SVRS`` — conferido no portal do SVRS (dfe-portal.svrs.rs.gov.br/Nfce/Servicos);
* ``GO`` (QR Code) — Informe Técnico 2025.003, por fonte secundária: **confira no
  portal da SEFAZ-GO antes de usar em produção**;
* o que não foi confirmado fica **em branco** de propósito.

Prazo de cancelamento
---------------------
Também é por estado: Minas dá 30 minutos para cancelar o cupom; o Tocantins, 24
horas (manual da NFC-e do estado). Quem não estiver na tabela usa 30 minutos, que
é o prazo mais curto — errar para o lado seguro.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import EnderecoSefaz

# os quatro serviços que um estado precisa ter para o cupom sair
SERVICOS = {
    "autorizacao": "Autorização (envio do cupom)",
    "evento": "Evento (cancelamento)",
    "qrcode": "QR Code impresso no cupom",
    "consulta": "Consulta pela chave de acesso",
}
AMBIENTES = {"1": "Produção", "2": "Homologação"}

# --------------------------------------------------------------------------- #
# SEFAZ Virtual do Rio Grande do Sul — autoriza a NFC-e da maioria dos estados
# --------------------------------------------------------------------------- #
_SVRS_AUT = {
    "1": "https://nfce.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
    "2": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
}
_SVRS_EVT = {
    "1": "https://nfce.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
    "2": "https://nfce-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
}

# --------------------------------------------------------------------------- #
# O padrão de fábrica do cupom (modelo 65)
#
# Estrutura: UF -> {serviço: {ambiente: url}}. Valor vazio quer dizer "não
# confirmei" — a tela pede, e o sistema recusa emitir até alguém preencher.
# --------------------------------------------------------------------------- #
PADRAO_65: dict[str, dict] = {
    "MG": {
        "nome": "Minas Gerais",
        "fonte": "em uso no sistema desde o início",
        "onde": "portalsped.fazenda.mg.gov.br/spedmg/nfce/web-services",
        "minutos_cancelamento": 30,
        "autorizacao": {"1": "https://nfce.fazenda.mg.gov.br/nfce/services/NFeAutorizacao4",
                        "2": "https://hnfce.fazenda.mg.gov.br/nfce/services/NFeAutorizacao4"},
        "evento": {"1": "https://nfce.fazenda.mg.gov.br/nfce/services/NFeRecepcaoEvento4",
                   "2": "https://hnfce.fazenda.mg.gov.br/nfce/services/NFeRecepcaoEvento4"},
        "qrcode": {"1": "https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml",
                   "2": "https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml"},
        "consulta": {"1": "https://portalsped.fazenda.mg.gov.br/portalnfce",
                     "2": "https://hportalsped.fazenda.mg.gov.br/portalnfce"},
    },
    "SP": {
        "nome": "São Paulo",
        "fonte": "portal.fazenda.sp.gov.br — serviços da NFC-e, WebServices",
        "onde": "portal.fazenda.sp.gov.br/servicos/nfce → WebServices",
        "minutos_cancelamento": 30,
        "autorizacao": {"1": "https://nfce.fazenda.sp.gov.br/ws/NFeAutorizacao4.asmx",
                        "2": "https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeAutorizacao4.asmx"},
        "evento": {"1": "https://nfce.fazenda.sp.gov.br/ws/NFeRecepcaoEvento4.asmx",
                   "2": "https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeRecepcaoEvento4.asmx"},
        "qrcode": {"1": "https://www.nfce.fazenda.sp.gov.br/qrcode",
                   "2": "https://www.homologacao.nfce.fazenda.sp.gov.br/qrcode"},
        "consulta": {"1": "https://www.nfce.fazenda.sp.gov.br/NFCeConsultaPublica",
                     "2": "https://www.homologacao.nfce.fazenda.sp.gov.br/consulta"},
    },
    "GO": {
        "nome": "Goiás",
        "fonte": "autorização pelo SVRS; QR Code do Informe Técnico 2025.003 "
                 "(fonte secundária — confira no portal da SEFAZ-GO)",
        "onde": "goias.gov.br/economia → NFC-e (Informe Técnico 2025.003)",
        "minutos_cancelamento": 30,
        "autorizacao": dict(_SVRS_AUT),
        "evento": dict(_SVRS_EVT),
        "qrcode": {"1": "https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe",
                   "2": "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"},
        # a consulta pela chave de Goiás eu não confirmei em fonte oficial
        "consulta": {"1": "", "2": ""},
    },
    "TO": {
        "nome": "Tocantins",
        "fonte": "autorização pelo SVRS, confirmada pela própria SEFAZ-TO "
                 "(o estado não tem servidor próprio de NFC-e). QR Code e consulta "
                 "por chave: copie do portal do estado — o site da SEFAZ-TO bloqueia "
                 "leitura automática, então estes dois não dá para trazer prontos",
        "onde": "to.gov.br/sefaz/nfc-e → documentação; a consulta por chave é a "
                "página sefaz.to.gov.br/nfce/consulta.jsf",
        # o manual da NFC-e do Tocantins fala em 24 horas para cancelar
        "minutos_cancelamento": 24 * 60,
        "autorizacao": dict(_SVRS_AUT),
        "evento": dict(_SVRS_EVT),
        "qrcode": {"1": "", "2": ""},
        "consulta": {"1": "", "2": ""},
    },
}

MINUTOS_CANCELAMENTO_PADRAO = 30


class EnderecoFaltando(Exception):
    """Falta um endereço para esse estado — a frase já é a da tela."""


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def _linha(db: Session | None, modelo: str, uf: str) -> EnderecoSefaz | None:
    """Sem banco à mão (testes de unidade), vale só o padrão de fábrica."""
    if db is None:
        return None
    return (
        db.query(EnderecoSefaz)
        .filter(EnderecoSefaz.modelo == modelo, EnderecoSefaz.uf == (uf or "").upper())
        .first()
    )


# Hoje a tela cuida só do cupom (65). A NF-e (55) tem a tabela dela em
# ``backend/emissao.py`` e já atende o país inteiro — quem não tem servidor
# próprio cai no SVRS. A coluna `modelo` existe para o dia em que a NF-e também
# precisar ser editável; até lá, só o 65 é aceito, para ninguém gravar uma linha
# que nada lê.
MODELOS = {"65": "Cupom fiscal (NFC-e)"}


def _do_padrao(modelo: str, uf: str) -> dict:
    if modelo != "65":
        return {}
    return PADRAO_65.get((uf or "").upper(), {})


def conferir_modelo(modelo: str) -> str:
    if modelo not in MODELOS:
        raise EnderecoFaltando(
            "Esta tela cuida dos endereços do cupom fiscal (modelo 65). A NF-e (55) "
            "usa a tabela do próprio sistema, que já atende todos os estados.")
    return modelo


def _coluna(servico: str, ambiente: str) -> str:
    """('qrcode', '1') -> 'qrcode_producao'."""
    return f"{servico}_{'producao' if ambiente == '1' else 'homologacao'}"


def endereco(db: Session | None, modelo: str, uf: str, servico: str, ambiente: str) -> str:
    """O endereço que vale: o gravado, senão o de fábrica, senão vazio."""
    uf = (uf or "").upper()
    ambiente = ambiente if ambiente in ("1", "2") else "2"
    linha = _linha(db, modelo, uf)
    if linha is not None:
        gravado = (getattr(linha, _coluna(servico, ambiente), None) or "").strip()
        if gravado:
            return gravado
    return (_do_padrao(modelo, uf).get(servico, {}).get(ambiente) or "").strip()


def exigir(db: Session | None, modelo: str, uf: str, servico: str, ambiente: str) -> str:
    """Igual a ``endereco``, mas explica o que fazer quando está em branco."""
    achado = endereco(db, modelo, uf, servico, ambiente)
    if achado:
        return achado
    uf = (uf or "").upper()
    if not uf:
        raise EnderecoFaltando(
            "A empresa está sem UF. Preencha o estado em Cadastros > Empresa para o "
            "sistema saber com qual SEFAZ falar."
        )
    raise EnderecoFaltando(
        f"Falta o endereço de \"{SERVICOS.get(servico, servico)}\" da SEFAZ de {uf} "
        f"({AMBIENTES.get(ambiente, ambiente).lower()}). O administrador do sistema "
        "preenche em Administração > Endereços da SEFAZ, copiando do portal da SEFAZ "
        f"de {uf}. Enquanto estiver em branco o sistema não emite — um endereço "
        "chutado faz a SEFAZ recusar (rejeição 395) ou gera um cupom que o consumidor "
        "não consegue conferir."
    )


def minutos_cancelamento(db: Session | None, modelo: str, uf: str) -> int:
    linha = _linha(db, modelo, uf)
    if linha is not None and linha.minutos_cancelamento:
        return int(linha.minutos_cancelamento)
    return int(_do_padrao(modelo, uf).get("minutos_cancelamento")
               or MINUTOS_CANCELAMENTO_PADRAO)


def ufs_atendidas(db: Session | None, modelo: str = "65") -> list[str]:
    """Os estados que têm, no mínimo, autorização e QR Code — os que emitem hoje."""
    saida = []
    gravadas = ({l.uf for l in db.query(EnderecoSefaz)
                 .filter(EnderecoSefaz.modelo == modelo).all()} if db is not None else set())
    for uf in sorted(set(PADRAO_65) | gravadas):
        if (endereco(db, modelo, uf, "autorizacao", "1")
                and endereco(db, modelo, uf, "qrcode", "1")):
            saida.append(uf)
    return saida


def faltando(db: Session | None, modelo: str, uf: str) -> list[str]:
    """Os serviços sem endereço, em português — é o que a tela mostra ao cliente."""
    if not (uf or "").strip():
        return ["a UF da empresa"]
    return [nome for servico, nome in SERVICOS.items()
            if not endereco(db, modelo, uf, servico, "1")]


def atendida(db: Session | None, uf: str, modelo: str = "65") -> bool:
    uf = (uf or "").upper()
    return bool(endereco(db, modelo, uf, "autorizacao", "1")
                and endereco(db, modelo, uf, "qrcode", "1"))


# --------------------------------------------------------------------------- #
# A tela do administrador
# --------------------------------------------------------------------------- #
def quadro(db: Session, modelo: str = "65") -> list[dict]:
    """Um estado por linha, com os oito endereços e de onde veio cada um."""
    gravadas = {l.uf: l for l in
                db.query(EnderecoSefaz).filter(EnderecoSefaz.modelo == modelo).all()}
    linhas = []
    for uf in sorted(set(PADRAO_65) | set(gravadas)):
        padrao = _do_padrao(modelo, uf)
        linha = gravadas.get(uf)
        campos = {}
        for servico in SERVICOS:
            for ambiente in ("1", "2"):
                chave = _coluna(servico, ambiente)
                gravado = (getattr(linha, chave, None) or "").strip() if linha else ""
                fabrica = (padrao.get(servico, {}).get(ambiente) or "").strip()
                campos[chave] = {"valor": gravado or fabrica,
                                 "editado": bool(gravado and gravado != fabrica),
                                 "padrao": fabrica}
        linhas.append({
            "uf": uf,
            "nome": padrao.get("nome") or uf,
            "fonte": padrao.get("fonte") or "cadastrado por você",
            "onde": padrao.get("onde") or "",
            "minutos_cancelamento": minutos_cancelamento(db, modelo, uf),
            "emite": atendida(db, uf, modelo),
            "faltando": [SERVICOS[s] for s in SERVICOS
                         if not endereco(db, modelo, uf, s, "1")],
            "campos": campos,
        })
    return linhas


def previa_qrcode(db: Session | None, uf: str, ambiente: str = "1") -> dict:
    """Monta o texto do QR Code com uma chave e um CSC de brincadeira.

    Serve para conferir o endereço **antes da primeira venda**: a pessoa compara
    o começo desta linha com o QR Code de um cupom de verdade daquele estado (ou
    com o que o portal da SEFAZ mostra). Endereço errado aparece aqui, e não na
    frente do cliente com a SEFAZ devolvendo rejeição 395.

    O CSC é falso de propósito — o hash sai diferente do de uma venda real, e é
    o **endereço** que se está conferindo, não a assinatura.
    """
    from . import cupom as nfce

    chave = "52" + "1" * 42          # 44 dígitos, só para desenhar a linha
    try:
        texto = nfce.texto_qrcode(chave, ambiente, "CSC-DE-EXEMPLO", "000001", uf, db)
    except nfce.ErroCupom as erro:
        return {"ok": False, "mensagem": str(erro)}
    return {
        "ok": True,
        "endereco": endereco(db, "65", uf, "qrcode", ambiente),
        "texto": texto,
        "consulta": endereco(db, "65", uf, "consulta", ambiente),
        "aviso": "Chave e CSC de exemplo — confira só o endereço no começo da linha.",
    }


def salvar(db: Session, modelo: str, uf: str, valores: dict) -> EnderecoSefaz:
    """Grava o que o administrador digitou. Campo igual ao de fábrica não é gravado.

    Assim a linha guarda só o que foi realmente mudado, e um estado volta sozinho
    ao padrão novo quando o sistema é atualizado com um endereço corrigido.
    """
    conferir_modelo(modelo)
    uf = (uf or "").upper()
    if len(uf) != 2 or not uf.isalpha():
        raise EnderecoFaltando("Informe a sigla do estado com duas letras (ex.: GO).")
    padrao = _do_padrao(modelo, uf)
    linha = _linha(db, modelo, uf)
    if linha is None:
        linha = EnderecoSefaz(modelo=modelo, uf=uf)
        db.add(linha)
    for servico in SERVICOS:
        for ambiente in ("1", "2"):
            chave = _coluna(servico, ambiente)
            if chave not in valores:
                continue
            novo = (valores.get(chave) or "").strip()
            if novo and not novo.lower().startswith(("http://", "https://")):
                raise EnderecoFaltando(
                    f"O endereço de {SERVICOS[servico]} precisa começar com https:// "
                    "— copie do portal da SEFAZ do estado.")
            fabrica = (padrao.get(servico, {}).get(ambiente) or "").strip()
            setattr(linha, chave, None if novo == fabrica else (novo or None))
    if "minutos_cancelamento" in valores:
        try:
            minutos = int(valores.get("minutos_cancelamento") or 0)
        except (TypeError, ValueError):
            raise EnderecoFaltando("O prazo de cancelamento é em minutos (ex.: 30).") from None
        padrao_minutos = int(padrao.get("minutos_cancelamento") or MINUTOS_CANCELAMENTO_PADRAO)
        linha.minutos_cancelamento = None if minutos in (0, padrao_minutos) else minutos
    db.flush()
    return linha


def voltar_ao_padrao(db: Session, modelo: str, uf: str) -> None:
    """Apaga o que foi editado; o estado volta a usar o padrão de fábrica."""
    linha = _linha(db, modelo, uf)
    if linha is not None:
        db.delete(linha)
        db.flush()
