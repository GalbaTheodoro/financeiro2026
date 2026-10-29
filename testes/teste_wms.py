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
  * guia de saída: cliente, destino e contrato de venda; escolhe lote e
    posição (quadra/pilha), com saída parcial; não passa do que a pilha tem
    nem do saldo do lote; fechar tira do saldo, reabrir devolve;
  * saída tira do saldo — e é recusada quando passa do que ele tem;
  * serviço registra nome e valor sem mexer no saldo;
  * guia de transferência: cliente e cliente novo, escolhe lote e posição
    (parcial); fechar gera o lote novo com "T" no fim ("1/1T", "1/1T2"...),
    nas mesmas quadras e pilhas; reabrir só se o lote novo não saiu;
  * remoção: escolhe o lote, vê os locais e muda de quadra/pilha (parcial);
    outro armazém só com o lote inteiro (o saldo vai junto); estorno da
    última; histórico do lote com entrada, remoções, saídas e transferências;
  * cada tipo tem a sua numeração;
  * tela de lotes: saldo, posições, de onde veio; Classificar cria (uma vez
    só) a amostra do lote já preenchida, e reabrir/fechar a guia religa;
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


ROTAS_WMS = {"/wms-lotes", "/wms-entradas", "/wms-saidas", "/wms-servicos", "/wms-transferencias",
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
checar("Plano 4: o menu traz as seis telas do WMS", ROTAS_WMS <= rotas)
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
checar("a quadra mostra as sacas que entraram nela", quadras_a1["A1"]["sacas_atuais"] == 300)

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
print("\n=== 3b. Guia de saída ===")
venda = api("POST", "/api/contratos", {"empresa_id": eid, "tipo": "VENDA",
                                       "comprador_id": maria["id"], "quantidade": 100,
                                       "preco_unitario": 1600, "local_descarga": "Santos/SP"}, tk)
contratos_saida = api("GET", f"/api/wms/contratos-saida?empresa_id={eid}", None, tk)
checar("o contrato de venda aparece para a saída",
       any(c["id"] == venda["id"] for c in contratos_saida))
disp = api("GET", f"/api/wms/posicoes-disponiveis?empresa_id={eid}&armazem_id={a1['id']}"
                  f"&cliente_id={joao['id']}", None, tk)
pos = {(d["lote_codigo"], d["quadra_nome"], d["pilha"]): d for d in disp}
checar("o cliente vê os lotes e as posições com o que tem em cada uma",
       pos[("1/1", "A1", "P1")]["sacas_disponiveis"] == 200
       and pos[("1/1", "A2", "P2")]["sacas_disponiveis"] == 100
       and pos[("1/2", "A1", "P3")]["sacas_disponiveis"] == 100, str(list(pos)))
p_a1 = pos[("1/1", "A1", "P1")]["posicao_id"]
p_a2 = pos[("1/1", "A2", "P2")]["posicao_id"]

gs1 = api("POST", "/api/wms/guias-saida", {
    "empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
    "destinatario_id": maria["id"], "destino": "Santos/SP", "contrato_id": venda["id"],
    "placa": "xyz9a88", "itens": [{"posicao_id": p_a1, "sacas": 50}, {"posicao_id": p_a2, "sacas": 0}]}, tk)
checar("guia de saída criada aberta, nº 1, com o item zerado ignorado",
       gs1.get("numero") == 1 and gs1.get("status") == "ABERTA" and len(gs1["itens"]) == 1)
checar("guia aberta ainda não tira do saldo", saldo(a1["id"], joao["id"]) == 300)
gs1 = api("POST", f"/api/wms/guias-saida/{gs1['id']}/fechar", None, tk)
checar("fecha a guia de saída", gs1.get("status") == "FECHADA")
checar("saída parcial: o saldo do lote 1/1 caiu para 250", saldo(a1["id"], joao["id"]) == 250)
checar("sem peso digitado, leva o peso médio da pilha (50 x 60 = 3.000)",
       gs1["itens"][0]["peso"] == 3000, str(gs1["itens"][0]["peso"]))
disp = api("GET", f"/api/wms/posicoes-disponiveis?empresa_id={eid}&armazem_id={a1['id']}"
                  f"&cliente_id={joao['id']}", None, tk)
checar("e a pilha P1 da quadra A1 ficou com 150",
       next(d for d in disp if d["posicao_id"] == p_a1)["sacas_disponiveis"] == 150)
quadras_a1 = {q["nome"]: q for q in
              api("GET", f"/api/wms/quadras?empresa_id={eid}&armazem_id={a1['id']}", None, tk)}
checar("a quadra A1 mostra as sacas de hoje (300 - 50)", quadras_a1["A1"]["sacas_atuais"] == 250)
checar("o contrato soma o embarcado",
       next(c for c in api("GET", f"/api/wms/contratos-saida?empresa_id={eid}", None, tk)
            if c["id"] == venda["id"])["sacas_embarcadas"] == 50)

gs2 = api("POST", "/api/wms/guias-saida", {
    "empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
    "itens": [{"posicao_id": p_a2, "sacas": 150}]}, tk)
demais = api("POST", f"/api/wms/guias-saida/{gs2['id']}/fechar", None, tk, esperar_erro=True)
checar("tirar da pilha mais do que tem é recusado",
       demais.get("_status") == 400 and "restam 100,00" in str(demais.get("detail")),
       str(demais.get("detail"))[:100])
de_outro = api("POST", "/api/wms/guias-saida", {
    "empresa_id": eid, "armazem_id": a1["id"], "cliente_id": maria["id"],
    "itens": [{"posicao_id": p_a2, "sacas": 10}]}, tk)
nao_e_dele = api("POST", f"/api/wms/guias-saida/{de_outro['id']}/fechar", None, tk,
                 esperar_erro=True)
checar("lote de outro cliente não sai na guia", nao_e_dele.get("_status") == 400)
for g in (gs2, de_outro):
    api("POST", f"/api/wms/guias-saida/{g['id']}/cancelar", {"motivo": "teste"}, tk)
lista_s = api("GET", f"/api/wms/guias-saida?empresa_id={eid}", None, tk)
checar("a lista de guias de saída esconde as canceladas e soma as sacas",
       lista_s["resumo"]["guias"] == 1 and lista_s["resumo"]["sacas"] == 50, str(lista_s["resumo"]))
direta = lancar("SAIDA", sacas=1, esperar_erro=True)
checar("saída solta (sem guia) é recusada", direta.get("_status") == 400)

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
print("\n=== 5. Guia de transferência (troca de dono) ===")
TR = "/api/wms/guias-transferencia"
mesmo = api("POST", TR, {"empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
                         "cliente_novo_id": joao["id"]}, tk, esperar_erro=True)
checar("transferir para o mesmo cliente é recusado", mesmo.get("_status") == 400)
direta = lancar("TRANSFERENCIA", sacas=1, depositante_destino_id=maria["id"], esperar_erro=True)
checar("transferência solta (sem guia) é recusada", direta.get("_status") == 400)

gt1 = api("POST", TR, {
    "empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
    "cliente_novo_id": maria["id"], "documento": "Contrato 45",
    "itens": [{"posicao_id": p_a1, "sacas": 80}, {"posicao_id": p_a2, "sacas": 40}]}, tk)
checar("guia de transferência criada aberta, nº 1",
       gt1.get("numero") == 1 and gt1.get("status") == "ABERTA" and len(gt1["itens"]) == 2)
checar("guia aberta ainda não mexe no saldo", saldo(a1["id"], joao["id"]) == 250)
gt1 = api("POST", f"{TR}/{gt1['id']}/fechar", None, tk)
checar("fecha a guia de transferência", gt1.get("status") == "FECHADA")
checar("gera o lote novo com T no fim do número de origem", gt1.get("lotes_novos") == ["1/1T"],
       str(gt1.get("lotes_novos")))
checar("sem peso digitado, leva o peso médio da pilha (4.800 + 2.400)",
       sorted(i["peso"] for i in gt1["itens"]) == [2400, 4800], str([i["peso"] for i in gt1["itens"]]))
checar("João ficou com 130 no lote 1/1", saldo(a1["id"], joao["id"]) == 130)
checar("Maria ficou com 120 no lote 1/1T", saldo(a1["id"], maria["id"], "1/1T") == 120)
lotes_agora = api("GET", f"/api/wms/lotes?empresa_id={eid}", None, tk)
lote_t = next(l for l in lotes_agora if l["codigo"] == "1/1T")
l11_id = next(l["id"] for l in lotes_agora if l["codigo"] == "1/1")
checar("o lote novo é da Maria, com peneira e padrão do de origem",
       lote_t["depositante_nome"] == "Maria Exportadora" and lote_t["peneira"] == "17/18")
checar("e fica nas mesmas quadras e pilhas",
       sorted((p_["quadra_nome"], p_["pilha"], p_["sacas"]) for p_ in lote_t["posicoes"])
       == [("A1", "P1", 80), ("A2", "P2", 40)])
disp = api("GET", f"/api/wms/posicoes-disponiveis?empresa_id={eid}&armazem_id={a1['id']}"
                  f"&cliente_id={joao['id']}", None, tk)
checar("a pilha de origem perde as sacas transferidas (A1/P1: 150 -> 70)",
       next(d for d in disp if d["posicao_id"] == p_a1)["sacas_disponiveis"] == 70)
quadras_a1 = {q["nome"]: q for q in
              api("GET", f"/api/wms/quadras?empresa_id={eid}&armazem_id={a1['id']}", None, tk)}
checar("a quadra continua com o mesmo café (só mudou o dono)", quadras_a1["A1"]["sacas_atuais"] == 250)

gt2 = api("POST", TR, {"empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
                       "cliente_novo_id": maria["id"], "itens": [{"posicao_id": p_a1, "sacas": 10}]}, tk)
gt2 = api("POST", f"{TR}/{gt2['id']}/fechar", None, tk)
checar("transferir de novo do mesmo lote não repete o número (1/1T2)",
       gt2.get("lotes_novos") == ["1/1T2"], str(gt2.get("lotes_novos")))
gt2 = api("POST", f"{TR}/{gt2['id']}/reabrir", None, tk)
checar("reabrir desfaz: lote novo some e o saldo volta",
       gt2.get("status") == "ABERTA" and saldo(a1["id"], maria["id"], "1/1T2") == 0
       and saldo(a1["id"], joao["id"]) == 130)
api("POST", f"{TR}/{gt2['id']}/cancelar", {"motivo": "teste"}, tk)
demais = api("POST", TR, {"empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
                          "cliente_novo_id": maria["id"], "itens": [{"posicao_id": p_a2, "sacas": 61}]}, tk)
nao = api("POST", f"{TR}/{demais['id']}/fechar", None, tk, esperar_erro=True)
checar("não transfere mais do que a pilha tem (A2/P2: restam 60)",
       nao.get("_status") == 400 and "restam 60,00" in str(nao.get("detail")), str(nao.get("detail"))[:100])
api("POST", f"{TR}/{demais['id']}/cancelar", {"motivo": "teste"}, tk)
lista_t = api("GET", f"{TR}?empresa_id={eid}", None, tk)
checar("a lista de transferências esconde as canceladas",
       lista_t["resumo"]["guias"] == 1 and lista_t["resumo"]["sacas"] == 120, str(lista_t["resumo"]))

# =========================================================================== #
print("\n=== 6. Remoção (mudança de local, com histórico) ===")
qa3 = api("POST", "/api/wms/quadras", {"empresa_id": eid, "armazem_id": a1["id"], "nome": "A3",
                                       "x": 3, "y": 1}, tk)
loc = api("GET", f"/api/wms/lotes/{lote_t['id']}/locais", None, tk)
checar("escolhendo o lote aparecem todos os locais dele",
       sorted((p_["quadra_nome"], p_["pilha"], p_["sacas_disponiveis"]) for p_ in loc["posicoes"])
       == [("A1", "P1", 80), ("A2", "P2", 40)] and loc["total_sacas"] == 120)
pos_a1t = next(p_["posicao_id"] for p_ in loc["posicoes"] if p_["quadra_nome"] == "A1")
pos_a2t = next(p_["posicao_id"] for p_ in loc["posicoes"] if p_["quadra_nome"] == "A2")
RM = "/api/wms/remocoes"
velha = api("POST", "/api/wms/movimentos", {
    "empresa_id": eid, "tipo": "REMOCAO", "armazem_id": a1["id"], "armazem_destino_id": a2["id"],
    "depositante_id": maria["id"], "lote": "1/1T", "sacas": 1}, tk, esperar_erro=True)
checar("remoção solta (sem a tela de remoção) é recusada", velha.get("_status") == 400)
mesmo_local = api("POST", RM, {"empresa_id": eid, "lote_id": lote_t["id"], "itens": [
    {"posicao_id": pos_a1t, "sacas": 5, "quadra_destino_id": qa1["id"], "pilha_destino": "p1"}]},
    tk, esperar_erro=True)
checar("mudar para o mesmo local é recusado", mesmo_local.get("_status") == 400)
demais = api("POST", RM, {"empresa_id": eid, "lote_id": lote_t["id"], "itens": [
    {"posicao_id": pos_a1t, "sacas": 81, "quadra_destino_id": qa3["id"]}]}, tk, esperar_erro=True)
checar("levar mais do que tem no local é recusado",
       demais.get("_status") == 400 and "restam 80,00" in str(demais.get("detail")))
rm1 = api("POST", RM, {"empresa_id": eid, "lote_id": lote_t["id"], "observacao": "arrumação",
                       "itens": [{"posicao_id": pos_a1t, "sacas": 30, "quadra_destino_id": qa3["id"],
                                  "pilha_destino": "p9"}]}, tk)
checar("remoção parcial feita (nº 1), A1/P1 → A3/P9",
       rm1.get("numero") == 1 and rm1["itens"][0]["de"] == "A1/P1" and rm1["itens"][0]["para"] == "A3/P9")
checar("sem peso digitado, leva o peso médio do local (30 x 60 = 1.800)",
       rm1["itens"][0]["peso"] == 1800, str(rm1["itens"][0]["peso"]))
loc = api("GET", f"/api/wms/lotes/{lote_t['id']}/locais", None, tk)
checar("os locais do lote mudaram (A1/P1 50, A2/P2 40, A3/P9 30)",
       sorted((p_["quadra_nome"], p_["pilha"], p_["sacas_disponiveis"]) for p_ in loc["posicoes"])
       == [("A1", "P1", 50), ("A2", "P2", 40), ("A3", "P9", 30)], str(loc["posicoes"]))
checar("o saldo do lote não muda (só o lugar)", saldo(a1["id"], maria["id"], "1/1T") == 120)
pos_a3t = next(p_["posicao_id"] for p_ in loc["posicoes"] if p_["quadra_nome"] == "A3")
parcial_outro = api("POST", RM, {"empresa_id": eid, "lote_id": lote_t["id"], "armazem_destino_id": a2["id"],
                                 "itens": [{"posicao_id": pos_a3t, "sacas": 30, "quadra_destino_id": qb1["id"]}]},
                    tk, esperar_erro=True)
checar("para outro armazém só vai o lote inteiro",
       parcial_outro.get("_status") == 400 and "lote inteiro" in str(parcial_outro.get("detail")))
quadra_errada = api("POST", RM, {"empresa_id": eid, "lote_id": lote_t["id"],
                                 "itens": [{"posicao_id": pos_a3t, "sacas": 1, "quadra_destino_id": qb1["id"]}]},
                    tk, esperar_erro=True)
checar("quadra de outro armazém sem trocar o armazém é recusada", quadra_errada.get("_status") == 400)
rm2 = api("POST", RM, {"empresa_id": eid, "lote_id": lote_t["id"], "armazem_destino_id": a2["id"],
                       "itens": [{"posicao_id": pos_a1t, "sacas": 50, "quadra_destino_id": qb1["id"], "pilha_destino": "P1"},
                                 {"posicao_id": pos_a2t, "sacas": 40, "quadra_destino_id": qb1["id"], "pilha_destino": "P1"},
                                 {"posicao_id": pos_a3t, "sacas": 30, "quadra_destino_id": qb1["id"], "pilha_destino": "P1"}]}, tk)
checar("o lote inteiro vai para o Galpão 2 (remoção nº 2)", rm2.get("armazem_destino_nome") == "Galpão 2")
checar("e o saldo vai junto", saldo(a1["id"], maria["id"], "1/1T") == 0
       and saldo(a2["id"], maria["id"], "1/1T") == 120)
loc = api("GET", f"/api/wms/lotes/{lote_t['id']}/locais", None, tk)
checar("tudo junto na quadra B1/P1", [(p_["quadra_nome"], p_["pilha"], p_["sacas_disponiveis"])
                                      for p_ in loc["posicoes"]] == [("B1", "P1", 120)], str(loc["posicoes"]))
nao = api("POST", f"{RM}/{rm1['id']}/estornar", None, tk, esperar_erro=True)
checar("só estorna a última remoção do lote", nao.get("_status") == 400)
lista_rm = api("GET", f"{RM}?empresa_id={eid}", None, tk)
checar("a lista diz qual pode estornar",
       [r["pode_estornar"] for r in lista_rm["remocoes"]] == [True, False])
api("POST", f"{RM}/{rm2['id']}/estornar", None, tk)
checar("estornar devolve o lote ao Central, nos locais de antes",
       saldo(a1["id"], maria["id"], "1/1T") == 120 and sorted(
           (p_["quadra_nome"], p_["sacas_disponiveis"]) for p_ in
           api("GET", f"/api/wms/lotes/{lote_t['id']}/locais", None, tk)["posicoes"])
       == [("A1", 50), ("A2", 40), ("A3", 30)])
hist = api("GET", f"/api/wms/lotes/{lote_t['id']}/historico", None, tk)
tipos = [e["tipo"] for e in hist["eventos"]]
checar("o histórico do lote guarda tudo: recebido, remoção 1 e remoção 2 (estornada)",
       tipos[:3] == ["TRANSFERENCIA_RECEBIDA", "REMOCAO", "REMOCAO"]
       and hist["eventos"][2]["situacao"] == "ESTORNADA", str(tipos))
checar("com de onde para onde", "A1/P1 → A3/P9" in hist["eventos"][1]["detalhe"])
hist11 = api("GET", f"/api/wms/lotes/{l11_id}/historico", None, tk)
checar("o lote de origem mostra a entrada, a saída e a transferência",
       {"ENTRADA", "SAIDA", "TRANSFERENCIA_ENVIADA"} <= {e["tipo"] for e in hist11["eventos"]},
       str([e["tipo"] for e in hist11["eventos"]]))

armazens = {a["id"]: a for a in api("GET", f"/api/wms/armazens?empresa_id={eid}", None, tk)}
checar("o armazém mostra quanto está guardado (130 + 100 + 120)",
       armazens[a1["id"]]["sacas_guardadas"] == 350, str(armazens[a1["id"]]["sacas_guardadas"]))
checar("e a ocupação", armazens[a1["id"]]["ocupacao"] == 3.5, str(armazens[a1["id"]]["ocupacao"]))

# =========================================================================== #
print("\n=== 7. Cancelamento ===")
sem_motivo = api("POST", f"/api/wms/movimentos/{sv['id']}/cancelar", {"motivo": ""}, tk,
                 esperar_erro=True)
checar("cancelar sem motivo é recusado", sem_motivo.get("_status") == 400)
api("POST", f"/api/wms/guias-saida/{gs1['id']}/reabrir", None, tk)
checar("reabrir a guia de saída devolve o saldo (130 -> 180)", saldo(a1["id"], joao["id"]) == 180)
# as pilhas do 1/1 somam 300, mas uma transferência levou 120 para a Maria:
# o saldo do João no lote (180) é quem manda
gs3 = api("POST", "/api/wms/guias-saida", {
    "empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
    "itens": [{"posicao_id": p_a1, "sacas": 150}, {"posicao_id": p_a2, "sacas": 50}]}, tk)
alem = api("POST", f"/api/wms/guias-saida/{gs3['id']}/fechar", None, tk, esperar_erro=True)
checar("a guia não tira do lote mais do que o cliente tem no saldo",
       alem.get("_status") == 400 and "180,00" in str(alem.get("detail")), str(alem.get("detail"))[:120])
api("PUT", f"/api/wms/guias-saida/{gs3['id']}", {
    "empresa_id": eid, "armazem_id": a1["id"], "cliente_id": joao["id"],
    "itens": [{"posicao_id": p_a1, "sacas": 120}, {"posicao_id": p_a2, "sacas": 30}]}, tk)
api("POST", f"/api/wms/guias-saida/{gs3['id']}/fechar", None, tk)
checar("com 150 fecha (sobram 30 no lote)", saldo(a1["id"], joao["id"]) == 30)
nao_da = api("POST", f"/api/wms/guias-entrada/{g1['id']}/reabrir", None, tk, esperar_erro=True)
checar("reabrir guia cujo café já saiu é recusado", nao_da.get("_status") == 400,
       str(nao_da.get("detail"))[:80])

g3 = api("POST", "/api/wms/guias-entrada", {
    "empresa_id": eid, "armazem_id": a2["id"], "cliente_id": maria["id"], "sacas": 20,
    "peso_total": 1200, "lotes": [{"sacas": 20, "peso": 1200,
                                   "locais": [{"quadra_id": qb1["id"], "sacas": 20}]}]}, tk)
api("POST", f"/api/wms/guias-entrada/{g3['id']}/fechar", None, tk)
checar("a guia 3 entrou no saldo (lote 3/1)", saldo(a2["id"], maria["id"], "3/1") == 20)
lote31 = next(l for l in api("GET", f"/api/wms/lotes?empresa_id={eid}&guia_id={g3['id']}", None, tk))
am31 = api("POST", f"/api/wms/lotes/{lote31['id']}/amostra", None, tk)
g3 = api("POST", f"/api/wms/guias-entrada/{g3['id']}/reabrir", None, tk)
checar("guia sem saída reabre", g3.get("status") == "ABERTA")
checar("e o saldo e os lotes dela somem",
       saldo(a2["id"], maria["id"], "3/1") == 0
       and not api("GET", f"/api/wms/lotes?empresa_id={eid}&guia_id={g3['id']}", None, tk))
checar("a amostra do lote continua, solta do lote enquanto a guia está aberta",
       api("GET", f"/api/amostras/{am31['amostra_id']}", None, tk).get("lote_armazem_id") is None)
api("POST", f"/api/wms/guias-entrada/{g3['id']}/fechar", None, tk)
lote31 = next(l for l in api("GET", f"/api/wms/lotes?empresa_id={eid}&guia_id={g3['id']}", None, tk))
checar("fechando de novo, o lote 3/1 recupera a amostra dele",
       (lote31.get("amostra") or {}).get("id") == am31["amostra_id"])
# o lote novo da Maria saiu numa guia de saída: a transferência não reabre mais
pos_t = {(p_["quadra_nome"]): p_["id"] for p_ in lote_t["posicoes"]}
gsm = api("POST", "/api/wms/guias-saida", {"empresa_id": eid, "armazem_id": a1["id"],
                                           "cliente_id": maria["id"],
                                           "itens": [{"posicao_id": pos_t["A1"], "sacas": 10}]}, tk)
gsm = api("POST", f"/api/wms/guias-saida/{gsm['id']}/fechar", None, tk)
checar("o lote 1/1T sai pela guia de saída da Maria", saldo(a1["id"], maria["id"], "1/1T") == 110)
nao_reabre = api("POST", f"{TR}/{gt1['id']}/reabrir", None, tk, esperar_erro=True)
checar("transferência cujo lote novo já saiu não reabre",
       nao_reabre.get("_status") == 400)
nao_cancela = api("POST", f"/api/wms/guias-saida/{gs3['id']}/cancelar", {"motivo": "x"}, tk,
                  esperar_erro=True)
checar("guia de saída fechada não se cancela sem reabrir", nao_cancela.get("_status") == 400)

# =========================================================================== #
print("\n=== 7b. Tela de lotes e amostra do lote ===")
todos = api("GET", f"/api/wms/lotes?empresa_id={eid}", None, tk)
com = api("GET", f"/api/wms/lotes?empresa_id={eid}&com_saldo=true", None, tk)
checar("o filtro 'só com saldo' só traz lote com saldo",
       len(com) <= len(todos) and all(l["saldo_total"] > 0 for l in com))
achou = api("GET", f"/api/wms/lotes?empresa_id={eid}&busca=1/1T", None, tk)
checar("procurar pelo número do lote", {l["codigo"] for l in achou} == {"1/1T"}, str([l["codigo"] for l in achou]))
l11 = next(l for l in todos if l["codigo"] == "1/1")
checar("o lote mostra de que guia veio e o lote transferido de onde veio",
       l11["guia_numero"] == 1 and next(l for l in todos if l["codigo"] == "1/1T")["lote_origem_codigo"] == "1/1")
checar("lote ainda sem amostra", l11["amostra"] is None)
am = api("POST", f"/api/wms/lotes/{l11['id']}/amostra", None, tk)
checar("Classificar cria a amostra do lote", am.get("nova") is True and am.get("amostra_id"))
ficha = api("GET", f"/api/amostras/{am['amostra_id']}", None, tk)
checar("a amostra já vem com o dono, o lote, as sacas e o armazém",
       ficha["lote"] == "1/1" and ficha["parceiro_id"] == joao["id"] and ficha["sacas"] == 300
       and ficha["armazem"] == "Armazém Central" and ficha["lote_armazem_id"] == l11["id"],
       str({k: ficha.get(k) for k in ("lote", "parceiro_id", "sacas", "armazem")}))
de_novo = api("POST", f"/api/wms/lotes/{l11['id']}/amostra", None, tk)
checar("cada lote tem uma amostra só (clicar de novo abre a mesma)",
       de_novo.get("nova") is False and de_novo.get("amostra_id") == am["amostra_id"])
l11 = next(l for l in api("GET", f"/api/wms/lotes?empresa_id={eid}", None, tk) if l["codigo"] == "1/1")
checar("a lista de lotes mostra a amostra", (l11["amostra"] or {}).get("situacao") == "RECEBIDA")

# =========================================================================== #
print("\n=== 8. Isolamento entre contas ===")
tk2, eid2 = conta("P4_SEMESTRAL")
alheio = api("GET", f"/api/wms/guias-entrada?empresa_id={eid}", None, tk2,
             esperar_erro=True)
checar("outra conta não lê o armazém desta", alheio.get("_status") == 403)
alheio2 = api("POST", f"/api/wms/guias-saida/{gs3['id']}/reabrir", None, tk2,
              esperar_erro=True)
checar("nem reabre guia dela", alheio2.get("_status") == 403)
alheio3 = api("POST", f"/api/wms/lotes/{l11['id']}/amostra", None, tk2, esperar_erro=True)
checar("nem cria amostra de lote dela", alheio3.get("_status") == 403)

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
