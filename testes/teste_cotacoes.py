"""Teste da faixa de cotações do café (sem internet: usa respostas gravadas).

Confere:
  * leitura das fontes: Yahoo (NY, DXY, dólar, euro), Notícias Agrícolas (Londres, B3,
    NY de reserva) e Banco Central (Ptax);
  * contratos de NY escolhidos pela data (mês de entrega corrente é pulado);
  * contrato de Londres do mês corrente fica de fora;
  * quando uma fonte cai: NY usa a reserva; o grupo sem reserva mantém o último valor
    marcado como "atrasado"; o dólar usa a AwesomeAPI;
  * o cache no banco evita consultar as fontes a cada visita;
  * a rota pública /api/publico/cotacoes e a chave de desligar a faixa.

Uso:  python testes/teste_cotacoes.py
"""
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

PASTA = Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA.parent))
banco = Path(tempfile.mkdtemp()) / "cotacoes.db"
for var in ("FIN_DATABASE_URL", "POSTGRES_URL", "VERCEL"):
    os.environ.pop(var, None)
os.environ["FIN_DATABASE_URL"] = ""

import backend.config as config  # noqa: E402

config.DATABASE_URL = f"sqlite:///{banco}"
import backend.database as database  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

database.engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})
database.SessionLocal = sessionmaker(bind=database.engine, autoflush=False, future=True)

from backend import cotacoes, models  # noqa: E402,F401
from backend.database import Base  # noqa: E402

Base.metadata.create_all(database.engine)
falhas = []


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


class Hoje(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 17)


cotacoes.date = Hoje  # o teste roda "em 17/09/2026", como as respostas gravadas
DADOS = PASTA / "dados_cotacoes"
chamadas = []
fora_do_ar = set()


def baixar_gravado(url: str) -> str:
    chamadas.append(url)
    for chave in fora_do_ar:
        if chave in url:
            raise OSError(f"{chave} fora do ar (simulado)")
    if "finance.yahoo.com" in url:
        simbolo = url.split("/chart/")[1].split("?")[0].replace("%3D", "=")
        return (DADOS / f"yahoo_{simbolo}.json").read_text(encoding="utf-8")
    if "noticiasagricolas" in url:
        return (DADOS / f"na_{url.rstrip('/').split('/')[-1]}.html").read_text(encoding="utf-8")
    if "olinda.bcb.gov.br" in url:
        return (DADOS / "bcb_ptax.json").read_text(encoding="utf-8")
    if "awesomeapi" in url:
        return (DADOS / f"awesome_{url.split('/')[-1]}.json").read_text(encoding="utf-8")
    raise OSError(f"URL inesperada: {url}")


cotacoes.baixar = baixar_gravado

print("\n=== 1. Contratos e leitura das páginas ===")
checar("NY em setembro/26: dezembro, março e maio",
       [r for _, r in cotacoes.contratos_kc(date(2026, 9, 17))] == ["Dezembro/26", "Março/27", "Maio/27"],
       str(cotacoes.contratos_kc(date(2026, 9, 17))))
checar("NY em dezembro pula o mês de entrega",
       cotacoes.contratos_kc(date(2026, 12, 2))[0][0] == "KCH27.NYB")
checar("número brasileiro com milhar", cotacoes._numero_br("3.430,00") == 3430.0)
checar("variação com sinal de mais", cotacoes._numero_br("+5") == 5.0)

print("\n=== 2. Atualização com todas as fontes no ar ===")
db = database.SessionLocal()
dados = cotacoes.obter(db, 10)
grupos = {g["chave"]: g for g in dados["grupos"]}
checar("quatro grupos", list(grupos) == ["ny", "londres", "b3", "moedas"], str(list(grupos)))
ny = grupos["ny"]["itens"]
checar("NY com 3 contratos do Yahoo", [i["contrato"] for i in ny] == ["Dezembro/26", "Março/27", "Maio/27"])
checar("NY dezembro 277,70 e -3,85 pontos",
       ny[0]["cotacao"] == 277.7 and ny[0]["variacao"] == -3.85, str(ny[0]))
lon = grupos["londres"]["itens"]
checar("Londres sem o vencimento de setembro (mês corrente)",
       [i["contrato"] for i in lon] == ["Novembro/26", "Janeiro/27", "Março/27"], str([i["contrato"] for i in lon]))
