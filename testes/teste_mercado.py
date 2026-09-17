"""Teste do painel "Mercado do Café" (sem internet: usa respostas gravadas).

Confere:
  * leitura de todos os fechamentos das páginas do Notícias Agrícolas (bolsas, Cepea,
    mercado físico por cidade e conilon do ES);
  * leitura do quadro "Cotações por Cidades" da AgnoCafé;
  * gravação do histórico sem duplicar (ler de novo só atualiza) e filtro por período,
    contrato e cidade;
  * uma fonte fora do ar não impede as outras;
  * notícias: RSS e lista do Notícias Agrícolas, filtro do que é do agro nos feeds
    regionais do g1, marcação de cultura e região (Patrocínio, Varginha, Araguari,
    Patos de Minas), notícia repetida em dois sites aparece uma vez, filtros;
  * rotas públicas /mercado, /api/publico/mercado/resumo, /historico, /noticias e a
    chave que desliga a AgnoCafé.

Uso:  python testes/teste_mercado.py
"""
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

PASTA = Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA.parent))
banco = Path(tempfile.mkdtemp()) / "mercado.db"
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

from backend import cotacoes, mercado, models  # noqa: E402
from backend.database import Base  # noqa: E402

Base.metadata.create_all(database.engine)
falhas = []


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


DADOS = PASTA / "dados_mercado"
chamadas = []
fora_do_ar = set()
ARQUIVOS = {
    "agnocafe.com.br": "agnocafe.html",
    "olinda.bcb.gov.br": "bcb_ptax_periodo.json",
    "/noticias/cafe/": "na_noticias_cafe.html",
    "canalrural.com.br/agricultura/cafe/feed": "canal_cafe.xml",
    "canalrural.com.br/feed": "canal_geral.xml",
    "economia/agronegocios": "g1_agro.xml",
    "mg/sul-de-minas": "g1_sul.xml",
    "mg/triangulo-mineiro": "g1_triangulo.xml",
}


def baixar_gravado(url: str) -> str:
    chamadas.append(url)
    for chave in fora_do_ar:
        if chave in url:
            raise OSError(f"{chave} fora do ar (simulado)")
    if "/cotacoes/cafe/" in url:
        return (DADOS / f"na_{url.rstrip('/').split('/')[-1]}.html").read_text(encoding="utf-8")
    for trecho, arquivo in ARQUIVOS.items():
        if trecho in url:
            return (DADOS / arquivo).read_text(encoding="utf-8")
    raise OSError(f"URL inesperada: {url}")


cotacoes.baixar = baixar_gravado
mercado.hoje_brasil = lambda: date(2026, 9, 17)

print("\n=== 1. Leitura das páginas ===")
blocos = mercado.blocos_na((DADOS / "na_cafe-bolsa-de-londres-liffe.html").read_text(encoding="utf-8"))
checar("Londres: três pregões com data", [b[0] for b in blocos] == [date(2026, 9, 16), date(2026, 9, 15), date(2026, 9, 14)])
duro = mercado.serie_na("fisico_6_duro")
patro = [l for l in duro if l["cidade"] == "Patrocínio" and l["data"] == date(2026, 9, 16)]
checar("tipo 6 duro: Patrocínio 1.635,00 (-1,51%)",
       len(patro) == 1 and patro[0]["valor"] == 1635.0 and patro[0]["variacao"] == -1.51, str(patro))
ara = [l for l in duro if l["cidade"] == "Araguari"]
checar("tipo 6 duro: Araguari nos dois dias, variação '-' vira vazio",
       len(ara) == 2 and ara[1]["variacao"] is None, str(ara))
checar("'Oeste da Bahia (AIBA)' vira cidade 'Oeste da Bahia'",
       any(l["cidade"] == "Oeste da Bahia" for l in duro))
