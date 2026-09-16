"""Teste do sistema rodando em banco PostgreSQL (nuvem).

Confere o que é diferente quando o banco não é mais o arquivo do PC:

  * o sistema sobe, cria as tabelas e reconhece dados que já existiam;
  * conta nova, cliente, contrato e baixa funcionam igual (numeração
    automática do banco continuando de onde parou, sem repetir id);
  * campos de sim/não, datas e valores com centavos voltam certos;
  * a conexão se recupera sozinha depois que o banco derruba a sessão
    (é o que o Neon faz ao desligar por falta de uso).

Uso:  FIN_DATABASE_URL=postgres://... python testes/teste_postgres.py
      (com o servidor no ar apontando para o mesmo banco)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = os.getenv("FIN_BASE", "http://127.0.0.1:8000")
erros = []


def api(metodo, caminho, dados=None, token=None):
    req = urllib.request.Request(
        f"{BASE}{caminho}",
        data=json.dumps(dados).encode() if dados is not None else None,
        method=metodo,
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"{}")


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


sufixo = str(int(time.time()))
hoje = date.today()

print("\n=== 1. O sistema está no ar e no PostgreSQL ===")
saude = api("GET", "/api/health")
checar("respondeu /api/health", saude.get("status") == "ok")

url = os.getenv("FIN_DATABASE_URL", "")
checar("o teste foi chamado apontando para um PostgreSQL",
       url.startswith("postgres"), url.split("@")[-1] or "(vazio)")

print("\n=== 2. Conta nova no banco que já tinha dados ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba Postgres", "email": f"pg{sufixo}@teste.com", "senha": "123456",
    "empresa": "Brascafé Assessoria",
})
token, eid = conta["token"], conta["empresa"]["id"]
checar("conta criada com id novo (numeração do banco certa)", eid > 0, f"empresa {eid}")

# entrar de novo com a mesma senha, para conferir que gravou direito
entrada = api("POST", "/api/auth/login",
              {"email": f"pg{sufixo}@teste.com", "senha": "123456"})
checar("login funciona depois de gravado", bool(entrada.get("token")))

print("\n=== 3. Cadastros e um contrato inteiro ===")
comprador = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "AMBOS", "nome": "OLAM AGRICOLA LTDA",
    "cpf_cnpj": "03.717.780/0001-40", "ativo": True}, token)
vendedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "AMBOS", "nome": "ROSALINA SILVEIRA FARIA",
    "ativo": False}, token)
checar("cliente gravado com ativo = sim", comprador["ativo"] is True)
checar("cliente gravado com ativo = não", vendedor["ativo"] is False)

banco = api("POST", "/api/bancos", {
    "empresa_id": eid, "nome": "Banco do Brasil", "tipo": "CORRENTE",
    "saldo_inicial": 5000}, token)

unidades = api("GET", f"/api/unidades?empresa_id={eid}", token=token)
unidades = unidades["linhas"] if isinstance(unidades, dict) else unidades
produtos = api("GET", f"/api/produtos?empresa_id={eid}", token=token)
produtos = produtos["linhas"] if isinstance(produtos, dict) else produtos
checar("unidades e produtos padrão vieram junto com a conta nova",
       len(unidades) > 0 and len(produtos) > 0, f"{len(unidades)}/{len(produtos)}")

contrato = api("POST", "/api/contratos", {
    "empresa_id": eid,
    "data": hoje.isoformat(),
    "produto_id": produtos[0]["id"],
    "unidade_id": unidades[0]["id"],
    "comprador_id": comprador["id"],
    "vendedor_id": vendedor["id"],
    "quantidade": 330,
    "preco_unitario": 1320,
    "comissao_comprador_percentual": 0.5,
    "comissao_vendedor_percentual": 0.5,
    "data_vencimento": (hoje + timedelta(days=30)).isoformat(),
    "observacao": "Contrato de teste no PostgreSQL",
}, token)
checar("contrato calculou o valor negociado", contrato["valor_total"] == 435600.0,
       f'R$ {contrato["valor_total"]:,.2f}')
checar("comissão dos dois lados", abs(contrato["comissao_total"] - 4356) < 0.01,
       f'R$ {contrato["comissao_total"]:,.2f}')
checar("data do contrato voltou como data", contrato["data"] == hoje.isoformat(),
       str(contrato["data"]))
checar("número automático com 8 dígitos", len(str(contrato["numero"])) == 8,
       str(contrato["numero"]))
checar("status inicial é Aberto", contrato["status"] == "ABERTO", contrato["status"])

print("\n=== 4. Financeiro ligado ao contrato ===")
resposta = api("POST", f'/api/contratos/{contrato["id"]}/gerar-recebiveis', {
    "vencimento": (hoje + timedelta(days=30)).isoformat(), "num_parcelas": 1,
    "gerar_comprador": True, "gerar_vendedor": True,
}, token)
ficha = resposta["contrato"]
checar("status virou Fechado a Receber",
       ficha["status"] == "FECHADO_A_RECEBER", ficha["status"])
checar("gerou o valor cheio em contas a receber",
       ficha["financeiro"]["gerado"] == 4356.0,
       f'R$ {ficha["financeiro"]["gerado"]:,.2f}')

parcelas = api("GET", f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=TODAS",
               token=token)
parcelas = parcelas["linhas"] if isinstance(parcelas, dict) else parcelas
checar("duas parcelas criadas (uma de cada lado)", len(parcelas) == 2, str(len(parcelas)))
checar("centavos preservados", parcelas[0]["valor"] == 2178.0,
       f'R$ {parcelas[0]["valor"]:,.2f}')

api("POST", f'/api/parcelas/{parcelas[0]["id"]}/baixar', {
    "banco_id": banco["id"], "data": hoje.isoformat(),
    "valor": parcelas[0]["valor"]}, token)
ficha = api("GET", f'/api/contratos/{contrato["id"]}', token=token)
checar("status virou Recebido Parcial",
       ficha["status"] == "RECEBIDO_PARCIAL", ficha["status"])
checar("saldo a receber calculado", ficha["financeiro"]["saldo"] == 2178.0,
       f'R$ {ficha["financeiro"]["saldo"]:,.2f}')

print("\n=== 5. Relatórios (somas feitas em cima do banco) ===")
dre = api("GET", f"/api/relatorios/dre?empresa_id={eid}"
                 f"&de={hoje.replace(day=1)}&ate={hoje}", token=token)
checar("DRE trouxe a receita da corretagem", dre["receita_bruta"] > 0,
       f'R$ {dre["receita_bruta"]:,.2f}')
balancete = api("GET", f"/api/relatorios/balancete?empresa_id={eid}"
                       f"&de={hoje.replace(day=1)}&ate={hoje}", token=token)
checar("balancete fecha (débitos = créditos)", balancete["totais"]["fecha"],
       f'{balancete["totais"]["debitos"]:,.2f} x {balancete["totais"]["creditos"]:,.2f}')
rel = api("GET", f"/api/relatorios/contratos?empresa_id={eid}"
                 f"&agrupar_por=status", token=token)
checar("relatório de contratos por situação",
       rel["resumo"][0]["quantidade"] >= 1, json.dumps(rel["resumo"][0], ensure_ascii=False))

print("\n=== 6. Dados que já estavam no banco antes ===")
tm = api("POST", "/api/auth/login",
         {"email": "admin@financeiro.local", "senha": "admin123"})["token"]
antigos = api("GET", "/api/admin/assinaturas", token=tm)["linhas"]
checar("o administrador enxerga as contas que vieram na migração",
       len(antigos) > 1, f"{len(antigos)} conta(s)")

print("\n=== 7. Banco que dorme e acorda ===")
# o Neon derruba a conexão quando fica parado; o sistema tem que reconectar
# sozinho na próxima tela, sem erro para quem está usando.
import subprocess  # noqa: E402
alvo = url.split("/")[-1].split("?")[0]
subprocess.run(
    ["su", "postgres", "-c",
     "psql -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
     f"WHERE datname = '{alvo}' AND pid <> pg_backend_pid();\""],
    capture_output=True)
time.sleep(1)
try:
    ficha = api("GET", f'/api/contratos/{contrato["id"]}', token=token)
    checar("o sistema reconectou sozinho depois da queda",
           ficha["status"] == "RECEBIDO_PARCIAL", ficha["status"])
except urllib.error.HTTPError as e:
    checar("o sistema reconectou sozinho depois da queda", False, f"HTTP {e.code}")

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} problema(s):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("PostgreSQL OK — o sistema roda igualzinho com o banco na nuvem.")
