"""Teste das regras fiscais: tipo de cliente x tipo de item.

Confere que o imposto de cada item da nota deixa de vir do cadastro do produto e
passa a vir da tabela de regras, escolhendo sempre a linha mais específica:

  * café cru para indústria dentro de MG  -> diferimento (CST 51, sem destaque);
  * café cru para indústria em SP         -> 7% de ICMS;
  * café cru para qualquer outro cliente  -> regra geral do item;
  * item sem regra nenhuma                -> cai no cadastro do produto.

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
                                              "embalagem", "descricao")},
    "empresa_id": eid, "ncm": "09011110", "cfop_padrao": "6101", "cst_icms": "00",
    "unidade_comercial": "SC", "origem": "0", "ativo": True,
    "aliquota_icms": 18, "aliquota_pis": 1.65, "aliquota_cofins": 7.6,
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
def simular(parceiro_id, produto_id=None):
    return api("POST", "/api/fiscal/simular", {
        "empresa_id": eid, "parceiro_id": parceiro_id,
        "produto_id": produto_id or cafe["id"], "operacao": "SAIDA"}, t)

dentro = simular(torrefacao_mg["id"])
checar("indústria dentro de MG cai na regra do diferimento",
       dentro["regra"]["nome"].startswith("Café cru para indústria em MG"),
       dentro["regra"]["nome"])
checar("e a regra traz o CST 51 e o CFOP 5102",
       dentro["regra"]["valores"]["icms_cst"] == "51"
       and dentro["regra"]["valores"]["cfop"] == "5102")

paulista = simular(torrefacao_sp["id"])
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
    "empresa_id": eid, "codigo": "SERV1", "nome": "CORRETAGEM",
    "unidade_id": cafe["unidade_id"], "ncm": "00000000", "cfop_padrao": "5949",
    "cst_icms": "41", "aliquota_icms": 0}, t)
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

nota_sp = rascunho(torrefacao_sp["id"])
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
checar("produto sem regra continua usando o cadastro do produto",
       nota_servico["itens"][0]["icms_cst"] == "41"
       and nota_servico["itens"][0]["cfop"] == "5949",
       nota_servico["itens"][0]["cfop"])

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
    "nome": "Outro", "email": f"outro{sufixo}@teste.com", "senha": "123456",
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
depois = simular(consumidor["id"])
checar("sem a regra geral, a padaria fica sem regra",
       depois["regra"] is None, str((depois["regra"] or {}).get("nome")))

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} falha(s): " + "; ".join(erros))
    sys.exit(1)
print("Regras fiscais OK — o imposto sai do cruzamento cliente x item.")
