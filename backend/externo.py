"""Chamadas HTTP às APIs externas (CNPJ e CEP), com mensagens de erro em português."""
import json
import re
import urllib.error
import urllib.request

from fastapi import HTTPException

TEMPO_LIMITE = 20  # segundos


def apenas_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def requisitar(
    url: str,
    headers: dict,
    dados: bytes | None = None,
    metodo: str = "GET",
    servico: str = "API de consulta",
):
    req = urllib.request.Request(url, data=dados, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as resposta:
            corpo = resposta.read().decode("utf-8", "replace")
            return json.loads(corpo) if corpo.strip() else {}
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:300]
        if e.code in (400, 404):
            raise HTTPException(404, f"Registro não encontrado na base d{servico}.") from None
        if e.code in (401, 403):
            raise HTTPException(
                502,
                f"{servico} recusou as credenciais (erro {e.code}). "
                "Confira os dados de acesso em Configurações do site.",
            ) from None
        if e.code == 429:
            raise HTTPException(
                429, f"Limite de consultas d{servico} atingido. Tente novamente em instantes."
            ) from None
        raise HTTPException(502, f"{servico} respondeu {e.code}: {detalhe}") from None
    except urllib.error.URLError as e:
        raise HTTPException(
            504,
            f"Não foi possível falar com {servico} ({e.reason}). Verifique a conexão com a internet.",
        ) from None
    except json.JSONDecodeError:
        raise HTTPException(502, f"{servico} devolveu uma resposta inválida.") from None
