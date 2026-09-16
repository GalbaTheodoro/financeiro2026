"""Conexão com o banco de dados.

Funciona dos dois jeitos, sem mudar mais nada no sistema:

  * sem configurar nada  -> arquivo dados/financeiro.db (SQLite), bom para o PC;
  * com FIN_DATABASE_URL -> banco PostgreSQL na nuvem (Supabase, Neon...).

Cuidados com o banco na nuvem:

  * ``pool_pre_ping`` testa a conexão antes de usar e ``pool_recycle`` troca as
    velhas — o banco pode derrubar conexões paradas e o sistema reconecta sozinho;
  * ``prepare_threshold=None`` desliga os *prepared statements* do psycopg. O
    pooler do Supabase na porta 6543 (modo transação, o indicado para o Vercel)
    não aceita prepared statements; sem isto aparecem erros como
    "prepared statement _pg3_0 does not exist" depois de algumas telas;
  * no Vercel cada cópia do sistema vive pouco e várias podem subir juntas,
    então cada uma segura poucas conexões — quem reparte é o pooler do Supabase.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL, EM_VERCEL, USANDO_POSTGRES

if USANDO_POSTGRES:
    engine = create_engine(
        DATABASE_URL,
        future=True,
        pool_pre_ping=True,                  # confere se a conexão ainda está viva
        pool_recycle=60 if EM_VERCEL else 280,
        pool_size=2 if EM_VERCEL else 5,
        max_overflow=3 if EM_VERCEL else 5,
        pool_timeout=20,
        connect_args={
            "connect_timeout": 15,
            "prepare_threshold": None,       # obrigatório no pooler (porta 6543)
            "application_name": "agrodock",
        },
    )
else:
    engine = create_engine(
        DATABASE_URL,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
