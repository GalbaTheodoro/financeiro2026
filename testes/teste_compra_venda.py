"""Teste dos contratos de compra e de venda de café (com agente).

Confere:
  * COMPRA: só o fornecedor é escolhido (o comprador é a empresa); gera conta a PAGAR
    do fornecedor com o valor do café e conta a PAGAR da comissão do agente;
  * VENDA: só o cliente é escolhido (o vendedor é a empresa); gera conta a RECEBER do
    cliente e conta a PAGAR do agente;
  * comissão do agente pelo percentual ou em valor fechado, e contrato sem agente;
  * situação do contrato com nome diferente na compra (Fechado a Pagar / Pago Total);
  * ICMS pela UF da empresa na compra e na venda;
  * classificação contábil: compra em custo, venda em receita, comissão do agente em despesa;
  * estorno apaga os dois títulos; contrato com título não pode ser editado nem excluído;
  * contrato de corretagem continua igual (duas contas a receber) e aceita agente;
  * a folha de impressão traz a empresa no lado dela e o agente.

Uso (com o servidor rodando em http://127.0.0.1:8000):  python testes/teste_compra_venda.py
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


sufixo = str(int(time.time()))

print("\n=== 1. Preparação ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba Teste", "email": f"cv{sufixo}@teste.com", "senha": "123456",
    "empresa": "AgroDock Comercial",
})
t = conta["token"]
eid = conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "AGRODOCK COMERCIO DE CAFE LTDA", "nome_fantasia": "AgroDock Comercial",
    "cnpj": "11222333000144", "cidade": "Patrocínio", "uf": "MG",
}, t)
fornecedor = api("POST", "/api/parceiros", {"empresa_id": eid, "tipo": "FORNECEDOR",
                                            "nome": "FAZENDA SANTA LUZIA", "cidade": "Patrocínio",
                                            "uf": "MG"}, t)
cliente = api("POST", "/api/parceiros", {"empresa_id": eid, "tipo": "CLIENTE",
                                         "nome": "TORREFAÇÃO PAULISTA", "cidade": "Santos",
                                         "uf": "SP"}, t)
agente = api("POST", "/api/parceiros", {"empresa_id": eid, "tipo": "AMBOS",
                                        "nome": "JOSE CORRETOR", "cidade": "Araguari",
                                        "uf": "MG"}, t)
api("POST", "/api/icms/gerar-padrao", {"empresa_id": eid, "uf_origem": "MG", "aliquota_interna": 18}, t)
produtos = api("GET", f"/api/produtos?empresa_id={eid}", token=t)
unidades = api("GET", f"/api/unidades?empresa_id={eid}", token=t)
saca = next(u for u in unidades if u["codigo"] == "SC")
contas = {c["codigo"]: c for c in api("GET", f"/api/contas-contabeis?empresa_id={eid}", token=t)}
checar("empresa, parceiros e cadastros prontos", fornecedor["id"] and cliente["id"] and agente["id"])

compra_base = {
    "empresa_id": eid, "tipo": "COMPRA", "vendedor_id": fornecedor["id"],
    "produto_id": produtos[0]["id"], "unidade_id": saca["id"],
    "quantidade": 200, "preco_unitario": 1300, "data_pagamento": "2026-10-10",
    "agente_id": agente["id"], "agente_percentual": 1,
}
venda_base = {
    "empresa_id": eid, "tipo": "VENDA", "comprador_id": cliente["id"],
    "produto_id": produtos[0]["id"], "unidade_id": saca["id"],
    "quantidade": 200, "preco_unitario": 1450, "data_pagamento": "2026-10-20",
    "agente_id": agente["id"], "agente_valor": 1500, "agente_percentual": 0,
}

print("\n=== 2. Contrato de COMPRA ===")
compra = api("POST", "/api/contratos", compra_base, t)
checar("valor da compra 200 x 1.300 = 260.000,00", compra["valor_total"] == 260000.0, str(compra["valor_total"]))
checar("comissão do agente 1% = 2.600,00", compra["agente_valor"] == 2600.0, str(compra["agente_valor"]))
checar("comprador é a própria empresa", compra["comprador_id"] is None
       and compra["comprador_nome"] == "AgroDock Comercial", str(compra["comprador_nome"]))
checar("vendedor é o fornecedor escolhido", compra["vendedor_nome"] == "FAZENDA SANTA LUZIA")
checar("tipo e total previsto", compra["tipo_nome"] == "Compra de café"
       and compra["valor_previsto"] == 262600.0, str(compra["valor_previsto"]))
checar("ICMS MG (fornecedor) -> MG (empresa) 18% = 46.800,00",
       compra["icms_percentual"] == 18 and compra["icms_valor"] == 46800.0, str(compra["icms_valor"]))
checar("classificação em custo (4.1.01.001)",
       compra["conta_contabil_id"] == contas["4.1.01.001"]["id"], str(compra["conta_contabil_nome"]))
checar("situação aberta", compra["status_nome"] == "Aberto")

sem_fornecedor = api("POST", "/api/contratos", {**compra_base, "vendedor_id": None}, t, esperar_erro=True)
checar("compra sem fornecedor é recusada", sem_fornecedor.get("_status") == 400, sem_fornecedor.get("_detalhe", ""))
agente_igual = api("POST", "/api/contratos", {**compra_base, "agente_id": fornecedor["id"]}, t, esperar_erro=True)
checar("agente igual ao fornecedor é recusado", agente_igual.get("_status") == 400)

gerado = api("POST", f"/api/contratos/{compra['id']}/gerar-recebiveis",
             {"vencimento": "2026-10-10", "num_parcelas": 2, "vencimento_agente": "2026-10-15"}, t)
checar("mensagem fala em contas a pagar", "a pagar" in gerado["mensagem"], gerado["mensagem"])
c = gerado["contrato"]
checar("título do café: a pagar 260.000,00 em 2 parcelas",
       c["titulo_mercadoria"]["valor"] == 260000.0 and c["titulo_mercadoria"]["qtd_parcelas"] == 2)
checar("título do agente: a pagar 2.600,00", c["titulo_agente"]["valor"] == 2600.0)
checar("situação: Fechado a Pagar", c["status_nome"] == "Fechado a Pagar", str(c["status_nome"]))
pagar = api("GET", f"/api/parcelas?empresa_id={eid}&tipo=PAGAR&situacao=TODAS", token=t)
do_contrato = [p for p in pagar if p["numero_documento"] == c["numero"]]
checar("3 parcelas a pagar (2 do café + 1 do agente)", len(do_contrato) == 3, str(len(do_contrato)))
checar("nenhuma conta a receber gerada na compra",
       not [p for p in api("GET", f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=TODAS", token=t)
            if p["numero_documento"] == c["numero"]])
titulo_agente = api("GET", f"/api/lancamentos/{c['titulo_agente']['id']}", token=t)
checar("comissão do agente em despesa comercial (4.4.01.001)",
       titulo_agente["itens"][0]["conta_contabil_id"] == contas["4.4.01.001"]["id"],
       str(titulo_agente["itens"][0].get("conta_contabil_nome")))

travado = api("PUT", f"/api/contratos/{compra['id']}", {**compra_base, "numero": c["numero"],
                                                        "data": c["data"]}, t, esperar_erro=True)
checar("contrato com título não pode ser editado", travado.get("_status") == 400, travado.get("_detalhe", "")[:40])

bancos = api("GET", f"/api/bancos?empresa_id={eid}", token=t)
if not bancos:
    bancos = [api("POST", "/api/bancos", {"empresa_id": eid, "nome": "Caixa", "tipo": "CAIXA",
                                          "saldo_inicial": 500000, "data_saldo_inicial": "2026-09-01"}, t)]
for p in do_contrato:
    api("POST", f"/api/parcelas/{p['id']}/baixar",
        {"banco_id": bancos[0]["id"], "data": "2026-10-10", "forma_pagamento": "PIX"}, t)
pago = api("GET", f"/api/contratos/{compra['id']}", token=t)
checar("depois de pagar tudo: Fechado Pago Total", pago["status_nome"] == "Fechado Pago Total",
       str(pago["status_nome"]))
checar("financeiro: pago 262.600,00 e saldo zero",
       pago["financeiro"]["recebido"] == 262600.0 and pago["financeiro"]["saldo"] == 0.0,
       str(pago["financeiro"]))

print("\n=== 3. Contrato de VENDA ===")
venda = api("POST", "/api/contratos", venda_base, t)
checar("valor da venda 200 x 1.450 = 290.000,00", venda["valor_total"] == 290000.0)
checar("comissão do agente em valor fechado 1.500,00", venda["agente_valor"] == 1500.0)
checar("vendedor é a própria empresa", venda["vendedor_id"] is None
       and venda["vendedor_nome"] == "AgroDock Comercial")
checar("ICMS MG (empresa) -> SP (cliente) 12% = 34.800,00",
       venda["icms_percentual"] == 12 and venda["icms_valor"] == 34800.0, str(venda["icms_valor"]))
checar("classificação em receita de venda (3.1.01.001)",
       venda["conta_contabil_id"] == contas["3.1.01.001"]["id"], str(venda["conta_contabil_nome"]))
sem_cliente = api("POST", "/api/contratos", {**venda_base, "comprador_id": None}, t, esperar_erro=True)
checar("venda sem cliente é recusada", sem_cliente.get("_status") == 400)

gerado = api("POST", f"/api/contratos/{venda['id']}/gerar-recebiveis", {"vencimento": "2026-10-20"}, t)
v = gerado["contrato"]
checar("mensagem fala em receber e pagar",
       "a receber" in gerado["mensagem"] and "a pagar" in gerado["mensagem"], gerado["mensagem"])
checar("café: conta a receber de 290.000,00", v["titulo_mercadoria"]["valor"] == 290000.0)
checar("agente: conta a pagar de 1.500,00", v["titulo_agente"]["valor"] == 1500.0)
checar("situação: Fechado a Receber", v["status_nome"] == "Fechado a Receber", str(v["status_nome"]))
receber = [p for p in api("GET", f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=TODAS", token=t)
           if p["numero_documento"] == v["numero"]]
pagar = [p for p in api("GET", f"/api/parcelas?empresa_id={eid}&tipo=PAGAR&situacao=TODAS", token=t)
         if p["numero_documento"] == v["numero"]]
checar("1 parcela a receber (café) e 1 a pagar (agente)", len(receber) == 1 and len(pagar) == 1,
       f"{len(receber)} / {len(pagar)}")

estornado = api("POST", f"/api/contratos/{venda['id']}/estornar-recebiveis", token=t)
checar("estorno apaga os dois títulos e volta para Aberto",
       estornado["removidos"] == 2 and estornado["contrato"]["status_nome"] == "Aberto",
       str(estornado["removidos"]))
checar("as parcelas do contrato saíram",
       not [p for p in api("GET", f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=TODAS", token=t)
            if p["numero_documento"] == v["numero"]])

print("\n=== 4. Venda sem agente e corretagem ===")
sem_agente = api("POST", "/api/contratos", {**venda_base, "agente_id": None, "agente_valor": 0}, t)
checar("venda sem agente: comissão zero", sem_agente["agente_valor"] == 0
       and sem_agente["agente_nome"] is None)
g = api("POST", f"/api/contratos/{sem_agente['id']}/gerar-recebiveis", {}, t)
checar("gera só a conta a receber do café", len(g["gerados"]) == 1
       and g["contrato"]["titulo_agente"] is None, str(g["gerados"]))

corretagem = api("POST", "/api/contratos", {
    "empresa_id": eid, "tipo": "CORRETAGEM", "comprador_id": cliente["id"],
    "vendedor_id": fornecedor["id"], "produto_id": produtos[0]["id"], "unidade_id": saca["id"],
    "quantidade": 100, "preco_unitario": 1400,
    "comissao_comprador_percentual": 0.5, "comissao_vendedor_percentual": 0.5,
    "agente_id": agente["id"], "agente_percentual": 0.2,
}, t)
checar("corretagem: comissões dos dois lados e do agente",
       corretagem["comissao_total"] == 1400.0 and corretagem["agente_valor"] == 280.0,
       str(corretagem["agente_valor"]))
g = api("POST", f"/api/contratos/{corretagem['id']}/gerar-recebiveis", {}, t)
lados = {x["lado"]: x["tipo"] for x in g["gerados"]}
checar("gera 2 contas a receber e 1 a pagar (agente)",
       lados == {"comprador": "RECEBER", "vendedor": "RECEBER", "agente": "PAGAR"}, str(lados))
checar("situação da corretagem continua 'Fechado a Receber'",
       g["contrato"]["status_nome"] == "Fechado a Receber")

print("\n=== 5. Lista e impressão ===")
lista = api("GET", f"/api/contratos?empresa_id={eid}", token=t)
checar("totais por tipo", lista["totais"]["por_tipo"]["COMPRA"] == 1
       and lista["totais"]["por_tipo"]["VENDA"] == 2
       and lista["totais"]["por_tipo"]["CORRETAGEM"] == 1, str(lista["totais"]["por_tipo"]))
checar("total de comissão do agente na lista", lista["totais"]["comissao_agente"] == 2600.0 + 1500.0 + 280.0,
       str(lista["totais"]["comissao_agente"]))
so_compra = api("GET", f"/api/contratos?empresa_id={eid}&tipo=COMPRA", token=t)
checar("filtro por tipo", len(so_compra["linhas"]) == 1 and so_compra["linhas"][0]["tipo"] == "COMPRA")
checar("tipos disponíveis na lista", [x["codigo"] for x in lista["tipos"]]
       == ["CORRETAGEM", "COMPRA", "VENDA"])

impressao = api("GET", f"/api/contratos/{compra['id']}/impressao", token=t)
checar("impressão da compra: comprador é a empresa",
       impressao["comprador"]["e_minha_empresa"] is True
       and impressao["comprador"]["cpf_cnpj"] == "11222333000144", str(impressao["comprador"]["nome"]))
checar("impressão da compra: vendedor é o fornecedor com endereço",
       impressao["vendedor"]["nome"] == "FAZENDA SANTA LUZIA" and "Patrocínio" in impressao["vendedor"]["endereco"])
checar("impressão traz o agente", impressao["agente"]["nome"] == "JOSE CORRETOR")
impressao_venda = api("GET", f"/api/contratos/{venda['id']}/impressao", token=t)
checar("impressão da venda: vendedor é a empresa",
       impressao_venda["vendedor"]["e_minha_empresa"] is True
       and impressao_venda["comprador"]["nome"] == "TORREFAÇÃO PAULISTA")

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    raise SystemExit(1)
print("Contratos de compra e venda OK.")
