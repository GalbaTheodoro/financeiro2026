"""Teste da edição: a janela não fecha sozinha e dá para salvar em qualquer etapa.

Confere o que o usuário reclamou:
  * o "x", a tecla Esc e o clique fora não jogam fora o que foi digitado —
    aparece o aviso com Continuar editando / Salvar e sair / Sair sem salvar;
  * o botão Salvar aparece em TODAS as etapas da NF-e e do contrato;
  * depois de salvar, você continua na mesma etapa (não volta para o começo);
  * o que foi digitado chega gravado no servidor.

Uso:  python testes/teste_edicao.py   (com o servidor no ar)
"""
import json
import pathlib
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SAIDA = pathlib.Path(__file__).parent / "capturas"
SAIDA.mkdir(exist_ok=True)
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


def entrar(pagina, token, empresa_id, rota):
    pagina.goto(BASE)
    pagina.evaluate(
        "d => { localStorage.setItem('fin_token', d[0]);"
        " localStorage.setItem('fin_empresa', d[1]); }",
        [token, str(empresa_id)],
    )
    pagina.goto(f"{BASE}/#/{rota}")
    pagina.reload()
    pagina.wait_for_timeout(3000)


def aberta(pagina):
    return not pagina.eval_on_selector("#modal-fundo", "e => e.classList.contains('oculto')")


def rotulos(pagina):
    return pagina.eval_on_selector_all("#modal-rodape .btn", "b => b.map((x) => x.textContent)")


# =========================================================================== #
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"edicao{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock",
})
token, eid = conta["token"], conta["empresa"]["id"]

api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "inscricao_estadual": "0022334455001", "logradouro": "AVENIDA FARIA PEREIRA",
    "numero": "1250", "bairro": "CENTRO", "cidade": "Patrocínio", "uf": "MG",
    "cep": "38740108", "codigo_municipio": "3148004", "crt": "1",
}, token)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, token)
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "AMBOS", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "33444555000166", "rg_ie": "123456789", "indicador_ie": "1",
    "logradouro": "RUA DO CAFE", "numero": "500", "bairro": "CENTRO",
    "cidade": "Santos", "uf": "SP", "cep": "11010000", "codigo_municipio": "3548500"}, token)
vendedor = api("POST", "/api/parceiros",
               {"empresa_id": eid, "tipo": "AMBOS", "nome": "ROSALINA SILVEIRA"}, token)
api("POST", "/api/nfe/series",
    {"empresa_id": eid, "serie": "1", "ambiente": "2", "proximo_numero": 120}, token)

cafe = api("GET", f"/api/produtos?empresa_id={eid}", None, token)[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: v for k, v in cafe.items() if k in ("codigo", "nome", "unidade_id",
                                              "embalagem", "descricao",
                                              "categoria_id", "marca_id")},
    "empresa_id": eid, "ncm": "09011110", "cfop_padrao": "6101", "cst_icms": "102",
    "unidade_comercial": "SC", "origem": "0", "ativo": True}, token)
unidade = api("GET", f"/api/unidades?empresa_id={eid}", None, token)[0]
modalidade = api("GET", f"/api/modalidades?empresa_id={eid}", None, token)[0]

venda = api("POST", "/api/contratos", {
    "empresa_id": eid, "tipo": "VENDA", "comprador_id": cliente["id"],
    "produto_id": cafe["id"], "unidade_id": unidade["id"],
    "modalidade_id": modalidade["id"], "quantidade": 330, "preco_unitario": 1320}, token)
rascunho = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "contrato_id": venda["id"], "ambiente": "2", "serie": "1",
    "parcelas": [{"vencimento": "2026-10-19", "valor": 435600}]}, token)
nota_id = rascunho["nota"]["id"]

corretagem = api("POST", "/api/contratos", {
    "empresa_id": eid, "tipo": "CORRETAGEM", "comprador_id": cliente["id"],
    "vendedor_id": vendedor["id"], "produto_id": cafe["id"], "unidade_id": unidade["id"],
    "modalidade_id": modalidade["id"], "quantidade": 100, "preco_unitario": 1000}, token)

