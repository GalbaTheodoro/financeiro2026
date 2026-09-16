"""Hash de senha e token de sessão — sem dependências externas."""
import base64
import hashlib
import hmac
import json
import os
import time

from .config import SECRET_KEY, TOKEN_HORAS_VALIDADE

_ITERACOES = 180_000


def hash_senha(senha: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, _ITERACOES)
    return f"pbkdf2${_ITERACOES}${salt.hex()}${dk.hex()}"


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = senha_hash.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def gerar_token(usuario_id: int, email: str) -> str:
    payload = {
        "sub": usuario_id,
        "email": email,
        "exp": int(time.time()) + TOKEN_HORAS_VALIDADE * 3600,
    }
    corpo = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    assinatura = _b64e(hmac.new(SECRET_KEY.encode(), corpo.encode(), hashlib.sha256).digest())
    return f"{corpo}.{assinatura}"


def ler_token(token: str):
    try:
        corpo, assinatura = token.split(".")
        esperado = _b64e(hmac.new(SECRET_KEY.encode(), corpo.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(esperado, assinatura):
            return None
        payload = json.loads(_b64d(corpo))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
