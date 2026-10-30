"""Teste da recriação de tabela no SQLite (coluna que deixa de ser obrigatória).

O SQLite não sabe tirar o NOT NULL de uma coluna: a migração renomeia a tabela,
cria a nova e copia as linhas. Três coisas davam errado antes (out/2026):

  * os índices ficavam presos à tabela renomeada e a nova não conseguia criar
    os dela ("index ... already exists") — era o erro do banco antigo do PC;
  * as chaves estrangeiras das OUTRAS tabelas passavam a apontar para o nome
    provisório, que some logo depois;
  * uma tentativa que parava no meio deixava os dados na tabela provisória, e a
    próxima tentativa apagava essa tabela.

Uso:  python testes/teste_migracao_nulo.py   (não precisa do servidor)
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine, inspect, text  # noqa: E402

from backend import migracao  # noqa: E402

erros = []


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


def tabelas(obrigatoria: bool):
    meta = MetaData()
    pai = Table("pai", meta, Column("id", Integer, primary_key=True),
                Column("guia_id", Integer, nullable=not obrigatoria, index=True),
                Column("codigo", String(10), index=True))
    filho = Table("filho", meta, Column("id", Integer, primary_key=True),
                  Column("pai_id", Integer, ForeignKey("pai.id"), nullable=False, index=True))
    return meta, pai, filho


pasta = tempfile.mkdtemp()
motor = create_engine(f"sqlite:///{pasta}/t.db")
migracao.engine = motor            # a migração usa o motor do módulo

print("=== recriar a tabela sem perder índice, chave estrangeira nem dado ===")
meta, pai, filho = tabelas(obrigatoria=True)
meta.create_all(motor)
with motor.begin() as c:
    c.execute(text("INSERT INTO pai (id, guia_id, codigo) VALUES (7, 1, '1/1'), (8, 2, '2/1')"))
    c.execute(text("INSERT INTO filho (id, pai_id) VALUES (1, 7), (2, 8)"))
_, pai_novo, _ = tabelas(obrigatoria=False)
migracao._permitir_nulo(pai_novo, ["guia_id"])
insp = inspect(motor)
checar("a coluna passou a aceitar vazio",
       [c["nullable"] for c in insp.get_columns("pai") if c["name"] == "guia_id"] == [True])
with motor.connect() as c:
    checar("as linhas continuam, com os mesmos ids",
           c.execute(text("SELECT id, codigo FROM pai ORDER BY id")).fetchall() == [(7, "1/1"), (8, "2/1")])
    sql_filho = c.execute(text("SELECT sql FROM sqlite_master WHERE name='filho'")).scalar()
    checar("a chave estrangeira da outra tabela continua apontando para 'pai'",
           "REFERENCES pai" in sql_filho and "antiga" not in sql_filho, sql_filho[-60:])
    checar("e não há referência quebrada", c.execute(text("PRAGMA foreign_key_check")).fetchall() == [])
checar("os índices foram recriados",
       {i["name"] for i in insp.get_indexes("pai")} == {"ix_pai_guia_id", "ix_pai_codigo"})
with motor.begin() as c:
    c.execute(text("PRAGMA foreign_keys=ON"))
    c.execute(text("INSERT INTO pai (id, guia_id, codigo) VALUES (9, NULL, 'S1/1')"))
    c.execute(text("INSERT INTO filho (id, pai_id) VALUES (3, 9)"))
checar("dá para gravar com a coluna vazia e apontar para a linha nova", True)

print("\n=== tentativa anterior que parou no meio ===")
with motor.begin() as c:            # simula: renomeou e criou a nova vazia, e parou
    c.execute(text("ALTER TABLE pai RENAME TO pai_antiga_migracao"))
    c.execute(text("CREATE TABLE pai (id INTEGER PRIMARY KEY, guia_id INTEGER, codigo VARCHAR(10))"))
migracao._permitir_nulo(pai_novo, ["guia_id"])
with motor.connect() as c:
    checar("os dados que estavam na tabela provisória voltaram",
           [r[0] for r in c.execute(text("SELECT id FROM pai ORDER BY id"))] == [7, 8, 9])
    checar("e a provisória sumiu", not c.execute(text(
        "SELECT 1 FROM sqlite_master WHERE name='pai_antiga_migracao'")).first())

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print("  -", e)
    sys.exit(1)
print("Recriação de tabela no SQLite OK.")
