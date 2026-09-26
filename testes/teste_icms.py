"""Teste da tabela de ICMS e do ICMS no contrato.

Confere:
  * cadastro da grade UF do vendedor x UF do comprador (x produto), sem repetir linha;
  * geração das alíquotas interestaduais de referência (MG -> SP 12%, MG -> GO 7%);
  * no contrato: MG -> SP busca 12% e calcula o ICMS sobre o valor negociado, sem mexer
    no valor nem na corretagem;
  * a linha do produto vale antes da linha "todos os produtos";
  * alíquota digitada (manual) e volta para a da tabela;
  * par de estados sem alíquota = 0 e parceiro sem UF;
  * o contrato guarda o percentual: mudar a tabela depois não altera o contrato salvo;
  * os dados de impressão trazem o ICMS.

Uso (com o servidor rodando em http://127.0.0.1:8000):  python testes/teste_icms.py
"""
import json
import os
import time
import urllib.error
import urllib.request

BASE = os.getenv("FIN_BASE", "http://127.0.0.1:8000")
falhas = []


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
    except urllib.error.HTTPError as e:
        corpo = json.loads(e.read() or b"{}")
        if esperar_erro:
            return {"_status": e.code, "_detalhe": corpo.get("detail", "")}
        raise AssertionError(f"{metodo} {caminho} -> HTTP {e.code}: {corpo}") from None


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


def classificacao(empresa_id, token):
    """A categoria e a marca padrão da empresa — o produto não salva sem elas."""
    categoria = api("GET", f"/api/categorias-produto?empresa_id={empresa_id}", None, token)
    marca = api("GET", f"/api/marcas-produto?empresa_id={empresa_id}", None, token)
    return {"categoria_id": categoria[0]["id"], "marca_id": marca[0]["id"]}


sufixo = str(int(time.time()))

print("\n=== 1. Preparação ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Corretor ICMS", "email": f"icms{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria ICMS",
})
t = conta["token"]
eid = conta["empresa"]["id"]
vendedor_mg = api("POST", "/api/parceiros", {"empresa_id": eid, "tipo": "CLIENTE", "nome": "FAZENDA PATROCINIO",
                                             "cidade": "Patrocínio", "uf": "MG"}, t)
comprador_sp = api("POST", "/api/parceiros", {"empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO SANTOS",
                                              "cidade": "Santos", "uf": "SP"}, t)
comprador_go = api("POST", "/api/parceiros", {"empresa_id": eid, "tipo": "CLIENTE", "nome": "ARMAZEM GOIANIA",
                                              "cidade": "Goiânia", "uf": "go"}, t)
sem_uf = api("POST", "/api/parceiros", {"empresa_id": eid, "tipo": "CLIENTE", "nome": "SEM ESTADO LTDA"}, t)
produtos = api("GET", f"/api/produtos?empresa_id={eid}", token=t)
if not produtos:
    api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", token=t)
    produtos = api("GET", f"/api/produtos?empresa_id={eid}", token=t)
classes = classificacao(eid, t)
cafe = api("POST", "/api/produtos", {"empresa_id": eid, "codigo": f"CAF{sufixo[-4:]}", "nome": "CAFÉ CRU", **classes}, t)
milho = api("POST", "/api/produtos", {"empresa_id": eid, "codigo": f"MIL{sufixo[-4:]}", "nome": "MILHO", **classes}, t)
checar("parceiros e produtos criados", vendedor_mg["id"] and comprador_sp["id"] and cafe["id"])

print("\n=== 2. Tabela de ICMS ===")
geral = api("POST", "/api/icms", {"empresa_id": eid, "uf_origem": "MG", "uf_destino": "SP", "aliquota": 12,
                                  "observacao": "interestadual"}, t)
checar("linha MG -> SP 12% (todos os produtos)", geral["aliquota"] == 12 and geral["produto_id"] is None
       and geral["regra"] == "MG → SP", str(geral))
repetida = api("POST", "/api/icms", {"empresa_id": eid, "uf_origem": "mg", "uf_destino": "sp", "aliquota": 7},
               t, esperar_erro=True)
checar("mesma linha não repete", repetida.get("_status") == 400, repetida.get("_detalhe", ""))
especifica = api("POST", "/api/icms", {"empresa_id": eid, "uf_origem": "MG", "uf_destino": "SP",
                                       "produto_id": milho["id"], "aliquota": 7}, t)
checar("linha só do milho MG -> SP 7% é aceita", especifica["produto_nome"] == "MILHO")
invalida = api("POST", "/api/icms", {"empresa_id": eid, "uf_origem": "XX", "uf_destino": "SP", "aliquota": 5},
               t, esperar_erro=True)
checar("UF inválida é recusada", invalida.get("_status") == 400)
acima = api("POST", "/api/icms", {"empresa_id": eid, "uf_origem": "MG", "uf_destino": "RJ", "aliquota": 150},
            t, esperar_erro=True)
checar("alíquota acima de 100% é recusada", acima.get("_status") == 400)

gerado = api("POST", "/api/icms/gerar-padrao", {"empresa_id": eid, "uf_origem": "MG", "aliquota_interna": 18}, t)
checar("gerar padrão de MG: 26 novas + interna, MG->SP mantida",
       gerado["criadas"] == 26 and gerado["mantidas"] == 1, gerado["mensagem"])
