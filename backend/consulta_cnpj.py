"""Consulta de CNPJ na API do governo (Conecta Gov / SERPRO).

Endpoints de produção usados (o caminho é montado com o CNPJ no final):

    .../api-cnpj-basica/v2/basica/{cnpj}     dados cadastrais básicos
    .../api-cnpj-qsa/v2/qsa/{cnpj}           quadro de sócios e administradores
    .../api-cnpj-empresa/v2/empresa/{cnpj}   básica + QSA numa resposta só

A autenticação é OAuth2 `client_credentials`: com a consumer key e o consumer
secret o sistema pega um token no endpoint `/oauth2/jwt-token` e o reaproveita
até expirar. As credenciais ficam em Configurações e nunca saem para o site.

Quando não há credenciais cadastradas, a consulta cai automaticamente na
BrasilAPI (base pública da Receita Federal, sem autenticação), para que o
cadastro continue funcionando. Isso é configurável em `cnpj_provedor`.
"""
import base64
import logging
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .assinaturas import config
from .externo import apenas_digitos, requisitar

log = logging.getLogger("financeiro")
BASE_PADRAO = "https://apigateway.conectagov.estaleiro.serpro.gov.br"
CAMINHOS = {
    "basica": "/api-cnpj-basica/v2/basica/",
    "qsa": "/api-cnpj-qsa/v2/qsa/",
    "empresa": "/api-cnpj-empresa/v2/empresa/",
}
BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/"

# códigos de situação cadastral da Receita Federal (quando vem só o número)
SITUACAO_CADASTRAL = {
    "1": "NULA", "2": "ATIVA", "3": "SUSPENSA", "4": "INAPTA", "8": "BAIXADA",
}

_token_cache: dict[str, tuple[str, float]] = {}


# --------------------------------------------------------------------------- #
# CNPJ
# --------------------------------------------------------------------------- #
def cnpj_valido(cnpj: str) -> bool:
    cnpj = apenas_digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(int(d) * p for d, p in zip(cnpj[:tamanho], pesos))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if int(cnpj[tamanho]) != digito:
            return False
    return True


def formatar_cnpj(cnpj: str) -> str:
    c = apenas_digitos(cnpj)
    if len(c) != 14:
        return cnpj
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def obter_token(db: Session) -> str:
    """Token OAuth2 do Conecta Gov, reaproveitado enquanto for válido."""
    chave = config(db, "cnpj_consumer_key")
    segredo = config(db, "cnpj_consumer_secret")
    if not chave or not segredo:
        raise HTTPException(
            400,
            "Consulta pela API do governo não configurada: informe a consumer key e o "
            "consumer secret em Configurações do site.",
        )

    base = config(db, "cnpj_endpoint") or BASE_PADRAO
    # a chave do cache inclui credenciais e endereço: trocar qualquer um pede token novo
    identidade = f"{base}|{chave}:{hash(segredo)}"
    cache = _token_cache.get(identidade)
    if cache and cache[1] > time.time() + 30:
        return cache[0]

    credencial = base64.b64encode(f"{chave}:{segredo}".encode()).decode()
    resposta = requisitar(
        f"{base.rstrip('/')}/oauth2/jwt-token",
        headers={
            "Authorization": f"Basic {credencial}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        dados=b"grant_type=client_credentials",
        metodo="POST",
        servico="a API do governo",
    )
    token = resposta.get("access_token") or resposta.get("token")
    if not token:
        raise HTTPException(502, "A API do governo não devolveu o token de acesso.")
    expira = float(resposta.get("expires_in") or 3600)
    _token_cache[identidade] = (token, time.time() + expira)
    return token


# --------------------------------------------------------------------------- #
# Normalização (a resposta muda conforme o endpoint escolhido)
# --------------------------------------------------------------------------- #
def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, dict):
        for chave in ("descricao", "nome", "valor", "texto", "codigo"):
            if valor.get(chave):
                return str(valor[chave]).strip()
        return ""
    return str(valor).strip()


def _buscar(dados: dict, *caminhos):
    """Procura o primeiro caminho existente. Cada caminho é 'a.b.c'."""
    for caminho in caminhos:
        atual = dados
        for parte in caminho.split("."):
            if isinstance(atual, dict) and parte in atual:
                atual = atual[parte]
            else:
                atual = None
                break
        if atual not in (None, "", [], {}):
            return atual
    return None


def _descricao_com_codigo(valor) -> str:
    if isinstance(valor, dict):
        codigo = _texto(valor.get("codigo"))
        descricao = _texto(valor.get("descricao") or valor.get("nome"))
        return f"{codigo} - {descricao}".strip(" -") if (codigo or descricao) else ""
    if isinstance(valor, list) and valor:
        return _descricao_com_codigo(valor[0])
    return _texto(valor)


