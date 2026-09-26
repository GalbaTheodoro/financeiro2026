"""Teste da classificação do produto: categoria e marca.

O que se confere
----------------
  * empresa nova nasce com as categorias e a marca padrão, e os produtos de
    fábrica já saem classificados — senão o cadastro nasceria inválido;
  * os dois cadastros funcionam (criar, editar, listar, inativar);
  * **código repetido** na mesma empresa é recusado;
  * o produto **não salva sem categoria e sem marca** — nem ao criar nem ao
    editar — e a mensagem diz onde cadastrar;
  * classificar com a categoria **de outra conta** é recusado (isolamento);
  * **filtrar** a lista de produtos por categoria e por marca;
  * **filtrar o estoque** por categoria e por marca;
  * o **relatório** soma o vendido no período e o estoque de hoje, por categoria
    e por marca, e o total bate com a soma das linhas;
  * produto **sem classificação** (o importado de XML, o antigo) não some do
    relatório: entra em linha própria;
  * a importação de XML da SEFAZ **não quebra** — o produto criado por ela cai
    em "Outros / Sem marca";
  * **não dá para apagar** categoria ou marca em uso por algum produto.

Uso:  python testes/teste_classificacao.py   (com o servidor no ar)
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


sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"class{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria Classificação", "plano": "P4_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]

# =========================================================================== #
print("=== 1. A empresa nova já nasce classificada ===")
categorias = api("GET", f"/api/categorias-produto?empresa_id={eid}", None, t)
marcas = api("GET", f"/api/marcas-produto?empresa_id={eid}", None, t)
codigos = {c["codigo"]: c for c in categorias}
checar("as categorias padrão são criadas",
       {"CAF", "GRA", "PEC", "INS", "EMB", "OUT"} <= set(codigos), str(sorted(codigos)))
checar("e a marca genérica também",
       any(m["codigo"] == "GEN" for m in marcas), str([m["codigo"] for m in marcas]))
checar("categoria tem código, nome e descrição",
       codigos["CAF"]["nome"] == "Café" and codigos["CAF"]["descricao"])

produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
checar("os produtos de fábrica já saem classificados",
       all(p["categoria_id"] and p["marca_id"] for p in produtos),
       str([(p["codigo"], p["categoria_nome"]) for p in produtos]))
cafe = next(p for p in produtos if p["codigo"] == "001")
checar("o café nasce na categoria Café",
       cafe["categoria_nome"] == "Café" and cafe["marca_nome"] == "Sem marca",
       f'{cafe["categoria_nome"]} / {cafe["marca_nome"]}')

# =========================================================================== #
print("\n=== 2. Os dois cadastros ===")
nova = api("POST", "/api/categorias-produto", {
    "empresa_id": eid, "codigo": "FER", "nome": "Ferramentas",
    "descricao": "Enxada, foice, peneira"}, t)
checar("cria categoria com código, nome e descrição",
       nova["codigo"] == "FER" and nova["descricao"] == "Enxada, foice, peneira")
marca_nova = api("POST", "/api/marcas-produto", {
    "empresa_id": eid, "codigo": "TRA", "nome": "Tramontina",
    "descricao": "Ferramentas manuais"}, t)
checar("cria marca com código, nome e descrição", marca_nova["nome"] == "Tramontina")

repetida = api("POST", "/api/categorias-produto", {
    "empresa_id": eid, "codigo": "FER", "nome": "Outra"}, t, esperar_erro=True)
checar("código repetido de categoria é recusado",
       repetida.get("_status") == 400 and "FER" in str(repetida.get("detail")),
       str(repetida.get("detail"))[:60])
sem_codigo = api("POST", "/api/marcas-produto", {
    "empresa_id": eid, "codigo": "  ", "nome": "Sem"}, t, esperar_erro=True)
checar("marca sem código é recusada", sem_codigo.get("_status") == 400)

editada = api("PUT", f"/api/categorias-produto/{nova['id']}", {
    "empresa_id": eid, "codigo": "FER", "nome": "Ferramentas e utensílios",
    "descricao": "Enxada, foice, peneira", "ativo": False}, t)
checar("edita e inativa a categoria",
       editada["nome"] == "Ferramentas e utensílios" and editada["ativo"] is False)
api("PUT", f"/api/categorias-produto/{nova['id']}", {
    "empresa_id": eid, "codigo": "FER", "nome": "Ferramentas e utensílios",
    "descricao": "Enxada, foice, peneira", "ativo": True}, t)

# =========================================================================== #
print("\n=== 3. O produto não salva sem classificação ===")
base = {"empresa_id": eid, "codigo": f"P{sufixo[-4:]}", "nome": "ENXADA LARGA",
        "unidade_comercial": "UN", "origem": "0", "ncm": "82013000",
        "cfop_padrao": "5102", "ativo": True}

sem_nada = api("POST", "/api/produtos", base, t, esperar_erro=True)
checar("produto sem categoria é recusado",
       sem_nada.get("_status") == 400 and "categoria" in str(sem_nada.get("detail")).lower(),
       str(sem_nada.get("detail"))[:80])
checar("e a mensagem diz onde cadastrar",
       "Cadastros" in str(sem_nada.get("detail")), str(sem_nada.get("detail"))[-40:])

sem_marca = api("POST", "/api/produtos", {**base, "categoria_id": nova["id"]},
                t, esperar_erro=True)
checar("produto sem marca é recusado",
       sem_marca.get("_status") == 400 and "marca" in str(sem_marca.get("detail")).lower(),
       str(sem_marca.get("detail"))[:70])

enxada = api("POST", "/api/produtos", {
    **base, "categoria_id": nova["id"], "marca_id": marca_nova["id"]}, t)
checar("com categoria e marca, o produto salva",
       enxada["categoria_nome"] == "Ferramentas e utensílios"
       and enxada["marca_nome"] == "Tramontina")

tirando = api("PUT", f"/api/produtos/{enxada['id']}", {
    **base, "categoria_id": None, "marca_id": marca_nova["id"]}, t, esperar_erro=True)
checar("tirar a categoria na edição também é recusado", tirando.get("_status") == 400)

# ------------------------------------------------------- isolamento entre contas
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Vizinho", "email": f"viz{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria Vizinha", "plano": "P1_SEMESTRAL"})
categoria_vizinha = api("GET", f"/api/categorias-produto?empresa_id={outra['empresa']['id']}",
                        None, outra["token"])[0]
invasor = api("PUT", f"/api/produtos/{enxada['id']}", {
    **base, "categoria_id": categoria_vizinha["id"], "marca_id": marca_nova["id"]},
    t, esperar_erro=True)
checar("categoria de outra conta é recusada — não dá para classificar com o que não é seu",
       invasor.get("_status") == 400 and "empresa" in str(invasor.get("detail")).lower(),
       str(invasor.get("detail"))[:70])

# =========================================================================== #
print("\n=== 4. Filtrar a lista de produtos ===")
so_ferramenta = api("GET", f"/api/produtos?empresa_id={eid}&categoria_id={nova['id']}", None, t)
checar("filtrar por categoria traz só os daquela categoria",
       [p["codigo"] for p in so_ferramenta] == [enxada["codigo"]],
       str([p["codigo"] for p in so_ferramenta]))
so_marca = api("GET", f"/api/produtos?empresa_id={eid}&marca_id={marca_nova['id']}", None, t)
checar("filtrar por marca também", len(so_marca) == 1 and so_marca[0]["id"] == enxada["id"])
cafe_cat = cafe["categoria_id"]
cafes = api("GET", f"/api/produtos?empresa_id={eid}&categoria_id={cafe_cat}", None, t)
checar("a categoria Café traz os dois cafés de fábrica", len(cafes) == 2,
       str([p["codigo"] for p in cafes]))
juntos = api("GET",
             f"/api/produtos?empresa_id={eid}&categoria_id={cafe_cat}&marca_id={marca_nova['id']}",
             None, t)
checar("os dois filtros juntos se somam (e aqui não sobra nada)", juntos == [])
checar("sem filtro vem tudo",
       len(api("GET", f"/api/produtos?empresa_id={eid}", None, t)) == 6)

# =========================================================================== #
print("\n=== 5. Filtrar o estoque ===")
# põe os dois cafés e a enxada no controle de estoque, com saldo
for produto in (cafe, enxada):
    api("PUT", f"/api/produtos/{produto['id']}", {
        "empresa_id": eid, "codigo": produto["codigo"], "nome": produto["nome"],
        "categoria_id": produto["categoria_id"] or nova["id"],
        "marca_id": produto["marca_id"] or marca_nova["id"],
        "unidade_id": produto.get("unidade_id"), "controla_estoque": True,
        "unidade_comercial": produto.get("unidade_comercial") or "UN",
        "origem": "0", "ativo": True}, t)
    api("POST", "/api/estoque/ajuste", {
        "empresa_id": eid, "produto_id": produto["id"], "quantidade": 10,
        "custo_unitario": 100, "tipo": "E",
        "historico": "carga inicial do teste"}, t)

posicao = api("GET", f"/api/estoque?empresa_id={eid}", None, t)
checar("os dois produtos entram na posição de estoque",
       len(posicao["produtos"]) == 2, str(len(posicao["produtos"])))
checar("a linha do estoque diz a categoria e a marca",
       all(p["categoria"] and p["marca"] for p in posicao["produtos"]),
       str([(p["codigo"], p["categoria"]) for p in posicao["produtos"]]))

so_cafe = api("GET", f"/api/estoque?empresa_id={eid}&categoria_id={cafe_cat}", None, t)
checar("filtrar o estoque por categoria",
       len(so_cafe["produtos"]) == 1 and so_cafe["produtos"][0]["codigo"] == cafe["codigo"],
       str([p["codigo"] for p in so_cafe["produtos"]]))
checar("e o resumo acompanha o filtro", so_cafe["resumo"]["produtos"] == 1
       and so_cafe["resumo"]["valor_total"] == 1000.0,
       str(so_cafe["resumo"]["valor_total"]))
so_tra = api("GET", f"/api/estoque?empresa_id={eid}&marca_id={marca_nova['id']}", None, t)
checar("filtrar o estoque por marca",
       len(so_tra["produtos"]) == 1 and so_tra["produtos"][0]["codigo"] == enxada["codigo"])

# =========================================================================== #
print("\n=== 6. O relatório por categoria e por marca ===")
rel = api("GET", f"/api/relatorios/produtos-classificacao?empresa_id={eid}"
                 f"&agrupar_por=categoria", None, t)
por_nome = {l["nome"]: l for l in rel["linhas"]}
checar("o relatório traz as categorias que têm estoque",
       {"Café", "Ferramentas e utensílios"} <= set(por_nome), str(sorted(por_nome)))
checar("o estoque de cada categoria é o custo médio x saldo",
       por_nome["Café"]["estoque"] == 1000.0
       and por_nome["Ferramentas e utensílios"]["estoque"] == 1000.0,
       str(por_nome["Café"]["estoque"]))
checar("a quantidade em estoque também sai",
       por_nome["Café"]["quantidade_estoque"] == 10.0)
checar("o total do relatório bate com a soma das linhas",
       rel["totais"]["estoque"] == round(sum(l["estoque"] for l in rel["linhas"]), 2),
       f'{rel["totais"]["estoque"]} x {sum(l["estoque"] for l in rel["linhas"])}')

rel_marca = api("GET", f"/api/relatorios/produtos-classificacao?empresa_id={eid}"
                       f"&agrupar_por=marca", None, t)
marcas_nome = {l["nome"]: l for l in rel_marca["linhas"]}
checar("agrupado por marca dá o mesmo total, dividido de outro jeito",
       rel_marca["totais"]["estoque"] == rel["totais"]["estoque"]
       and {"Sem marca", "Tramontina"} <= set(marcas_nome),
       str(sorted(marcas_nome)))
checar("e o relatório diz o período que usou", bool(rel["periodo"]["de"]))

# ----------------------------------------------- o lado do "vendido"
from datetime import datetime                      # noqa: E402

from backend.database import SessionLocal          # noqa: E402
from backend.models import Nota, NotaItem, Produto  # noqa: E402

db = SessionLocal()
try:
    # uma nota de saída autorizada hoje, com um item de cada produto. É o que o
    # relatório soma; emitir de verdade exigiria certificado e SEFAZ.
    for produto, valor, quantidade in ((cafe, 3000.0, 4), (enxada, 250.0, 5)):
        nota = Nota(empresa_id=eid, chave=f"T{produto['id']}{sufixo}".ljust(44, "0"),
                    tipo="NFE", modelo="55", serie="1", numero=str(produto["id"]),
                    resumo=False, tipo_operacao="1", situacao="AUTORIZADA",
                    data_emissao=datetime.utcnow(), valor_total=valor)
        db.add(nota)
        db.flush()
        db.add(NotaItem(nota_id=nota.id, numero=1, descricao=produto["nome"],
                        produto_id=produto["id"], quantidade=quantidade,
                        valor_unitario=valor / quantidade, valor_total=valor))
    # e uma nota de ENTRADA, que não pode entrar na conta de vendido
    entrada = Nota(empresa_id=eid, chave=f"E{sufixo}".ljust(44, "0"), tipo="NFE",
                   modelo="55", serie="1", numero="999", resumo=False,
                   tipo_operacao="0", situacao="AUTORIZADA",
                   data_emissao=datetime.utcnow(), valor_total=9999.0)
    db.add(entrada)
    db.flush()
    db.add(NotaItem(nota_id=entrada.id, numero=1, descricao=cafe["nome"],
                    produto_id=cafe["id"], quantidade=1, valor_unitario=9999,
                    valor_total=9999.0))
    # e uma saída CANCELADA, que também não conta
    cancelada = Nota(empresa_id=eid, chave=f"C{sufixo}".ljust(44, "0"), tipo="NFE",
                     modelo="55", serie="1", numero="998", resumo=False,
                     tipo_operacao="1", situacao="CANCELADA",
                     data_emissao=datetime.utcnow(), valor_total=5555.0)
    db.add(cancelada)
    db.flush()
    db.add(NotaItem(nota_id=cancelada.id, numero=1, descricao=cafe["nome"],
                    produto_id=cafe["id"], quantidade=1, valor_unitario=5555,
                    valor_total=5555.0))
    db.commit()
finally:
    db.close()

vendas = api("GET", f"/api/relatorios/produtos-classificacao?empresa_id={eid}"
                    f"&agrupar_por=categoria", None, t)
linhas = {l["nome"]: l for l in vendas["linhas"]}
checar("o vendido de cada categoria sai das notas de saída autorizadas",
       linhas["Café"]["vendido"] == 3000.0
       and linhas["Ferramentas e utensílios"]["vendido"] == 250.0,
       f'café={linhas["Café"]["vendido"]} ferr={linhas["Ferramentas e utensílios"]["vendido"]}')
checar("a quantidade vendida também", linhas["Café"]["quantidade_vendida"] == 4.0)
checar("nota de ENTRADA não entra no vendido — senão a compra viraria venda",
       vendas["totais"]["vendido"] == 3250.0, str(vendas["totais"]["vendido"]))
checar("nota CANCELADA também não entra",
       linhas["Café"]["vendido"] == 3000.0)
checar("a participação de cada categoria fecha 100%",
       round(sum(l["percentual"] for l in vendas["linhas"] if l["vendido"]), 1) == 100.0,
       str([l["percentual"] for l in vendas["linhas"]]))
checar("a maior venda vem primeiro na lista", vendas["linhas"][0]["nome"] == "Café")

fora = api("GET", f"/api/relatorios/produtos-classificacao?empresa_id={eid}"
                  f"&agrupar_por=categoria&de=2020-01-01&ate=2020-12-31", None, t)
checar("em período sem venda o vendido zera, mas o estoque de hoje continua",
       fora["totais"]["vendido"] == 0 and fora["totais"]["estoque"] == 2000.0,
       f'vendido={fora["totais"]["vendido"]} estoque={fora["totais"]["estoque"]}')

# ------------------------------------- produto sem classificação não some

db = SessionLocal()
try:
    solto = db.get(Produto, enxada["id"])
    solto.categoria_id = None            # como ficam os produtos cadastrados antes disto
    solto.marca_id = None
    db.commit()
finally:
    db.close()
rel2 = api("GET", f"/api/relatorios/produtos-classificacao?empresa_id={eid}"
                  f"&agrupar_por=categoria", None, t)
sem_cat = next((l for l in rel2["linhas"] if l["nome"] == "Sem categoria"), None)
checar("produto sem classificação entra em linha própria, não some",
       sem_cat is not None and sem_cat["estoque"] == 1000.0,
       str(sem_cat))
checar("e o total continua o mesmo de antes",
       rel2["totais"]["estoque"] == rel["totais"]["estoque"],
       f'{rel2["totais"]["estoque"]} x {rel["totais"]["estoque"]}')
api("PUT", f"/api/produtos/{enxada['id']}", {
    "empresa_id": eid, "codigo": enxada["codigo"], "nome": enxada["nome"],
    "categoria_id": nova["id"], "marca_id": marca_nova["id"],
    "controla_estoque": True, "unidade_comercial": "UN", "origem": "0", "ativo": True}, t)

# =========================================================================== #
print("\n=== 7. Apagar categoria em uso é barrado ===")
recusa = api("DELETE", f"/api/categorias-produto/{nova['id']}", None, t, esperar_erro=True)
checar("categoria com produto não pode ser apagada",
       recusa.get("_status") == 400 and "produtos" in str(recusa.get("detail")).lower(),
       str(recusa.get("detail"))[:70])
recusa_marca = api("DELETE", f"/api/marcas-produto/{marca_nova['id']}", None, t,
                   esperar_erro=True)
checar("marca com produto também não", recusa_marca.get("_status") == 400)

vazia = api("POST", "/api/categorias-produto",
            {"empresa_id": eid, "codigo": "TMP", "nome": "Temporária"}, t)
apagou = api("DELETE", f"/api/categorias-produto/{vazia['id']}", None, t)
checar("categoria sem nenhum produto pode ser apagada", apagou.get("ok") is True)

# =========================================================================== #
print("\n=== 8. A importação de XML não quebra ===")
from backend.notas import produto_do_item           # noqa: E402

db = SessionLocal()
try:
    produto, criado = produto_do_item(
        db, eid, {"descricao": "ADUBO 20-05-20", "codigo": f"XML{sufixo[-4:]}",
                  "unidade": "KG", "ncm": "31052000"}, atualizar=True)
    db.commit()
    checar("o produto criado pela importação nasce classificado em Outros / Sem marca",
           criado and produto.categoria is not None
           and produto.categoria.codigo == "OUT" and produto.marca.codigo == "GEN",
           f"{produto.categoria and produto.categoria.nome} / "
           f"{produto.marca and produto.marca.nome}")
finally:
    db.close()

# =========================================================================== #
print("\n=== 9. A conta do vizinho não enxerga nada disso ===")
checar("outra conta não lê as categorias desta empresa",
       api("GET", f"/api/categorias-produto?empresa_id={eid}", None, outra["token"],
           esperar_erro=True).get("_status") == 403)
checar("nem cria categoria nela",
       api("POST", "/api/categorias-produto",
           {"empresa_id": eid, "codigo": "XX", "nome": "Invasora"}, outra["token"],
           esperar_erro=True).get("_status") == 403)

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Classificação OK — categoria e marca no produto, nos filtros e no relatório.")
