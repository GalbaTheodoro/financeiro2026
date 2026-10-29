"""Teste do WMS / Armazém (entrada, saídas, serviços, transferências e remoção).

O que se confere
----------------
  * o módulo é **só do Plano 4**: os planos 1, 2 e 3 recebem 403 do servidor,
    com a frase dizendo que está no Plano 4, e o menu deles não traz as rotas;
  * o Plano 4 recebe as cinco rotas do menu;
  * cadastro de armazém;
  * entrada soma no saldo do depositante, por armazém e lote;
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


def lancar(tipo, esperar_erro=False, **campos):
    dados = {"empresa_id": eid, "tipo": tipo, "armazem_id": a1["id"],
             "depositante_id": joao["id"], "lote": "L1", **campos}
    return api("POST", "/api/wms/movimentos", dados, tk, esperar_erro=esperar_erro)


def saldo(armazem, depositante, lote="L1"):
    r = api("GET", f"/api/wms/saldos?empresa_id={eid}", None, tk)
    for s in r["saldos"]:
        if s["armazem_id"] == armazem and s["depositante_id"] == depositante and s["lote"] == lote:
            return s["sacas"]
    return 0.0


# =========================================================================== #
print("\n=== 3. Entrada e saída ===")
e1 = lancar("ENTRADA", sacas=300, peso_kg=18000, documento="NF 123", placa="abc1d23")
checar("entrada lançada com número 1", e1.get("numero") == 1, str(e1.get("numero")))
checar("a placa fica em maiúsculas", e1.get("placa") == "ABC1D23", str(e1.get("placa")))
e2 = lancar("ENTRADA", sacas=100, peso_kg=6000)
checar("a segunda entrada é a número 2", e2.get("numero") == 2)
checar("saldo do João no Central = 400", saldo(a1["id"], joao["id"]) == 400,
       str(saldo(a1["id"], joao["id"])))

s1 = lancar("SAIDA", sacas=50, peso_kg=3000)
checar("saída tem a própria numeração (nº 1)", s1.get("numero") == 1)
checar("saldo caiu para 350", saldo(a1["id"], joao["id"]) == 350)
demais = lancar("SAIDA", sacas=999, esperar_erro=True)
checar("saída maior que o saldo é recusada", demais.get("_status") == 400,
       str(demais.get("detail"))[:90])
checar("e a frase diz quanto ele tem", "350,00" in str(demais.get("detail")))
outro_lote = lancar("SAIDA", sacas=1, lote="L9", esperar_erro=True)
checar("saída de lote que ele não tem é recusada", outro_lote.get("_status") == 400)
zero = lancar("ENTRADA", sacas=0, esperar_erro=True)
checar("entrada sem sacas é recusada", zero.get("_status") == 400)

# =========================================================================== #
print("\n=== 4. Serviço ===")
sv = lancar("SERVICO", servico="Rebenefício", sacas=100, valor=850)
checar("serviço lançado", sv.get("servico") == "Rebenefício" and sv.get("valor") == 850)
checar("e não mexe no saldo", saldo(a1["id"], joao["id"]) == 350)
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
checar("João ficou com 230", saldo(a1["id"], joao["id"]) == 230)
checar("Maria ficou com 120 no mesmo armazém", saldo(a1["id"], maria["id"]) == 120)
mesmo = lancar("TRANSFERENCIA", sacas=1, depositante_destino_id=joao["id"], esperar_erro=True)
checar("transferir para ele mesmo é recusado", mesmo.get("_status") == 400)

# =========================================================================== #
print("\n=== 6. Remoção (troca de armazém) ===")
rm = api("POST", "/api/wms/movimentos", {
    "empresa_id": eid, "tipo": "REMOCAO", "armazem_id": a1["id"], "armazem_destino_id": a2["id"],
    "depositante_id": maria["id"], "lote": "L1", "sacas": 70}, tk)
checar("remoção lançada", rm.get("armazem_destino_nome") == "Galpão 2")
checar("Maria ficou com 50 no Central", saldo(a1["id"], maria["id"]) == 50)
checar("e 70 no Galpão 2", saldo(a2["id"], maria["id"]) == 70)
mesmo_arm = api("POST", "/api/wms/movimentos", {
    "empresa_id": eid, "tipo": "REMOCAO", "armazem_id": a1["id"], "armazem_destino_id": a1["id"],
    "depositante_id": maria["id"], "lote": "L1", "sacas": 1}, tk, esperar_erro=True)
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
checar("cancelar a saída devolve o saldo (230 -> 280)", saldo(a1["id"], joao["id"]) == 280)
# tirar 250 do João: a entrada de 100 (e2) não pode mais ser cancelada,
# senão o saldo dele no lote L1 ficaria negativo (280 - 250 - 100 < 0)
lancar("SAIDA", sacas=250)
nao_da = api("POST", f"/api/wms/movimentos/{e2['id']}/cancelar", {"motivo": "teste"}, tk,
             esperar_erro=True)
checar("cancelar entrada cujo café já saiu é recusado", nao_da.get("_status") == 400,
       str(nao_da.get("detail"))[:80])
padrao = api("GET", f"/api/wms/movimentos?empresa_id={eid}&tipo=SAIDA", None, tk)
checar("a lista esconde os cancelados", all(m["status"] == "ATIVO" for m in padrao["movimentos"]))
todos = api("GET", f"/api/wms/movimentos?empresa_id={eid}&tipo=SAIDA&mostrar_cancelados=true",
            None, tk)
checar("e mostra quando pedido", any(m["status"] == "CANCELADO" for m in todos["movimentos"]))

# =========================================================================== #
print("\n=== 8. Isolamento entre contas ===")
tk2, eid2 = conta("P4_SEMESTRAL")
alheio = api("GET", f"/api/wms/movimentos?empresa_id={eid}&tipo=ENTRADA", None, tk2,
             esperar_erro=True)
checar("outra conta não lê o armazém desta", alheio.get("_status") == 403)
alheio2 = api("POST", f"/api/wms/movimentos/{e1['id']}/cancelar", {"motivo": "x"}, tk2,
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