conilon = mercado.serie_na("conilon_es")
checar("conilon: linhas de título (***) ficam de fora e dão nome ao item",
       [l["item"] for l in conilon[:3]] == ["Vitória (CCCV) · Tipo 7/8", "São Gabriel (Cooabriel) · Tipo 7",
                                             "São Gabriel (Cooabriel) · Tipo 8"], str([l["item"] for l in conilon[:3]]))
ny = mercado.serie_na("ny")
checar("NY: linha 'Dólar: 5,15' fica de fora; 9 linhas em 3 dias", len(ny) == 9, str(len(ny)))
checar("NY: Dezembro/26 em 14/09 com +4,80 pontos",
       any(l["item"] == "Dezembro/26" and l["data"] == date(2026, 9, 14) and l["variacao"] == 4.8 for l in ny))
cepea = mercado.serie_cepea()
checar("Cepea arábica 1.566,48 e conilon 977,32 em 16/09",
       {(l["item"], l["valor"]) for l in cepea if l["data"] == date(2026, 9, 16)} == {("Arábica", 1566.48), ("Conilon", 977.32)})
agno = mercado.serie_agnocafe()
checar("AgnoCafé: Patrocínio com 4 cotações", len([l for l in agno if l["cidade"] == "Patrocínio"]) == 4)
checar("AgnoCafé: 'Peneira 17/18' em Patrocínio R$ 1.950",
       any(l["item"] == "Patrocínio · Peneira 17/18" and l["valor"] == 1950.0 for l in agno))
checar("AgnoCafé: 'Indicadores' não vira cidade",
       all(l["cidade"] is None for l in agno if l["item"].startswith("Indicadores")))
ptax = mercado.serie_ptax()
checar("Ptax: 3 dias e variação calculada",
       len(ptax) == 3 and abs(ptax[-1]["variacao"] - 0.0037) < 1e-9, str(ptax[-1]))

print("\n=== 2. Histórico no banco ===")
db = database.SessionLocal()
meta = mercado.atualizar_mercado(db)
checar("todas as fontes ok", set(meta["fontes"].values()) == {"ok"}, str(meta["fontes"]))
total = db.query(models.CotacaoHistorico).count()
mercado.atualizar_mercado(db)
checar("ler de novo não duplica", db.query(models.CotacaoHistorico).count() == total, f"{total} linhas")
hist = mercado.historico(db, "londres", "Novembro/26", de=date(2026, 9, 15))
checar("filtro por contrato e período", [h["data"] for h in hist] == ["2026-09-16", "2026-09-15"], str(hist))
cid = mercado.historico(db, cidade="Patrocínio", de=date(2026, 9, 1))
grupos_patro = {h["grupo"] for h in cid}
checar("filtro por cidade junta NA e AgnoCafé",
       grupos_patro == {"fisico_6_7", "fisico_6_duro", "cereja", "agnocafe"}, str(grupos_patro))
res = mercado.resumo(db, meta)
g = {x["chave"]: x for x in res["grupos"]}
checar("resumo com as 10 séries", len(g) == 10, str(list(g)))
checar("resumo: último fechamento de Londres é 16/09", g["londres"]["data"] == "2026-09-16")
checar("resumo: contratos de Londres em ordem de vencimento",
       g["londres"]["todos_itens"] == ["Setembro/26", "Novembro/26", "Janeiro/27", "Março/27"], str(g["londres"]["todos_itens"]))
checar("cidades em destaque primeiro", res["cidades"][:4] == ["Patrocínio", "Varginha", "Araguari", "Patos de Minas"])
checar("outras praças incluem Guaxupé e Três Pontas", "Guaxupé" in res["cidades"] and "Três Pontas" in res["cidades"])

# valor corrigido pela fonte no mesmo dia é atualizado
original = (DADOS / "agnocafe.html").read_text(encoding="utf-8")
cotacoes.baixar = lambda url: original.replace("R$ 1950,00", "R$ 1960,00") if "agnocafe" in url else baixar_gravado(url)
mercado.gravar_historico(db, mercado.serie_agnocafe())
novo = mercado.historico(db, "agnocafe", "Patrocínio · Peneira 17/18")
checar("mesmo dia: valor atualizado, sem linha nova", len(novo) == 1 and novo[0]["valor"] == 1960.0, str(novo))
cotacoes.baixar = baixar_gravado

