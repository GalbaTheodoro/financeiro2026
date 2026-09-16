"""Consulta de CEP.

Provedores suportados (escolhidos em `cep_provedor`):

    CORREIOS  API oficial dos Correios (api.correios.com.br). Exige contrato:
              usuário e senha do Meu Correios + número do cartão de postagem.
              Token: POST /token/v1/autentica/cartaopostagem  (Basic + cartão)
              Consulta: GET /cep/v2/enderecos/{cep}           (Bearer)
    VIACEP    Base pública dos Correios (viacep.com.br), sem credencial.
    BRASILAPI Consulta em vários provedores, inclusive os Correios.
    AUTO      Usa os Correios se houver credenciais; senão, o ViaCEP.
"""
import base64
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .assinaturas import config
from .externo import apenas_digitos, requisitar

BASE_CORREIOS = "https://api.correios.com.br"
VIACEP = "https://viacep.com.br/ws/{cep}/json/"
BRASILAPI_CEP = "https://brasilapi.com.br/api/cep/v2/"

_token_cache: dict[str, tuple[str, float]] = {}


# --------------------------------------------------------------------------- #
# CEP
# --------------------------------------------------------------------------- #
def cep_valido(cep: str) -> bool:
    limpo = apenas_digitos(cep)
    return len(limpo) == 8 and limpo != "0" * 8


def formatar_cep(cep: str) -> str:
    c = apenas_digitos(cep)
    return f"{c[:5]}-{c[5:]}" if len(c) == 8 else cep


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, dict):
        for chave in ("nome", "descricao", "valor"):
            if valor.get(chave):
                return str(valor[chave]).strip()
        return ""
    return str(valor).strip()


def _primeiro(dados: dict, *chaves) -> str:
    for chave in chaves:
        valor = dados.get(chave)
        if valor not in (None, "", [], {}):
            return _texto(valor)
    return ""


def normalizar(dados: dict, fonte: str) -> dict:
    if not isinstance(dados, dict):
        raise HTTPException(502, "Resposta inesperada do serviço de CEP.")
    if str(dados.get("erro", "")).lower() in ("true", "1"):  # ViaCEP responde assim
        raise HTTPException(404, "CEP não encontrado.")

    logradouro = _primeiro(dados, "logradouro", "street", "endereco")
    tipo = _primeiro(dados, "tipoLogradouro", "tipo_logradouro")
    if tipo and not logradouro.upper().startswith(tipo.upper()):
        logradouro = f"{tipo} {logradouro}".strip()

    return {
        "fonte": fonte,
        "cep": formatar_cep(_primeiro(dados, "cep", "code")),
        "logradouro": logradouro,
        "complemento": _primeiro(dados, "complemento", "complement"),
        "bairro": _primeiro(dados, "bairro", "neighborhood", "distrito"),
        "cidade": _primeiro(dados, "localidade", "cidade", "city", "municipio", "nomeLocalidade"),
        "uf": _primeiro(dados, "uf", "state", "estado", "siglaUf")[:2].upper(),
        "ibge": _primeiro(dados, "ibge", "codigoIbge", "city_ibge"),
    }


# --------------------------------------------------------------------------- #
# Correios (API oficial, com contrato)
# --------------------------------------------------------------------------- #
def obter_token(db: Session) -> str:
    usuario = config(db, "cep_usuario")
    senha = config(db, "cep_senha")
    cartao = config(db, "cep_cartao_postagem")
    if not usuario or not senha:
        raise HTTPException(
            400,
            "Consulta pelos Correios não configurada: informe usuário, senha e cartão de "
            "postagem em Configurações do site.",
        )

    base = (config(db, "cep_endpoint") or BASE_CORREIOS).rstrip("/")
    # a chave do cache inclui credenciais e endereço: trocar qualquer um pede token novo
    identidade = f"{base}|{usuario}:{hash(senha)}:{cartao}"
    cache = _token_cache.get(identidade)
    if cache and cache[1] > time.time() + 30:
        return cache[0]

    credencial = base64.b64encode(f"{usuario}:{senha}".encode()).decode()
    caminho = "/token/v1/autentica/cartaopostagem" if cartao else "/token/v1/autentica"
    corpo = f'{{"numero": "{cartao}"}}'.encode() if cartao else None

    resposta = requisitar(
        f"{base}{caminho}",
        headers={
            "Authorization": f"Basic {credencial}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        dados=corpo,
        metodo="POST",
        servico="a API dos Correios",
    )
    token = resposta.get("token") or resposta.get("access_token")
    if not token:
        raise HTTPException(502, "Os Correios não devolveram o token de acesso.")
    _token_cache[identidade] = (token, time.time() + 3600)
    return token


def _consultar_correios(db: Session, cep: str) -> dict:
    base = (config(db, "cep_endpoint") or BASE_CORREIOS).rstrip("/")
    dados = requisitar(
        f"{base}/cep/v2/enderecos/{cep}",
        headers={"Authorization": f"Bearer {obter_token(db)}", "Accept": "application/json"},
        servico="a API dos Correios",
    )
    return normalizar(dados, "Correios · API oficial")


def _consultar_viacep(cep: str) -> dict:
    dados = requisitar(
        VIACEP.format(cep=cep), {"Accept": "application/json"}, servico="o ViaCEP"
    )
    return normalizar(dados, "ViaCEP · base pública dos Correios")


def _consultar_brasilapi(cep: str) -> dict:
    dados = requisitar(
        f"{BRASILAPI_CEP}{cep}", {"Accept": "application/json"}, servico="a BrasilAPI"
    )
    return normalizar(dados, "BrasilAPI · consulta múltiplos provedores")


# --------------------------------------------------------------------------- #
# Entrada
# --------------------------------------------------------------------------- #
def consultar(db: Session, cep: str) -> dict:
    limpo = apenas_digitos(cep)
    if not cep_valido(limpo):
        raise HTTPException(400, "CEP inválido. Informe os 8 dígitos.")

    provedor = (config(db, "cep_provedor") or "AUTO").upper()
    tem_credenciais = bool(config(db, "cep_usuario") and config(db, "cep_senha"))

    if provedor == "DESATIVADO":
        raise HTTPException(400, "A busca automática de CEP está desativada nas configurações.")
    if provedor == "CORREIOS" or (provedor == "AUTO" and tem_credenciais):
        return _consultar_correios(db, limpo)
    if provedor == "BRASILAPI":
        return _consultar_brasilapi(limpo)
    return _consultar_viacep(limpo)


def situacao_servico(db: Session) -> dict:
    provedor = (config(db, "cep_provedor") or "AUTO").upper()
    tem_credenciais = bool(config(db, "cep_usuario") and config(db, "cep_senha"))
    if provedor == "DESATIVADO":
        return {"disponivel": False, "provedor": "DESATIVADO",
                "descricao": "Busca de CEP desativada"}
    if provedor == "CORREIOS" and not tem_credenciais:
        return {"disponivel": False, "provedor": "CORREIOS",
                "descricao": "Faltam as credenciais dos Correios nas configurações"}
    if provedor == "CORREIOS" or (provedor == "AUTO" and tem_credenciais):
        return {"disponivel": True, "provedor": "CORREIOS",
                "descricao": "API oficial dos Correios"}
    if provedor == "BRASILAPI":
        return {"disponivel": True, "provedor": "BRASILAPI",
                "descricao": "BrasilAPI (vários provedores)"}
    return {"disponivel": True, "provedor": "VIACEP",
            "descricao": "ViaCEP · base pública dos Correios"}
