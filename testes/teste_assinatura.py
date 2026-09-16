"""Teste do fluxo de assinatura: cadastro pelo site, teste de 48h, bloqueio,
pagamento por Pix, confirmação e liberação — além do isolamento entre contas.

Uso:  python testes/teste_assinatura.py
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
        if esperar_erro:
            return {"_status": e.code, "_detalhe": json.loads(e.read() or b"{}").get("detail", "")}
        raise AssertionError(f"{metodo} {caminho} -> HTTP {e.code}: {e.read().decode()[:300]}") from None


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


sufixo = str(int(time.time()))
email_a = f"cliente.a{sufixo}@teste.com"
email_b = f"cliente.b{sufixo}@teste.com"

print("\n=== 1. Site público ===")
info = api("GET", "/api/publico/info")
planos = {p["codigo"]: p for p in info["planos"]}
checar("site informa os planos", set(planos) == {"SEMESTRAL", "ANUAL"})
checar("plano semestral R$ 350", planos["SEMESTRAL"]["valor"] == 350.0, f"R$ {planos['SEMESTRAL']['valor']:.2f}")
checar("plano anual R$ 600", planos["ANUAL"]["valor"] == 600.0, f"R$ {planos['ANUAL']['valor']:.2f}")
checar("teste de 48 horas", info["horas_teste"] == 48, f"{info['horas_teste']}h")

print("\n=== 2. Configuração do Pix pelo administrador ===")
master = api("POST", "/api/auth/login", {"email": "admin@financeiro.local", "senha": "admin123"})
tm = master["token"]
api("PUT", "/api/admin/configuracoes", {"valores": {
    "pix_chave": "financeiro@minhaempresa.com.br",
    "pix_titular": "Minha Assessoria Financeira",
    "pix_cidade": "SAO PAULO",
    "pix_banco": "Banco do Brasil",
    "empresa_titular": "Minha Assessoria",
}}, tm)
checar("perfil do administrador é MASTER", master["usuario"]["perfil"] == "MASTER")

print("\n=== 3. Cadastro pelo site ===")
conta_a = api("POST", "/api/publico/cadastro", {
    "nome": "Cliente A", "email": email_a, "senha": "123456",
    "empresa": "Empresa A Ltda", "plano": "SEMESTRAL", "telefone": "(11) 91111-1111",
})
ta = conta_a["token"]
checar("conta criada com acesso liberado", conta_a["assinatura"]["liberado"] is True)
checar("status inicial é TESTE", conta_a["assinatura"]["status"] == "TESTE")
checar("plano de contas gerado para a empresa nova",
       len(api("GET", f"/api/contas-contabeis?empresa_id={conta_a['empresa']['id']}", token=ta)) > 80)
checar("Pix já vem calculado", conta_a["pagamento"]["copia_e_cola"].startswith("000201"))
checar("QR Code gerado", "<svg" in conta_a["pagamento"]["qrcode_svg"])

print("\n=== 4. Uso normal durante o teste ===")
eid = conta_a["empresa"]["id"]
contas = {c["codigo"]: c for c in api("GET", f"/api/contas-contabeis?empresa_id={eid}", token=ta)}
lanc = api("POST", "/api/lancamentos", {
    "empresa_id": eid, "tipo": "RECEBER", "descricao": "Serviço prestado durante o teste",
    "valor_total": 1500.00, "num_parcelas": 1,
    "itens": [{"conta_contabil_id": contas["3.1.01.002"]["id"], "valor": 1500.00}],
}, ta)
checar("assinante consegue lançar durante o teste", lanc["id"] > 0)

print("\n=== 5. Isolamento entre contas ===")
conta_b = api("POST", "/api/publico/cadastro", {
    "nome": "Cliente B", "email": email_b, "senha": "123456",
    "empresa": "Empresa B Ltda", "plano": "ANUAL",
})
tb = conta_b["token"]
empresas_b = api("GET", "/api/empresas", token=tb)
checar("cada assinante vê apenas a própria empresa",
       len(empresas_b) == 1 and empresas_b[0]["id"] == conta_b["empresa"]["id"])
invasao = api("GET", f"/api/parceiros?empresa_id={eid}", token=tb, esperar_erro=True)
checar("acesso à empresa de outro assinante é bloqueado", invasao.get("_status") == 403,
       str(invasao.get("_detalhe", ""))[:60])
invasao_post = api("POST", "/api/parceiros", {
    "empresa_id": eid, "nome": "Invasor", "tipo": "CLIENTE",
}, tb, esperar_erro=True)
checar("gravação em empresa de terceiros é bloqueada", invasao_post.get("_status") == 403)

print("\n=== 6. Fim das 48 horas: conta bloqueada ===")
assinaturas = api("GET", "/api/admin/assinaturas", token=tm)["linhas"]
assinatura_a = next(a for a in assinaturas if a["usuario_email"] == email_a)
api("POST", f"/api/admin/assinaturas/{assinatura_a['id']}/status",
    {"status": "TESTE", "horas_teste": 0}, tm)
bloqueio = api("GET", f"/api/relatorios/dashboard?empresa_id={eid}", token=ta, esperar_erro=True)
checar("acesso bloqueado depois do teste", bloqueio.get("_status") == 402,
       str(bloqueio.get("_detalhe"))[:70])
minha = api("GET", "/api/assinatura/minha", token=ta)
checar("tela de assinatura continua acessível", minha["situacao"]["motivo"] == "TESTE_EXPIRADO")
checar("dados de pagamento disponíveis mesmo bloqueado", minha["pagamento"]["configurado"] is True)

print("\n=== 7. Troca de plano e informe do Pix ===")
troca = api("POST", "/api/assinatura/plano", {"plano": "ANUAL"}, ta)
checar("assinante pode trocar o plano antes de pagar", troca["pagamento"]["plano"]["valor"] == 600.0)
aviso = api("POST", "/api/assinatura/pagamento", {"observacao": "Pix feito às 10h"}, ta)
checar("pagamento informado", aviso["ok"] is True)
ainda = api("GET", f"/api/relatorios/dashboard?empresa_id={eid}", token=ta, esperar_erro=True)
checar("continua bloqueado até a confirmação", ainda.get("_status") == 402)
checar("situação passa a aguardar confirmação",
       api("GET", "/api/assinatura/minha", token=ta)["situacao"]["motivo"] == "AGUARDANDO_CONFIRMACAO")

print("\n=== 8. Confirmação do recebimento e liberação ===")
painel_admin = api("GET", "/api/admin/assinaturas", token=tm)
checar("administrador vê quem informou pagamento", painel_admin["resumo"]["aguardando"] >= 1)
confirmado = api("POST", f"/api/admin/assinaturas/{assinatura_a['id']}/confirmar",
                 {"status": "ATIVA", "meses": 12, "observacao": "Pix conferido"}, tm)
checar("assinatura ativada", confirmado["status"] == "ATIVA", f"vence em {confirmado['data_fim']}")
painel = api("GET", f"/api/relatorios/dashboard?empresa_id={eid}", token=ta)
checar("acesso liberado após a confirmação", "saldo_disponivel" in painel)
titulos = api("GET", f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=TODAS", token=ta)
checar("dados lançados no teste continuam lá", len(titulos) == 1,
       f"{len(titulos)} título(s)")
situacao = api("GET", "/api/assinatura/minha", token=ta)["situacao"]
checar("situação final é assinatura ativa", situacao["status"] == "ATIVA" and situacao["liberado"])

print("\n=== 9. Proteção da área do administrador ===")
proibido = api("GET", "/api/admin/assinaturas", token=ta, esperar_erro=True)
checar("assinante não acessa a área do administrador", proibido.get("_status") == 403)
config_proibida = api("GET", "/api/admin/configuracoes", token=ta, esperar_erro=True)
checar("assinante não acessa as configurações", config_proibida.get("_status") == 403)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("Fluxo de assinatura OK.")
