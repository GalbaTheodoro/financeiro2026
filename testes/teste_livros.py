"""Teste dos livros fiscais — Fiscal → Relatórios Fiscais.

O que se confere
----------------
  * **entradas e saídas separadas como no SPED**: nota importada é entrada; NF-e
    e cupom emitidos são saída; rascunho e nota de outro mês não entram (a regra
    da cópia do DF-e é a do SPED, conferida no teste dele);
  * **uma linha por documento e por CFOP + alíquota**, e a soma das linhas é o
    total da nota (frete incluído), com a última linha levando o arredondamento;
  * **tributada, isenta ou outras** pelo CST: 00 com base, 20 com a redução em
    isentas, 40 isenta, 51 (diferimento do café) em outras;
  * **nota cancelada** aparece zerada, com a observação, e fica fora dos resumos;
  * **resumo por CFOP e por estado** batem com os livros; cupom conta no estado
    da empresa; saída para SP vai para SP;
  * **livro de estoque**: saldo inicial, entradas, saídas e saldo final pela soma
    dos movimentos — inclusive um lançado com data retroativa —, e o saldo
    final bate com o estoque de hoje quando o período vai até hoje;
  * período inválido, livro que não existe e empresa de outra conta são
    recusados.

Uso:  python testes/teste_livros.py   (com o servidor no ar)
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
        dados = json.loads(erro.read() or b"{}")
        dados["_status"] = erro.code
        return dados


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


from backend import estoque, livros                           # noqa: E402
from backend.database import SessionLocal                     # noqa: E402
from backend.models import Nota, NotaItem, Produto            # noqa: E402

# =========================================================================== #
print("=== 1. Classificação pelo CST ===")
checar("CST 00 com base: o que sobra (frete) vai para outras",
       livros._classificar("000", 1100, 1000) == (0.0, 100.0),
       livros._classificar("000", 1100, 1000))
checar("CST 20: a redução de base vai para isentas",
       livros._classificar("020", 1000, 600) == (400.0, 0.0),
       livros._classificar("020", 1000, 600))
checar("CST 40 sem base: isenta", livros._classificar("040", 500, 0) == (500.0, 0.0))
checar("CST 41 sem base: não tributada", livros._classificar("041", 500, 0) == (500.0, 0.0))
checar("CST 51 (diferimento do café): outras",
       livros._classificar("051", 500, 0) == (0.0, 500.0))
checar("UF do destinatário sai do XML quando não há cadastro",
       livros._uf_do_xml("<emit><UF>MG</UF></emit><dest><enderDest><UF>GO</UF>"
                         "</enderDest></dest>", "dest") == "GO")

# =========================================================================== #
print("\n=== 2. Montar a empresa, as notas e o estoque ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"livros{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria Livros", "plano": "P4_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA LIVROS LTDA", "cnpj": "12.345.678/0001-95",
    "inscricao_estadual": "0011223344556", "uf": "MG", "cidade": "VARGINHA",
    "codigo_municipio": "3170701", "crt": "3"}, t)

produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe = produtos[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: cafe[k] for k in ("empresa_id", "codigo", "nome", "unidade_id",
                            "categoria_id", "marca_id")},
    "ncm": "09011110", "unidade_comercial": "SC", "controla_estoque": True}, t)
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "11.222.333/0001-44", "uf": "SP", "cidade": "SAO PAULO"}, t)

sessao = SessionLocal()


def chave(cnpj, modelo, numero):
    base = "31" + "2601" + cnpj + modelo + "001" + str(numero).zfill(9) + "1" + "00000"
    return (base + "0" * 44)[:44]


def gravar_nota(**dados):
    itens = dados.pop("itens", [])
    nota = Nota(empresa_id=eid, tipo="NFE", resumo=False, **dados)
    sessao.add(nota)
    sessao.flush()
    for numero, item in enumerate(itens, start=1):
        sessao.add(NotaItem(nota_id=nota.id, numero=numero, origem_mercadoria="0",
                            produto_id=cafe["id"], unidade="SC", **item))
    sessao.flush()
    return nota


EMPRESA = "12345678000195"
FORNECEDOR = "98765432000110"

# entrada de MG com dois grupos: 1102 tributado 12% e 1102 diferido (CST 51), + frete
gravar_nota(
    chave=chave(FORNECEDOR, "55", 101), origem="DFE", modelo="55", serie="1",
    numero="101", data_emissao=datetime(2026, 1, 12, 9), emitente_cnpj=FORNECEDOR,
    emitente_nome="FAZENDA BOA VISTA LTDA", emitente_uf="MG", situacao="AUTORIZADA",
    valor_total=1100, valor_produtos=1000, valor_frete=100, valor_icms=72,
    itens=[
        dict(descricao="CAFE A", cfop="1102", quantidade=1, valor_unitario=600,
             valor_total=600, icms_cst="00", icms_base=600, icms_aliquota=12, icms_valor=72),
        dict(descricao="CAFE B", cfop="1102", quantidade=1, valor_unitario=400,
             valor_total=400, icms_cst="51", icms_base=0, icms_aliquota=0, icms_valor=0),
    ],
)
# entrada de GO, isenta (CST 40), UF só no XML
gravar_nota(
    chave=chave("55666777000188", "55", 55), origem="DFE", modelo="55", serie="2",
    numero="55", data_emissao=datetime(2026, 1, 15, 10), emitente_cnpj="55666777000188",
    emitente_nome="COOPERATIVA GOIANA", situacao="AUTORIZADA", valor_total=300,
    valor_produtos=300, xml="<nfeProc><emit><enderEmit><UF>GO</UF></enderEmit></emit></nfeProc>",
    itens=[dict(descricao="CAFE C", cfop="2102", quantidade=1, valor_unitario=300,
                valor_total=300, icms_cst="40", icms_base=0, icms_aliquota=0, icms_valor=0)],
)
# saída para SP, CST 20 com redução
saida = gravar_nota(
    chave=chave(EMPRESA, "55", 201), origem="EMITIDA", modelo="55", serie="1",
    numero="201", data_emissao=datetime(2026, 1, 20, 14), emitente_cnpj=EMPRESA,
    destinatario_nome="TORREFACAO PAULISTA LTDA", destinatario_cnpj="11222333000144",
    situacao="AUTORIZADA", status_emissao="AUTORIZADA", parceiro_id=cliente["id"],
    valor_total=1000, valor_produtos=1000, valor_icms=42, cfop="6102",
    itens=[dict(descricao="CAFE", cfop="6102", quantidade=1, valor_unitario=1000,
                valor_total=1000, icms_cst="20", icms_base=600, icms_aliquota=7,
                icms_valor=42)],
)
# cupom (conta no estado da empresa)
gravar_nota(
    chave=chave(EMPRESA, "65", 301), origem="EMITIDA", modelo="65", serie="1",
    numero="301", data_emissao=datetime(2026, 1, 22, 11), emitente_cnpj=EMPRESA,
    situacao="AUTORIZADA", status_emissao="AUTORIZADA", valor_total=90,
    valor_produtos=90, valor_icms=16.2, cfop="5102",
    itens=[dict(descricao="CAFE TORRADO", cfop="5102", quantidade=3, valor_unitario=30,
                valor_total=90, icms_cst="00", icms_base=90, icms_aliquota=18,
                icms_valor=16.2)],
)
# cancelada
gravar_nota(
    chave=chave(EMPRESA, "55", 202), origem="EMITIDA", modelo="55", serie="1",
    numero="202", data_emissao=datetime(2026, 1, 25, 8), emitente_cnpj=EMPRESA,
    situacao="CANCELADA", status_emissao="CANCELADA", valor_total=5000, cfop="5102",
    itens=[dict(descricao="CAFE", cfop="5102", quantidade=1, valor_unitario=5000,
                valor_total=5000, icms_cst="00", icms_base=5000, icms_aliquota=18,
                icms_valor=900)],
)
# rascunho: não é documento fiscal
gravar_nota(
    chave=f"RASCUNHO-livros-{sufixo}", origem="EMITIDA", modelo="55", serie="1",
    data_emissao=datetime(2026, 1, 26, 8), emitente_cnpj=EMPRESA,
    situacao="AUTORIZADA", status_emissao="RASCUNHO", valor_total=7777,
)
# fora do período
gravar_nota(
    chave=chave(EMPRESA, "55", 203), origem="EMITIDA", modelo="55", serie="1",
    numero="203", data_emissao=datetime(2026, 2, 2, 8), emitente_cnpj=EMPRESA,
    situacao="AUTORIZADA", status_emissao="AUTORIZADA", valor_total=999, cfop="5102",
    itens=[dict(descricao="CAFE", cfop="5102", quantidade=1, valor_unitario=999,
                valor_total=999, icms_cst="00", icms_base=999, icms_aliquota=18,
                icms_valor=179.82)],
)
sessao.commit()

# estoque: saldo inicial em dezembro, entrada e saída em janeiro, uma saída em
# fevereiro, e uma entrada de janeiro lançada DEPOIS (data retroativa)
produto = sessao.get(Produto, cafe["id"])
estoque.registrar(sessao, produto, "E", 10, custo_unitario=100, unidade="SC",
                  origem="SALDO_INICIAL", data_movimento=date(2025, 12, 1))
estoque.registrar(sessao, produto, "E", 10, custo_unitario=130, unidade="SC",
                  origem="AJUSTE", data_movimento=date(2026, 1, 10), historico="compra")
estoque.registrar(sessao, produto, "S", 5, unidade="SC", origem="AJUSTE",
                  data_movimento=date(2026, 1, 20), historico="venda")
estoque.registrar(sessao, produto, "S", 2, unidade="SC", origem="AJUSTE",
                  data_movimento=date(2026, 2, 5), historico="venda de fevereiro")
estoque.registrar(sessao, produto, "E", 4, custo_unitario=115, unidade="SC",
                  origem="AJUSTE", data_movimento=date(2026, 1, 28), historico="retroativa")
sessao.commit()
sessao.refresh(produto)
checar("estoque montado", produto.estoque_atual == 17, produto.estoque_atual)

PERIODO = "de=2026-01-01&ate=2026-01-31"


def livro(nome, extra=""):
    return api("GET", f"/api/livros/{nome}?empresa_id={eid}&{PERIODO}{extra}", None, t)


# =========================================================================== #
print("\n=== 3. Registro de Entradas ===")
ent = livro("entradas")
checar("duas notas de entrada no período", ent["documentos"] == 2, ent["documentos"])
nota101 = [x for x in ent["linhas"] if x["numero"] == "101"]
checar("a nota 101 tem duas linhas (tributada e diferida)", len(nota101) == 2, len(nota101))
checar("a soma das linhas é o total da nota, frete incluído",
       round(sum(x["valor_contabil"] for x in nota101), 2) == 1100,
       sum(x["valor_contabil"] for x in nota101))
trib = next(x for x in nota101 if x["base"] > 0)
dif = next(x for x in nota101 if x["base"] == 0)
checar("linha tributada: base 600, ICMS 72, 12%",
       trib["base"] == 600 and trib["icms"] == 72 and trib["aliquota"] == 12, trib)
checar("linha tributada: o frete repartido vai para outras",
       trib["outras"] == 60 and trib["isentas"] == 0, (trib["outras"], trib["isentas"]))
checar("linha diferida (CST 51) vai toda para outras",
       dif["outras"] == dif["valor_contabil"] == 440, (dif["outras"], dif["valor_contabil"]))
go = next(x for x in ent["linhas"] if x["numero"] == "55")
checar("UF do emitente lida do XML", go["uf"] == "GO", go["uf"])
checar("CST 40 vai para isentas", go["isentas"] == 300 and go["outras"] == 0, go)
checar("totais das entradas: contábil 1400, ICMS 72",
       ent["totais"]["valor_contabil"] == 1400 and ent["totais"]["icms"] == 72, ent["totais"])
checar("cabeçalho da empresa vem junto",
       ent["empresa"]["razao_social"] == "ASSESSORIA LIVROS LTDA", ent["empresa"])

# =========================================================================== #
print("\n=== 4. Registro de Saídas ===")
sai = livro("saidas")
numeros = sorted(x["numero"] for x in sai["linhas"])
checar("saídas: NF-e 201, cupom 301 e a cancelada 202 — sem rascunho, sem fevereiro",
       numeros == ["201", "202", "301"], numeros)
n201 = next(x for x in sai["linhas"] if x["numero"] == "201")
checar("saída para SP: UF do cliente", n201["uf"] == "SP", n201["uf"])
checar("CST 20: base 600, redução de 400 em isentas",
       n201["base"] == 600 and n201["isentas"] == 400 and n201["outras"] == 0, n201)
cup = next(x for x in sai["linhas"] if x["numero"] == "301")
checar("cupom é NFC-e e conta no estado da empresa",
       cup["especie"] == "NFC-e" and cup["uf"] == "MG", (cup["especie"], cup["uf"]))
canc = next(x for x in sai["linhas"] if x["numero"] == "202")
checar("cancelada aparece zerada, com a observação",
       canc["observacao"] == "CANCELADA" and canc["valor_contabil"] == 0, canc)
checar("totais das saídas: contábil 1090, ICMS 58,20",
       sai["totais"]["valor_contabil"] == 1090 and sai["totais"]["icms"] == 58.2,
       sai["totais"])
checar("contagem de canceladas", sai["canceladas"] == 1, sai["canceladas"])

# =========================================================================== #
print("\n=== 5. Resumo por CFOP ===")
cf = livro("cfop")
cf_ent = {x["cfop"]: x for x in cf["entradas"]["linhas"]}
cf_sai = {x["cfop"]: x for x in cf["saidas"]["linhas"]}
checar("entradas: 1102 e 2102", sorted(cf_ent) == ["1102", "2102"], sorted(cf_ent))
checar("1102 soma as duas linhas da nota 101",
       cf_ent["1102"]["valor_contabil"] == 1100 and cf_ent["1102"]["documentos"] == 1,
       cf_ent["1102"])
checar("saídas: 5102 e 6102 — a cancelada não conta",
       sorted(cf_sai) == ["5102", "6102"] and cf_sai["5102"]["valor_contabil"] == 90,
       {k: v["valor_contabil"] for k, v in cf_sai.items()})
checar("grupo do CFOP descrito", cf_sai["6102"]["grupo"] == "Saídas para outros estados")
checar("total de saídas por CFOP bate com o livro de saídas",
       cf["saidas"]["totais"]["valor_contabil"] == sai["totais"]["valor_contabil"])

# =========================================================================== #
print("\n=== 6. Resumo por Estado ===")
uf = livro("uf")
uf_ent = {x["uf"]: x for x in uf["entradas"]["linhas"]}
uf_sai = {x["uf"]: x for x in uf["saidas"]["linhas"]}
checar("entradas de MG e GO", sorted(uf_ent) == ["GO", "MG"], sorted(uf_ent))
checar("saídas para MG (cupom) e SP", sorted(uf_sai) == ["MG", "SP"], sorted(uf_sai))
checar("MG marcado como dentro do estado",
       uf_sai["MG"]["dentro_do_estado"] and not uf_sai["SP"]["dentro_do_estado"])
checar("total por estado bate com o livro de entradas",
       uf["entradas"]["totais"]["valor_contabil"] == ent["totais"]["valor_contabil"])

# =========================================================================== #
print("\n=== 7. Livro de estoque ===")
es = livro("estoque")
linha = next(x for x in es["linhas"] if x["produto_id"] == cafe["id"])
checar("saldo inicial: 10 sacas a 100 = 1.000",
       linha["inicial_quantidade"] == 10 and linha["inicial_valor"] == 1000, linha)
checar("entradas de janeiro: 14 sacas (inclusive a retroativa) = 1.760",
       linha["entradas_quantidade"] == 14 and linha["entradas_valor"] == 1760, linha)
checar("saídas de janeiro: 5 sacas", linha["saidas_quantidade"] == 5, linha)
checar("saldo final de janeiro: 19 sacas (a saída de fevereiro fica de fora)",
       linha["final_quantidade"] == 19, linha["final_quantidade"])
checar("valor final = inicial + entradas − saídas",
       round(linha["inicial_valor"] + linha["entradas_valor"] - linha["saidas_valor"], 2)
       == linha["final_valor"], linha)
hoje = date.today().isoformat()
ate_hoje = api("GET", f"/api/livros/estoque?empresa_id={eid}&de=2026-01-01&ate={hoje}",
               None, t)
l2 = next(x for x in ate_hoje["linhas"] if x["produto_id"] == cafe["id"])
checar("até hoje, o saldo final bate com o estoque do produto",
       l2["final_quantidade"] == produto.estoque_atual, (l2["final_quantidade"],
                                                         produto.estoque_atual))
checar("totais do livro de estoque", es["totais"]["produtos"] >= 1, es["totais"])
dez = api("GET", f"/api/livros/estoque?empresa_id={eid}&de=2025-11-01&ate=2025-11-30"
               "&apenas_com_movimento=true", None, t)
checar("só com movimento: novembro não tem nada", dez["linhas"] == [], dez["linhas"])

# =========================================================================== #
print("\n=== 8. O que é recusado ===")
r = api("GET", f"/api/livros/diario?empresa_id={eid}&{PERIODO}", None, t, esperar_erro=True)
checar("livro que não existe: 404", r.get("_status") == 404, r)
r = api("GET", f"/api/livros/entradas?empresa_id={eid}&de=2026-02-01&ate=2026-01-01",
        None, t, esperar_erro=True)
checar("data inicial maior que a final: 400", r.get("_status") == 400, r)
r = api("GET", f"/api/livros/entradas?empresa_id={eid}&de=2024-01-01&ate=2026-01-01",
        None, t, esperar_erro=True)
checar("período maior que um ano: 400", r.get("_status") == 400, r)
r = api("GET", f"/api/livros/entradas?empresa_id={eid}&de=ontem", None, t, esperar_erro=True)
checar("data inválida: 400, não erro interno", r.get("_status") == 400, r)
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"livros-outro{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra", "plano": "P1_ANUAL", "uf": "SP"})
r = api("GET", f"/api/livros/entradas?empresa_id={eid}&{PERIODO}", None,
        outra["token"], esperar_erro=True)
checar("empresa de outra conta: recusado", r.get("_status") in (403, 404), r.get("_status"))

sessao.close()
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(" -", e)
    sys.exit(1)
print("Todos os testes dos livros fiscais passaram.")
