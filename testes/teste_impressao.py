"""Teste da impressão do contrato em PDF.

Monta um contrato completo (empresa com logotipo, comprador e vendedor com endereço e
formas de pagamento, produto/unidade/modalidade), confere o pacote de dados do endpoint
de impressão e, se o Playwright estiver instalado, abre a folha no navegador e gera o
PDF de verdade em `testes/capturas/contrato.pdf`.

Uso:  python testes/teste_impressao.py   (com o servidor no ar)
"""
import base64
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
SAIDA = pathlib.Path(__file__).parent / "capturas"
SAIDA.mkdir(exist_ok=True)
falhas = []

# PNG 1x1 vermelho — serve de logotipo no teste
LOGO = "data:image/png;base64," + base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c636064f80f00010501013027a2d7"
    "0000000049454e44ae426082"
)).decode()


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

print("\n=== 1. Empresa com logotipo e cláusulas ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Corretor Impressão", "email": f"impressao{sufixo}@teste.com", "senha": "123456",
    "empresa": "Brascafé Assessoria",
})
t = conta["token"]
eid = conta["empresa"]["id"]

empresa = api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "BRASCAFE ASSESSORIA E CORRETAGEM LTDA",
    "nome_fantasia": "BRASCAFÉ",
    "cnpj": "12345678000199", "inscricao_estadual": "001234567",
    "logradouro": "Rua do Café", "numero": "150", "bairro": "Centro",
    "cidade": "Varginha", "uf": "MG", "cep": "37002-000",
    "telefone": "(35) 3222-1000", "email": "contato@brascafe.com.br",
    "site": "www.brascafe.com.br",
    "logo": LOGO,
    "texto_contrato": "As partes elegem o foro da comarca de Varginha/MG para dirimir "
                      "qualquer questão oriunda deste contrato.",
}, t)
checar("logotipo gravado na empresa", (empresa.get("logo") or "").startswith("data:image/"))
checar("cláusulas gravadas", "foro da comarca" in (empresa.get("texto_contrato") or ""))

print("\n=== 2. Partes com endereço e formas de pagamento ===")
comprador = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "OLAM AGRICOLA LTDA",
    "cpf_cnpj": "07028528000894", "logradouro": "Rodovia MG 179", "numero": "km 5",
    "bairro": "Distrito Industrial", "cidade": "Alfenas", "uf": "MG", "cep": "37130-000",
    "telefone": "(35) 3299-0000", "email": "compras@olam.com.br", "contato": "Marcos",
}, t)
vendedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "pessoa": "F", "nome": "ROSALINA SILVEIRA FARIA",
    "cpf_cnpj": "03037474980", "logradouro": "Sítio Boa Vista", "bairro": "Zona Rural",
    "cidade": "Indianópolis", "uf": "MG", "celular": "(34) 99999-0000",
}, t)
api("POST", f"/api/parceiros/{vendedor['id']}/formas-pagamento", {
    "tipo": "PIX", "pix_tipo": "CPF", "pix_chave": "030.374.749-80",
    "apelido": "Pix da produtora", "principal": True,
}, t)
api("POST", f"/api/parceiros/{vendedor['id']}/formas-pagamento", {
    "tipo": "DEPOSITO", "banco_codigo": "756", "banco_nome": "Sicoob",
    "agencia": "3080", "conta": "12345-6", "tipo_conta": "CORRENTE",
    "apelido": "Conta Sicoob",
}, t)

print("\n=== 3. Contrato completo ===")
produtos = api("GET", f"/api/produtos?empresa_id={eid}", token=t)
modalidades = api("GET", f"/api/modalidades?empresa_id={eid}", token=t)
unidades = api("GET", f"/api/unidades?empresa_id={eid}", token=t)
saca = next(u for u in unidades if u["codigo"] == "SC")

contrato = api("POST", "/api/contratos", {
    "empresa_id": eid, "data": "2026-09-10",
    "comprador_id": comprador["id"], "vendedor_id": vendedor["id"],
    "representante_id": conta["usuario"]["id"],
    "produto_id": produtos[0]["id"], "modalidade_id": modalidades[0]["id"],
    "unidade_id": saca["id"],
    "quantidade": 330, "preco_unitario": 1320,
    "comissao_comprador_percentual": 0.5, "comissao_vendedor_percentual": 0.5,
    "numero_compra": "CPA103829", "data_embarque": "2026-09-16",
    "data_pagamento": "2026-09-16",
    "local_coleta": "BRASCAFE ARMAZENS GERAIS LTDA",
    "local_descarga": "OLAM AGRICOLA LTDA - ALFENAS",
    "observacao": "0,50% COMISSÃO COMPRADOR. R$ 1.320,00 LIVRE.",
}, t)

print("\n=== 4. Pacote de dados da impressão ===")
d = api("GET", f"/api/contratos/{contrato['id']}/impressao", token=t)
checar("contrato no pacote", d["contrato"]["numero"] == contrato["numero"], contrato["numero"])
checar("logotipo da empresa vai junto", (d["empresa"].get("logo") or "").startswith("data:image/"))
checar("endereço da empresa montado em uma linha",
       "Varginha/MG" in d["empresa"]["endereco"], d["empresa"]["endereco"])
checar("endereço do comprador montado",
       "Alfenas/MG" in d["comprador"]["endereco"], d["comprador"]["endereco"])
