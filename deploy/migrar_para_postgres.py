"""Leva os dados do arquivo do PC (SQLite) para o banco na nuvem (PostgreSQL)
— e traz de volta, quando você quiser uma cópia de segurança no computador.

Serve para quando você já usou o sistema no PC e não quer perder nada ao
colocá-lo no ar. Copia tabela por tabela, na ordem certa, e no fim confere se
a quantidade de linhas bateu dos dois lados.

Como usar (na pasta do AgroDock):

  Subir o que está no PC para a nuvem:
      python deploy/migrar_para_postgres.py "postgresql://usuario:senha@host/banco"

  Trazer uma cópia da nuvem para o PC (backup):
      python deploy/migrar_para_postgres.py "postgresql://..." --baixar

  Só comparar os dois, sem copiar nada:
      python deploy/migrar_para_postgres.py "postgresql://..." --conferir

Opções:
    --origem caminho\\financeiro.db   outro arquivo do PC (padrão: dados/financeiro.db)
    --limpar                          apaga o que já existe no destino antes de copiar

Nada é apagado sem você pedir: sem --limpar, o programa para se o destino já
tiver dados.
"""
import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PASTA))



def _garantir_driver_postgres():
    """Instala o driver do PostgreSQL (psycopg) se ele ainda não estiver no
    ambiente do Python — acontece em ambientes criados antes de o driver
    entrar no requirements.txt."""
    try:
        import psycopg  # noqa: F401
        return
    except ImportError:
        pass
    import subprocess
    print("Instalando o driver do PostgreSQL (psycopg)... isso acontece uma vez só.",
          flush=True)
    comando = [sys.executable, "-m", "pip", "install", "psycopg[binary]>=3.1"]
    if subprocess.call(comando) != 0:
        print("\nNão consegui instalar o psycopg. Confira a internet e rode de novo.\n"
              "Se continuar, copie as mensagens acima e mande para o suporte.")
        sys.exit(1)
    import importlib
    importlib.invalidate_caches()
    try:
        import psycopg  # noqa: F401,F811
    except ImportError as erro:
        print(f"\nO psycopg foi instalado, mas não carregou: {erro}")
        sys.exit(1)


_garantir_driver_postgres()

from sqlalchemy import Boolean, Date, DateTime  # noqa: E402
from sqlalchemy import create_engine, func, insert, inspect, select, text  # noqa: E402

from backend import models  # noqa: E402,F401  (registra as tabelas)
from backend.config import _normalizar  # noqa: E402
from backend.database import Base  # noqa: E402


def falar(msg=""):
    print(msg, flush=True)


def _converter(linha, tabela):
    """Ajusta valores que o SQLite guarda de um jeito e o PostgreSQL de outro."""
    dados = dict(linha)
    for nome, valor in list(dados.items()):
        coluna = tabela.columns.get(nome)
        if valor is None or coluna is None:
            continue
        tipo = coluna.type
        if isinstance(tipo, Boolean) and not isinstance(valor, bool):
            # SQLite guarda 0/1; o PostgreSQL exige verdadeiro/falso
            dados[nome] = str(valor) not in ("0", "False", "false", "")
        elif isinstance(tipo, (Date, DateTime)) and isinstance(valor, str):
            texto = valor.replace("T", " ").strip()
            try:
                dados[nome] = (datetime.fromisoformat(texto) if isinstance(tipo, DateTime)
                               else date.fromisoformat(texto[:10]))
            except ValueError:
                dados[nome] = None
    return dados


def contar(engine, tabela):
    with engine.connect() as con:
        return con.execute(select(func.count()).select_from(tabela)).scalar_one()


def copiar(origem, destino, tabelas):
    total = 0
    for tabela in tabelas:
        with origem.connect() as con:
            linhas = [_converter(l._mapping, tabela)
                      for l in con.execute(select(tabela))]
        if linhas:
            with destino.begin() as con:
                for i in range(0, len(linhas), 500):   # em blocos, para não pesar
                    con.execute(insert(tabela), linhas[i:i + 500])
        total += len(linhas)
        falar(f"   {tabela.name:<28} {len(linhas):>6} linha(s)")
    return total


def acertar_numeracao(destino, tabelas):
    """No PostgreSQL a numeração automática é um contador à parte: depois de
    copiar linhas com id pronto, ele precisa saber de onde continuar."""
    if destino.dialect.name != "postgresql":
        return
    with destino.begin() as con:
        for tabela in tabelas:
            if "id" not in tabela.columns:
                continue
            con.execute(text(
                "SELECT setval(pg_get_serial_sequence(:t, 'id'),"
                f" COALESCE((SELECT MAX(id) FROM {tabela.name}), 1),"
                f" (SELECT COUNT(*) > 0 FROM {tabela.name}))"
            ), {"t": tabela.name})