print("\n=== 3. Fonte fora do ar ===")
fora_do_ar.add("agnocafe")
meta2 = mercado.atualizar_mercado(db)
checar("AgnoCafé fora do ar não derruba as outras",
       meta2["fontes"]["agnocafe"] == "indisponível" and meta2["fontes"]["ny"] == "ok")
fora_do_ar.clear()
antes = len(chamadas)
mercado.garantir_atualizado(db, 30)
checar("dentro de 30 minutos não consulta a internet", len(chamadas) == antes)

print("\n=== 4. Faixa grava moedas do dia ===")
mercado.registrar_faixa(db, {"grupos": [{"chave": "moedas", "atrasado": False, "itens": [
    {"contrato": "Dólar", "cotacao": 5.1474, "variacao": -0.02}, {"contrato": "Ptax", "cotacao": 5.15, "variacao": 0}]}]})
dolar = mercado.historico(db, "moedas", "Dólar comercial")
checar("dólar comercial de hoje no histórico", len(dolar) == 1 and dolar[0]["data"] == "2026-09-17")

print("\n=== 5. Notícias ===")
cult, reg, agro = mercado.classificar("Com patrocínio de cooperativas, feira de milho safrinha começa em Goiás")
checar("'patrocínio de' não é a cidade", "Patrocínio" not in reg and "Milho" in cult, str(reg))
cult, reg, agro = mercado.classificar("Granizo atinge lavouras de café na zona rural de Patrocínio",
                                      "Em Patos de Minas e Araguari também houve chuva forte.")
checar("cidade da região e culturas marcadas",
       {"Patrocínio", "Patos de Minas", "Araguari"} <= set(reg) and "Café" in cult and "Clima" in cult, f"{reg} {cult}")
checar("chuva na cidade sem lavoura não é do agro",
       mercado.classificar("Chuva alaga ruas e aciona alerta em Uberlândia")[2] is False)

noticias = mercado.atualizar_noticias(db)
itens = noticias["itens"]
titulos = [n["titulo"] for n in itens]
checar("todas as fontes de notícias ok", set(noticias["fontes"].values()) == {"ok"}, str(noticias["fontes"]))
checar("feed regional: acidente e telejornal ficam de fora",
       not any("Passageiro" in t or "Bom Dia Cidade" in t or "Agências da Caixa" in t for t in titulos))
checar("feed regional: colheita de café no Sul de Minas entra",
       any(t.startswith("Chuvas atrasam fim da colheita") for t in titulos))
checar("mesma notícia em dois sites aparece uma vez",
       sum(1 for t in titulos if t.startswith("Café em NY afunda")) == 1)
na = next(n for n in itens if n["titulo"].startswith("Colheita de café da Cooxupé"))
checar("Notícias Agrícolas: link completo e horário em UTC",
       na["link"].startswith("https://www.noticiasagricolas.com.br/noticias/cafe/428074") and na["quando"] == "2026-09-16T12:54Z", str(na))
checar("ordem: mais nova primeiro", itens[0]["quando"] >= itens[-1]["quando"])
foco = mercado.filtrar_noticias(itens, regiao="foco")
checar("filtro região em destaque",
       foco and all(n["foco"] for n in foco) and any("Varginha" in n["titulo"] for n in foco), str([n["titulo"] for n in foco]))
checar("filtro por cidade Patrocínio",
       {n["titulo"][:20] for n in mercado.filtrar_noticias(itens, regiao="Patrocínio")}
       == {"Granizo atinge lavou", "Expocaccer reúne pro"})
