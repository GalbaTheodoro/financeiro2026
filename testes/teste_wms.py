"""Teste do WMS / Armazém (entrada, saídas, serviços, transferências e remoção).

O que se confere
----------------
  * o módulo é **só do Plano 4**: os planos 1, 2 e 3 recebem 403 do servidor,
    com a frase dizendo que está no Plano 4, e o menu deles não traz as rotas;
  * o Plano 4 recebe as cinco rotas do menu;
  * cadastro de armazém;
  * quadras do armazém (nome, X, Y);
  * guia de entrada: cabeçalho, lotes (número/sequência, peneira, padrão,
    peso, sacas, valor por saca) e locais (quadra, pilha, sacas, peso);
    só fecha quando os totais batem, e fechar gera os lotes, as posições e a
    entrada no saldo; reabrir só se nada saiu;
  * saída tira do saldo — e é recusada quando passa do que ele tem;
  * serviço registra nome e valor sem mexer no saldo;
  * transferência tira de um depositante e põe no outro, no mesmo armazém;
  * remoção tira de um armazém e põe no outro, para o mesmo depositante;
  * cada tipo tem a sua numeração;
  * cancelar volta o saldo — e é recusado quando o café da entrada já saiu.

Uso:  python testes/teste_wms.py   (com o servidor no ar)
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
        corpo = json.loads(erro.read() or b"{}")
        corpo["_status"] = erro.code
        return corpo


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


sufixo = str(int(time.time()))


def conta(plano):
    dados = api("POST", "/api/publico/cadastro", {
        "nome": "Galba", "email": f"wms{plano.lower()}{sufixo}@teste.com", "senha": "123456",
        "empresa": f"Armazém {plano}", "plano": plano})
    return dados["token"], dados["empresa"]["id"]


ROTAS_WMS = {"/wms-entradas", "/wms-saidas", "/wms-servicos", "/wms-transferencias",
             "/wms-remocoes"}

# =========================================================================== #
print("=== 1. Só o Plano 4 tem o WMS ===")
for plano in ("P1_SEMESTRAL", "P2_SEMESTRAL", "P3_ANUAL"):
    token, empresa = conta(plano)
    rotas = set(api("GET", "/api/auth/me", None, token)["assinatura"]["rotas"])
    checar(f"{plano}: o menu não traz o WMS", not (rotas & ROTAS_WMS))
    r = api("GET", f"/api/wms/armazens?empresa_id={empresa}", None, token, esperar_erro=True)
    checar(f"{plano}: o servidor recusa", r.get("_status") == 403, str(r.get("_status")))
    checar(f"{plano}: e a frase diz que está no Plano 4", "Plano 4" in str(r.get("detail")),
           str(r.get("detail"))[:80])

tk, eid = conta("P4_ANUAL")
rotas = set(api("GET", "/api/auth/me", None, tk)["assinatura"]["rotas"])
checar("Plano 4: o menu traz as cinco telas do WMS", ROTAS_WMS <= rotas)
info = api("GET", "/api/publico/info")
p4 = next(p for p in info["planos"] if p["nome"] == "Plano 4")
checar("a página inicial mostra o WMS no Plano 4",
       "WMS" in [m["codigo"] for m in p4["modulos"]])
outros = [p for p in info["planos"] if p["nome"] != "Plano 4"]
checar("e em nenhum outro plano",
       not any("WMS" in [m["codigo"] for m in p["modulos"]] for p in outros))

# =========================================================================== #
print("\n=== 2. Armazéns e depositantes ===")
a1 = api("POST", "/api/wms/armazens", {"empresa_id": eid, "nome": "Armazém Central",
                                       "cidade": "Patrocínio", "uf": "mg",
                                       "capacidade_sacas": 10000}, tk)
a2 = api("POST", "/api/wms/armazens", {"empresa_id": eid, "nome": "Galpão 2",
                                       "capacidade_sacas": 5000}, tk)
checar("cria o armazém", a1.get("id") and a1["uf"] == "MG")
sem_nome = api("POST", "/api/wms/armazens", {"empresa_id": eid, "nome": " "}, tk, esperar_erro=True)
checar("armazém sem nome é recusado", sem_nome.get("_status") == 400)

joao = api("POST", "/api/parceiros", {"empresa_id": eid, "nome": "João Produtor",
                                      "tipo": "FORNECEDOR", "pessoa": "F"}, tk)
maria = api("POST", "/api/parceiros", {"empresa_id": eid, "nome": "Maria Exportadora",
                                       "tipo": "CLIENTE", "pessoa": "J"}, tk)


origem = api("POST", "/api/parceiros", {"empresa_id": eid, "nome": "Sítio Boa Vista",
                                       "tipo": "FORNECEDOR", "pessoa": "F"}, tk)


def lancar(tipo, esperar_erro=False, **campos):
    dados = {"empresa_id": eid, "tipo": tipo, "armazem_id": a1["id"],
             "depositante_id": joao["id"], "lote": "1/1", **campos}
    return api("POST", "/api/wms/movimentos", dados, tk, esperar_erro=esperar_erro)


def saldo(armazem, depositante, lote="1/1"):
    r = api("GET", f"/api/wms/saldos?empresa_id={eid}", None, tk)
    for s in r["saldos"]:
        if s["armazem_id"] == armazem and s["depositante_id"] == depositante and s["lote"] == lote:
            return s["sacas"]
    return 0.0


# =========================================================================== #
print("\n=== 3. Quadras e guia de entrada ===")
qa1 = api("POST", "/api/wms/quadras", {"empresa_id": eid, "armazem_id": a1["id"],
                                       "nome": "a1", "x": 1, "y": 1}, tk)
qa2 = api("POST", "/api/wms/quadras", {"empresa_id": eid, "armazem_id": a1["id"],
                                       "nome": "A2", "x": 2, "y": 1}, tk)
qb1 = api("POST", "/api/wms/quadras", {"empresa_id": eid, "armazem_id": a2["id"],
                                       "nome": "B1", "x": 1, "y": 1}, tk)
checar("cria a quadra (nome em maiúsculas, com X e Y)",
       qa1.get("nome") == "A1" and qa1.get("x") == 1 and qa1.get("armazem_nome") == "Armazém Central")
repetida = api("POST", "/api/wms/quadras", {"empresa_id": eid, "armazem_id": a1["id"],
                                            "nome": "A1"}, tk, esperar_erro=True)
checar("quadra repetida no mesmo armazém é recusada", repetida.get("_status") == 400)
quadras_a1 = api("GET", f"/api/wms/quadras?empresa_id={eid}&armazem_id={a1['id']}", None, tk)
checar("a lista filtra as quadras do armazém", {q["nome"] for q in quadras_a1} == {"A1", "A2"})
checar("contratos de compra respondem (lista)",
       isinstance(api("GET", f"/api/wms/contratos-compra?empresa_id={eid}", None, tk), list))

guia_dados = {
    "empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
    "cliente_origem_id": origem["id"], "sacas": 410, "peso_total": 24000,
    "documento": "NF 123", "placa": "abc1d23",
    "lotes": [
        {"peneira": "17/18", "padrao": "Tipo 6 bebida dura", "sacas": 300, "peso": 18000,
         "valor_unitario": 1500,
         "locais": [{"quadra_id": qa1["id"], "pilha": "p1", "sacas": 200},
                    {"quadra_id": qa2["id"], "pilha": "P2", "sacas": 100},
                    {"quadra_id": None, "sacas": 0}]},           # linha em branco: ignorada
        {"peneira": "15/16", "padrao": "Tipo 7", "sacas": 100, "peso": 6000,
         "valor_unitario": 1300,
         "locais": [{"quadra_id": qa1["id"], "pilha": "P3", "sacas": 100, "peso": 6000}]},
    ],
}
g1 = api("POST", "/api/wms/guias-entrada", guia_dados, tk)
checar("guia criada aberta com número 1", g1.get("numero") == 1 and g1.get("status") == "ABERTA")
checar("os lotes ganham o código número/sequência",
       [l["codigo"] for l in g1["lotes"]] == ["1/1", "1/2"])
checar("valor do lote = sacas x valor por saca", g1["lotes"][0]["valor_total"] == 450000)
checar("a linha de local em branco não entra", len(g1["lotes"][0]["locais"]) == 2)
checar("a placa fica em maiúsculas", g1.get("placa") == "ABC1D23")
checar("guia aberta ainda não mexe no saldo", saldo(a1["id"], joao["id"]) == 0)

nao_fecha = api("POST", f"/api/wms/guias-entrada/{g1['id']}/fechar", None, tk, esperar_erro=True)
checar("não fecha com o cabeçalho diferente da soma dos lotes",
       nao_fecha.get("_status") == 400 and "410,00" in str(nao_fecha.get("detail")),
       str(nao_fecha.get("detail"))[:110])
guia_dados["sacas"] = 400
guia_dados["lotes"][1]["locais"][0]["sacas"] = 90
g1 = api("PUT", f"/api/wms/guias-entrada/{g1['id']}", guia_dados, tk)
nao_fecha = api("POST", f"/api/wms/guias-entrada/{g1['id']}/fechar", None, tk, esperar_erro=True)
checar("nem com os locais diferentes das sacas do lote",
       nao_fecha.get("_status") == 400 and "Lote 1/2" in str(nao_fecha.get("detail")),
       str(nao_fecha.get("detail"))[:110])
guia_dados["lotes"][1]["locais"][0]["sacas"] = 100
api("PUT", f"/api/wms/guias-entrada/{g1['id']}", guia_dados, tk)
g1 = api("POST", f"/api/wms/guias-entrada/{g1['id']}/fechar", None, tk)
checar("fecha a guia", g1.get("status") == "FECHADA")
checar("o saldo do João recebe o lote 1/1 (300) e o 1/2 (100)",
       saldo(a1["id"], joao["id"]) == 300 and saldo(a1["id"], joao["id"], "1/2") == 100)
lotes = {l["codigo"]: l for l in api("GET", f"/api/wms/lotes?empresa_id={eid}", None, tk)}
checar("os lotes foram gerados", set(lotes) == {"1/1", "1/2"})
pos = lotes["1/1"]["posicoes"]
checar("com as posições: quadra e pilha",
       [(p["quadra_nome"], p["pilha"], p["sacas"]) for p in pos]
       == [("A1", "P1", 200), ("A2", "P2", 100)], str([(p["quadra_nome"], p["pilha"]) for p in pos]))
checar("local sem peso recebe o peso proporcional (12.000 + 6.000)",
       [p["peso"] for p in pos] == [12000, 6000], str([p["peso"] for p in pos]))
checar("o lote guarda peneira e padrão",
       lotes["1/1"]["peneira"] == "17/18" and lotes["1/1"]["padrao"] == "Tipo 6 bebida dura")
quadras_a1 = {q["nome"]: q for q in
              api("GET", f"/api/wms/quadras?empresa_id={eid}&armazem_id={a1['id']}", None, tk)}
checar("a quadra mostra as sacas que entraram nela", quadras_a1["A1"]["sacas_na_entrada"] == 300)

fechada = api("PUT", f"/api/wms/guias-entrada/{g1['id']}", guia_dados, tk, esperar_erro=True)
checar("guia fechada não se edita", fechada.get("_status") == 400)
direta = lancar("ENTRADA", sacas=10, esperar_erro=True)
checar("entrada solta (sem guia) é recusada", direta.get("_status") == 400)
mov_guia = api("GET", f"/api/wms/movimentos?empresa_id={eid}&tipo=ENTRADA", None, tk)["movimentos"]
nao_cancela = api("POST", f"/api/wms/movimentos/{mov_guia[0]['id']}/cancelar", {"motivo": "x"},
                  tk, esperar_erro=True)
checar("a entrada da guia não se cancela pela lista de movimentos",
       nao_cancela.get("_status") == 400)

g2 = api("POST", "/api/wms/guias-entrada", {
    "empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"], "sacas": 10,
    "peso_total": 600, "lotes": [{"sacas": 10, "peso": 600,
                                  "locais": [{"quadra_id": qb1["id"], "sacas": 10}]}]}, tk)
outra = api("POST", f"/api/wms/guias-entrada/{g2['id']}/fechar", None, tk, esperar_erro=True)
checar("quadra de outro armazém impede o fechamento",
       outra.get("_status") == 400 and "outro armazém" in str(outra.get("detail")))
sem_motivo = api("POST", f"/api/wms/guias-entrada/{g2['id']}/cancelar", {"motivo": ""}, tk,
                 esperar_erro=True)
checar("cancelar guia pede motivo", sem_motivo.get("_status") == 400)
api("POST", f"/api/wms/guias-entrada/{g2['id']}/cancelar", {"motivo": "quadra errada"}, tk)
lista = api("GET", f"/api/wms/guias-entrada?empresa_id={eid}", None, tk)
checar("a lista de guias esconde a cancelada e soma as sacas",
       lista["resumo"]["guias"] == 1 and lista["resumo"]["sacas"] == 400, str(lista["resumo"]))

# =========================================================================== #
print("\n=== 3b. Saídas ===")
s1 = lancar("SAIDA", sacas=50, peso_kg=3000)
checar("saída tem a própria numeração (nº 1)", s1.get("numero") == 1)
checar("saldo do lote 1/1 caiu para 250", saldo(a1["id"], joao["id"]) == 250)
demais = lancar("SAIDA", sacas=999, esperar_erro=True)
checar("saída maior que o saldo é recusada", demais.get("_status") == 400,
       str(demais.get("detail"))[:90])
checar("e a frase diz quanto ele tem", "250,00" in str(demais.get("detail")))
outro_lote = lancar("SAIDA", sacas=1, lote="L9", esperar_erro=True)
checar("saída de lote que ele não tem é recusada", outro_lote.get("_status") == 400)

# =========================================================================== #
print("\n=== 4. Serviço ===")
sv = lancar("SERVICO", servico="Rebenefício", sacas=100, valor=850)
checar("serviço lançado", sv.get("servico") == "Rebenefício" and sv.get("valor") == 850)
checar("e não mexe no saldo", saldo(a1["id"], joao["id"]) == 250)
sem_servico = lancar("SERVICO", sacas=10, esperar_erro=True)
checar("serviço sem nome é recusado", sem_servico.get("_status") == 400)
lista = api("GET", f"/api/wms/movimentos?empresa_id={eid}&tipo=SERVICO", None, tk)
checar("a lista de serviços soma o valor", lista["resumo"]["valor"] == 850)

# =========================================================================== #
print("\n=== 5. Transferência (troca de dono) ===")
tr = lancar("TRANSFERENCIA", sacas=120, depositante_destino_id=maria["id"])
checar("transferência lançada", tr.get("depositante_destino_nome") == "Maria Exportadora")
checar("sem peso digitado, sai o peso médio da saca do lote (60 kg x 120)",
       tr.get("peso_kg") == 7200, str(tr.get("peso_kg")))
checar("João ficou com 130", saldo(a1["id"], joao["id"]) == 130)
checar("Maria ficou com 120 no mesmo armazém", saldo(a1["id"], maria["id"]) == 120)
mesmo = lancar("TRANSFERENCIA", sacas=1, depositante_destino_id=joao["id"], esperar_erro=True)
checar("transferir para ele mesmo é recusado", mesmo.get("_status") == 400)

# =========================================================================== #
print("\n=== 6. Remoção (troca de armazém) ===")
rm = api("POST", "/api/wms/movimentos", {
    "empresa_id": eid, "tipo": "REMOCAO", "armazem_id": a1["id"], "armazem_destino_id": a2["id"],
    "depositante_id": maria["id"], "lote": "1/1", "sacas": 70}, tk)
checar("remoção lançada", rm.get("armazem_destino_nome") == "Galpão 2")
checar("Maria ficou com 50 no Central", saldo(a1["id"], maria["id"]) == 50)
checar("e 70 no Galpão 2", saldo(a2["id"], maria["id"]) == 70)
mesmo_arm = api("POST", "/api/wms/movimentos", {
    "empresa_id": eid, "tipo": "REMOCAO", "armazem_id": a1["id"], "armazem_destino_id": a1["id"],
    "depositante_id": maria["id"], "lote": "1/1", "sacas": 1}, tk, esperar_erro=True)
checar("remoção para o mesmo armazém é recusada", mesmo_arm.get("_status") == 400)

armazens = {a["id"]: a for a in api("GET", f"/api/wms/armazens?empresa_id={eid}", None, tk)}
checar("o armazém mostra quanto está guardado",
       armazens[a1["id"]]["sacas_guardadas"] == 280, str(armazens[a1["id"]]["sacas_guardadas"]))
checar("e a ocupação", armazens[a2["id"]]["ocupacao"] == 1.4, str(armazens[a2["id"]]["ocupacao"]))

# =========================================================================== #
print("\n=== 7. Cancelamento ===")
sem_motivo = api("POST", f"/api/wms/movimentos/{s1['id']}/cancelar", {"motivo": ""}, tk,
                 esperar_erro=True)
checar("cancelar sem motivo é recusado", sem_motivo.get("_status") == 400)
api("POST", f"/api/wms/movimentos/{s1['id']}/cancelar", {"motivo": "lançada em dobro"}, tk)
checar("cancelar a saída devolve o saldo (130 -> 180)", saldo(a1["id"], joao["id"]) == 180)
# tira 150 do lote 1/1: agora a guia 1 não pode mais ser reaberta,
# senão o saldo do João no lote ficaria negativo (30 - 300 < 0)
lancar("SAIDA", sacas=150)
nao_da = api("POST", f"/api/wms/guias-entrada/{g1['id']}/reabrir", None, tk, esperar_erro=True)
checar("reabrir guia cujo café já saiu é recusado", nao_da.get("_status") == 400,
       str(nao_da.get("detail"))[:80])

g3 = api("POST", "/api/wms/guias-entrada", {
    "empresa_id": eid, "armazem_id": a2["id"], "cliente_id": maria["id"], "sacas": 20,
    "peso_total": 1200, "lotes": [{"sacas": 20, "peso": 1200,
                                   "locais": [{"quadra_id": qb1["id"], "sacas": 20}]}]}, tk)
api("POST", f"/api/wms/guias-entrada/{g3['id']}/fechar", None, tk)
checar("a guia 3 entrou no saldo (lote 3/1)", saldo(a2["id"], maria["id"], "3/1") == 20)
g3 = api("POST", f"/api/wms/guias-entrada/{g3['id']}/reabrir", None, tk)
checar("guia sem saída reabre", g3.get("status") == "ABERTA")
checar("e o saldo e os lotes dela somem",
       saldo(a2["id"], maria["id"], "3/1") == 0
       and not api("GET", f"/api/wms/lotes?empresa_id={eid}&guia_id={g3['id']}", None, tk))
padrao = api("GET", f"/api/wms/movimentos?empresa_id={eid}&tipo=SAIDA", None, tk)
checar("a lista esconde os cancelados", all(m["status"] == "ATIVO" for m in padrao["movimentos"]))
todos = api("GET", f"/api/wms/movimentos?empresa_id={eid}&tipo=SAIDA&mostrar_cancelados=true",
            None, tk)
checar("e mostra quando pedido", any(m["status"] == "CANCELADO" for m in todos["movimentos"]))

# =========================================================================== #
print("\n=== 8. Isolamento entre contas ===")
tk2, eid2 = conta("P4_SEMESTRAL")
alheio = api("GET", f"/api/wms/guias-entrada?empresa_id={eid}", None, tk2,
             esperar_erro=True)
checar("outra conta não lê o armazém desta", alheio.get("_status") == 403)
alheio2 = api("POST", f"/api/wms/movimentos/{s1['id']}/cancelar", {"motivo": "x"}, tk2,
              esperar_erro=True)
checar("nem cancela lançamento dela", alheio2.get("_status") == 403)

# =========================================================================== #
print("\n=== 9. Quem já tinha o sistema ganha o WMS no Plano 4 ===")
# roda direto no motor, num banco de memória: a grade de fábrica antiga do
# Plano 4 vira a nova; a grade montada à mão pelo administrador fica como está
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend import assinaturas  # noqa: E402
from backend.database import Base  # noqa: E402
from backend.models import Configuracao  # noqa: E402

for antes, esperado, rotulo in (
    ("CONTRATOS,FINANCEIRO,NFE,CUPOM,GTA", "CONTRATOS,FINANCEIRO,NFE,CUPOM,GTA,WMS",
     "grade de fábrica antiga recebe o WMS"),
    ("CONTRATOS,FINANCEIRO,NFE,GTA", "CONTRATOS,FINANCEIRO,NFE,GTA",
     "grade montada à mão não é mexida"),
):
    motor = create_engine("sqlite://")
    Base.metadata.create_all(motor)
    db = sessionmaker(bind=motor)()
    db.add(Configuracao(chave="plano4_modulos", valor=antes, publica=True))
    db.commit()
    assinaturas.garantir_configuracoes(db)
    db.commit()
    depois = db.query(Configuracao).filter_by(chave="plano4_modulos").one().valor
    checar(rotulo, depois == esperado, depois)
    db.close()

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print("  -", e)
    sys.exit(1)
print("WMS OK — entrada, saída, serviço, transferência e remoção batem no saldo.")
