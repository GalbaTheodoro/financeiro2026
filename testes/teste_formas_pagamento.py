"""Teste das formas de pagamento do cliente/fornecedor.

Cadastra várias contas e chaves Pix para um mesmo fornecedor, confere a regra
da conta principal, o uso na baixa do título e o isolamento entre contas.

Uso:  python testes/teste_formas_pagamento.py
"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date

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


sufixo = str(int(time.time()))
hoje = date.today().isoformat()

print("\n=== 1. Preparação ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Dono Teste", "email": f"formas{sufixo}@teste.com", "senha": "123456",
    "empresa": "Empresa das Formas",
})
t = conta["token"]
eid = conta["empresa"]["id"]
contas_contabeis = {c["codigo"]: c for c in api("GET", f"/api/contas-contabeis?empresa_id={eid}", token=t)}
banco = api("POST", "/api/bancos", {
    "empresa_id": eid, "nome": "Banco da Empresa", "tipo": "CORRENTE",
    "conta_contabil_id": contas_contabeis["1.1.01.002"]["id"], "saldo_inicial": 20000,
}, t)
fornecedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "FORNECEDOR", "nome": "Transportadora Beta Ltda",
    "cpf_cnpj": "22.333.444/0001-55",
}, t)
checar("fornecedor cadastrado", fornecedor["id"] > 0)
checar("começa sem forma de pagamento", fornecedor.get("qtd_formas_pagamento", 0) == 0)

print("\n=== 2. Várias formas para o mesmo fornecedor ===")
pix = api("POST", f"/api/parceiros/{fornecedor['id']}/formas-pagamento", {
    "tipo": "PIX", "pix_tipo": "CNPJ", "pix_chave": "22333444000155", "apelido": "Pix da matriz",
}, t)
checar("primeira forma vira principal automaticamente", pix["principal"] is True)
checar("resumo do Pix legível", pix["resumo"] == "Pix (CNPJ): 22333444000155", pix["resumo"])
checar("titular herdado do cadastro", pix["titular"] == "Transportadora Beta Ltda")

itau = api("POST", f"/api/parceiros/{fornecedor['id']}/formas-pagamento", {
    "tipo": "DEPOSITO", "banco_codigo": "341", "banco_nome": "Itaú", "agencia": "1234",
    "conta": "56789-0", "tipo_conta": "CORRENTE", "apelido": "Conta Itaú",
}, t)
caixa = api("POST", f"/api/parceiros/{fornecedor['id']}/formas-pagamento", {
    "tipo": "DEPOSITO", "banco_codigo": "104", "banco_nome": "Caixa", "agencia": "0011",
    "operacao": "013", "conta": "9876-5", "tipo_conta": "POUPANCA",
}, t)
checar("conta corrente descrita corretamente",
       itau["resumo"] == "341 Itaú · Ag 1234 · C/C 56789-0", itau["resumo"])
checar("poupança da Caixa mostra a operação",
       caixa["resumo"] == "104 Caixa · Ag 0011 · Op 013 · Poupança 9876-5", caixa["resumo"])
checar("texto para copiar traz banco, agência e conta",
       all(x in itau["texto_copia"] for x in ["Itaú", "1234", "56789-0"]))

lista = api("GET", f"/api/parceiros/{fornecedor['id']}/formas-pagamento", token=t)
checar("três formas cadastradas", len(lista["formas"]) == 3)
checar("apenas uma é principal", sum(1 for f in lista["formas"] if f["principal"]) == 1)

print("\n=== 3. Troca da forma principal ===")
api("POST", f"/api/formas-pagamento/{itau['id']}/principal", token=t)
lista = api("GET", f"/api/parceiros/{fornecedor['id']}/formas-pagamento", token=t)
principal = next(f for f in lista["formas"] if f["principal"])
checar("Itaú passou a ser a principal", principal["id"] == itau["id"], principal["resumo"])
checar("continua só uma principal", sum(1 for f in lista["formas"] if f["principal"]) == 1)
checar("principal vem em primeiro na lista", lista["formas"][0]["id"] == itau["id"])

print("\n=== 4. Validações ===")
sem_chave = api("POST", f"/api/parceiros/{fornecedor['id']}/formas-pagamento",
                {"tipo": "PIX"}, t, esperar_erro=True)
checar("Pix sem chave é recusado", sem_chave.get("_status") == 400,
       str(sem_chave.get("_detalhe"))[:40])
sem_conta = api("POST", f"/api/parceiros/{fornecedor['id']}/formas-pagamento",
                {"tipo": "DEPOSITO", "banco_nome": "Bradesco"}, t, esperar_erro=True)
checar("depósito sem conta é recusado", sem_conta.get("_status") == 400,
       str(sem_conta.get("_detalhe"))[:40])
tipo_errado = api("POST", f"/api/parceiros/{fornecedor['id']}/formas-pagamento",
                  {"tipo": "CRIPTO", "pix_chave": "x"}, t, esperar_erro=True)
checar("tipo desconhecido é recusado", tipo_errado.get("_status") == 400)

print("\n=== 5. Uso na baixa do título ===")
titulo = api("POST", "/api/lancamentos", {
    "empresa_id": eid, "tipo": "PAGAR", "parceiro_id": fornecedor["id"],
    "descricao": "Frete da semana", "valor_total": 1200.00, "num_parcelas": 1,
    "primeiro_vencimento": hoje,
    "itens": [{"conta_contabil_id": contas_contabeis["4.4.01.003"]["id"], "valor": 1200.00}],
}, t)
parcela = titulo["parcelas"][0]
baixa = api("POST", f"/api/parcelas/{parcela['id']}/baixar", {
    "banco_id": banco["id"], "data": hoje, "forma_pagamento": "TRANSFERENCIA",
    "forma_parceiro_id": itau["id"], "historico": "Pagamento do frete",
}, t)
checar("baixa registra a conta usada", baixa["baixa"]["forma_parceiro_id"] == itau["id"])
checar("baixa mostra o resumo da conta",
       "Itaú" in (baixa["baixa"]["forma_parceiro"] or ""), baixa["baixa"]["forma_parceiro"])

detalhe = api("GET", f"/api/lancamentos/{titulo['id']}", token=t)
registrada = detalhe["parcelas"][0]["baixas"][0]
checar("histórico do título guarda por onde foi pago",
       "Itaú" in (registrada["forma_parceiro"] or ""))

print("\n=== 6. Regras de segurança e exclusão ===")
usada = api("DELETE", f"/api/formas-pagamento/{itau['id']}", token=t, esperar_erro=True)
checar("forma já usada não pode ser excluída", usada.get("_status") == 400,
       str(usada.get("_detalhe"))[:60])
api("DELETE", f"/api/formas-pagamento/{caixa['id']}", token=t)
lista = api("GET", f"/api/parceiros/{fornecedor['id']}/formas-pagamento", token=t)
checar("forma não usada é excluída", len(lista["formas"]) == 2)

outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro Dono", "email": f"outro{sufixo}@teste.com", "senha": "123456",
    "empresa": "Empresa Concorrente",
})
invasao = api("GET", f"/api/parceiros/{fornecedor['id']}/formas-pagamento",
              token=outra["token"], esperar_erro=True)
checar("outro assinante não vê estas contas", invasao.get("_status") == 403,
       str(invasao.get("_detalhe"))[:50])
invasao_edicao = api("PUT", f"/api/formas-pagamento/{pix['id']}",
                     {"tipo": "PIX", "pix_chave": "invadido"}, outra["token"], esperar_erro=True)
checar("outro assinante não altera estas contas", invasao_edicao.get("_status") == 403)

print("\n=== 7. Resumo na lista de clientes/fornecedores ===")
parceiros = api("GET", f"/api/parceiros?empresa_id={eid}", token=t)
linha = next(p for p in parceiros if p["id"] == fornecedor["id"])
checar("lista mostra a quantidade de formas", linha["qtd_formas_pagamento"] == 2,
       str(linha["qtd_formas_pagamento"]))
checar("lista mostra a forma principal", "Itaú" in linha["forma_principal"],
       linha["forma_principal"])

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("Formas de pagamento OK.")
