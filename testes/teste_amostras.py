"""Teste das amostras de café — classificação física, sensorial e laudo.

O que se confere
----------------
  * **equivalência de defeitos** da IN 8/2003: 1 preto = 1, 2 ardidos = 1,
    5 verdes = 1, 1 pau/pedra grande = 5...;
  * **tipo pelo total em 300 g**: os limites inteiros (2 = 4, 3 = 12 ... 8 = 360),
    os intermediários em passos de 5, e fora de tipo (acima de 360, ou mais de
    50 pretos, ou mais de 100 ardidos);
  * a **amostra menor que 300 g** é levada à base de 300 g;
  * **peneiras**: percentual de cada uma, chato graúdo/médio/miúdo, moca, e a
    peneira "de leitura" (17 acima...);
  * **prova SCA**: soma das dez notas menos os defeitos de xícara, categoria
    (80 = especial), e prova incompleta não dá pontuação;
  * **padrão sugerido** e o tipo corrigido à mão;
  * pela API: criar com número em sequência, salvar recalcula, lista e filtros,
    laudo traz empresa e resultado, recusas (umidade fora de 0–100, produtor de
    outra empresa) e amostra de outra conta não abre.

Uso:  python testes/teste_amostras.py   (com o servidor no ar)
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8000"
erros = []


def api(metodo, caminho, dados=None, token=None, esperar_erro=False):
    req = urllib.request.Request(
        f"{BASE}{caminho}",
        data=json.dumps(dados).encode() if dados is not None else None,
        method=metodo,
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as erro:
        if not esperar_erro:
            raise
        dados = json.loads(erro.read() or b"{}")
        dados["_status"] = erro.code
        return dados


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


from backend import classificacao as c                       # noqa: E402

# =========================================================================== #
print("=== 1. Equivalência de defeitos ===")
r = c.contar_defeitos({"preto": 3, "ardido": 4, "verde": 10, "pau_pedra_grande": 1,
                       "casca_pequena": 6, "coco": 2})
por = {x["chave"]: x["defeitos"] for x in r["linhas"]}
checar("3 pretos = 3 defeitos", por["preto"] == 3)
checar("4 ardidos = 2 defeitos", por["ardido"] == 2)
checar("10 verdes = 2 defeitos", por["verde"] == 2)
checar("1 pau/pedra grande = 5 defeitos", por["pau_pedra_grande"] == 5)
checar("6 cascas pequenas = 2 defeitos", por["casca_pequena"] == 2)
checar("total 16 em 300 g", r["total_300g"] == 16, r["total_300g"])
checar("valor esquisito é ignorado, não quebra",
       c.contar_defeitos({"preto": "abc", "verde": -3, "inventado": 9})["total_300g"] == 0)
meia = c.contar_defeitos({"preto": 5}, peso_amostra=150)
checar("amostra de 150 g: 5 pretos viram 10 defeitos em 300 g",
       meia["total_300g"] == 10, meia["total_300g"])

# =========================================================================== #
print("\n=== 2. Tipo pelos defeitos ===")
casos = [(0, "2"), (4, "2"), (12, "3"), (26, "4"), (46, "5"), (86, "6"), (160, "7"),
         (360, "8"), (5, "2-10"), (8, "2-25"), (11.9, "2-45"), (66, "5-25"), (361, c.FORA_DE_TIPO)]
for total, esperado in casos:
    obtido = c.tipo_pelos_defeitos(total)["tipo"]
    checar(f"{total} defeitos -> tipo {esperado}", obtido == esperado, obtido)
checar("51 pretos: fora de tipo, mesmo com soma baixa",
       c.tipo_pelos_defeitos(51, {"preto": 51})["tipo"] == c.FORA_DE_TIPO)
checar("101 ardidos: fora de tipo",
       c.tipo_pelos_defeitos(50, {"ardido": 101})["tipo"] == c.FORA_DE_TIPO)

# =========================================================================== #
print("\n=== 3. Peneiras ===")
p = c.peneirar({"C19": 5, "C18": 20, "C17": 30, "C16": 20, "C15": 10, "C14": 5,
                "M11": 6, "FUNDO": 4})
checar("soma 100 g", p["soma"] == 100)
checar("chato graúdo (17 acima) 55%", p["grupos"]["chato_graudo"] == 55, p["grupos"])
checar("chato médio 30%, miúdo 5%",
       p["grupos"]["chato_medio"] == 30 and p["grupos"]["chato_miudo"] == 5)
checar("moca 6%, fundo 4%", p["grupos"]["moca_total"] == 6 and p["grupos"]["fundo"] == 4)
checar("peneira de leitura: 17 acima", p["leitura"] == "17 acima", p["leitura"])
checar("soma diferente do peso gera aviso",
       any("peneiras somam" in a for a in c.calcular(
           {"peneiras": {"C17": 80}, "peso_peneiras": 100})["avisos"]))

# =========================================================================== #
print("\n=== 4. Prova de xícara (SCA) ===")
notas = {"fragrancia": 8, "sabor": 8, "finalizacao": 7.75, "acidez": 7.75, "corpo": 7.75,
         "equilibrio": 7.75, "docura": 10, "uniformidade": 10, "xicara_limpa": 10,
         "nota_geral": 7.75}
prova = c.provar(notas)
checar("soma das dez notas: 84,75", prova["pontuacao"] == 84.75, prova["pontuacao"])
checar("categoria: muito bom — especial", prova["categoria"].startswith("Muito bom"))
checar("defeito de xícara desconta",
       c.provar(notas, defeitos_xicara=4)["pontuacao"] == 80.75)
checar("nota acima de 10 vira 10", c.provar({**notas, "sabor": 15})["notas"]["sabor"] == 10)
incompleta = c.provar({"sabor": 8})
checar("prova incompleta não dá pontuação", incompleta["pontuacao"] is None
       and incompleta["parcial"] == 8)

# =========================================================================== #
print("\n=== 5. Tudo junto: padrão e tipo corrigido ===")
tudo = c.calcular({"defeitos": {"preto": 20, "verde": 50, "ardido": 40, "quebrado": 25},
                   "peneiras": {"C18": 30, "C17": 30, "C16": 40}, "bebida": "Dura"})
checar("55 defeitos (20 pretos, 10 de verdes, 20 de ardidos, 5 de quebrados) -> tipo 5-15",
       tudo["tipo"] == "5-15", tudo["tipo"])
checar("padrão sugerido junta tipo, bebida e peneira",
       tudo["padrao_sugerido"] == "Tipo 5-15 · bebida dura · peneira 17 acima",
       tudo["padrao_sugerido"])
manual = c.calcular({"defeitos": {"preto": 20}, "tipo": "4-35", "tipo_manual": True})
checar("tipo corrigido à mão vale no laudo",
       manual["tipo"] == "4-35" and manual["tipo_calculado"] != "4-35", manual["tipo"])
checar("sem defeito digitado, não inventa tipo", c.calcular({})["tipo"] == "")

# =========================================================================== #
print("\n=== 6. Pela API ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"amostra{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria Café", "plano": "P1_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]
produtor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "FORNECEDOR", "nome": "SITIO BOA ESPERANCA",
    "cidade": "TRES PONTAS", "uf": "MG"}, t)

base = {"empresa_id": eid, "parceiro_id": produtor["id"], "lote": "L-01", "sacas": 120,
        "safra": "2025/2026", "preparo": "CEREJA_DESCASCADO", "umidade": 11.5,
        "defeitos": {"preto": 2, "verde": 5}, "peneiras": {"C17": 60, "C16": 40},
        "bebida": "Mole", "sensorial": notas}
a1 = api("POST", "/api/amostras", base, t)
checar("primeira amostra é a nº 1", a1["numero"] == 1, a1["numero"])
checar("nome, cidade e UF vieram do cadastro do produtor",
       a1["produtor_nome"] == "SITIO BOA ESPERANCA" and a1["municipio"] == "TRES PONTAS"
       and a1["uf"] == "MG")
checar("tipo gravado: 3 defeitos -> tipo 2", a1["tipo"] == "2" and a1["total_defeitos"] == 3,
       (a1["tipo"], a1["total_defeitos"]))
checar("pontuação gravada", a1["pontuacao"] == 84.75, a1["pontuacao"])
a2 = api("POST", "/api/amostras", {**base, "lote": "L-02", "sensorial": {}}, t)
checar("segunda amostra é a nº 2", a2["numero"] == 2)

salvo = api("PUT", f"/api/amostras/{a2['id']}", {
    **base, "lote": "L-02", "sensorial": {}, "situacao": "CLASSIFICADA",
    "defeitos": {"preto": 30, "ardido": 40}}, t)
checar("salvar recalcula: 50 defeitos -> 5-5", salvo["tipo"] == "5-5", salvo["tipo"])
checar("classificada ganha a data de classificação", bool(salvo["data_classificacao"]))

lista = api("GET", f"/api/amostras?empresa_id={eid}", None, t)
checar("lista com as duas", lista["resumo"]["total"] == 2)
checar("resumo: 1 classificada, 1 especial",
       lista["resumo"]["classificadas"] == 1 and lista["resumo"]["especiais"] == 1,
       lista["resumo"])
busca = api("GET", f"/api/amostras?empresa_id={eid}&busca=L-02", None, t)
checar("busca pelo lote", [x["numero"] for x in busca["amostras"]] == [2])
num = api("GET", f"/api/amostras?empresa_id={eid}&busca=1", None, t)
checar("busca pelo número", 1 in [x["numero"] for x in num["amostras"]])

laudo = api("GET", f"/api/amostras/{a1['id']}/laudo", None, t)
checar("laudo traz a empresa e o resultado",
       laudo["empresa"]["razao_social"] and laudo["amostra"]["resultado"]["sensorial"]["pontuacao"]
       == 84.75)

r = api("POST", "/api/amostras", {**base, "umidade": 140}, t, esperar_erro=True)
checar("umidade de 140% é recusada", r.get("_status") == 400, r)
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"amostra-outro{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra", "plano": "P1_ANUAL", "uf": "SP"})
r = api("POST", "/api/amostras", {**base, "empresa_id": outra["empresa"]["id"]},
        outra["token"], esperar_erro=True)
checar("produtor de outra empresa é recusado", r.get("_status") == 400, r)
r = api("GET", f"/api/amostras/{a1['id']}", None, outra["token"], esperar_erro=True)
checar("amostra de outra conta não abre", r.get("_status") in (403, 404), r.get("_status"))
r = api("GET", f"/api/amostras/{a1['id']}/laudo", None, outra["token"], esperar_erro=True)
checar("nem o laudo", r.get("_status") in (403, 404), r.get("_status"))

api("DELETE", f"/api/amostras/{a2['id']}", None, t)
lista = api("GET", f"/api/amostras?empresa_id={eid}", None, t)
checar("apagar tira da lista", lista["resumo"]["total"] == 1)

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(" -", e)
    sys.exit(1)
print("Todos os testes das amostras de café passaram.")
