"""Configurações gerais do sistema financeiro."""
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "dados"

# Rodando no Vercel? (o Vercel define esta variável sozinho em todo deploy)
EM_VERCEL = bool(os.getenv("VERCEL"))

try:
    DATA_DIR.mkdir(exist_ok=True)
except OSError:
    # No Vercel a pasta do sistema é só de leitura — lá o banco fica na nuvem (Neon).
    pass

# Parâmetros do endereço que o driver do PostgreSQL entende. A integração
# Supabase ↔ Vercel acrescenta outros (ex.: "supa=base-pooler.x") que fariam
# a conexão falhar com "invalid URI query parameter"; esses são descartados.
_PARAMETROS_LIBPQ = {
    "sslmode", "sslrootcert", "sslcert", "sslkey", "connect_timeout",
    "application_name", "options", "target_session_attrs", "channel_binding",
    "gssencmode", "keepalives", "keepalives_idle", "keepalives_interval",
    "keepalives_count",
}


def _normalizar(url: str) -> str:
    """Aceita o endereço do banco no formato que o serviço de nuvem entregar.

    Supabase, Neon, Render e Railway mostram o endereço começando com
    ``postgres://`` ou ``postgresql://``. O SQLAlchemy precisa saber qual
    driver usar, então acrescentamos ``+psycopg`` (psycopg 3, o que está no
    requirements.txt). Quem já colar o endereço com o driver escrito continua
    funcionando.
    """
    url = (url or "").strip().strip('"').strip("'")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgresql+psycopg://"):
        partes = urlsplit(url)
        consulta = [(k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
                    if k in _PARAMETROS_LIBPQ]
        url = urlunsplit(partes._replace(query=urlencode(consulta)))
    return url


def _endereco_do_banco() -> str:
    """Primeiro FIN_DATABASE_URL; se não houver, os nomes que a integração
    Supabase do Vercel cria sozinha (POSTGRES_URL é o pooler, porta 6543)."""
    for nome in ("FIN_DATABASE_URL", "POSTGRES_URL"):
        valor = os.getenv(nome, "").strip()
        if valor:
            return valor
    return ""


# Banco de dados: sem configurar nada, usa o arquivo dados/financeiro.db (SQLite).
# Para usar um banco na nuvem, defina FIN_DATABASE_URL com o endereço que o
# serviço fornece, por exemplo (Neon, conexão "pooled"):
#   postgresql://neondb_owner:SENHA@ep-xxxx-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require
DATABASE_URL = _normalizar(_endereco_do_banco()) or \
    f"sqlite:///{DATA_DIR / 'financeiro.db'}"

USANDO_POSTGRES = DATABASE_URL.startswith("postgresql")

if EM_VERCEL and not USANDO_POSTGRES:
    # Sem isto o sistema "funcionaria" num arquivo temporário e perderia tudo.
    raise RuntimeError(
        "AgroDock no Vercel precisa do banco na nuvem: cadastre FIN_DATABASE_URL "
        "(endereço do Neon) em Settings → Environment Variables e faça Redeploy."
    )

# Chave usada para assinar os tokens de sessão.
# Em produção defina a variável de ambiente FIN_SECRET_KEY.
SECRET_KEY = os.getenv("FIN_SECRET_KEY", "troque-esta-chave-em-producao-1234567890")

if EM_VERCEL and SECRET_KEY.startswith("troque-esta-chave"):
    raise RuntimeError(
        "AgroDock no Vercel precisa de FIN_SECRET_KEY (uma frase longa e secreta) "
        "em Settings → Environment Variables."
    )

TOKEN_HORAS_VALIDADE = int(os.getenv("FIN_TOKEN_HORAS", "12"))

FRONTEND_DIR = BASE_DIR / "frontend"