so_cafe = mercado.filtrar_noticias(itens, cultura="Café")
checar("filtro cultura Café", so_cafe and all("Café" in n["culturas"] for n in so_cafe))
checar("busca sem acento acha 'Exportação'",
       any("Exportação" in n["titulo"] for n in mercado.filtrar_noticias(itens, busca="exportacao")))
checar("filtro por data", all(n["quando"][:10] >= "2026-09-16"
                              for n in mercado.filtrar_noticias(itens, de=date(2026, 9, 16))))
fora_do_ar.add("g1.globo.com")
parcial = mercado.atualizar_noticias(db, noticias)
checar("g1 fora do ar: notícias antigas do g1 continuam guardadas",
       parcial["fontes"]["g1_sul"] == "indisponível" and any("Sul de Minas" in n["regioes"] for n in parcial["itens"]))
fora_do_ar.clear()
velha = {"itens": [{"titulo": "Notícia de 3 meses atrás", "link": "https://x/1", "resumo": "", "fonte": "X",
                    "quando": (datetime.utcnow() - timedelta(days=90)).isoformat(timespec="minutes") + "Z",
                    "culturas": ["Café"], "regioes": [], "foco": False}]}
checar("notícias com mais de 60 dias saem", not any(n["titulo"].startswith("Notícia de 3 meses")
                                                  for n in mercado.atualizar_noticias(db, velha)["itens"]))
db.close()

print("\n=== 6. Rotas públicas ===")
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

cliente = TestClient(app)
cliente.__enter__()
pagina = cliente.get("/mercado")
checar("página /mercado abre sem login", pagina.status_code == 200 and "Mercado do Café" in pagina.text)
checar("página usa arquivos com versão", "/static/js/mercado.js?v=" in pagina.text)
r = cliente.get("/api/publico/mercado/resumo")
checar("resumo responde", r.status_code == 200 and len(r.json()["grupos"]) == 10, str(r.status_code))
r = cliente.get("/api/publico/mercado/historico", params={"grupo": "b3", "item": "Dezembro/26", "de": "2026-09-01"})
checar("histórico B3 dezembro: 3 dias", r.status_code == 200 and len(r.json()["linhas"]) == 3, r.text[:200])
checar("histórico sem série nem cidade é recusado", cliente.get("/api/publico/mercado/historico").status_code == 422)
checar("data inválida é recusada",
       cliente.get("/api/publico/mercado/historico", params={"grupo": "ny", "de": "17/09/2026"}).status_code == 422)
r = cliente.get("/api/publico/mercado/noticias", params={"regiao": "Varginha"})
corpo = r.json()
checar("notícias de Varginha", r.status_code == 200 and corpo["itens"]
       and all("Varginha" in n["regioes"] for n in corpo["itens"]), str(corpo.get("itens", [])[:1]))
checar("lista de regiões para os filtros", corpo["regioes"][:4] == ["Patrocínio", "Varginha", "Araguari", "Patos de Minas"])

db = database.SessionLocal()
from backend.assinaturas import salvar_configuracoes  # noqa: E402

salvar_configuracoes(db, {"mercado_agnocafe": "0"})
db.commit()
db.close()
sem_agno = cliente.get("/api/publico/mercado/resumo").json()
checar("AgnoCafé desligada some do resumo", "agnocafe" not in {x["chave"] for x in sem_agno["grupos"]})
r = cliente.get("/api/publico/mercado/historico", params={"cidade": "Patrocínio", "de": "2026-09-01"})
checar("AgnoCafé desligada some do histórico por cidade",
       r.status_code == 200 and all(x["grupo"] != "agnocafe" for x in r.json()["linhas"]))
db = database.SessionLocal()
salvar_configuracoes(db, {"cotacoes_ativas": "0"})
db.commit()
db.close()
checar("faixa desligada desliga o painel", cliente.get("/api/publico/mercado/resumo").status_code == 404)
cliente.__exit__(None, None, None)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("Mercado OK.")