checar("formas de pagamento do vendedor no pacote",
       len(d["vendedor"]["formas"]) == 2, str(len(d["vendedor"]["formas"])))
checar("forma principal marcada",
       any(f["principal"] for f in d["vendedor"]["formas"]))
checar("resumo da conta bancária pronto para imprimir",
       any("Sicoob" in f["resumo"] for f in d["vendedor"]["formas"]),
       next((f["resumo"] for f in d["vendedor"]["formas"] if "Sicoob" in f["resumo"]), ""))
checar("peso de conversão da unidade no pacote",
       d["unidade"] and abs(d["unidade"]["peso_conversao"] - 60) < 0.001)
checar("peso total do contrato", abs(d["contrato"]["peso_total"] - 19800) < 0.001,
       f"{d['contrato']['peso_total']} kg")
checar("comissão total", abs(d["contrato"]["comissao_total"] - 4356.00) < 0.01)
checar("representante no contrato",
       d["contrato"]["representante_nome"] == conta["usuario"]["nome"])

outro = api("POST", "/api/publico/cadastro", {
    "nome": "Intruso", "email": f"intruso{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra Corretora",
})
bloqueado = api("GET", f"/api/contratos/{contrato['id']}/impressao",
                token=outro["token"], esperar_erro=True)
checar("outro assinante não imprime o contrato alheio", bloqueado.get("_status") == 403,
       str(bloqueado.get("_detalhe", ""))[:40])

# --------------------------------------------------------------------------- #
# Geração do PDF pelo navegador
# --------------------------------------------------------------------------- #
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("\n  (Playwright não instalado — pulei a geração do PDF)")
    sync_playwright = None

if sync_playwright:
    print("\n=== 5. Folha impressa no navegador ===")
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1280, "height": 1400})
        pagina.goto(BASE, wait_until="networkidle")
        pagina.evaluate(
            "([token, eid]) => { localStorage.setItem('fin_token', token);"
            " localStorage.setItem('fin_empresa', String(eid)); }", [t, eid])
        pagina.goto(f"{BASE}/#/contratos")
        pagina.reload(wait_until="networkidle")   # o hash sozinho não recarrega a página
        pagina.wait_for_timeout(1800)

        # monta a folha sem depender de pop-up: usa as próprias funções da tela
        html = pagina.evaluate(
            "async (id) => {"
            " const d = await Api.get(`/api/contratos/${id}/impressao`);"
            " return `<!doctype html><html><head><meta charset=\"utf-8\">"
            "<style>${Impressao.estilo()}</style></head>"
            "<body><div class=\"folha\">${Impressao.folha(d)}</div></body></html>`; }",
            contrato["id"])
        ok_html = "Contrato de intermediação" in html and "CONTRATO" not in html[:50]
        checar("folha montada pelo Impressao.folha()", "Contrato de intermediação" in html)

        folha = navegador.new_page()
        folha.set_content(html, wait_until="load")
        folha.wait_for_timeout(400)
        texto = folha.inner_text("body")

        for rotulo, esperado in [
            ("razão social da corretora", "BRASCAFE ASSESSORIA"),
            ("nome do comprador", "OLAM AGRICOLA"),
            ("nome do vendedor", "ROSALINA SILVEIRA FARIA"),
            ("CNPJ do comprador", "07028528000894"),
            ("mercadoria", "CAFE ARABICA"),
            ("quantidade", "330,000"),
            ("peso total", "19.800,000 kg"),
            ("valor negociado", "R$ 435.600,00"),
            ("valor por extenso", "quatrocentos e trinta e cinco mil e seiscentos reais"),
            ("comissão do comprador", "R$ 2.178,00"),
            ("total da corretagem", "R$ 4.356,00"),
            ("Pix do vendedor", "030.374.749-80"),
            ("conta bancária do vendedor", "Sicoob"),
            ("local de coleta", "BRASCAFE ARMAZENS GERAIS"),
            ("cláusula do foro", "foro da comarca de Varginha"),
            ("representante", "Corretor Impressão"),
        ]:
            checar(f"folha traz {rotulo}", esperado in texto, "" if esperado in texto else esperado)

        tem_logo = folha.query_selector(".topo .logo img") is not None
        checar("logotipo no cabeçalho", tem_logo)
        assinaturas = len(folha.query_selector_all(".linha-assinatura"))
        checar("três campos de assinatura", assinaturas == 3, str(assinaturas))

        folha.screenshot(path=SAIDA / "contrato-impressao.png", full_page=True)
        folha.pdf(path=SAIDA / "contrato.pdf", format="A4",
                  margin={"top": "14mm", "bottom": "14mm", "left": "13mm", "right": "13mm"})
        arquivo = SAIDA / "contrato.pdf"
        ok_pdf = arquivo.exists() and arquivo.stat().st_size > 5000
        checar("PDF gerado", ok_pdf, f"{arquivo.stat().st_size // 1024} KB")

        # uma folha só: medido no modo de impressão, contra a área útil do A4
        # (297mm - 14mm de margem em cima e embaixo = 269mm)
        folha.emulate_media(media="print")
        folha.wait_for_timeout(200)
        altura_mm = folha.evaluate(
            "() => document.querySelector('.folha').getBoundingClientRect().height / 3.7795")
        checar("cabe em uma página A4", altura_mm <= 269, f"{altura_mm:.0f}mm de 269mm")

        navegador.close()

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("Impressão do contrato OK — PDF em testes/capturas/contrato.pdf")