def main():
    p = argparse.ArgumentParser(add_help=True)
    p.add_argument("nuvem", nargs="?", default=os.getenv("FIN_DATABASE_URL", ""),
                   help="endereço do PostgreSQL (ou defina FIN_DATABASE_URL)")
    p.add_argument("--origem", default=str(PASTA / "dados" / "financeiro.db"),
                   help="arquivo do PC (padrão: dados/financeiro.db)")
    p.add_argument("--baixar", action="store_true",
                   help="sentido contrário: traz a nuvem para o arquivo do PC")
    p.add_argument("--limpar", action="store_true")
    p.add_argument("--conferir", action="store_true")
    args = p.parse_args()

    nuvem_url = _normalizar(args.nuvem)
    if not nuvem_url.startswith("postgresql"):
        falar("Informe o endereço do banco na nuvem. Exemplo:")
        falar('  python deploy/migrar_para_postgres.py '
              '"postgresql://neondb_owner:SENHA@ep-xxxx-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"')
        sys.exit(1)

    arquivo = Path(args.origem)
    if not args.baixar and not arquivo.exists():
        falar(f"Não encontrei o banco do PC em {arquivo}")
        sys.exit(1)
    arquivo.parent.mkdir(parents=True, exist_ok=True)

    pc = create_engine(f"sqlite:///{arquivo}", future=True)
    # prepare_threshold=None: o pooler do Supabase (porta 6543) não aceita
    # prepared statements
    nuvem = create_engine(nuvem_url, future=True, pool_pre_ping=True,
                          connect_args={"prepare_threshold": None, "connect_timeout": 20})

    origem, destino = (nuvem, pc) if args.baixar else (pc, nuvem)
    nome_origem = "a nuvem" if args.baixar else f"o PC ({arquivo.name})"
    nome_destino = f"o PC ({arquivo.name})" if args.baixar else "a nuvem"
    endereco = nuvem_url.split("@")[-1]

    falar(f"De  : {nome_origem}")
    falar(f"Para: {nome_destino}")
    falar(f"Nuvem: {endereco}")
    falar()

    falar("1. Preparando as tabelas no destino...")
    Base.metadata.create_all(bind=destino)

    inspetor = inspect(origem)
    tabelas = [t for t in Base.metadata.sorted_tables if inspetor.has_table(t.name)]
    if not tabelas:
        falar("   A origem está vazia — não há nada para copiar.")
        sys.exit(1)

    if args.conferir:
        falar("\n   tabela                       no PC     na nuvem")
        iguais = True
        for tabela in tabelas:
            a, b = contar(pc, tabela), contar(nuvem, tabela)
            iguais = iguais and a == b
            falar(f"   {tabela.name:<26}{a:>8}{b:>13}   {'ok' if a == b else 'DIFERENTE'}")
        falar("\nOs dois bancos estão iguais." if iguais
              else "\nOs bancos estão diferentes.")
        sys.exit(0 if iguais else 1)

    ocupadas = [t.name for t in tabelas if contar(destino, t) > 0]
    if ocupadas and not args.limpar:
        falar("\nO destino já tem dados em: " + ", ".join(ocupadas))
        falar("Se for para substituir tudo, rode de novo acrescentando  --limpar")
        sys.exit(1)
    if args.limpar and ocupadas:
        falar("2. Limpando o destino...")
        with destino.begin() as con:
            if destino.dialect.name == "postgresql":
                con.execute(text("TRUNCATE TABLE "
                                 + ", ".join(t.name for t in tabelas)
                                 + " RESTART IDENTITY CASCADE"))
            else:
                for tabela in reversed(tabelas):
                    con.execute(tabela.delete())

    falar("2. Copiando os dados...")
    total = copiar(origem, destino, tabelas)

    falar("\n3. Acertando a numeração automática (próximo id de cada tabela)...")
    acertar_numeracao(destino, tabelas)

    falar("\n4. Conferindo...")
    problemas = [f"{t.name}: {contar(origem, t)} x {contar(destino, t)}"
                 for t in tabelas if contar(origem, t) != contar(destino, t)]
    if problemas:
        falar("   Diferenças encontradas:")
        for p_ in problemas:
            falar(f"   - {p_}")
        sys.exit(1)

    falar(f"   Tudo certo: {total} linha(s) copiadas, todas as tabelas conferem.")
    if args.baixar:
        falar(f"\nPronto! A cópia da nuvem está em {arquivo}")
    else:
        falar("\nPronto! Agora é só o sistema apontar para o banco novo "
              "(variável FIN_DATABASE_URL).")


if __name__ == "__main__":
    main()