with sync_playwright() as p:
    navegador = p.chromium.launch()

    # ------------------------------------------------------------- NF-e (celular)
    print("\n=== 1. Emissão de NF-e no celular ===")
    pagina = navegador.new_page(viewport={"width": 390, "height": 844})
    falhas_js = []
    pagina.on("pageerror", lambda e: falhas_js.append(str(e)))
    entrar(pagina, token, eid, "notas")
    pagina.evaluate(f"Emissao.abrir({nota_id})")
    pagina.wait_for_timeout(2500)

    for i, nome in enumerate(["Nota", "Itens", "Pagamento", "Transporte"]):
        if i:
            pagina.click(f"[data-etapa='{i}']")
            pagina.wait_for_timeout(600)
        checar(f"etapa {i + 1} ({nome}) tem botão Salvar", "Salvar" in rotulos(pagina),
               str(rotulos(pagina)))

    pagina.click("[data-etapa='1']")
    pagina.wait_for_timeout(600)
    campo = pagina.query_selector('[data-campo="quantidade"]')
    campo.click()
    campo.fill("")
    pagina.keyboard.type("444", delay=30)
    pagina.wait_for_timeout(300)

    pagina.click("#modal-fechar")
    pagina.wait_for_timeout(600)
    checar("o x pergunta antes de perder o que foi digitado",
           aberta(pagina) and pagina.query_selector("#pergunta-saida") is not None)
    pagina.screenshot(path=str(SAIDA / "edicao-aviso-saida.png"))

    pagina.click("#saida-continuar")
    pagina.wait_for_timeout(400)
    checar("continuar editando mantém o valor",
           pagina.eval_on_selector('[data-campo="quantidade"]', "e => e.value") == "444")

    pagina.keyboard.press("Escape")
    pagina.wait_for_timeout(500)
    checar("tecla Esc não fecha com edição pendente", aberta(pagina))
    if pagina.query_selector("#saida-continuar"):
        pagina.click("#saida-continuar")
        pagina.wait_for_timeout(300)

    pagina.click("#modal-rodape .btn >> text=Salvar")
    pagina.wait_for_timeout(2500)
    checar("depois de salvar continua na mesma etapa", pagina.evaluate("Emissao._etapa") == 1,
           f"etapa {pagina.evaluate('Emissao._etapa')}")
    gravada = api("GET", f"/api/nfe/{nota_id}", None, token)
    checar("o que foi digitado chegou gravado no servidor",
           abs(gravada["itens"][0]["quantidade"] - 444) < 1e-6,
           str(gravada["itens"][0]["quantidade"]))

    pagina.click("#modal-fechar")
    pagina.wait_for_timeout(600)
    checar("sem edição pendente a janela fecha no x", not aberta(pagina))
    pagina.close()

    # ------------------------------------------------------------- NF-e (desktop)
    print("\n=== 2. Clique fora da janela, no computador ===")
    pagina = navegador.new_page(viewport={"width": 1440, "height": 900})
    pagina.on("pageerror", lambda e: falhas_js.append(str(e)))
    entrar(pagina, token, eid, "notas")
    pagina.evaluate(f"Emissao.abrir({nota_id})")
    pagina.wait_for_timeout(2500)
    pagina.click("[data-etapa='1']")
    pagina.wait_for_timeout(600)
    campo = pagina.query_selector('[data-campo="quantidade"]')
    campo.click()
    campo.fill("")
    pagina.keyboard.type("777", delay=30)
    pagina.wait_for_timeout(300)
    pagina.mouse.click(30, 450)
    pagina.wait_for_timeout(600)
    checar("clique fora não perde o que foi digitado",
           aberta(pagina) and pagina.query_selector("#pergunta-saida") is not None)

    pagina.click("#saida-salvar")
    pagina.wait_for_timeout(2500)
    checar("o botão Salvar e sair grava e fecha", not aberta(pagina))
    gravada = api("GET", f"/api/nfe/{nota_id}", None, token)
    checar("salvar e sair gravou o valor",
           abs(gravada["itens"][0]["quantidade"] - 777) < 1e-6,
           str(gravada["itens"][0]["quantidade"]))
    pagina.close()

    # ------------------------------------------------------------------ contrato
    print("\n=== 3. Contrato em etapas ===")
    pagina = navegador.new_page(viewport={"width": 390, "height": 844})
    pagina.on("pageerror", lambda e: falhas_js.append(str(e)))
    entrar(pagina, token, eid, "contratos")
    pagina.evaluate(f"Contratos.formulario({json.dumps(corretagem)})")
    pagina.wait_for_timeout(2000)
    for i in range(4):
        if i:
            pagina.click(f"[data-etapa='{i}']")
            pagina.wait_for_timeout(500)
        checar(f"contrato: etapa {i + 1} tem botão Salvar", "Salvar" in rotulos(pagina),
               str(rotulos(pagina)))

    destino = pagina.evaluate(
        "document.querySelector('[name=quantidade]').closest('[data-painel]').dataset.painel")
    pagina.click(f"[data-etapa='{destino}']")
    pagina.wait_for_timeout(600)
    quantidade = pagina.query_selector("[name=quantidade]")
    quantidade.click()
    quantidade.fill("250")
    pagina.wait_for_timeout(300)
    pagina.click("#modal-rodape .btn >> text=Salvar")
    pagina.wait_for_timeout(2500)
    checar("contrato: a janela continua aberta depois de salvar", aberta(pagina))
    salvo = api("GET", f"/api/contratos/{corretagem['id']}", None, token)
    checar("contrato: quantidade gravada", abs(float(salvo["quantidade"]) - 250) < 1e-6,
           str(salvo["quantidade"]))
    checar("contrato: continua na mesma etapa",
           pagina.eval_on_selector(".etapa.ativa", "e => e.dataset.etapa") == destino)
    pagina.close()

    if falhas_js:
        checar("nenhum erro de JavaScript", False, str(falhas_js[:3]))
    navegador.close()

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} falha(s): " + "; ".join(erros))
    sys.exit(1)
print("Edição OK — a janela não fecha sozinha e o Salvar está em todas as etapas.")
