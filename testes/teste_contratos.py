"""Teste dos contratos de intermediação.

Usa os números do contrato real de compra e venda de café nº 00000295
(330 sacas x R$ 1.320,00 = R$ 435.600,00, corretagem de 0,50% de cada lado)
para conferir o cálculo, a geração das contas a receber e o estorno.

Uso:  python testes/teste_contratos.py
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
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


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


sufixo = str(int(time.time()))

print("\n=== 1. Preparação da corretora ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Corretor Teste", "email": f"contrato{sufixo}@teste.com", "senha": "123456",
    "empresa": "Brascafé Assessoria",
})
t = conta["token"]
eid = conta["empresa"]["id"]
comprador = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "OLAM AGRICOLA LTDA - ALFENAS",
    "cpf_cnpj": "07028528000894", "cidade": "Alfenas", "uf": "MG",
}, t)
vendedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "pessoa": "F", "nome": "ROSALINA SILVEIRA FARIA",
    "cpf_cnpj": "03037474980", "cidade": "Indianópolis", "uf": "MG",
}, t)
checar("comprador e vendedor cadastrados", comprador["id"] > 0 and vendedor["id"] > 0)

print("\n=== 2. Lançamento do contrato 00000295 ===")
contrato = api("POST", "/api/contratos", {
    "empresa_id": eid, "numero": "00000295", "data": "2026-09-10",
    "comprador_id": comprador["id"], "vendedor_id": vendedor["id"],
    "corretor": "BRASCAFE ARMAZENS GERAIS LTDA",
    "produto": "CAFÉ", "modalidade": "DISPONÍVEL", "embalagem": "A GRANEL", "unidade": "SACA",
    "quantidade": 330, "preco_unitario": 1320, "diferencial": 0,
    "numero_compra": "CPA103829", "data_embarque": "2026-09-16", "data_pagamento": "2026-09-16",
    "comissao_comprador_percentual": 0.5, "comissao_vendedor_percentual": 0.5,
    "local_coleta": "BRASCAFE ARMAZENS GERAIS LTDA",
    "local_descarga": "BRASCAFE ARMAZENS GERAIS LTDA",
    "observacao": "0,50% COMISSÃO COMPRADOR. R$ 1.320,00 LIVRE.",
}, t)
checar("valor negociado calculado (330 x 1.320,00)",
       abs(contrato["valor_total"] - 435600.00) < 0.01, brl(contrato["valor_total"]))
checar("comissão do comprador 0,50%",
       abs(contrato["comissao_comprador_valor"] - 2178.00) < 0.01,
       brl(contrato["comissao_comprador_valor"]))
checar("comissão do vendedor 0,50%",
       abs(contrato["comissao_vendedor_valor"] - 2178.00) < 0.01,
       brl(contrato["comissao_vendedor_valor"]))
checar("comissão total", abs(contrato["comissao_total"] - 4356.00) < 0.01,
       brl(contrato["comissao_total"]))
checar("conta de receita de corretagem vinculada sozinha",
       "Corretagem" in (contrato["conta_contabil_nome"] or ""), contrato["conta_contabil_nome"])
checar("contrato nasce em aberto", contrato["status"] == "ABERTO")

print("\n=== 3. Percentuais diferentes e valor digitado ===")
outro = api("POST", "/api/contratos", {
    "empresa_id": eid, "numero": "00000296", "comprador_id": comprador["id"],
    "vendedor_id": vendedor["id"], "quantidade": 100, "preco_unitario": 1500,
    "comissao_comprador_percentual": 1.5, "comissao_vendedor_percentual": 0.75,
}, t)
checar("comissões com percentuais diferentes",
       abs(outro["comissao_comprador_valor"] - 2250.00) < 0.01
       and abs(outro["comissao_vendedor_valor"] - 1125.00) < 0.01,
       f"{brl(outro['comissao_comprador_valor'])} e {brl(outro['comissao_vendedor_valor'])}")
manual = api("POST", "/api/contratos", {
    "empresa_id": eid, "numero": "00000297", "comprador_id": comprador["id"],
    "vendedor_id": vendedor["id"], "valor_total": 50000,
    "comissao_comprador_valor": 900, "comissao_vendedor_percentual": 1,
}, t)
checar("aceita comissão em valor fixo", manual["comissao_comprador_valor"] == 900.00)
checar("mistura valor fixo e percentual", manual["comissao_vendedor_valor"] == 500.00)

print("\n=== 4. Validações ===")
duplicado = api("POST", "/api/contratos", {
    "empresa_id": eid, "numero": "00000295", "comprador_id": comprador["id"],
    "vendedor_id": vendedor["id"], "quantidade": 1, "preco_unitario": 1,
}, t, esperar_erro=True)
checar("número de contrato duplicado é recusado", duplicado.get("_status") == 400,
       str(duplicado.get("_detalhe"))[:50])
mesmos = api("POST", "/api/contratos", {
    "empresa_id": eid, "numero": "00000298", "comprador_id": comprador["id"],
    "vendedor_id": comprador["id"], "quantidade": 1, "preco_unitario": 1,
}, t, esperar_erro=True)
checar("comprador igual ao vendedor é recusado", mesmos.get("_status") == 400)
sem_valor = api("POST", "/api/contratos", {
    "empresa_id": eid, "numero": "00000299", "comprador_id": comprador["id"],
    "vendedor_id": vendedor["id"],
}, t, esperar_erro=True)
checar("contrato sem valor é recusado", sem_valor.get("_status") == 400)

print("\n=== 5. Geração das contas a receber ===")
geracao = api("POST", f"/api/contratos/{contrato['id']}/gerar-recebiveis", {
    "gerar_comprador": True, "gerar_vendedor": True,
}, t)
checar("duas contas a receber geradas", len(geracao["gerados"]) == 2)
checar("contrato passa a Fechado a Receber",
       geracao["contrato"]["status"] == "FECHADO_A_RECEBER",
       geracao["contrato"]["status_nome"])

parcelas = api("GET", f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=ABERTAS", token=t)
por_parceiro = {p["parceiro_nome"]: p for p in parcelas}
checar("título no nome do comprador",
       abs(por_parceiro["OLAM AGRICOLA LTDA - ALFENAS"]["valor"] - 2178.00) < 0.01)
checar("título no nome do vendedor",
       abs(por_parceiro["ROSALINA SILVEIRA FARIA"]["valor"] - 2178.00) < 0.01)
checar("vencimento na data de pagamento do contrato",
       all(p["data_vencimento"] == "2026-09-16" for p in parcelas), parcelas[0]["data_vencimento"])
checar("documento do título é o número do contrato",
       all(p["numero_documento"] == "00000295" for p in parcelas))
checar("classificado como corretagem",
       "Corretagem" in parcelas[0]["classificacao"], parcelas[0]["classificacao"])

repetir = api("POST", f"/api/contratos/{contrato['id']}/gerar-recebiveis", {}, t, esperar_erro=True)
checar("não gera duas vezes", repetir.get("_status") == 400,
       str(repetir.get("_detalhe"))[:45])
alterar = api("PUT", f"/api/contratos/{contrato['id']}", {
    "empresa_id": eid, "numero": "00000295", "comprador_id": comprador["id"],
    "vendedor_id": vendedor["id"], "quantidade": 400, "preco_unitario": 1320,
}, t, esperar_erro=True)
checar("contrato com título gerado não pode ser alterado", alterar.get("_status") == 400)

print("\n=== 6. Reflexo na contabilidade ===")
dre = api("GET", f"/api/relatorios/dre?empresa_id={eid}&de=2026-09-01&ate=2026-09-30", token=t)
checar("receita de corretagem entra no DRE",
       abs(dre["receita_bruta"] - 4356.00) < 0.01, brl(dre["receita_bruta"]))
balancete = api(
    "GET", f"/api/relatorios/balancete?empresa_id={eid}&de=2000-01-01&ate=2026-12-31", token=t
)
checar("balancete continua fechando", balancete["totais"]["fecha"],
       brl(balancete["totais"]["debitos"]))

print("\n=== 7. Parcelamento da comissão ===")
parcelado = api("POST", f"/api/contratos/{outro['id']}/gerar-recebiveis", {
    "num_parcelas": 3, "periodicidade": "MENSAL", "vencimento": "2026-10-05",
    "gerar_comprador": True, "gerar_vendedor": False,
}, t)
detalhe = api("GET", f"/api/contratos/{outro['id']}", token=t)
checar("comissão parcelada em 3 vezes",
       detalhe["recebivel_comprador"]["qtd_parcelas"] == 3)
checar("apenas o lado escolhido foi gerado",
       detalhe["recebivel_vendedor"] is None and len(parcelado["gerados"]) == 1)

print("\n=== 8. Estorno ===")
api("POST", f"/api/contratos/{contrato['id']}/estornar-recebiveis", token=t)
depois = api("GET", f"/api/contratos/{contrato['id']}", token=t)
checar("contrato volta para aberto", depois["status"] == "ABERTO")
checar("títulos removidos",
       depois["recebivel_comprador"] is None and depois["recebivel_vendedor"] is None)
restantes = api("GET", f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=ABERTAS", token=t)
checar("contas a receber do contrato sumiram",
       all(p["numero_documento"] != "00000295" for p in restantes))
# o contrato 296 (comissão de R$ 2.250,00) continua faturado, então a receita cai
# exatamente os R$ 4.356,00 estornados
dre_depois = api("GET", f"/api/relatorios/dre?empresa_id={eid}&de=2026-09-01&ate=2026-09-30", token=t)
checar("receita do contrato estornado sai do DRE",
       abs(dre_depois["receita_bruta"] - 2250.00) < 0.01,
       f"{brl(dre_depois['receita_bruta'])} (restou só o outro contrato)")

print("\n=== 9. Listagem e isolamento ===")
lista = api("GET", f"/api/contratos?empresa_id={eid}", token=t)
checar("lista traz os contratos", lista["totais"]["quantidade"] == 3,
       str(lista["totais"]["quantidade"]))
checar("totaliza o valor negociado",
       abs(lista["totais"]["valor_negociado"] - (435600 + 150000 + 50000)) < 0.01,
       brl(lista["totais"]["valor_negociado"]))
busca = api("GET", f"/api/contratos?empresa_id={eid}&q=00000296", token=t)
checar("busca por número funciona", busca["totais"]["quantidade"] == 1)

outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outra Corretora", "email": f"outra{sufixo}@teste.com", "senha": "123456",
    "empresa": "Concorrente",
})
invasao = api("GET", f"/api/contratos/{contrato['id']}", token=outra["token"], esperar_erro=True)
checar("outro assinante não vê o contrato", invasao.get("_status") == 403)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("Contratos OK.")