checar("Londres novembro 3.430 e -51", lon[0]["cotacao"] == 3430.0 and lon[0]["variacao"] == -51.0)
checar("Londres março com variação positiva", lon[2]["variacao"] == 5.0)
b3 = grupos["b3"]["itens"]
checar("B3 dezembro 337,35 e -2,12%",
       b3[0]["contrato"] == "Dezembro/26" and b3[0]["cotacao"] == 337.35
       and b3[0]["variacao"] == -2.12 and b3[0]["tipo_variacao"] == "%", str(b3[0]))
checar("B3 com data de fechamento", grupos["b3"]["referencia"] == "fechamento 16/09/2026")
moedas = {i["contrato"]: i for i in grupos["moedas"]["itens"]}
checar("moedas DXY, Dólar, Euro e Ptax", list(moedas) == ["DXY", "Dólar", "Euro", "Ptax"], str(list(moedas)))
checar("dólar 5,1474", moedas["Dólar"]["cotacao"] == 5.1474)
checar("Ptax 5,1527 com variação +0,0037",
       moedas["Ptax"]["cotacao"] == 5.1527 and abs(moedas["Ptax"]["variacao"] - 0.0037) < 1e-9,
       str(moedas["Ptax"]))
checar("nenhum grupo atrasado", not any(g["atrasado"] for g in dados["grupos"]))

print("\n=== 3. Cache no banco ===")
antes = len(chamadas)
de_novo = cotacoes.obter(db, 10)
checar("segunda visita não consulta a internet", len(chamadas) == antes, f"{len(chamadas) - antes} consulta(s)")
checar("devolve o mesmo conteúdo", de_novo["atualizado_em"] == dados["atualizado_em"])
registro = db.get(models.CacheExterno, cotacoes.CHAVE_CACHE)
registro.atualizado_em = datetime.utcnow() - timedelta(minutes=11)
db.commit()
cotacoes.obter(db, 10)
checar("depois de 10 minutos consulta de novo", len(chamadas) > antes)

print("\n=== 4. Fontes fora do ar ===")
fora_do_ar.update({"finance.yahoo.com", "olinda.bcb.gov.br"})
registro = db.get(models.CacheExterno, cotacoes.CHAVE_CACHE)
registro.atualizado_em = datetime.utcnow() - timedelta(hours=1)
db.commit()
sem_yahoo = {g["chave"]: g for g in cotacoes.obter(db, 10)["grupos"]}
checar("NY cai para o Notícias Agrícolas",
       [i["contrato"] for i in sem_yahoo["ny"]["itens"]] == ["Dezembro/26", "Março/27"]
       and sem_yahoo["ny"]["itens"][0]["cotacao"] == 281.55, str(sem_yahoo["ny"]["itens"]))
moedas2 = {i["contrato"]: i for i in sem_yahoo["moedas"]["itens"]}
checar("dólar e euro pela AwesomeAPI", moedas2.get("Dólar", {}).get("cotacao") == 5.15
       and moedas2.get("Euro", {}).get("cotacao") == 5.91, str(list(moedas2)))
checar("sem Yahoo não há DXY, sem BCB não há Ptax", "DXY" not in moedas2 and "Ptax" not in moedas2)

fora_do_ar.add("noticiasagricolas")
registro = db.get(models.CacheExterno, cotacoes.CHAVE_CACHE)
registro.atualizado_em = datetime.utcnow() - timedelta(hours=1)
db.commit()
tudo_fora = {g["chave"]: g for g in cotacoes.obter(db, 10)["grupos"]}
checar("Londres continua com o último valor, marcado como atrasado",
       tudo_fora["londres"]["atrasado"] and tudo_fora["londres"]["itens"][0]["cotacao"] == 3430.0)
checar("B3 também mantém o último valor", tudo_fora["b3"]["atrasado"])
fora_do_ar.clear()
db.close()

print("\n=== 5. Rota pública ===")
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

cliente = TestClient(app)
cliente.__enter__()
resposta = cliente.get("/api/publico/cotacoes")
corpo = resposta.json()
checar("rota responde sem login", resposta.status_code == 200 and corpo["ativo"] is True)
checar("rota traz os grupos", len(corpo["grupos"]) == 4, str(len(corpo["grupos"])))
checar("navegador pode guardar por 1 minuto", "max-age=60" in resposta.headers.get("cache-control", ""))
db = database.SessionLocal()
from backend.assinaturas import salvar_configuracoes  # noqa: E402

salvar_configuracoes(db, {"cotacoes_ativas": "0"})
db.commit()
db.close()
desligada = cliente.get("/api/publico/cotacoes").json()
checar("faixa desligada em Config. do site", desligada["ativo"] is False and desligada["grupos"] == [])
cliente.__exit__(None, None, None)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("Cotações OK.")
