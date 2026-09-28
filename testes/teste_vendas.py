"""Teste dos relatórios de vendas e margens.

Estes relatórios respondem perguntas de dono de negócio — quanto vendi, para
quem, com que margem, o que está encalhado — e vêm das vendas e do estoque, não
dos lançamentos. Por isso o risco aqui é diferente do risco do DRE: é **contar a
mesma venda duas vezes** ou **mostrar margem maior do que a real**.

O que se confere
----------------
  * a venda entra **uma vez só**: o pedido finalizado sem nota conta; quando a
    nota daquele pedido sai, quem conta é a nota — nunca as duas;
  * nota **cancelada** não conta, e rascunho também não;
  * o **custo** sai do movimento de estoque (o custo médio na hora da venda),
    não do custo de hoje — vender hoje o que custou 1.000 ontem tem margem de
    ontem;
  * produto **sem custo conhecido** entra na venda mas é **marcado**, e o total
    diz quanto de faturamento está sem custo: margem incompleta avisada é melhor
    que margem inflada em silêncio;
  * **os totais batem entre as abas**: cliente, produto e categoria somam o
    mesmo faturamento;
  * o **desconto do pedido** é rateado entre os itens — senão a receita do
    relatório não fecha com o que o cliente pagou;
  * o ranking de **margem %** não deixa produto de uma venda só liderar;
  * **parados**: só produto com saldo, e o que nunca saiu aparece;
  * a **evolução** vira mensal em período longo, para o gráfico não virar uma
    fileira de traços;
  * relatório de outra conta não abre.

Uso:  python testes/teste_vendas.py   (com o servidor no ar)
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

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


from backend import vendas as regras                          # noqa: E402
from backend.database import SessionLocal                      # noqa: E402
from backend.models import (                                   # noqa: E402
    MovimentoEstoque, Nota, NotaItem, Pedido, PedidoItem, Produto,
)

# =========================================================================== #
print("=== 1. Montar a empresa, os produtos e as vendas ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"vend{sufixo}@teste.com", "senha": "123456",
    "empresa": "Loja do Cafe", "plano": "P4_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "LOJA DO CAFE LTDA", "cnpj": "12.345.678/0001-95", "uf": "MG",
    "cidade": "VARGINHA", "crt": "3"}, t)

produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe, soja = produtos[0], produtos[2]
for produto, custo in ((cafe, 1000), (soja, 100)):
    base = {k: produto[k] for k in ("empresa_id", "codigo", "nome", "unidade_id",
                                    "categoria_id", "marca_id")}
    api("PUT", f"/api/produtos/{produto['id']}", {
        **base, "unidade_comercial": "SC", "controla_estoque": True,
        "custo_compra": custo, "preco_venda": custo * 1.5}, t)

cliente_a = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA",
    "cpf_cnpj": "11.222.333/0001-44", "uf": "SP"}, t)
cliente_b = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "MERCADO CENTRAL",
    "cpf_cnpj": "22.333.444/0001-55", "uf": "MG"}, t)

sessao = SessionLocal()
HOJE = date.today()
MES = HOJE.replace(day=1)


def gravar_nota(numero, chave_extra, parceiro_id, itens, modelo="55",
                situacao="AUTORIZADA", status="AUTORIZADA", dia=None):
    nota = Nota(
        empresa_id=eid, chave=f"V{sufixo}{chave_extra}".ljust(44, "0")[:44],
        origem="EMITIDA", tipo="NFE", resumo=False, modelo=modelo, serie="1",
        numero=numero, data_emissao=datetime.combine(dia or HOJE, datetime.min.time()),
        emitente_cnpj="12345678000195", emitente_nome="LOJA DO CAFE LTDA",
        emitente_uf="MG", parceiro_id=parceiro_id, situacao=situacao,
        status_emissao=status, valor_total=sum(i["valor_total"] for i in itens),
    )
    sessao.add(nota)
    sessao.flush()
    for n, item in enumerate(itens, start=1):
        sessao.add(NotaItem(nota_id=nota.id, numero=n, unidade="SC", **item))
    sessao.flush()
    return nota


def movimento(produto_id, quantidade, custo_total, *, nota_item_id=None,
              pedido_item_id=None, origem="SAIDA", dia=None):
    """O movimento de saída que o estoque teria gravado naquela venda."""
    sessao.add(MovimentoEstoque(
        empresa_id=eid, produto_id=produto_id, data=dia or HOJE, tipo="S",
        quantidade=quantidade, unidade="SC", custo_unitario=custo_total / quantidade,
        custo_total=custo_total, saldo=0, custo_medio=custo_total / quantidade,
        origem=origem, nota_item_id=nota_item_id, pedido_item_id=pedido_item_id,
    ))
    sessao.flush()


# venda 1: NF-e para o cliente A, 10 sacas a 1.500 (custou 950 na época)
n1 = gravar_nota("101", "A", cliente_a["id"], [dict(
    descricao=cafe["nome"], quantidade=10, valor_unitario=1500, valor_total=15000,
    produto_id=cafe["id"])])
movimento(cafe["id"], 10, 9500, nota_item_id=n1.itens[0].id)

# venda 2: cupom para consumidor, 5 sacas a 1.600 (custou 950)
n2 = gravar_nota("201", "B", None, [dict(
    descricao=cafe["nome"], quantidade=5, valor_unitario=1600, valor_total=8000,
    produto_id=cafe["id"])], modelo="65")
movimento(cafe["id"], 5, 4750, nota_item_id=n2.itens[0].id)

# venda 3: NF-e cancelada — não pode contar
gravar_nota("102", "C", cliente_a["id"], [dict(
    descricao=cafe["nome"], quantidade=99, valor_unitario=1500, valor_total=148500,
    produto_id=cafe["id"])], situacao="CANCELADA", status="CANCELADA")

# venda 4: rascunho — também não conta
gravar_nota("", "D", cliente_b["id"], [dict(
    descricao=cafe["nome"], quantidade=50, valor_unitario=1500, valor_total=75000,
    produto_id=cafe["id"])], status="RASCUNHO")


def gravar_pedido(numero, parceiro_id, itens, *, nota_id=None, desconto=0, dia=None):
    pedido = Pedido(
        empresa_id=eid, numero=numero, tipo="PEDIDO", situacao="FINALIZADO",
        data=dia or HOJE, parceiro_id=parceiro_id, nota_id=nota_id,
        desconto=desconto, documento="SEM" if nota_id is None else "NFE",
        valor_produtos=sum(i["valor_total"] for i in itens),
        valor_total=sum(i["valor_total"] for i in itens) - desconto,
    )
    sessao.add(pedido)
    sessao.flush()
    for item in itens:
        sessao.add(PedidoItem(pedido_id=pedido.id, unidade="SC", **item))
    sessao.flush()
    return pedido


# venda 5: pedido finalizado SEM documento — venda feita, conta
p1 = gravar_pedido("000001", cliente_b["id"], [dict(
    descricao=soja["nome"], quantidade=20, valor_unitario=150, valor_total=3000,
    produto_id=soja["id"])])
movimento(soja["id"], 20, 2000, pedido_item_id=p1.itens[0].id, origem="PEDIDO")

# venda 6: pedido que JÁ virou nota — quem conta é a nota, não as duas
n3 = gravar_nota("103", "E", cliente_b["id"], [dict(
    descricao=soja["nome"], quantidade=10, valor_unitario=160, valor_total=1600,
    produto_id=soja["id"])])
gravar_pedido("000002", cliente_b["id"], [dict(
    descricao=soja["nome"], quantidade=10, valor_unitario=160, valor_total=1600,
    produto_id=soja["id"])], nota_id=n3.id)
movimento(soja["id"], 10, 1000, nota_item_id=n3.itens[0].id)

sessao.commit()
checar("as vendas do cenário foram gravadas", True)

# =========================================================================== #
print("\n=== 2. A venda conta uma vez só ===")
de, ate = MES.isoformat(), HOJE.isoformat()
resumo = api("GET", f"/api/vendas/resumo?empresa_id={eid}&de={de}&ate={ate}", None, t)
t_ = resumo["totais"]
# 15.000 + 8.000 + 3.000 + 1.600 = 27.600
checar("o faturamento soma só as vendas que valem", t_["receita"] == 27600.0,
       str(t_["receita"]))
checar("a nota cancelada ficou de fora", t_["receita"] < 100000)
checar("o rascunho também", t_["itens"] == 4, str(t_["itens"]))
tipos = {l["tipo"]: l["receita"] for l in resumo["tipos"]}
checar("a venda sem documento aparece como tal",
       tipos.get("Sem documento") == 3000.0, str(tipos))
checar("e o pedido que virou nota conta como NF-e, não duas vezes",
       tipos.get("NF-e") == 16600.0, str(tipos))

print("\n=== 3. O custo vem do movimento, não do custo de hoje ===")
# custo: 9.500 + 4.750 + 2.000 + 1.000 = 17.250
checar("o custo é o do momento de cada venda", t_["custo"] == 17250.0, str(t_["custo"]))
checar("a margem é faturamento menos custo", t_["margem"] == 10350.0, str(t_["margem"]))
checar("e a margem % bate", t_["margem_percentual"] == round(10350 / 27600 * 100, 2),
       str(t_["margem_percentual"]))
checar("nada ficou sem custo neste cenário", t_["receita_sem_custo"] == 0,
       str(t_["receita_sem_custo"]))

print("\n=== 4. Os totais batem entre as abas ===")
clientes = api("GET", f"/api/vendas/clientes?empresa_id={eid}&de={de}&ate={ate}", None, t)
prods = api("GET", f"/api/vendas/produtos?empresa_id={eid}&de={de}&ate={ate}", None, t)
custos = api("GET", f"/api/vendas/custos?empresa_id={eid}&de={de}&ate={ate}", None, t)
soma_clientes = round(sum(l["receita"] for l in clientes["linhas"]), 2)
soma_produtos = round(sum(l["receita"] for l in prods["linhas"]), 2)
soma_categorias = round(sum(l["receita"] for l in custos["categorias"]), 2)
checar("cliente, produto e categoria somam o mesmo faturamento",
       soma_clientes == soma_produtos == soma_categorias == t_["receita"],
       f"{soma_clientes} / {soma_produtos} / {soma_categorias}")
soma_custo = round(sum(l["custo"] for l in custos["categorias"]), 2)
checar("e o mesmo custo", soma_custo == t_["custo"], str(soma_custo))

print("\n=== 5. Melhores clientes ===")
primeiro = clientes["linhas"][0]
checar("o maior cliente lidera a lista", primeiro["cliente"] == "TORREFACAO PAULISTA",
       primeiro["cliente"])
checar("com o faturamento dele", primeiro["receita"] == 15000.0, str(primeiro["receita"]))
checar("e o ticket médio = faturamento / nº de vendas",
       primeiro["ticket_medio"] == 15000.0, str(primeiro["ticket_medio"]))
nomes = [l["cliente"] for l in clientes["linhas"]]
checar("o cupom sem cliente vira \"consumidor não identificado\"",
       "Consumidor não identificado" in nomes, str(nomes))
checar("a lista vem ordenada do maior para o menor",
       [l["receita"] for l in clientes["linhas"]]
       == sorted([l["receita"] for l in clientes["linhas"]], reverse=True))

print("\n=== 6. Produtos: mais vendidos e melhor margem ===")
por_qtd = api("GET",
              f"/api/vendas/produtos?empresa_id={eid}&de={de}&ate={ate}&ordem=quantidade",
              None, t)
checar("por quantidade, a soja (30) vem antes do café (15)",
       por_qtd["linhas"][0]["quantidade"] == 30, str(por_qtd["linhas"][0]["quantidade"]))
por_margem = api("GET",
                 f"/api/vendas/produtos?empresa_id={eid}&de={de}&ate={ate}&ordem=margem",
                 None, t)
checar("por margem em reais, o café lidera",
       por_margem["linhas"][0]["produto"] == cafe["nome"],
       por_margem["linhas"][0]["produto"])
checar("ordem inventada cai no padrão",
       api("GET", f"/api/vendas/produtos?empresa_id={eid}&de={de}&ate={ate}&ordem=xyz",
           None, t)["ordem"] == "receita")

# um produto de venda mínima com margem altíssima não pode liderar o ranking de %
n4 = gravar_nota("104", "F", cliente_a["id"], [dict(
    descricao="BRINDE", quantidade=1, valor_unitario=10, valor_total=10)])
sessao.commit()
pct = api("GET",
          f"/api/vendas/produtos?empresa_id={eid}&de={de}&ate={ate}&ordem=margem_percentual",
          None, t)
checar("o item de 10 reais com 100% de margem não lidera o ranking de margem %",
       pct["linhas"][0]["produto"] != "BRINDE",
       f'{pct["linhas"][0]["produto"]} ({pct["linhas"][0]["margem_percentual"]}%)')
checar("mas continua na lista, no fim",
       any(l["produto"] == "BRINDE" for l in pct["linhas"]))

print("\n=== 7. Produto sem custo é marcado, não escondido ===")
custos2 = api("GET", f"/api/vendas/custos?empresa_id={eid}&de={de}&ate={ate}", None, t)
checar("o faturamento sem custo é contado", custos2["totais"]["receita_sem_custo"] == 10.0,
       str(custos2["totais"]["receita_sem_custo"]))
checar("e o produto aparece na lista de custo incompleto",
       any(l["produto"] == "BRINDE" for l in custos2["sem_custo"]),
       str([l["produto"] for l in custos2["sem_custo"]]))

print("\n=== 8. O desconto do pedido é rateado ===")
p3 = gravar_pedido("000003", cliente_b["id"], [
    dict(descricao=cafe["nome"], quantidade=2, valor_unitario=1500, valor_total=3000,
         produto_id=cafe["id"]),
    dict(descricao=soja["nome"], quantidade=10, valor_unitario=100, valor_total=1000,
         produto_id=soja["id"]),
], desconto=400)
sessao.commit()
detalhe = api("GET", f"/api/vendas/linhas?empresa_id={eid}&de={de}&ate={ate}", None, t)
do_pedido = [l for l in detalhe["linhas"] if l["documento"] == "Pedido 000003"]
checar("as duas linhas do pedido saíram", len(do_pedido) == 2, str(len(do_pedido)))
checar("e a soma delas é o total que o cliente pagou (4.000 − 400)",
       round(sum(l["receita"] for l in do_pedido), 2) == 3600.0,
       str(round(sum(l["receita"] for l in do_pedido), 2)))

print("\n=== 9. A evolução muda de dia para mês em período longo ===")
curto = regras.evolucao([{"data": "2026-03-10", "receita": 1, "margem": 1, "custo": 0,
                          "documento": "x", "quantidade": 1, "origem_custo": "MEDIO"}],
                        date(2026, 3, 1), date(2026, 3, 31))
checar("período de um mês sai por dia", curto[0]["periodo"] == "10/03", curto[0]["periodo"])
longo = regras.evolucao([{"data": "2026-03-10", "receita": 1, "margem": 1, "custo": 0,
                          "documento": "x", "quantidade": 1, "origem_custo": "MEDIO"}],
                        date(2026, 1, 1), date(2026, 12, 31))
checar("período de um ano sai por mês", longo[0]["periodo"] == "mar/26", longo[0]["periodo"])
checar("a evolução do período tem dado", len(resumo["evolucao"]) >= 1)

print("\n=== 10. Parados em estoque ===")
produto = sessao.get(Produto, cafe["id"])
produto.estoque_atual = 40
produto.custo_medio = 950
produto.estoque_unidade = "SC"
parado = sessao.get(Produto, soja["id"])
parado.estoque_atual = 500
parado.custo_medio = 100
parado.estoque_unidade = "SC"
sessao.commit()

# o café saiu hoje; a soja teve saída hoje também — com 60 dias, nenhum está parado
r = api("GET", f"/api/vendas/parados?empresa_id={eid}&dias=60", None, t)
checar("produto que acabou de sair não está parado", r["produtos"] == 0, str(r["produtos"]))

# empurra a saída da soja para 200 dias atrás
for m in sessao.query(MovimentoEstoque).filter(
        MovimentoEstoque.empresa_id == eid,
        MovimentoEstoque.produto_id == soja["id"]).all():
    m.data = HOJE - timedelta(days=200)
sessao.commit()
r = api("GET", f"/api/vendas/parados?empresa_id={eid}&dias=60", None, t)
checar("com a última saída há 200 dias, a soja aparece", r["produtos"] == 1,
       str(r["produtos"]))
linha = r["linhas"][0]
checar("com o saldo e o dinheiro parado", linha["saldo"] == 500 and linha["valor"] == 50000.0,
       f'{linha["saldo"]} / {linha["valor"]}')
checar("e há quantos dias não sai", linha["dias_parado"] == 200, str(linha["dias_parado"]))
checar("o total soma o dinheiro parado", r["valor_total"] == 50000.0, str(r["valor_total"]))

# produto com saldo e sem saída nenhuma
novo = sessao.get(Produto, produtos[1]["id"])
novo.controla_estoque = True
novo.estoque_atual = 7
novo.custo_medio = 30
sessao.commit()
r = api("GET", f"/api/vendas/parados?empresa_id={eid}&dias=60", None, t)
checar("produto que nunca saiu também é parado", r["nunca_vendidos"] == 1,
       str(r["nunca_vendidos"]))
nunca = next(l for l in r["linhas"] if l["ultima_saida"] is None)
checar("e vem sem data de última saída", nunca["dias_parado"] is None)

# saldo zerado não é "parado", é acabado
parado.estoque_atual = 0
sessao.commit()
r = api("GET", f"/api/vendas/parados?empresa_id={eid}&dias=60", None, t)
checar("produto zerado sai da lista — não está parado, está acabado",
       all(l["produto_id"] != soja["id"] for l in r["linhas"]))
ruim = api("GET", f"/api/vendas/parados?empresa_id={eid}&dias=9999", None, t,
           esperar_erro=True)
checar("dias fora da faixa é recusado", ruim.get("_status") == 400)

print("\n=== 11. Relatório de outra conta não abre ===")
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outrovend{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra Loja", "plano": "P1_ANUAL", "uf": "MG"})
invasao = api("GET", f"/api/vendas/resumo?empresa_id={eid}", None, outra["token"],
              esperar_erro=True)
checar("resumo de outra empresa é recusado", invasao.get("_status") == 403,
       str(invasao.get("_status")))
invasao2 = api("GET", f"/api/vendas/parados?empresa_id={eid}", None, outra["token"],
               esperar_erro=True)
checar("e o de parados também", invasao2.get("_status") == 403)
datas = api("GET", f"/api/vendas/resumo?empresa_id={eid}&de=2026-05-01&ate=2026-01-01",
            None, t, esperar_erro=True)
checar("data inicial maior que a final é recusada", datas.get("_status") == 400)

sessao.close()

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Todos os testes de vendas e margens passaram.")
