"""Teste da migração automática num banco antigo (não precisa de servidor).

Cria um SQLite no formato antigo — tabela `contratos` sem as colunas novas e com
`comprador_id`/`vendedor_id` obrigatórios — roda a migração e confere que:

  * as colunas novas foram criadas (tipo, agente, ICMS, títulos gerados);
  * as colunas que agora podem ficar vazias deixaram de ser obrigatórias
    (na compra o comprador é a empresa, então o campo fica em branco);
  * as linhas antigas continuam lá, com CORRETAGEM como tipo;
  * dá para gravar um contrato de compra sem comprador;
  * a tabela temporária da conversão não fica para trás.

Uso:  python testes/teste_migracao.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
banco = Path(tempfile.mkdtemp()) / "antigo.db"
for var in ("POSTGRES_URL", "VERCEL"):
    os.environ.pop(var, None)
os.environ["FIN_DATABASE_URL"] = f"sqlite:///{banco}"

falhas = []


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


# ------------------------------------------------- banco no formato antigo
con = sqlite3.connect(banco)
con.executescript("""
CREATE TABLE contratos (
  id INTEGER PRIMARY KEY, empresa_id INTEGER NOT NULL, numero VARCHAR(30) NOT NULL,
  data DATE NOT NULL, comprador_id INTEGER NOT NULL, vendedor_id INTEGER NOT NULL,
  corretor VARCHAR(160), quantidade NUMERIC NOT NULL DEFAULT 0,
  preco_unitario NUMERIC NOT NULL DEFAULT 0, diferencial NUMERIC NOT NULL DEFAULT 0,
  valor_total NUMERIC NOT NULL DEFAULT 0, peso_total NUMERIC NOT NULL DEFAULT 0,
  comissao_comprador_percentual NUMERIC NOT NULL DEFAULT 0,
  comissao_comprador_valor NUMERIC NOT NULL DEFAULT 0,
  comissao_vendedor_percentual NUMERIC NOT NULL DEFAULT 0,
  comissao_vendedor_valor NUMERIC NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'ABERTO', observacao TEXT);
INSERT INTO contratos (id, empresa_id, numero, data, comprador_id, vendedor_id,
                       quantidade, preco_unitario, valor_total, status, observacao)
VALUES (7, 1, '00000295', '2026-09-10', 3, 4, 330, 1320, 435600, 'FECHADO_A_RECEBER',
        'contrato antigo');
""")
con.commit()
con.close()

import backend.models  # noqa: E402,F401  (registra as tabelas)
from backend.migracao import migrar  # noqa: E402

print("\n=== 1. Migração ===")
mudou = migrar()
checar("a migração mexeu na tabela contratos", any("contratos." in m for m in mudou), f"{len(mudou)} alteração(ões)")

con = sqlite3.connect(banco)
colunas = {r[1]: {"obrigatoria": bool(r[3])} for r in con.execute("PRAGMA table_info(contratos)")}
novas = ["tipo", "agente_id", "agente_percentual", "agente_valor", "icms_percentual",
         "icms_valor", "lancamento_mercadoria_id", "lancamento_agente_id"]
faltando = [c for c in novas if c not in colunas]
checar("colunas novas criadas", not faltando, str(faltando))
checar("comprador_id e vendedor_id aceitam vazio",
       not colunas["comprador_id"]["obrigatoria"] and not colunas["vendedor_id"]["obrigatoria"])
checar("empresa_id e numero continuam obrigatórios",
       colunas["empresa_id"]["obrigatoria"] and colunas["numero"]["obrigatoria"])

print("\n=== 2. Dados antigos e novos ===")
linha = con.execute("SELECT numero, comprador_id, vendedor_id, valor_total, status, tipo, "
                    "observacao FROM contratos WHERE id = 7").fetchone()
checar("contrato antigo intacto", linha[:5] == ("00000295", 3, 4, 435600, "FECHADO_A_RECEBER")
       and linha[6] == "contrato antigo", str(linha))
checar("contrato antigo virou CORRETAGEM", linha[5] == "CORRETAGEM", str(linha[5]))

con.execute("INSERT INTO contratos (id, empresa_id, numero, data, vendedor_id, tipo, valor_total, "
            "status, quantidade, preco_unitario, diferencial, peso_total, "
            "comissao_comprador_percentual, comissao_comprador_valor, "
            "comissao_vendedor_percentual, comissao_vendedor_valor, agente_percentual, "
            "agente_valor, icms_percentual, icms_valor, icms_manual) "
            "VALUES (8, 1, '00000296', '2026-09-17', 4, 'COMPRA', 260000, 'ABERTO', 200, 1300, "
            "0, 0, 0, 0, 0, 0, 1, 2600, 18, 46800, 0)")
con.commit()
compra = con.execute("SELECT numero, comprador_id, tipo FROM contratos WHERE id = 8").fetchone()
checar("compra grava sem comprador", compra == ("00000296", None, "COMPRA"), str(compra))
sobrou = con.execute("SELECT name FROM sqlite_master WHERE name LIKE '%antiga_migracao'").fetchall()
checar("tabela temporária da conversão foi apagada", not sobrou, str(sobrou))

print("\n=== 3. Rodar de novo não muda nada ===")
de_novo = migrar()
checar("segunda migração não altera nada", not de_novo, str(de_novo))
con.close()

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    raise SystemExit(1)
print("Migração OK.")
