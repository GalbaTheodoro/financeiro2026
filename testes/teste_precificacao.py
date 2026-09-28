"""Teste da formação do preço de venda — o markup e a conta que o gera.

A conta é a do **markup divisor**: tudo que é percentual sobre a venda (imposto,
comissão, cartão, frete, despesa fixa e o lucro desejado) entra num bolo, e o
preço é o custo dividido pelo que sobra. Somar o lucro ao custo — que é como
quase todo mundo faz — dá um preço menor e um lucro bem menor que o desejado.

O que se confere
----------------
  * **a conta fecha**: multiplicando cada percentual pelo preço, cada real vai
    para um lugar e a soma da composição é exatamente o preço;
  * o exemplo clássico: custo 1.000, lucro 20%, imposto 10%, comissão 5% dá
    **1.538,46** — e não 1.200, que é o que sai da conta errada;
  * vendendo pelos 1.200 da conta errada, o lucro real é **1,67%**, não 20% —
    é este número que a tela precisa mostrar;
  * o **IPI fica de fora do markup** (é por fora, somado ao preço) e aparece
    como "preço com IPI";
  * na empresa do **Simples**, o DAS entra e o ICMS/PIS/COFINS do cadastro não;
  * **markup digitado manda**: o preço vira custo x markup e o lucro é o que
    sobra — inclusive negativo, que é o que precisa aparecer;
  * a **base do custo** é o custo de compra quando há, senão o custo médio do
    estoque, mais os outros custos por unidade;
  * percentuais somando 100% ou mais **não viram preço**, viram aviso;
  * gravar os percentuais **não muda o preço**; só "usar este preço" muda;
  * produto de outra conta não abre.

Uso:  python testes/teste_precificacao.py   (com o servidor no ar)
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

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


from backend import precificacao as regras                    # noqa: E402

# =========================================================================== #
print("=== 1. A conta do markup divisor ===")
r = regras.calcular({"custo_compra": 1000, "perc_lucro": 20,
                     "perc_simples": 10, "perc_comissao": 5})
checar("os percentuais somam 35%", r["soma"] == 35.0, str(r["soma"]))
checar("o markup é 1/(1-0,35) = 1,5385", r["markup"] == 1.5385, str(r["markup"]))
checar("e o preço é 1.538,50 — não 1.200, que é a conta errada",
       r["preco"] == 1538.5, str(r["preco"]))
checar("o lucro sai exatamente nos 20% pedidos",
       r["lucro_percentual"] == 20.0, str(r["lucro_percentual"]))

soma_composicao = round(sum(l["valor"] for l in r["composicao"]), 2)
checar("A CONTA FECHA: a composição soma o preço, ao centavo",
       soma_composicao == r["preco"], f'{soma_composicao} x {r["preco"]}')
rotulos = [l["rotulo"] for l in r["composicao"]]
checar("a composição começa no custo e termina no lucro",
       rotulos[0] == "Custo da mercadoria" and rotulos[-1] == "Lucro", str(rotulos))
checar("percentual zerado não polui a lista",
       "Frete" not in rotulos and "Taxa de cartão" not in rotulos, str(rotulos))

print("\n=== 2. A conta errada, mostrada como ela é ===")
errado = regras.calcular({"custo_compra": 1000, "perc_lucro": 20, "perc_simples": 10,
                          "perc_comissao": 5, "preco_atual": 1200})
atual = errado["atual"]
checar("com o preço de 1.200 o markup praticado é 1,20", atual["markup"] == 1.2,
       str(atual["markup"]))
checar("e o lucro REAL é 1,67%, não os 20% que a pessoa achava que tinha",
       atual["lucro_percentual"] == 1.67, str(atual["lucro_percentual"]))
checar("em reais, sobram 20,00 de 1.200,00", atual["lucro_valor"] == 20.0,
       str(atual["lucro_valor"]))
checar("e a tela avisa que o preço está abaixo do sugerido",
       any("abaixo do sugerido" in a for a in errado["avisos"]),
       str(errado["avisos"])[:90])

prejuizo = regras.calcular({"custo_compra": 1000, "perc_lucro": 20, "perc_simples": 10,
                            "perc_comissao": 5, "preco_atual": 1050})
checar("preço que dá prejuízo é dito com todas as letras",
       prejuizo["atual"]["lucro_valor"] < 0
       and any("prejuízo" in a for a in prejuizo["avisos"]),
       str(prejuizo["avisos"])[:90])

print("\n=== 3. O IPI é por fora — não come a margem ===")
com_ipi = regras.calcular({"custo_compra": 1000, "perc_lucro": 20, "perc_simples": 10,
                           "perc_comissao": 5, "perc_ipi": 5})
checar("o IPI não entra na soma do markup", com_ipi["soma"] == 35.0, str(com_ipi["soma"]))
checar("o preço é o mesmo de antes", com_ipi["preco"] == 1538.5, str(com_ipi["preco"]))
checar("e o preço com IPI aparece à parte: 1.538,50 + 5%",
       com_ipi["preco_com_ipi"] == 1615.43, str(com_ipi["preco_com_ipi"]))
checar("sem IPI, os dois preços são iguais",
       r["preco_com_ipi"] == r["preco"])

print("\n=== 4. A base do custo ===")
base = regras.custo_da_base({"custo_medio": 800, "custo_compra": 0, "outros_custos": 0})
checar("sem custo de compra, a base é o custo médio do estoque",
       base["base"] == 800 and "médio" in base["origem"], base["origem"])
base = regras.custo_da_base({"custo_medio": 800, "custo_compra": 950, "outros_custos": 0})
checar("com custo de compra, é ele que manda — é o que custa repor",
       base["base"] == 950 and "reposição" in base["origem"], base["origem"])
base = regras.custo_da_base({"custo_medio": 800, "custo_compra": 950, "outros_custos": 12.5})
checar("os outros custos por unidade somam ao custo, em reais",
       base["custo_total"] == 962.5, str(base["custo_total"]))
zerado = regras.calcular({"perc_lucro": 20})
checar("custo zerado vira aviso, não preço inventado",
       any("custo está zerado" in a for a in zerado["avisos"]), str(zerado["avisos"])[:70])

print("\n=== 5. Markup digitado manda na conta ===")
digitado = regras.calcular({"custo_compra": 1000, "perc_lucro": 20, "perc_simples": 10,
                            "perc_comissao": 5, "markup": 2})
checar("preço = custo x markup", digitado["preco"] == 2000.0, str(digitado["preco"]))
checar("e o sistema diz que o markup veio digitado",
       digitado["markup_digitado"] is True)
checar("o lucro vira o que sobra depois de tudo",
       digitado["lucro_valor"] == round(2000 - 1000 - 2000 * 0.15, 2),
       str(digitado["lucro_valor"]))
apertado = regras.calcular({"custo_compra": 1000, "perc_simples": 10,
                            "perc_comissao": 5, "markup": 1.1})
checar("markup baixo demais mostra o prejuízo por unidade",
       apertado["lucro_valor"] < 0 and any("prejuízo" in a for a in apertado["avisos"]),
       f'{apertado["lucro_valor"]} {str(apertado["avisos"])[:60]}')

print("\n=== 6. Conta impossível não vira preço ===")
impossivel = regras.calcular({"custo_compra": 1000, "perc_lucro": 60, "perc_despesas": 45})
checar("percentuais somando 105% não geram preço",
       impossivel["preco"] == 0 and impossivel["markup"] == 0)
checar("e o aviso explica o que fazer",
       any("Não existe preço" in a for a in impossivel["avisos"]),
       str(impossivel["avisos"])[:90])
negativo = regras.calcular({"custo_compra": 1000, "perc_lucro": -30})
checar("percentual negativo é tratado como zero, não inverte a conta",
       negativo["soma"] == 0.0, str(negativo["soma"]))

# =========================================================================== #
print("\n=== 7. Pela tela: empresa de regime normal ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"preco{sufixo}@teste.com", "senha": "123456",
    "empresa": "Torrefacao Preco", "plano": "P4_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "TORREFACAO PRECO LTDA", "uf": "MG", "cidade": "VARGINHA",
    "regime_tributario": "LUCRO PRESUMIDO", "crt": "3"}, t)

produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe = produtos[0]
base_produto = {k: cafe[k] for k in ("empresa_id", "codigo", "nome", "unidade_id",
                                     "categoria_id", "marca_id")}
api("PUT", f"/api/produtos/{cafe['id']}", {
    **base_produto, "aliquota_icms": 7, "aliquota_pis": 1.65, "aliquota_cofins": 7.6,
    "aliquota_ipi": 5, "custo_compra": 1000, "preco_venda": 1200,
    "perc_comissao": 3, "perc_despesas": 8, "perc_lucro": 15}, t)

abertura = api("GET", f"/api/precificacao?empresa_id={eid}&produto_id={cafe['id']}", None, t)
e = abertura["estado"]
checar("a tela abre com os impostos do cadastro fiscal do produto",
       e["perc_icms"] == 7 and e["perc_pis"] == 1.65 and e["perc_cofins"] == 7.6,
       f'{e["perc_icms"]}/{e["perc_pis"]}/{e["perc_cofins"]}')
checar("e com o DAS zerado, porque a empresa não é do Simples",
       e["simples"] is False and e["perc_simples"] == 0)
c = abertura["calculo"]
esperado = round(7 + 1.65 + 7.6 + 3 + 8 + 15, 4)
checar("a soma junta impostos, comissão, despesa e lucro", c["soma"] == esperado,
       f'{c["soma"]} x {esperado}')
checar("o preço sugerido já vem calculado, sem clicar em nada", c["preco"] > 0,
       str(c["preco"]))
checar("e o preço praticado hoje entra na comparação",
       c["atual"] and c["atual"]["preco"] == 1200.0)

mexido = api("POST", "/api/precificacao", {
    "empresa_id": eid, "produto_id": cafe["id"], "perc_lucro": 25}, t)
checar("mudar o lucro na tela muda o preço, sem gravar nada",
       mexido["calculo"]["preco"] > c["preco"],
       f'{c["preco"]} -> {mexido["calculo"]["preco"]}')
conferir = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
ainda = next(p for p in conferir if p["id"] == cafe["id"])
checar("o produto continua com o lucro antigo e o preço antigo",
       ainda["perc_lucro"] == 15 and ainda["preco_venda"] == 1200,
       f'{ainda["perc_lucro"]} / {ainda["preco_venda"]}')

print("\n=== 8. Gravar: percentuais e preço são coisas diferentes ===")
so_percentuais = api("PUT", "/api/precificacao", {
    "empresa_id": eid, "produto_id": cafe["id"], "perc_lucro": 25}, t)
depois = next(p for p in api("GET", f"/api/produtos?empresa_id={eid}", None, t)
              if p["id"] == cafe["id"])
checar("salvar os percentuais grava o lucro", depois["perc_lucro"] == 25,
       str(depois["perc_lucro"]))
checar("e NÃO mexe no preço de venda", depois["preco_venda"] == 1200,
       str(depois["preco_venda"]))
checar("a mensagem diz o que foi feito",
       "percentuais" in so_percentuais["mensagem"].lower()
       or "Formação" in so_percentuais["mensagem"], so_percentuais["mensagem"])

sugerido = so_percentuais["calculo"]["preco"]
com_preco = api("PUT", "/api/precificacao", {
    "empresa_id": eid, "produto_id": cafe["id"], "preco_venda": sugerido}, t)
depois = next(p for p in api("GET", f"/api/produtos?empresa_id={eid}", None, t)
              if p["id"] == cafe["id"])
checar("usar o preço grava o preço de venda", depois["preco_venda"] == sugerido,
       f'{depois["preco_venda"]} x {sugerido}')
checar("e o markup gravado passa a ser o desse preço",
       abs(depois["markup"] - round(sugerido / 1000, 4)) < 0.0002,
       f'{depois["markup"]} x {round(sugerido / 1000, 4)}')
checar("a mensagem confirma o preço novo", "Preço de venda" in com_preco["mensagem"],
       com_preco["mensagem"])

print("\n=== 9. Empresa do Simples: o DAS no lugar dos três ===")
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "TORREFACAO PRECO LTDA", "uf": "MG", "cidade": "VARGINHA",
    "regime_tributario": "SIMPLES NACIONAL", "crt": "1"}, t)
simples = api("GET", f"/api/precificacao?empresa_id={eid}&produto_id={cafe['id']}", None, t)
e = simples["estado"]
checar("o ICMS, o PIS e a COFINS do cadastro saem da conta",
       e["perc_icms"] == 0 and e["perc_pis"] == 0 and e["perc_cofins"] == 0,
       f'{e["perc_icms"]}/{e["perc_pis"]}/{e["perc_cofins"]}')
checar("o IPI continua, porque é por fora e independe do regime", e["perc_ipi"] == 5)
checar("e a tela avisa que falta informar a alíquota do DAS",
       any("DAS" in a for a in simples["calculo"]["avisos"]),
       str(simples["calculo"]["avisos"])[:80])

com_das = api("PUT", "/api/precificacao", {
    "empresa_id": eid, "produto_id": cafe["id"], "perc_simples": 7.3}, t)
checar("informado o DAS, o aviso some",
       not any("DAS" in a for a in com_das["calculo"]["avisos"]),
       str(com_das["calculo"]["avisos"])[:70])
checar("e ele entra na soma no lugar dos três impostos",
       com_das["calculo"]["soma"] == round(7.3 + 3 + 8 + 25, 4),
       str(com_das["calculo"]["soma"]))

# voltando ao regime normal, o DAS guardado não pode sujar a conta
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "TORREFACAO PRECO LTDA", "uf": "MG", "cidade": "VARGINHA",
    "regime_tributario": "LUCRO PRESUMIDO", "crt": "3"}, t)
voltou = api("PUT", "/api/precificacao", {"empresa_id": eid, "produto_id": cafe["id"]}, t)
checar("de volta ao regime normal, o DAS é zerado no cadastro",
       voltou["estado"]["perc_simples"] == 0, str(voltou["estado"]["perc_simples"]))
checar("e os impostos do produto voltam a valer",
       voltou["estado"]["perc_icms"] == 7, str(voltou["estado"]["perc_icms"]))

print("\n=== 10. Salvar o cadastro do produto não apaga o estudo de preço ===")
# o formulário do cadastro não tem os percentuais: se eles viessem zerados por
# padrão, gravar o produto apagaria em silêncio a formação do preço inteira
antes = next(p for p in api("GET", f"/api/produtos?empresa_id={eid}", None, t)
             if p["id"] == cafe["id"])
api("PUT", f"/api/produtos/{cafe['id']}", {
    **base_produto, "aliquota_icms": 7, "aliquota_pis": 1.65, "aliquota_cofins": 7.6,
    "aliquota_ipi": 5, "preco_venda": antes["preco_venda"],
    "markup": antes["markup"]}, t)
agora = next(p for p in api("GET", f"/api/produtos?empresa_id={eid}", None, t)
             if p["id"] == cafe["id"])
checar("os percentuais continuam lá depois de salvar o cadastro",
       agora["perc_lucro"] == antes["perc_lucro"]
       and agora["perc_comissao"] == antes["perc_comissao"]
       and agora["perc_despesas"] == antes["perc_despesas"],
       f'lucro {agora["perc_lucro"]}, comissão {agora["perc_comissao"]}')
checar("o custo de compra também", agora["custo_compra"] == antes["custo_compra"],
       str(agora["custo_compra"]))
checar("e o preço não mudou sozinho", agora["preco_venda"] == antes["preco_venda"])
# mas zero explícito grava zero — em branco é "não mexer", zero é zero
api("PUT", "/api/precificacao", {"empresa_id": eid, "produto_id": cafe["id"],
                                 "perc_comissao": 0}, t)
zerado = next(p for p in api("GET", f"/api/produtos?empresa_id={eid}", None, t)
              if p["id"] == cafe["id"])
checar("zero digitado de propósito grava zero", zerado["perc_comissao"] == 0,
       str(zerado["perc_comissao"]))

print("\n=== 11. Produto de outra conta não abre ===")
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outropreco{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra Preco", "plano": "P1_ANUAL", "uf": "MG"})
invasao = api("GET", f"/api/precificacao?empresa_id={eid}&produto_id={cafe['id']}",
              None, outra["token"], esperar_erro=True)
checar("abrir o preço de outra empresa é recusado", invasao.get("_status") == 403,
       str(invasao.get("_status")))
outro_eid = outra["empresa"]["id"]
trocado = api("GET", f"/api/precificacao?empresa_id={outro_eid}&produto_id={cafe['id']}",
              None, outra["token"], esperar_erro=True)
checar("e produto que não é da empresa dá 404", trocado.get("_status") == 404,
       str(trocado.get("_status")))

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Todos os testes da formação do preço passaram.")
