"""Teste ponta a ponta do sistema financeiro.

Executa o fluxo completo contra o servidor rodando em http://127.0.0.1:8000:
login, cadastros, lançamento simples, lançamento múltiplo (rateio + parcelas),
baixas com juros e desconto, movimento de caixa, transferência e conferência
do balancete, do DRE e do saldo de caixa.

Uso:  python testes/teste_completo.py
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://127.0.0.1:8000"
TOKEN = None
falhas = []


def api(metodo: str, caminho: str, dados=None):
    url = f"{BASE}{caminho}"
    corpo = json.dumps(dados).encode() if dados is not None else None
    req = urllib.request.Request(url, data=corpo, method=metodo)
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode()
        raise AssertionError(f"{metodo} {caminho} -> HTTP {e.code}: {detalhe}") from None


def checar(descricao: str, condicao: bool, extra=""):
    marca = "OK  " if condicao else "FALHA"
    print(f"  [{marca}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


hoje = date.today()
mes_inicio = date(hoje.year, hoje.month, 1).isoformat()
mes_fim = hoje.isoformat()

print("\n=== 1. Autenticação ===")
resposta = api("POST", "/api/auth/login", {"email": "admin@financeiro.local", "senha": "admin123"})
TOKEN = resposta["token"]
checar("login do administrador", bool(TOKEN))

print("\n=== 2. Empresa e cadastros ===")
empresa = api("POST", "/api/empresas", {
    "razao_social": "Assessoria Financeira Teste Ltda",
    "nome_fantasia": "Assessoria Teste",
    "cnpj": "12.345.678/0001-90",
    "cidade": "São Paulo", "uf": "SP",
    "criar_plano_padrao": True,
})
eid = empresa["id"]
contas = api("GET", f"/api/contas-contabeis?empresa_id={eid}")
centros = api("GET", f"/api/centros-custo?empresa_id={eid}")
operacoes = api("GET", f"/api/operacoes?empresa_id={eid}")
checar("plano de contas criado", len(contas) > 80, f"({len(contas)} contas)")
checar("centros de custo criados", len(centros) >= 5, f"({len(centros)})")
checar("operações criadas", len(operacoes) >= 15, f"({len(operacoes)})")

por_codigo = {c["codigo"]: c for c in contas}
cc_admin = next(c for c in centros if c["nome"].startswith("Administrativo"))
cc_comercial = next(c for c in centros if "Comercial" in c["nome"])
op_servico = next(o for o in operacoes if o["codigo"] == "002")
op_aluguel = next(o for o in operacoes if o["codigo"] == "105")

cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "pessoa": "J",
    "nome": "Cliente Alfa Comércio Ltda", "cpf_cnpj": "11.111.111/0001-11",
    "cidade": "Campinas", "uf": "SP", "email": "financeiro@alfa.com.br",
})
fornecedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "FORNECEDOR", "pessoa": "J",
    "nome": "Imobiliária Beta Ltda", "cpf_cnpj": "22.222.222/0001-22",
})
checar("cliente e fornecedor cadastrados", cliente["id"] > 0 and fornecedor["id"] > 0)

banco = api("POST", "/api/bancos", {
    "empresa_id": eid, "codigo": "001", "nome": "Banco do Brasil C/C",
    "codigo_banco": "001", "agencia": "1234-5", "conta": "98765-4",
    "tipo": "CORRENTE", "conta_contabil_id": por_codigo["1.1.01.002"]["id"],
    "saldo_inicial": 10000.00, "data_saldo_inicial": (hoje - timedelta(days=40)).isoformat(),
})
caixa = api("POST", "/api/bancos", {
    "empresa_id": eid, "codigo": "002", "nome": "Caixa Loja", "tipo": "CAIXA",
    "conta_contabil_id": por_codigo["1.1.01.001"]["id"], "saldo_inicial": 500.00,
    "data_saldo_inicial": (hoje - timedelta(days=40)).isoformat(),
})
checar("contas bancárias cadastradas com saldo inicial", banco["id"] > 0 and caixa["id"] > 0)

print("\n=== 3. Lançamento SIMPLES (a receber, à vista) ===")
simples = api("POST", "/api/lancamentos", {
    "empresa_id": eid, "tipo": "RECEBER", "modo": "SIMPLES",
    "numero_documento": "NF-1001", "parceiro_id": cliente["id"],
    "descricao": "Honorários de assessoria - mensalidade",
    "data_emissao": hoje.isoformat(), "data_competencia": hoje.isoformat(),
    "valor_total": 3500.00, "operacao_id": op_servico["id"],
    "itens": [{"conta_contabil_id": por_codigo["3.1.01.002"]["id"],
               "centro_custo_id": cc_comercial["id"], "valor": 3500.00}],
    "num_parcelas": 1, "primeiro_vencimento": hoje.isoformat(),
    "baixar_agora": True, "banco_id": banco["id"],
})
checar("lançamento simples quitado na hora", simples["status"] == "QUITADO", simples["status"])
checar("uma parcela gerada", len(simples["parcelas"]) == 1)

print("\n=== 4. Lançamento MÚLTIPLO (a pagar, rateio + 3 parcelas) ===")
multiplo = api("POST", "/api/lancamentos", {
    "empresa_id": eid, "tipo": "PAGAR", "modo": "MULTIPLO",
    "numero_documento": "CTR-77", "parceiro_id": fornecedor["id"],
    "descricao": "Aluguel + condomínio da sede",
    "data_emissao": hoje.isoformat(), "data_competencia": hoje.isoformat(),
    "valor_total": 9000.00, "operacao_id": op_aluguel["id"],
    "itens": [
        {"conta_contabil_id": por_codigo["4.3.01.001"]["id"],
         "centro_custo_id": cc_admin["id"], "descricao": "Aluguel", "valor": 6000.00},
        {"conta_contabil_id": por_codigo["4.3.01.009"]["id"],
         "centro_custo_id": cc_admin["id"], "descricao": "Manutenção", "valor": 3000.00},
    ],
    "num_parcelas": 3, "primeiro_vencimento": hoje.isoformat(), "periodicidade": "MENSAL",
})
checar("rateio em 2 contas", len(multiplo["itens"]) == 2)
checar("3 parcelas geradas", len(multiplo["parcelas"]) == 3)
checar("soma das parcelas confere",
       abs(sum(p["valor"] for p in multiplo["parcelas"]) - 9000) < 0.01)

print("\n=== 5. Rateio inválido deve ser recusado ===")
try:
    api("POST", "/api/lancamentos", {
        "empresa_id": eid, "tipo": "PAGAR", "descricao": "Rateio errado",
        "valor_total": 1000.00,
        "itens": [{"conta_contabil_id": por_codigo["4.3.01.002"]["id"], "valor": 400.00}],
    })
    checar("rateio divergente recusado", False)
except AssertionError as e:
    checar("rateio divergente recusado", "400" in str(e))

print("\n=== 6. Baixa com juros e baixa parcial ===")
parcelas_pagar = api("GET", f"/api/parcelas?empresa_id={eid}&tipo=PAGAR&situacao=ABERTAS")
p1, p2 = parcelas_pagar[0], parcelas_pagar[1]
api("POST", f"/api/parcelas/{p1['id']}/baixar", {
    "banco_id": banco["id"], "data": hoje.isoformat(),
    "juros": 45.00, "multa": 15.00, "forma_pagamento": "PIX",
    "historico": "Pagamento aluguel parcela 1 com juros",
})
api("POST", f"/api/parcelas/{p2['id']}/baixar", {
    "banco_id": banco["id"], "data": hoje.isoformat(), "valor": 1000.00,
    "forma_pagamento": "TRANSFERENCIA", "historico": "Pagamento parcial",
})
detalhe1 = api("GET", f"/api/parcelas/{p1['id']}")
detalhe2 = api("GET", f"/api/parcelas/{p2['id']}")
checar("parcela 1 quitada", detalhe1["status"] == "PAGO", detalhe1["status"])
checar("parcela 2 parcial", detalhe2["status"] == "PARCIAL", detalhe2["status"])
checar("saldo da parcela 2 correto", abs(detalhe2["saldo"] - 2000.00) < 0.01,
       brl(detalhe2["saldo"]))

print("\n=== 7. Recebimento com desconto ===")
recebivel = api("POST", "/api/lancamentos", {
    "empresa_id": eid, "tipo": "RECEBER", "numero_documento": "NF-1002",
    "parceiro_id": cliente["id"], "descricao": "Venda de mercadorias",
    "data_emissao": hoje.isoformat(), "valor_total": 2000.00,
    "itens": [{"conta_contabil_id": por_codigo["3.1.01.001"]["id"],
               "centro_custo_id": cc_comercial["id"], "valor": 2000.00}],
    "num_parcelas": 1, "primeiro_vencimento": hoje.isoformat(),
})
parcela_receb = recebivel["parcelas"][0]
api("POST", f"/api/parcelas/{parcela_receb['id']}/baixar", {
    "banco_id": banco["id"], "data": hoje.isoformat(), "desconto": 100.00,
    "forma_pagamento": "PIX", "historico": "Recebimento com desconto de 100",
})
detalhe_receb = api("GET", f"/api/parcelas/{parcela_receb['id']}")
checar("título recebido com desconto está quitado", detalhe_receb["status"] == "PAGO")

print("\n=== 8. Caixa: movimento avulso e transferência ===")
api("POST", "/api/caixa/movimentos", {
    "empresa_id": eid, "banco_id": banco["id"], "data": hoje.isoformat(),
    "tipo": "S", "valor": 89.90, "historico": "Tarifa mensal de manutenção de conta",
    "conta_contabil_id": por_codigo["4.5.01.003"]["id"], "centro_custo_id": cc_admin["id"],
})
api("POST", "/api/caixa/transferencias", {
    "empresa_id": eid, "banco_origem_id": banco["id"], "banco_destino_id": caixa["id"],
    "data": hoje.isoformat(), "valor": 700.00, "historico": "Suprimento de caixa",
})
saldos = api("GET", f"/api/caixa/saldos?empresa_id={eid}")
extrato = api("GET", f"/api/caixa/extrato?empresa_id={eid}&de={mes_inicio}&ate={mes_fim}")

# Conferência manual do saldo esperado
esperado = (
    10000 + 500          # saldos iniciais
    + 3500               # recebimento à vista
    - (3000 + 45 + 15)   # aluguel parcela 1 + juros + multa
    - 1000               # pagamento parcial
    + (2000 - 100)       # recebimento com desconto
    - 89.90              # tarifa
)
checar("saldo total do caixa confere", abs(saldos["total"] - esperado) < 0.01,
       f"{brl(saldos['total'])} (esperado {brl(esperado)})")
checar("extrato traz os movimentos", len(extrato["movimentos"]) >= 6,
       f"({len(extrato['movimentos'])} movimentos)")

print("\n=== 9. Balancete ===")
balancete = api("GET", f"/api/relatorios/balancete?empresa_id={eid}&de=2000-01-01&ate={mes_fim}")
checar("balancete fecha (débitos = créditos)", balancete["totais"]["fecha"],
       f"D {brl(balancete['totais']['debitos'])} / C {brl(balancete['totais']['creditos'])}")

linhas_bal = {l["codigo"]: l for l in balancete["linhas"]}
banco_linha = linhas_bal.get("1.1.01.002")
checar("conta de bancos aparece no balancete", banco_linha is not None)

print("\n=== 10. DRE ===")
dre = api("GET", f"/api/relatorios/dre?empresa_id={eid}&de={mes_inicio}&ate={mes_fim}")
linhas_dre = {l["chave"]: l for l in dre["linhas"]}
checar("receita bruta do período", abs(dre["receita_bruta"] - 5500.00) < 0.01,
       brl(dre["receita_bruta"]))
resultado_esperado = 5500 - 9000 - 89.90 - 100 + 0   # receitas - despesas do período
# juros e multa pagos entram como despesa financeira
resultado_esperado -= 60
checar("resultado líquido do período",
       abs(dre["resultado_liquido"] - resultado_esperado) < 0.01,
       f"{brl(dre['resultado_liquido'])} (esperado {brl(resultado_esperado)})")
checar("DRE traz subtotais", "RECEITA LÍQUIDA" in linhas_dre and "LUCRO BRUTO" in linhas_dre)

print("\n=== 11. Relatórios analíticos ===")
por_cc = api(
    "GET",
    f"/api/relatorios/por-classificacao?empresa_id={eid}&agrupar_por=centro_custo"
    f"&de={mes_inicio}&ate={mes_fim}",
)
por_op = api(
    "GET",
    f"/api/relatorios/por-classificacao?empresa_id={eid}&agrupar_por=operacao"
    f"&de={mes_inicio}&ate={mes_fim}",
)
titulos = api(
    "GET",
    f"/api/relatorios/titulos?empresa_id={eid}&tipo=PAGAR&situacao=ABERTAS"
    f"&de=2000-01-01&ate=2099-12-31",
)
razao = api(
    "GET",
    f"/api/relatorios/razao?empresa_id={eid}&conta_contabil_id={por_codigo['1.1.01.002']['id']}"
    f"&de=2000-01-01&ate={mes_fim}",
)
fluxo = api(
    "GET",
    f"/api/relatorios/fluxo-caixa?empresa_id={eid}&de={mes_inicio}&ate={mes_fim}"
    f"&agrupar=dia&incluir_previsto=true",
)
dashboard = api("GET", f"/api/relatorios/dashboard?empresa_id={eid}")

checar("relatório por centro de custo", len(por_cc["linhas"]) > 0)
checar("relatório por operação", len(por_op["linhas"]) > 0)
checar("contas a pagar em aberto", titulos["totais"]["quantidade"] == 2,
       f"saldo {brl(titulos['totais']['saldo'])}")
checar("razão da conta banco", len(razao["linhas"]) >= 5)
checar("fluxo de caixa gerado", len(fluxo["linhas"]) > 0)
checar("dashboard traz saldo disponível",
       abs(dashboard["saldo_disponivel"] - esperado) < 0.01, brl(dashboard["saldo_disponivel"]))

print("\n=== 12. Estorno de baixa ===")
baixas = api("GET", f"/api/relatorios/../baixas?empresa_id={eid}") if False else api(
    "GET", f"/api/baixas?empresa_id={eid}"
)
ultima = baixas[0]
api("DELETE", f"/api/baixas/{ultima['id']}")
saldos_pos = api("GET", f"/api/caixa/saldos?empresa_id={eid}")
balancete_pos = api(
    "GET", f"/api/relatorios/balancete?empresa_id={eid}&de=2000-01-01&ate={mes_fim}"
)
checar("estorno alterou o saldo do caixa", abs(saldos_pos["total"] - saldos["total"]) > 0.01)
checar("balancete continua fechando após estorno", balancete_pos["totais"]["fecha"])

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("Todos os testes passaram.")
