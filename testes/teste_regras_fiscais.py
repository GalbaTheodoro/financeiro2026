"""Teste das regras fiscais: tipo de cliente x tipo de item.

Confere que o imposto de cada item da nota deixa de vir do cadastro do produto e
passa a vir da tabela de regras, escolhendo sempre a linha mais específica:

  * café cru para indústria dentro de MG  -> diferimento (CST 51, sem destaque);
  * café cru para indústria em SP         -> 7% de ICMS;
  * café cru para qualquer outro cliente  -> regra geral do item;
  * CFOP digitado no item                 -> escolhe a legislação daquele CFOP;
  * item sem regra nenhuma                -> nasce sem CST (o produto não decide).

Uso:  python testes/teste_regras_fiscais.py   (com o servidor no ar)
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
erros = []


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
    except urllib.error.HTTPError as erro:
        if not esperar_erro:
            raise
        corpo = json.loads(erro.read() or b"{}")
        corpo["_status"] = erro.code
        return corpo


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


def classificacao(empresa_id, token):
    """A categoria e a marca padrão da empresa — o produto não salva sem elas."""
    categoria = api("GET", f"/api/categorias-produto?empresa_id={empresa_id}", None, token)
    marca = api("GET", f"/api/marcas-produto?empresa_id={empresa_id}", None, token)
    return {"categoria_id": categoria[0]["id"], "marca_id": marca[0]["id"]}


# =========================================================================== #
print("=== 1. Conta, tipos fiscais e cadastros ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"regras{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock",
})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "inscricao_estadual": "0022334455001", "logradouro": "AVENIDA FARIA PEREIRA",
    "numero": "1250", "bairro": "CENTRO", "cidade": "Patrocínio", "uf": "MG",
    "cep": "38740108", "codigo_municipio": "3148004", "crt": "3"}, t)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, t)

padrao = api("POST", f"/api/fiscal/tipos/padrao?empresa_id={eid}", None, t)
checar("os tipos sugeridos são criados de uma vez", padrao["criados"] >= 10,
       f"{padrao['criados']} tipos")
de_novo = api("POST", f"/api/fiscal/tipos/padrao?empresa_id={eid}", None, t)
checar("rodar de novo não duplica nada", de_novo["criados"] == 0)

tipos = api("GET", f"/api/fiscal/tipos?empresa_id={eid}", None, t)
por_codigo = {(x["aplicacao"], x["codigo"]): x["id"] for x in tipos}
industria = por_codigo[("CLIENTE", "INDUSTRIA")]
nao_contrib = por_codigo[("CLIENTE", "NAOCONTRIB")]
cafe_cru = por_codigo[("ITEM", "CAFECRU")]
servico = por_codigo[("ITEM", "SERVICO")]
checar("os tipos nascem separados por aplicação",
       len([x for x in tipos if x["aplicacao"] == "CLIENTE"]) >= 5
       and len([x for x in tipos if x["aplicacao"] == "ITEM"]) >= 5)

repetido = api("POST", "/api/fiscal/tipos", {
    "empresa_id": eid, "aplicacao": "ITEM", "codigo": "CAFECRU", "nome": "Outro"},
    t, esperar_erro=True)
checar("código repetido na mesma aplicação é recusado", repetido.get("_status") == 400)

# produtos e clientes com os tipos
produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe = produtos[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: v for k, v in cafe.items() if k in ("codigo", "nome", "unidade_id",
                                              "embalagem", "descricao",
                                              "categoria_id", "marca_id")},
    "empresa_id": eid, "ncm": "09011110", "cfop_padrao": "5102",
    "unidade_comercial": "SC", "origem": "0", "ativo": True,
    "tipo_fiscal_id": cafe_cru}, t)
conferido = api("GET", f"/api/produtos?empresa_id={eid}", None, t)[0]
checar("o produto guarda o tipo fiscal", conferido["tipo_fiscal_id"] == cafe_cru)

endereco = {"logradouro": "RUA DO CAFE", "numero": "500", "bairro": "CENTRO",
            "cep": "11010000", "indicador_ie": "1", "rg_ie": "123456789"}
torrefacao_mg = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO MINEIRA LTDA",
    "cpf_cnpj": "33444555000166", "cidade": "Belo Horizonte", "uf": "MG",
    "codigo_municipio": "3106200", "tipo_fiscal_id": industria, **endereco}, t)
torrefacao_sp = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "11444777000161", "cidade": "Santos", "uf": "SP",
    "codigo_municipio": "3548500", "tipo_fiscal_id": industria, **endereco}, t)
consumidor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "PADARIA DO CENTRO",
    "cpf_cnpj": "11222333000181", "cidade": "Uberlândia", "uf": "MG",
    "codigo_municipio": "3170206", "tipo_fiscal_id": nao_contrib, **endereco}, t)
checar("o cliente guarda o tipo fiscal", torrefacao_mg["tipo_fiscal_id"] == industria)

# =========================================================================== #
print("\n=== 2. A tabela de regras ===")
geral = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Café cru — regra geral",
    "tipo_item_id": cafe_cru, "cfop": "5102", "icms_cst": "00", "icms_aliquota": 18,
    "cst_pis": "01", "aliquota_pis": 1.65, "cst_cofins": "01", "aliquota_cofins": 7.6}, t)
dentro_mg = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Café cru para indústria em MG (diferimento)",
    "tipo_cliente_id": industria, "tipo_item_id": cafe_cru,
    "uf_origem": "MG", "uf_destino": "MG", "operacao": "SAIDA",
    "cfop": "5102", "icms_cst": "51", "icms_aliquota": 18,
    "cst_pis": "01", "aliquota_pis": 1.65, "cst_cofins": "01", "aliquota_cofins": 7.6,
    "ibs_cbs_cst": "000", "ibs_cbs_classe": "000001", "cbs_aliquota": 0.9,
    "ibs_uf_aliquota": 0.1, "observacao": "Diferimento do café cru — confirmar com o contador."}, t)
fora = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Café cru para indústria fora de MG",
    "tipo_cliente_id": industria, "tipo_item_id": cafe_cru,
    "uf_origem": "MG", "uf_destino": "SP",
    "cfop": "6102", "icms_cst": "00", "icms_aliquota": 7,
    "cst_pis": "01", "aliquota_pis": 1.65, "cst_cofins": "01", "aliquota_cofins": 7.6}, t)
checar("a regra mais específica tem a maior pontuação",
       dentro_mg["especificidade"] > fora["especificidade"] > geral["especificidade"],
       f"{dentro_mg['especificidade']} > {fora['especificidade']} > {geral['especificidade']}")
checar("a lista mostra o nome dos tipos",
       dentro_mg["tipo_cliente_nome"] == "Indústria"
       and geral["tipo_cliente_nome"] == "Qualquer cliente")

invalida = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Errada", "icms_aliquota": 150}, t, esperar_erro=True)
checar("alíquota fora de 0 a 100 é recusada", invalida.get("_status") == 400)
trocada = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Errada", "tipo_cliente_id": cafe_cru}, t, esperar_erro=True)
checar("tipo de item no lugar de tipo de cliente é recusado", trocada.get("_status") == 400)

# =========================================================================== #
print("\n=== 3. Qual regra ganha (simulação) ===")
def simular(parceiro_id, produto_id=None, cfop=None):
    return api("POST", "/api/fiscal/simular", {
        "empresa_id": eid, "parceiro_id": parceiro_id,
        "produto_id": produto_id or cafe["id"], "cfop": cfop, "operacao": "SAIDA"}, t)

dentro = simular(torrefacao_mg["id"])
checar("indústria dentro de MG cai na regra do diferimento",
       dentro["regra"]["nome"].startswith("Café cru para indústria em MG"),
       dentro["regra"]["nome"])
checar("e a regra traz o CST 51 e o CFOP 5102",
       dentro["regra"]["valores"]["icms_cst"] == "51"
       and dentro["regra"]["valores"]["cfop"] == "5102")

paulista = simular(torrefacao_sp["id"], cfop="6102")
checar("indústria em SP cai na regra de fora do estado",
       paulista["regra"]["nome"].endswith("fora de MG")
       and paulista["regra"]["valores"]["icms_aliquota"] == 7.0,
       paulista["regra"]["nome"])

padaria = simular(consumidor["id"])
checar("cliente de outro tipo cai na regra geral do item",
       padaria["regra"]["nome"] == "Café cru — regra geral"
       and padaria["regra"]["valores"]["icms_aliquota"] == 18.0,
       padaria["regra"]["nome"])

sem_tipo = api("POST", "/api/produtos", {
    **classificacao(eid, t),
    "empresa_id": eid, "codigo": "SERV1", "nome": "CORRETAGEM",
    "unidade_id": cafe["unidade_id"], "ncm": "00000000", "cfop_padrao": "5949"}, t)
nenhuma = simular(torrefacao_mg["id"], sem_tipo["id"])
checar("item sem tipo fiscal não casa com regra de item específico",
       nenhuma["regra"] is None or nenhuma["regra"]["nome"] != "Café cru — regra geral",
       (nenhuma["regra"] or {}).get("nome", "nenhuma"))

# =========================================================================== #
print("\n=== 4. A nota usa a regra em vez do cadastro do produto ===")
api("POST", "/api/nfe/series",
    {"empresa_id": eid, "serie": "1", "ambiente": "2", "proximo_numero": 1}, t)


def rascunho(parceiro_id, produto_id=None):
    return api("POST", "/api/nfe/rascunho", {
        "empresa_id": eid, "parceiro_id": parceiro_id, "ambiente": "2", "serie": "1",
        "itens": [{"produto_id": produto_id or cafe["id"], "quantidade": 100,
                   "valor_unitario": 1000}]}, t)

nota_mg = rascunho(torrefacao_mg["id"])
item = nota_mg["itens"][0]
checar("o item da nota nasce com o CST da regra, não com o do produto",
       item["icms_cst"] == "51" and item["cfop"] == "5102",
       f"CST {item['icms_cst']} / CFOP {item['cfop']}")
checar("diferimento não destaca ICMS mesmo com alíquota na regra",
       abs(item["icms_valor"]) < 0.01, str(item["icms_valor"]))
checar("PIS e COFINS vêm da regra",
       abs(item["pis_valor"] - 1650) < 0.01 and abs(item["cofins_valor"] - 7600) < 0.01)
checar("o IBS/CBS da regra chega no item",
       item["ibs_cbs_cst"] == "000" and item["ibs_cbs_classe"] == "000001"
       and abs(item["cbs_valor"] - 900) < 0.01, str(item["cbs_valor"]))
checar("o item diz qual regra foi usada",
       (item.get("regra_nome") or "").startswith("Café cru para indústria em MG"),
       str(item.get("regra_nome")))

nota_sp = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "parceiro_id": torrefacao_sp["id"], "ambiente": "2", "serie": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1000,
               "cfop": "6102"}]}, t)
item_sp = nota_sp["itens"][0]
checar("o mesmo produto para SP sai com 7% e CFOP 6102",
       item_sp["icms_cst"] == "00" and item_sp["cfop"] == "6102"
       and abs(item_sp["icms_valor"] - 7000) < 0.01,
       f"{item_sp['cfop']} / {item_sp['icms_valor']}")

nota_padaria = rascunho(consumidor["id"])
checar("e para a padaria sai com os 18% da regra geral",
       abs(nota_padaria["itens"][0]["icms_valor"] - 18000) < 0.01,
       str(nota_padaria["itens"][0]["icms_valor"]))

nota_servico = rascunho(torrefacao_mg["id"], sem_tipo["id"])
checar("sem regra o item nasce sem CST — o produto não decide mais imposto",
       not nota_servico["itens"][0]["icms_cst"]
       and abs(nota_servico["itens"][0]["icms_valor"]) < 0.01,
       str(nota_servico["itens"][0]["icms_cst"]))
checar("mas o CFOP padrão do produto ainda serve de sugestão",
       nota_servico["itens"][0]["cfop"] == "5949", nota_servico["itens"][0]["cfop"])

# =========================================================================== #
print("\n=== 4b. O CFOP faz parte do cruzamento ===")
api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Café cru — devolução (CFOP 1202)",
    "tipo_item_id": cafe_cru, "cfop": "1202",
    "icms_cst": "00", "icms_aliquota": 4, "cst_pis": "01", "cst_cofins": "01"}, t)
por_cfop = simular(torrefacao_mg["id"], cfop="1202")
checar("com o CFOP 1202 ganha a regra daquele CFOP",
       por_cfop["regra"]["nome"].endswith("(CFOP 1202)"), por_cfop["regra"]["nome"])
checar("e o resumo da regra mostra o CFOP", "CFOP 1202" in por_cfop["regra"]["resumo"])
sem_cfop = simular(torrefacao_mg["id"], cfop="5102")
checar("com outro CFOP volta a regra do diferimento",
       sem_cfop["regra"]["nome"].startswith("Café cru para indústria em MG"),
       sem_cfop["regra"]["nome"])

nota_cfop = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "parceiro_id": torrefacao_mg["id"], "ambiente": "2", "serie": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1000,
               "cfop": "1202"}]}, t)
checar("na nota, o CFOP digitado no item escolhe a legislação",
       abs(nota_cfop["itens"][0]["icms_valor"] - 4000) < 0.01
       and nota_cfop["itens"][0]["cfop"] == "1202",
       str(nota_cfop["itens"][0]["icms_valor"]))

print("\n=== 4c. Tabela de classificação tributária (cClassTrib) ===")
tabela = api("GET", "/api/fiscal/cclasstrib", None, t)
checar("a tabela vem com códigos e com a lista de CST",
       len(tabela["linhas"]) > 20 and len(tabela["cst"]) >= 7,
       f"{len(tabela['linhas'])} códigos")
integral = [l for l in tabela["linhas"] if l["codigo"] == "000001"]
checar("o código 000001 é a tributação integral",
       integral and integral[0]["cst"] == "000"
       and "integralmente" in integral[0]["descricao"].lower())
busca = api("GET", "/api/fiscal/cclasstrib?busca=exporta", None, t)
checar("procurar por palavra acha os códigos de exportação",
       any(l["codigo"] == "410004" for l in busca["linhas"]),
       f"{len(busca['linhas'])} achados")
por_cst = api("GET", "/api/fiscal/cclasstrib?cst=410", None, t)
checar("filtrar por CST devolve só aquele CST",
       por_cst["linhas"] and all(l["cst"] == "410" for l in por_cst["linhas"]))
acento = api("GET", "/api/fiscal/cclasstrib?busca=imunidade", None, t)
checar("a busca ignora acento", isinstance(acento["linhas"], list))

# =========================================================================== #
print("\n=== 4d. Base de cálculo, redução de base e redução de alíquota ===")
completa = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Café cru — com bases e reduções",
    "tipo_item_id": cafe_cru, "cfop": "5949",
    "icms_cst": "20", "icms_base": 80, "icms_reducao": 25, "icms_aliquota": 18,
    "cst_pis": "01", "cst_cofins": "01", "pis_cofins_base": 90,
    "pis_cofins_reducao": 10, "aliquota_pis": 1.65, "aliquota_cofins": 7.6,
    "ibs_cbs_cst": "200", "ibs_cbs_classe": "200003", "ibs_cbs_base": 100,
    "ibs_cbs_reducao_base": 20, "ibs_cbs_reducao_aliquota": 60,
    "cbs_aliquota": 0.9, "ibs_uf_aliquota": 0.1, "ibs_mun_aliquota": 0}, t)
checar("a regra guarda as três bases e as reduções",
       completa["icms_base"] == 80 and completa["pis_cofins_base"] == 90
       and completa["ibs_cbs_reducao_base"] == 20
       and completa["ibs_cbs_reducao_aliquota"] == 60,
       f"icms {completa['icms_base']} / pis {completa['pis_cofins_base']}")

# item de 100 x 1.000 = 100.000
com_bases = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "parceiro_id": consumidor["id"], "ambiente": "2", "serie": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1000,
               "cfop": "5949"}]}, t)["itens"][0]
# 100.000 x 80% = 80.000, menos 25% de redução = 60.000; 18% = 10.800
checar("base do ICMS: 80% do item, menos 25% de redução",
       abs(com_bases["icms_base"] - 60000) < 0.01, str(com_bases["icms_base"]))
checar("e o ICMS sai de 18% sobre essa base",
       abs(com_bases["icms_valor"] - 10800) < 0.01, str(com_bases["icms_valor"]))
# 100.000 x 90% = 90.000, menos 10% = 81.000; PIS 1,65% = 1.336,50
checar("base do PIS/COFINS: 90% do item, menos 10% de redução",
       abs(com_bases["pis_cofins_base"] - 81000) < 0.01, str(com_bases["pis_cofins_base"]))
checar("e o PIS sai de 1,65% sobre essa base",
       abs(com_bases["pis_valor"] - 1336.50) < 0.01, str(com_bases["pis_valor"]))
checar("a COFINS também", abs(com_bases["cofins_valor"] - 6156) < 0.01,
       str(com_bases["cofins_valor"]))
# 100.000 menos 20% = 80.000; CBS 0,9% reduzida em 60% = 0,36% -> 288,00
checar("base do IBS/CBS: 100% do item, menos 20% de redução",
       abs(com_bases["ibs_cbs_base"] - 80000) < 0.01, str(com_bases["ibs_cbs_base"]))
checar("a redução de alíquota de 60% derruba a CBS para 0,36%",
       abs(com_bases["cbs_aliquota"] - 0.36) < 0.0001
       and abs(com_bases["cbs_valor"] - 288) < 0.01,
       f"{com_bases['cbs_aliquota']}% = {com_bases['cbs_valor']}")
checar("e o IBS estadual para 0,04%",
       abs(com_bases["ibs_uf_aliquota"] - 0.04) < 0.0001
       and abs(com_bases["ibs_uf_valor"] - 32) < 0.01,
       f"{com_bases['ibs_uf_aliquota']}% = {com_bases['ibs_uf_valor']}")
checar("o cClassTrib da regra chega no item", com_bases["ibs_cbs_classe"] == "200003")

sem_base = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Café cru — base cheia", "tipo_item_id": cafe_cru,
    "cfop": "5910", "icms_cst": "00", "icms_aliquota": 12,
    "cst_pis": "01", "aliquota_pis": 1.65}, t)
checar("regra sem base informada nasce com 100%",
       sem_base["icms_base"] == 100 and sem_base["pis_cofins_base"] == 100
       and sem_base["ibs_cbs_base"] == 100)
cheio = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "parceiro_id": consumidor["id"], "ambiente": "2", "serie": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1000,
               "cfop": "5910"}]}, t)["itens"][0]
checar("sem base informada o item usa o valor inteiro",
       abs(cheio["icms_base"] - 100000) < 0.01
       and abs(cheio["pis_cofins_base"] - 100000) < 0.01,
       f"{cheio['icms_base']} / {cheio['pis_cofins_base']}")

fora_faixa = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Errada", "icms_base": 120}, t, esperar_erro=True)
checar("base fora de 0 a 100 é recusada", fora_faixa.get("_status") == 400)

# =========================================================================== #
print("\n=== 4e. A tela mostra a conta da base antes de salvar ===")
# a janela da regra manda os percentuais digitados e recebe a conta pronta
conta = api("POST", "/api/fiscal/calcular", {
    "empresa_id": eid, "valor": 100000,
    "valores": {"icms_cst": "20", "icms_base": 80, "icms_reducao": 25,
                "icms_aliquota": 18, "pis_cofins_base": 90, "pis_cofins_reducao": 10,
                "aliquota_pis": 1.65, "aliquota_cofins": 7.6,
                "ibs_cbs_base": 100, "ibs_cbs_reducao_base": 20,
                "ibs_cbs_reducao_aliquota": 60, "cbs_aliquota": 0.9,
                "ibs_uf_aliquota": 0.1, "ibs_mun_aliquota": 0}}, t)["calculo"]
checar("a conta mostra a base cheia e a base já reduzida",
       abs(conta["icms"]["base_cheia"] - 80000) < 0.01
       and abs(conta["icms"]["base"] - 60000) < 0.01,
       f"{conta['icms']['base_cheia']} -> {conta['icms']['base']}")
checar("o percentual de base volta para a tela explicar a conta",
       conta["icms"]["percentual_base"] == 80 and conta["icms"]["reducao"] == 25)
checar("a conta da tela dá o mesmo ICMS que a nota gravou",
       abs(conta["icms"]["valor"] - com_bases["icms_valor"]) < 0.01,
       f"{conta['icms']['valor']} x {com_bases['icms_valor']}")
checar("e o mesmo PIS, COFINS, CBS e IBS",
       abs(conta["pis_cofins"]["valor_pis"] - com_bases["pis_valor"]) < 0.01
       and abs(conta["pis_cofins"]["valor_cofins"] - com_bases["cofins_valor"]) < 0.01
       and abs(conta["ibs_cbs"]["valor_cbs"] - com_bases["cbs_valor"]) < 0.01
       and abs(conta["ibs_cbs"]["valor_ibs_uf"] - com_bases["ibs_uf_valor"]) < 0.01,
       f"pis {conta['pis_cofins']['valor_pis']} / cbs {conta['ibs_cbs']['valor_cbs']}")
checar("o total de impostos do item é a soma de tudo",
       abs(conta["total_impostos"] - (10800 + 1336.50 + 6156 + 288 + 32)) < 0.01,
       str(conta["total_impostos"]))

metade = api("POST", "/api/fiscal/calcular", {
    "empresa_id": eid, "valor": 1000,
    "valores": {"icms_cst": "00", "icms_base": 50, "icms_aliquota": 18}}, t)["calculo"]
checar("base de 50% sobre R$ 1.000 dá R$ 500 e ICMS de R$ 90",
       abs(metade["icms"]["base"] - 500) < 0.01
       and abs(metade["icms"]["valor"] - 90) < 0.01,
       f"{metade['icms']['base']} / {metade['icms']['valor']}")

sem_nada = api("POST", "/api/fiscal/calcular", {
    "empresa_id": eid, "valor": 1000, "valores": {}}, t)["calculo"]
checar("sem nada preenchido a base nasce com 100% do valor",
       abs(sem_nada["icms"]["base"] - 1000) < 0.01
       and sem_nada["icms"]["percentual_base"] == 100)

conta_ruim = api("POST", "/api/fiscal/calcular", {
    "empresa_id": eid, "valor": 1000, "valores": {"icms_base": 150}},
    t, esperar_erro=True)
checar("percentual de base fora de 0 a 100 também é recusado na conferência",
       conta_ruim.get("_status") == 400)

# =========================================================================== #
print("\n=== 4f. Zero na regra é zero mesmo ===")
zerada = api("POST", "/api/fiscal/calcular", {
    "empresa_id": eid, "valor": 1000,
    "valores": {"icms_cst": "40", "icms_base": 0, "icms_aliquota": 0,
                "pis_cofins_base": 0, "aliquota_pis": 0, "aliquota_cofins": 0,
                "ibs_cbs_base": 0, "cbs_aliquota": 0, "ibs_uf_aliquota": 0}}, t)["calculo"]
checar("base 0% zera a base, não vira 100%",
       zerada["icms"]["base"] == 0 and zerada["pis_cofins"]["base"] == 0
       and zerada["ibs_cbs"]["base"] == 0,
       f"{zerada['icms']['base']} / {zerada['pis_cofins']['base']}")
checar("alíquota 0% não cai em padrão nenhum",
       zerada["ibs_cbs"]["aliquota_cbs"] == 0
       and zerada["ibs_cbs"]["aliquota_ibs_uf"] == 0
       and zerada["total_impostos"] == 0, str(zerada["total_impostos"]))

sem_ibs = api("POST", "/api/fiscal/regras", {
    "empresa_id": eid, "nome": "Café cru — isento, sem IBS/CBS",
    "tipo_item_id": cafe_cru, "cfop": "5927", "icms_cst": "40"}, t)
checar("a regra guarda o zero que não foi preenchido",
       sem_ibs["cbs_aliquota"] == 0 and sem_ibs["ibs_uf_aliquota"] == 0)
item_zero = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "parceiro_id": consumidor["id"], "ambiente": "2", "serie": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 10, "valor_unitario": 100,
               "cfop": "5927"}]}, t)["itens"][0]
checar("regra com IBS/CBS em branco deixa o item com alíquota zero",
       item_zero["cbs_aliquota"] == 0 and item_zero["cbs_valor"] == 0
       and item_zero["ibs_uf_aliquota"] == 0,
       f"CBS {item_zero['cbs_aliquota']} = {item_zero['cbs_valor']}")
checar("mas a base cheia continua aparecendo",
       abs(item_zero["ibs_cbs_base"] - 1000) < 0.01, str(item_zero["ibs_cbs_base"]))

# a tela da regra avisa quando o CST não leva base nem alíquota (rejeição 1021)
tributado = api("POST", "/api/fiscal/calcular", {
    "empresa_id": eid, "valor": 1000,
    "valores": {"ibs_cbs_cst": "000", "cbs_aliquota": 0.9}}, t)["calculo"]
isento = api("POST", "/api/fiscal/calcular", {
    "empresa_id": eid, "valor": 1000,
    "valores": {"ibs_cbs_cst": "400", "cbs_aliquota": 0.9}}, t)["calculo"]
checar("CST 000 leva o grupo de IBS/CBS; CST 400 não leva",
       tributado["ibs_cbs"]["leva_grupo"] is True
       and isento["ibs_cbs"]["leva_grupo"] is False,
       f"{tributado['ibs_cbs']['leva_grupo']} / {isento['ibs_cbs']['leva_grupo']}")

# o "Testar uma situação" traz a conta junto com a regra que ganhou
testado = api("POST", "/api/fiscal/simular", {
    "empresa_id": eid, "parceiro_id": consumidor["id"], "produto_id": cafe["id"],
    "cfop": "5949", "operacao": "SAIDA", "valor": 100000}, t)
checar("o teste da tabela já mostra a base em reais",
       testado["calculo"] and abs(testado["calculo"]["icms"]["base"] - 60000) < 0.01,
       str((testado.get("calculo") or {}).get("icms")))

# =========================================================================== #
print("\n=== 5. O que foi digitado à mão continua mandando ===")
mao = api("PUT", f"/api/nfe/{nota_mg['nota']['id']}", {
    "empresa_id": eid, "parceiro_id": torrefacao_mg["id"], "serie": "1", "ambiente": "2",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1000,
               "icms_cst": "00", "icms_aliquota": 12}]}, t)
checar("o que a tela mandou vence a regra",
       mao["itens"][0]["icms_cst"] == "00"
       and abs(mao["itens"][0]["icms_valor"] - 12000) < 0.01,
       f"{mao['itens'][0]['icms_cst']} / {mao['itens'][0]['icms_valor']}")

refeito = api("PUT", f"/api/nfe/{nota_mg['nota']['id']}", {
    "empresa_id": eid, "parceiro_id": torrefacao_mg["id"], "serie": "1", "ambiente": "2",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1000,
               "icms_cst": "00", "icms_aliquota": 12, "usar_regra": True}]}, t)
checar("com usar_regra a tela é descartada e a regra volta a valer",
       refeito["itens"][0]["icms_cst"] == "51"
       and abs(refeito["itens"][0]["icms_valor"]) < 0.01,
       refeito["itens"][0]["icms_cst"])

# =========================================================================== #
print("\n=== 6. Segurança e apagar ===")
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outroregras{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra"})
alheia = api("GET", f"/api/fiscal/regras?empresa_id={eid}", None, outra["token"],
             esperar_erro=True)
checar("outra conta não enxerga as regras", alheia.get("_status") in (400, 403, 404))

em_uso = api("DELETE", f"/api/fiscal/tipos/{cafe_cru}", None, t, esperar_erro=True)
checar("tipo em uso não é apagado", em_uso.get("_status") == 400)

api("DELETE", f"/api/fiscal/regras/{geral['id']}", None, t)
restantes = api("GET", f"/api/fiscal/regras?empresa_id={eid}", None, t)
checar("a regra apagada some da tabela",
       all(r["id"] != geral["id"] for r in restantes))
depois = simular(consumidor["id"], cfop="5102")
checar("sem a regra geral, a padaria fica sem regra",
       depois["regra"] is None, str((depois["regra"] or {}).get("nome")))

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} falha(s): " + "; ".join(erros))
    sys.exit(1)
print("Regras fiscais OK — o imposto sai do cruzamento cliente x item.")
