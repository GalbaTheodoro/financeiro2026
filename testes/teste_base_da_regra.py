"""Teste: no item da nota, a base de cálculo sai da REGRA FISCAL.

O que o usuário reclamou: "no item da nota a base de cálculo continua pegando do
item, tem que pegar das regras". A tela calculava a base sozinha (valor do item
menos a redução) e mandava esse número para o servidor; como número digitado
vence a regra, o percentual de base da tabela de regras nunca era usado.

Aqui se confere, com o navegador de verdade:

  * ao abrir o item, a base já aparece com o percentual da regra aplicado;
  * ao gravar, o servidor guarda essa base — e não o total do item;
  * mudando a regra, o rascunho **acompanha** sem ninguém mexer no item;
  * base digitada à mão continua valendo, inclusive depois de fechar e reabrir;
  * apagando o campo, a base volta a seguir a regra.

Uso:  python testes/teste_base_da_regra.py   (com o servidor no ar)
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


# =========================================================================== #
print("=== 1. Empresa, regra fiscal e rascunho ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"base{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock"})
token, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "inscricao_estadual": "0022334455001", "logradouro": "AVENIDA FARIA PEREIRA",
    "numero": "1250", "bairro": "CENTRO", "cidade": "Patrocínio", "uf": "MG",
    "cep": "38740108", "codigo_municipio": "3148004", "crt": "3"}, token)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, token)
api("POST", f"/api/fiscal/tipos/padrao?empresa_id={eid}", None, token)

tipos = api("GET", f"/api/fiscal/tipos?empresa_id={eid}", None, token)
cafe_cru = [t for t in tipos if t["codigo"] == "CAFECRU"][0]["id"]

cafe = api("GET", f"/api/produtos?empresa_id={eid}", None, token)[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: v for k, v in cafe.items() if k in ("codigo", "nome", "unidade_id",
                                              "embalagem", "descricao")},
    "empresa_id": eid, "ncm": "09011110", "cfop_padrao": "6102",
    "unidade_comercial": "SC", "origem": "0", "ativo": True,
    "tipo_fiscal_id": cafe_cru}, token)
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "33444555000166", "rg_ie": "123456789", "indicador_ie": "1",
    "logradouro": "RUA DO CAFE", "numero": "500", "bairro": "CENTRO",
    "cidade": "Santos", "uf": "SP", "cep": "11010000",
    "codigo_municipio": "3548500"}, token)

regra = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Café cru para SP — base reduzida",
    "tipo_item_id": cafe_cru, "cfop": "6102", "uf_origem": "MG", "uf_destino": "SP",
    "icms_cst": "20", "icms_base": 80, "icms_reducao": 25, "icms_aliquota": 12,
    "cst_pis": "01", "cst_cofins": "01", "pis_cofins_base": 90,
    "pis_cofins_reducao": 10, "aliquota_pis": 1.65, "aliquota_cofins": 7.6,
    "ibs_cbs_cst": "200", "ibs_cbs_classe": "200003", "ibs_cbs_base": 100,
    "ibs_cbs_reducao_base": 20, "ibs_cbs_reducao_aliquota": 60,
    "cbs_aliquota": 0.9, "ibs_uf_aliquota": 0.1}, token)

# item de 100 x R$ 1.000 = R$ 100.000
rascunho = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "parceiro_id": cliente["id"], "ambiente": "2", "serie": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1000,
               "cfop": "6102"}]}, token)
nota_id = rascunho["nota"]["id"]
checar("o rascunho já nasce com a base da regra (80% menos 25%)",
       abs(rascunho["itens"][0]["icms_base"] - 60000) < 0.01,
       str(rascunho["itens"][0]["icms_base"]))


def item_gravado():
    return api("GET", f"/api/nfe/{nota_id}", None, token)["itens"][0]


def entrar(pagina):
    pagina.goto(BASE)
    pagina.evaluate(
        "d => { localStorage.setItem('fin_token', d[0]);"
        " localStorage.setItem('fin_empresa', d[1]); }", [token, str(eid)])
    pagina.goto(f"{BASE}/#/notas")
    pagina.reload()
    pagina.wait_for_timeout(2500)


def abrir_itens(pagina):
    """Abre a nota e vai para a etapa dos itens."""
    pagina.evaluate(f"Emissao.abrir({nota_id})")
    pagina.wait_for_timeout(2500)
    pagina.click("[data-etapa='1']")
    pagina.wait_for_timeout(900)


def campo(pagina, nome):
    return pagina.input_value(f"[data-campo='{nome}'][data-linha='0']")


def salvar(pagina):
    pagina.click("#modal-rodape >> text=Salvar")
    pagina.wait_for_timeout(1800)


with sync_playwright() as p:
    navegador = p.chromium.launch()
    pagina = navegador.new_page(viewport={"width": 1280, "height": 1000})
    falhas = []
    pagina.on("pageerror", lambda e: falhas.append(str(e)))
    entrar(pagina)

    # ----------------------------------------------------------------------- #
    print("\n=== 2. A tela mostra a base da regra, não o total do item ===")
    abrir_itens(pagina)
    checar("base do ICMS na tela: 80% de 100.000 menos 25% = 60.000",
           campo(pagina, "icms_base") == "60.000", campo(pagina, "icms_base"))
    checar("base do PIS/COFINS na tela: 90% menos 10% = 81.000",
           campo(pagina, "pis_cofins_base") == "81.000",
           campo(pagina, "pis_cofins_base"))
    checar("base do IBS/CBS na tela: 100% menos 20% = 80.000",
           campo(pagina, "ibs_cbs_base") == "80.000", campo(pagina, "ibs_cbs_base"))
    pagina.screenshot(path=SAIDA / "30-base-da-regra.png", full_page=True)

    salvar(pagina)
    gravado = item_gravado()
    checar("depois de salvar pela tela a base continua a da regra",
           abs(gravado["icms_base"] - 60000) < 0.01
           and abs(gravado["icms_valor"] - 7200) < 0.01,
           f"base {gravado['icms_base']} / icms {gravado['icms_valor']}")
    checar("e o PIS/COFINS também",
           abs(gravado["pis_cofins_base"] - 81000) < 0.01
           and abs(gravado["pis_valor"] - 1336.50) < 0.01,
           f"{gravado['pis_cofins_base']} / {gravado['pis_valor']}")

    # ----------------------------------------------------------------------- #
    print("\n=== 3. Mudando a regra, o rascunho acompanha ===")
    api("PUT", f"/api/fiscal/regras/{regra['id']}", {
        "empresa_id": eid, "nome": regra["nome"], "tipo_item_id": cafe_cru,
        "cfop": "6102", "uf_origem": "MG", "uf_destino": "SP",
        "icms_cst": "20", "icms_base": 50, "icms_reducao": 0, "icms_aliquota": 12,
        "cst_pis": "01", "cst_cofins": "01", "pis_cofins_base": 100,
        "pis_cofins_reducao": 0, "aliquota_pis": 1.65, "aliquota_cofins": 7.6,
        "ibs_cbs_cst": "200", "ibs_cbs_classe": "200003", "ibs_cbs_base": 100,
        "ibs_cbs_reducao_base": 0, "ibs_cbs_reducao_aliquota": 60,
        "cbs_aliquota": 0.9, "ibs_uf_aliquota": 0.1}, token)

    pagina.reload()
    pagina.wait_for_timeout(2500)
    abrir_itens(pagina)
    checar("ao reabrir, a base já vem com o percentual novo (50%)",
           campo(pagina, "icms_base") == "50.000", campo(pagina, "icms_base"))
    # campo de valor nunca fica vazio: zero aparece como 0
    checar("e a redução antiga de 25% virou 0 no item",
           campo(pagina, "icms_reducao") == "0", campo(pagina, "icms_reducao"))
    salvar(pagina)
    gravado = item_gravado()
    checar("gravou a base nova sem ninguém mexer no item",
           abs(gravado["icms_base"] - 50000) < 0.01
           and abs(gravado["icms_valor"] - 6000) < 0.01,
           f"base {gravado['icms_base']} / icms {gravado['icms_valor']}")

    # ----------------------------------------------------------------------- #
    print("\n=== 4. Base digitada à mão continua valendo ===")
    pagina.fill("[data-campo='icms_base'][data-linha='0']", "10.000,00")
    pagina.dispatch_event("[data-campo='icms_base'][data-linha='0']", "input")
    pagina.wait_for_timeout(500)
    salvar(pagina)
    gravado = item_gravado()
    checar("a base digitada vence a regra",
           abs(gravado["icms_base"] - 10000) < 0.01
           and abs(gravado["icms_valor"] - 1200) < 0.01,
           f"base {gravado['icms_base']} / icms {gravado['icms_valor']}")
    checar("o item guarda que essa base foi digitada à mão",
           "icms_base" in (gravado.get("campos_manuais") or ""),
           str(gravado.get("campos_manuais")))

    pagina.reload()
    pagina.wait_for_timeout(2500)
    abrir_itens(pagina)
    checar("fechou e abriu de novo, a base digitada está lá",
           campo(pagina, "icms_base") == "10.000", campo(pagina, "icms_base"))

    # ----------------------------------------------------------------------- #
    print("\n=== 5. Apagando o campo, volta a seguir a regra ===")
    pagina.fill("[data-campo='icms_base'][data-linha='0']", "")
    pagina.dispatch_event("[data-campo='icms_base'][data-linha='0']", "input")
    pagina.wait_for_timeout(600)
    salvar(pagina)
    gravado = item_gravado()
    checar("a base voltou para a da regra",
           abs(gravado["icms_base"] - 50000) < 0.01, str(gravado["icms_base"]))
    checar("e o item não guarda mais base digitada",
           "icms_base" not in (gravado.get("campos_manuais") or ""),
           str(gravado.get("campos_manuais")))
    pagina.screenshot(path=SAIDA / "31-base-manual.png", full_page=True)

    checar("nenhum erro de JavaScript", not falhas, str(falhas[:2]))
    navegador.close()

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S): " + "; ".join(erros))
    sys.exit(1)
print("Base da regra OK — o item da nota calcula a base pela tabela de regras.")
