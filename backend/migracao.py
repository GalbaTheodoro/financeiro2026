"""Migração automática do banco de dados.

Cria as tabelas que faltam e acrescenta colunas novas em bancos já existentes,
para que uma versão antiga do sistema continue funcionando após a atualização.

Funciona igual no SQLite (arquivo no PC) e no PostgreSQL (banco na nuvem) —
o que muda é só o nome de alguns tipos de coluna e o jeito de escrever
verdadeiro/falso, tratados em ``_tipo_sql`` e ``_padrao_sql``.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError, OperationalError

from .database import Base, engine

log = logging.getLogger("financeiro")

# Tipos SQL usados ao acrescentar colunas em bancos antigos.
# O PostgreSQL não conhece "DATETIME": lá o tipo se chama TIMESTAMP.
_TIPOS = {
    "INTEGER": {"padrao": "INTEGER"},
    "VARCHAR": {"padrao": "VARCHAR"},
    "TEXT": {"padrao": "TEXT"},
    "BOOLEAN": {"padrao": "BOOLEAN"},
    "DATE": {"padrao": "DATE"},
    "DATETIME": {"padrao": "DATETIME", "postgresql": "TIMESTAMP"},
    "NUMERIC": {"padrao": "NUMERIC"},
}


def _e_postgres() -> bool:
    return engine.dialect.name == "postgresql"


def _tipo_sql(coluna) -> str:
    nome = coluna.type.__class__.__name__.upper()
    if nome.startswith("VARCHAR") or nome == "STRING":
        nome = "VARCHAR"
    tipo = _TIPOS.get(nome, {"padrao": "VARCHAR"})
    if _e_postgres():
        return tipo.get("postgresql", tipo["padrao"])
    return tipo["padrao"]


def _padrao_sql(coluna) -> str:
    """Trecho DEFAULT da coluna nova, no formato que cada banco entende."""
    if coluna.default is None or not getattr(coluna.default, "is_scalar", False):
        return ""
    valor = coluna.default.arg
    if isinstance(valor, bool):
        # o PostgreSQL exige TRUE/FALSE em coluna booleana; o SQLite usa 1/0
        if _e_postgres():
            return f" DEFAULT {'TRUE' if valor else 'FALSE'}"
        return f" DEFAULT {1 if valor else 0}"
    if isinstance(valor, (int, float)):
        return f" DEFAULT {valor}"
    if isinstance(valor, str):
        seguro = valor.replace("'", "''")
        return f" DEFAULT '{seguro}'"
    return ""


def migrar() -> list[str]:
    """Sincroniza o esquema do banco com os modelos. Devolve o que foi alterado."""
    Base.metadata.create_all(bind=engine)
    inspetor = inspect(engine)
    alteracoes: list[str] = []

    for tabela in Base.metadata.sorted_tables:
        if not inspetor.has_table(tabela.name):
            continue
        existentes = {c["name"] for c in inspetor.get_columns(tabela.name)}
        for coluna in tabela.columns:
            if coluna.name in existentes:
                continue
            comando = (
                f'ALTER TABLE {tabela.name} '
                f'ADD COLUMN "{coluna.name}" {_tipo_sql(coluna)}{_padrao_sql(coluna)}'
            )
            try:
                with engine.begin() as conexao:
                    conexao.execute(text(comando))
            except (ProgrammingError, OperationalError) as erro:
                # dois processos subindo ao mesmo tempo: o segundo encontra a
                # coluna já criada pelo primeiro. Não é motivo para derrubar.
                if "exist" not in str(erro).lower():
                    raise
                continue
            alteracoes.append(f"{tabela.name}.{coluna.name}")

    if alteracoes:
        log.info("Banco atualizado: %s", ", ".join(alteracoes))
    return alteracoes


# --------------------------------------------------------------------------- #
# Preparação do banco na subida do sistema
#
# No PC (SQLite) a conferência completa é instantânea e roda sempre.
#
# No Vercel o sistema "liga" várias vezes ao dia (cada cópia nova que sobe) e
# conferir tabela por tabela no Supabase custaria alguns segundos em cada uma.
# Então guardamos no próprio banco uma "impressão digital" do esquema: se a
# versão do código é a mesma da última conferência, basta uma consulta rápida.
# Quando um deploy novo muda tabelas ou dados iniciais, a impressão muda e a
# conferência completa roda uma vez — com trava, para duas cópias subindo ao
# mesmo tempo não tentarem criar a mesma coluna juntas.
# --------------------------------------------------------------------------- #
_TRAVA_MIGRACAO = 72_451_903  # número qualquer, só precisa ser sempre o mesmo


def impressao_digital() -> str:
    """Resumo do esquema dos modelos + arquivos que definem os dados iniciais."""
    import hashlib
    from pathlib import Path

    h = hashlib.sha256()
    for tabela in Base.metadata.sorted_tables:
        h.update(tabela.name.encode())
        for coluna in tabela.columns:
            h.update(f"{coluna.name}:{coluna.type!r}:{coluna.nullable}".encode())
    pasta = Path(__file__).resolve().parent
    for nome in ("seed.py", "assinaturas.py", "plano_contas.py", "migracao.py"):
        arquivo = pasta / nome
        if arquivo.exists():
            h.update(arquivo.read_bytes())
    return h.hexdigest()[:40]


def _migrar_e_semear() -> None:
    from .database import SessionLocal
    from .seed import criar_dados_iniciais

    migrar()
    db = SessionLocal()
    try:
        info = criar_dados_iniciais(db)
        if info:
            log.info("Dados iniciais criados: %s", info)
    finally:
        db.close()


def preparar_banco() -> str:
    """Deixa o banco pronto para uso. Devolve 'completa' ou 'rapida'."""
    if not _e_postgres():
        _migrar_e_semear()
        return "completa"

    versao = impressao_digital()
    criar_meta = text(
        "CREATE TABLE IF NOT EXISTS agrodock_meta "
        "(chave VARCHAR(50) PRIMARY KEY, valor VARCHAR(200) NOT NULL)"
    )
    ler = text("SELECT valor FROM agrodock_meta WHERE chave = 'esquema'")

    def _em_dia(conexao) -> bool:
        return conexao.execute(ler).scalar() == versao

    # caminho rápido: uma consulta só
    try:
        with engine.connect() as conexao:
            if _em_dia(conexao):
                return "rapida"
    except (ProgrammingError, OperationalError):
        pass  # tabela agrodock_meta ainda não existe (banco novo)

    with engine.begin() as conexao:
        # a trava vale até o fim desta transação (funciona no pooler do Supabase)
        conexao.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _TRAVA_MIGRACAO})
        conexao.execute(criar_meta)
        if _em_dia(conexao):
            return "rapida"  # outra cópia terminou enquanto esta esperava
        log.info("Conferindo o banco para a versão nova do sistema…")
        _migrar_e_semear()
        conexao.execute(
            text(
                "INSERT INTO agrodock_meta (chave, valor) VALUES ('esquema', :v) "
                "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor"
            ),
            {"v": versao},
        )
    return "completa"