tabela = {(l["uf_origem"], l["uf_destino"], l["produto_id"]): l for l in api("GET", f"/api/icms?empresa_id={eid}", token=t)}
checar("MG -> GO 7% e MG -> BA 7%", tabela[("MG", "GO", None)]["aliquota"] == 7 and tabela[("MG", "BA", None)]["aliquota"] == 7)
checar("MG -> RJ 12% e MG -> ES 7%", tabela[("MG", "RJ", None)]["aliquota"] == 12 and tabela[("MG", "ES", None)]["aliquota"] == 7)
checar("MG -> MG interna 18%", tabela[("MG", "MG", None)]["aliquota"] == 18)
checar("MG -> SP manual continuou com a observação", tabela[("MG", "SP", None)]["observacao"] == "interestadual")
consulta = api("GET", f"/api/icms/aliquota?empresa_id={eid}&uf_origem=MG&uf_destino=SP&produto_id={milho['id']}", token=t)
checar("consulta: milho usa a linha do produto (7%)", consulta["aliquota"] == 7)

print("\n=== 3. ICMS no contrato ===")
base = {
    "empresa_id": eid, "vendedor_id": vendedor_mg["id"], "comprador_id": comprador_sp["id"],
    "produto_id": cafe["id"], "quantidade": 330, "preco_unitario": 1320,
    "comissao_comprador_percentual": 0.5, "comissao_vendedor_percentual": 0.5,
}
c1 = api("POST", "/api/contratos", base, t)
checar("MG -> SP café: 12% da tabela", c1["icms_percentual"] == 12 and c1["icms_manual"] is False, str(c1["icms_percentual"]))
checar("ICMS = 435.600,00 x 12% = 52.272,00", c1["icms_valor"] == 52272.0, str(c1["icms_valor"]))
checar("valor negociado e corretagem não mudam",
       c1["valor_total"] == 435600.0 and c1["comissao_comprador_valor"] == 2178.0)
checar("contrato guarda as UFs", c1["icms_uf_origem"] == "MG" and c1["icms_uf_destino"] == "SP"
       and c1["icms_regra"] == "MG → SP")

c2 = api("POST", "/api/contratos", {**base, "produto_id": milho["id"]}, t)
checar("MG -> SP milho: linha do produto (7%)", c2["icms_percentual"] == 7 and c2["icms_valor"] == 30492.0, str(c2["icms_valor"]))

c3 = api("POST", "/api/contratos", {**base, "comprador_id": comprador_go["id"]}, t)
checar("MG -> GO (UF digitada em minúsculas): 7%", c3["icms_percentual"] == 7 and c3["icms_uf_destino"] == "GO")

c4 = api("POST", "/api/contratos", {**base, "icms_manual": True, "icms_percentual": 4.5}, t)
checar("alíquota digitada 4,5% = 19.602,00", c4["icms_percentual"] == 4.5 and c4["icms_valor"] == 19602.0
       and c4["icms_manual"] is True)

c5 = api("POST", "/api/contratos", {**base, "vendedor_id": comprador_sp["id"], "comprador_id": vendedor_mg["id"]}, t)
checar("SP -> MG sem alíquota cadastrada: 0", c5["icms_percentual"] == 0 and c5["icms_valor"] == 0
       and c5["icms_regra"] == "SP → MG")
c6 = api("POST", "/api/contratos", {**base, "comprador_id": sem_uf["id"]}, t)
checar("comprador sem UF: sem ICMS", c6["icms_percentual"] == 0 and c6["icms_uf_destino"] is None)

# a tabela muda depois: contrato salvo continua igual até ser editado
api("PUT", f"/api/icms/{geral['id']}", {"empresa_id": eid, "uf_origem": "MG", "uf_destino": "SP", "aliquota": 10}, t)
salvo = api("GET", f"/api/contratos/{c1['id']}", token=t)
checar("tabela alterada não muda contrato já salvo", salvo["icms_percentual"] == 12)
editado = api("PUT", f"/api/contratos/{c1['id']}", {**base, "numero": c1["numero"], "data": c1["data"], "quantidade": 100}, t)
checar("ao editar, contrato pega a nova alíquota (10%) e o novo valor",
       editado["icms_percentual"] == 10 and editado["icms_valor"] == 13200.0, str(editado["icms_valor"]))
voltou = api("PUT", f"/api/contratos/{c4['id']}", {**base, "numero": c4["numero"], "data": c4["data"],
                                                     "icms_manual": False, "icms_percentual": 4.5}, t)
checar("desmarcar manual volta para a tabela", voltou["icms_percentual"] == 10 and voltou["icms_manual"] is False)

impressao = api("GET", f"/api/contratos/{c2['id']}/impressao", token=t)
checar("impressão traz ICMS", impressao["contrato"]["icms_valor"] == 30492.0
       and impressao["contrato"]["icms_regra"] == "MG → SP")

print("\n=== 4. Exclusões ===")
recusa = api("DELETE", f"/api/produtos/{milho['id']}", token=t, esperar_erro=True)
checar("produto usado em contrato/alíquota não é excluído", recusa.get("_status") == 400, recusa.get("_detalhe", ""))
api("DELETE", f"/api/icms/{especifica['id']}", token=t)
checar("excluir alíquota não mexe no contrato", api("GET", f"/api/contratos/{c2['id']}", token=t)["icms_percentual"] == 7)
outra = api("POST", "/api/publico/cadastro", {"nome": "Outro", "email": f"outroicms{sufixo}@teste.com",
                                              "senha": "123456", "empresa": "Outra"})
alheia = api("GET", f"/api/icms?empresa_id={eid}", token=outra["token"], esperar_erro=True)
checar("outra conta não vê a tabela", alheia.get("_status") == 403, str(alheia))

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    raise SystemExit(1)
print("ICMS OK.")