def _situacao(valor) -> str:
    """Descrição da situação cadastral; traduz quando vier só o código."""
    if isinstance(valor, dict):
        descricao = _texto(valor.get("descricao") or valor.get("nome") or valor.get("situacao"))
        if descricao and not descricao.isdigit():
            return descricao.upper()
        codigo = _texto(valor.get("codigo") or descricao).lstrip("0")
        return SITUACAO_CADASTRAL.get(codigo, f"CÓDIGO {codigo}" if codigo else "")
    texto = _texto(valor)
    if texto.isdigit():
        return SITUACAO_CADASTRAL.get(texto.lstrip("0"), f"CÓDIGO {texto}")
    return texto.upper()


def _telefone(dados: dict) -> str:
    telefones = _buscar(dados, "telefones", "telefone", "contato.telefones")
    if isinstance(telefones, list) and telefones:
        primeiro = telefones[0]
        if isinstance(primeiro, dict):
            ddd = _texto(primeiro.get("ddd"))
            numero = _texto(primeiro.get("numero") or primeiro.get("telefone"))
            return f"({ddd}) {numero}".strip() if ddd else numero
        return _texto(primeiro)
    direto = _buscar(dados, "ddd_telefone_1", "ddd_telefone")
    return _texto(direto or telefones)


def _socios(dados: dict) -> list[dict]:
    lista = _buscar(dados, "socios", "qsa", "quadroSocietario", "listaSocios") or []
    if isinstance(lista, dict):
        lista = [lista]
    saida = []
    for item in lista if isinstance(lista, list) else []:
        if not isinstance(item, dict):
            continue
        saida.append(
            {
                "nome": _texto(
                    _buscar(item, "nome", "nomeSocio", "nome_socio", "nomeSocioRazaoSocial")
                ),
                "qualificacao": _descricao_com_codigo(
                    _buscar(item, "qualificacao", "qualificacaoSocio", "qualificacao_socio")
                ),
                "documento": _texto(
                    _buscar(item, "cpfCnpj", "cpf_cnpj_socio", "documento", "cnpjCpfDoSocio")
                ),
                "entrada": _texto(
                    _buscar(item, "dataEntrada", "data_entrada_sociedade", "dataEntradaSociedade")
                ),
            }
        )
    return [s for s in saida if s["nome"]]


def normalizar(dados: dict, fonte: str) -> dict:
    if isinstance(dados, dict) and isinstance(dados.get("dados"), dict):
        dados = dados["dados"]  # algumas respostas vêm embrulhadas

    endereco = _buscar(dados, "endereco", "enderecoEstabelecimento") or {}
    if not isinstance(endereco, dict):
        endereco = {}

    tipo_logradouro = _texto(_buscar(endereco, "tipoLogradouro", "tipo_logradouro"))
    logradouro = _texto(
        _buscar(endereco, "logradouro", "nomeLogradouro")
        or _buscar(dados, "logradouro", "nomeLogradouro")
    )
    if tipo_logradouro and not logradouro.upper().startswith(tipo_logradouro.upper()):
        logradouro = f"{tipo_logradouro} {logradouro}".strip()

    cidade = _texto(
        _buscar(endereco, "municipio", "cidade", "nomeMunicipio")
        or _buscar(dados, "municipio", "cidade", "nomeMunicipio")
    )
    situacao = _buscar(dados, "situacaoCadastral", "situacao_cadastral", "descricao_situacao_cadastral")

    resultado = {
        "fonte": fonte,
        "cnpj": formatar_cnpj(
            _texto(_buscar(dados, "cnpj", "ni", "numeroDeInscricao")) or ""
        ),
        "razao_social": _texto(
            _buscar(dados, "nomeEmpresarial", "razao_social", "razaoSocial", "nome")
        ),
        "nome_fantasia": _texto(
            _buscar(dados, "nomeFantasia", "nome_fantasia", "fantasia")
        ),
        # na situação cadastral interessa só a descrição (ATIVA, BAIXADA, SUSPENSA...)
        "situacao": _situacao(situacao),
        "data_situacao": _texto(
            _buscar(dados, "situacaoCadastral.data", "data_situacao_cadastral")
        ),
        "data_abertura": _texto(
            _buscar(dados, "dataAbertura", "data_inicio_atividade", "dataInicioAtividade")
        ),
        "natureza_juridica": _descricao_com_codigo(
            _buscar(dados, "naturezaJuridica", "natureza_juridica")
        ),
        "porte": _descricao_com_codigo(_buscar(dados, "porte", "porte_empresa")),
        "capital_social": _texto(_buscar(dados, "capitalSocial", "capital_social")),
        "cnae_principal": _descricao_com_codigo(
            _buscar(dados, "cnaePrincipal", "cnae_fiscal", "atividadePrincipal")
        )
        or _texto(_buscar(dados, "cnae_fiscal_descricao")),
        "logradouro": logradouro,
        "numero": _texto(_buscar(endereco, "numero") or _buscar(dados, "numero")),
        "complemento": _texto(_buscar(endereco, "complemento") or _buscar(dados, "complemento")),
        "bairro": _texto(_buscar(endereco, "bairro") or _buscar(dados, "bairro")),
        "cidade": cidade,
        "uf": _texto(_buscar(endereco, "uf", "siglaUf") or _buscar(dados, "uf", "siglaUf"))[:2],
        "cep": apenas_digitos(
            _texto(_buscar(endereco, "cep") or _buscar(dados, "cep"))
        ),
        "telefone": _telefone(dados),
        "email": _texto(
            _buscar(dados, "correioEletronico", "email", "correio_eletronico")
        ).lower(),
        "socios": _socios(dados),
    }
    if len(resultado["cep"]) == 8:
        resultado["cep"] = f"{resultado['cep'][:5]}-{resultado['cep'][5:]}"
    return resultado


# --------------------------------------------------------------------------- #
# Consulta
# --------------------------------------------------------------------------- #
def _consultar_conecta_gov(db: Session, cnpj: str) -> dict:
    base = (config(db, "cnpj_endpoint") or BASE_PADRAO).rstrip("/")
    tipo = (config(db, "cnpj_tipo_consulta") or "basica").lower()
    caminho = CAMINHOS.get(tipo, CAMINHOS["basica"])
    headers = {
        "Authorization": f"Bearer {obter_token(db)}",
        "Accept": "application/json",
    }
    cpf_usuario = apenas_digitos(config(db, "cnpj_cpf_usuario"))
    if cpf_usuario:
        headers["x-cpf-usuario"] = cpf_usuario

    dados = requisitar(f"{base}{caminho}{cnpj}", headers, servico="a API do governo")
    resultado = normalizar(dados, f"Conecta Gov · api-cnpj-{tipo}")

    # a consulta básica não traz o QSA; busca em seguida quando pedido
    if tipo == "basica" and config(db, "cnpj_incluir_socios") == "1":
        try:
            qsa = requisitar(f"{base}{CAMINHOS['qsa']}{cnpj}", headers, servico="a API do governo")
            resultado["socios"] = _socios(qsa if isinstance(qsa, dict) else {})
        except HTTPException:
            pass  # o QSA é complementar: se falhar, mantém o resto
    return resultado


def _consultar_brasilapi(cnpj: str) -> dict:
    dados = requisitar(f"{BRASILAPI}{cnpj}", {"Accept": "application/json"}, servico="a BrasilAPI")
    return normalizar(dados, "BrasilAPI · base pública da Receita Federal")


def consultar(db: Session, cnpj: str) -> dict:
    """Consulta o CNPJ no provedor configurado."""
    limpo = apenas_digitos(cnpj)
    if len(limpo) == 11:
        raise HTTPException(
            400, "A consulta automática funciona apenas para CNPJ. "
                 "Para pessoa física, preencha os dados manualmente."
        )
    if not cnpj_valido(limpo):
        raise HTTPException(400, "CNPJ inválido. Confira os 14 dígitos digitados.")

    provedor = (config(db, "cnpj_provedor") or "AUTO").upper()
    tem_credenciais = bool(config(db, "cnpj_consumer_key") and config(db, "cnpj_consumer_secret"))

    if provedor == "DESATIVADO":
        raise HTTPException(400, "A consulta automática de CNPJ está desativada nas configurações.")
    if provedor == "CONECTA_GOV" or (provedor == "AUTO" and tem_credenciais):
        return _consultar_conecta_gov(db, limpo)
    if provedor == "BRASILAPI" or provedor == "AUTO":
        return _consultar_brasilapi(limpo)
    raise HTTPException(400, f"Provedor de consulta desconhecido: {provedor}")


def situacao_servico(db: Session) -> dict:
    """Usado pela tela para saber se a busca está disponível e por qual provedor."""
    provedor = (config(db, "cnpj_provedor") or "AUTO").upper()
    tem_credenciais = bool(config(db, "cnpj_consumer_key") and config(db, "cnpj_consumer_secret"))
    if provedor == "DESATIVADO":
        return {"disponivel": False, "provedor": "DESATIVADO",
                "descricao": "Consulta automática desativada"}
    if provedor == "CONECTA_GOV" and not tem_credenciais:
        return {"disponivel": False, "provedor": "CONECTA_GOV",
                "descricao": "Faltam as credenciais do Conecta Gov nas configurações"}
    if provedor == "CONECTA_GOV" or (provedor == "AUTO" and tem_credenciais):
        return {"disponivel": True, "provedor": "CONECTA_GOV",
                "descricao": f"API do governo · {config(db, 'cnpj_tipo_consulta') or 'basica'}"}
    return {"disponivel": True, "provedor": "BRASILAPI",
            "descricao": "Base pública da Receita Federal"}
