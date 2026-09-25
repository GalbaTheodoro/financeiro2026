"""Teste do controle de estoque.

O que se confere
----------------
  * só o produto marcado **controla estoque** entra no controle — comissão,
    frete e serviço passam batido;
  * o **custo médio ponderado** bate com a conta feita à mão, entrada a entrada;
  * a nota de **entrada** põe no estoque pelo botão, com o custo do item
    (valor − desconto + frete), e só uma vez;
  * o **estorno** desfaz sem apagar: o extrato mostra os dois movimentos;
  * a NF-e de **saída** e o **cupom** baixam sozinhos ao serem autorizados, e o
    custo que sai é o custo médio do momento;
  * **falta de saldo barra a transmissão** antes de a nota ir para a SEFAZ, com
    a frase dizendo quanto tem e quanto a nota quer;
  * misturar unidades (saca com quilo) é recusado;
  * o **acerto à mão** exige motivo, e o **saldo inicial** só vale uma vez;
  * a posição soma o valor parado e acusa saldo negativo e abaixo do mínimo.

Uso:  python testes/teste_estoque.py   (com o servidor no ar)
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import date

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


def perto(a, b, casas=2):
    return abs(float(a) - float(b)) < 10 ** -casas


# =========================================================================== #
print("=== 1. Conta, produtos e quem controla estoque ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"estoque{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock", "plano": "P4_SEMESTRAL"})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "inscricao_estadual": "0022334455001", "logradouro": "AVENIDA FARIA PEREIRA",
    "numero": "1250", "bairro": "CENTRO", "cidade": "Patrocínio", "uf": "MG",
    "cep": "38740108", "codigo_municipio": "3148004", "crt": "3"}, t)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, t)
unidade = api("GET", f"/api/unidades?empresa_id={eid}", None, t)[0]

cafe = api("POST", "/api/produtos", {
    "empresa_id": eid, "codigo": "CAFE-01", "nome": "CAFE CRU EM GRAO",
    "unidade_id": unidade["id"], "ncm": "09011110", "cfop_padrao": "5102",
    "unidade_comercial": "SC", "origem": "0",
    "controla_estoque": True, "estoque_minimo": 20}, t)
comissao = api("POST", "/api/produtos", {
    "empresa_id": eid, "codigo": "COM-01", "nome": "COMISSAO DE CORRETAGEM",
    "unidade_id": unidade["id"], "ncm": "09011110", "cfop_padrao": "5102",
    "unidade_comercial": "UN", "origem": "0"}, t)   # sem controlar estoque

checar("produto de mercadoria controla estoque", cafe["controla_estoque"] is True)
checar("e nasce com saldo zero", perto(cafe["estoque"]["saldo"], 0))
checar("comissão não controla estoque",
       comissao["controla_estoque"] is False and comissao["estoque"] is None)

posicao = api("GET", f"/api/estoque?empresa_id={eid}", None, t)
checar("a posição só traz quem controla estoque",
       len(posicao["produtos"]) == 1 and posicao["produtos"][0]["nome"] == "CAFE CRU EM GRAO",
       str([p["nome"] for p in posicao["produtos"]]))

# =========================================================================== #
print("\n=== 2. Saldo inicial e custo médio ===")
inicial = api("POST", "/api/estoque/saldo-inicial", {
    "empresa_id": eid, "produto_id": cafe["id"], "quantidade": 100,
    "custo_unitario": 1000, "unidade": "SC"}, t)
checar("saldo inicial de 100 sacas a R$ 1.000",
       perto(inicial["produto"]["saldo"], 100) and perto(inicial["produto"]["custo_medio"], 1000),
       f'{inicial["produto"]["saldo"]} x {inicial["produto"]["custo_medio"]}')

de_novo = api("POST", "/api/estoque/saldo-inicial", {
    "empresa_id": eid, "produto_id": cafe["id"], "quantidade": 50}, t, esperar_erro=True)
checar("saldo inicial só vale uma vez",
       de_novo.get("_status") == 400 and "acerto" in str(de_novo.get("detail")),
       str(de_novo.get("detail"))[:70])

# 100 sc a 1.000 + 50 sc a 1.300 => (100.000 + 65.000) / 150 = 1.100
ajuste = api("POST", "/api/estoque/ajuste", {
    "empresa_id": eid, "produto_id": cafe["id"], "tipo": "E", "quantidade": 50,
    "custo_unitario": 1300, "historico": "compra direta do produtor"}, t)
checar("custo médio ponderado: 100 a 1.000 + 50 a 1.300 = 1.100",
       perto(ajuste["produto"]["saldo"], 150) and perto(ajuste["produto"]["custo_medio"], 1100),
       f'{ajuste["produto"]["saldo"]} sc a {ajuste["produto"]["custo_medio"]}')
checar("e o valor parado é 150 x 1.100 = 165.000",
       perto(ajuste["produto"]["valor"], 165000), str(ajuste["produto"]["valor"]))

sem_motivo = api("POST", "/api/estoque/ajuste", {
    "empresa_id": eid, "produto_id": cafe["id"], "tipo": "E", "quantidade": 5}, t,
    esperar_erro=True)
checar("acerto sem motivo é recusado",
       sem_motivo.get("_status") == 400 and "motivo" in str(sem_motivo.get("detail")),
       str(sem_motivo.get("detail"))[:60])

outra_unidade = api("POST", "/api/estoque/ajuste", {
    "empresa_id": eid, "produto_id": cafe["id"], "tipo": "E", "quantidade": 10,
    "unidade": "KG", "historico": "teste de unidade"}, t, esperar_erro=True)
checar("misturar saca com quilo é recusado",
       outra_unidade.get("_status") == 400 and "SC" in str(outra_unidade.get("detail")),
       str(outra_unidade.get("detail"))[:80])

nao_controla = api("POST", "/api/estoque/ajuste", {
    "empresa_id": eid, "produto_id": comissao["id"], "tipo": "E", "quantidade": 1,
    "historico": "teste"}, t, esperar_erro=True)
checar("produto que não controla estoque não aceita movimento",
       nao_controla.get("_status") == 400, str(nao_controla.get("detail"))[:60])

# =========================================================================== #
print("\n=== 3. Entrada pela nota ===")
from backend.database import SessionLocal            # noqa: E402
from backend.models import Nota, NotaItem, Produto   # noqa: E402

fornecedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "FORNECEDOR", "nome": "FAZENDA BOA ESPERANCA",
    "cpf_cnpj": "11222333000181", "cidade": "Patrocínio", "uf": "MG",
    "codigo_municipio": "3148004", "indicador_ie": "9"}, t)

db = SessionLocal()
try:
    nota_entrada = Nota(
        empresa_id=eid, chave="9" * 44, origem="DFE", tipo="NFE", resumo=False,
        modelo="55", serie="1", numero="000123", situacao="AUTORIZADA",
        emitente_cnpj="11222333000181", emitente_nome="FAZENDA BOA ESPERANCA",
        parceiro_id=fornecedor["id"], valor_total=42000, valor_produtos=42000,
        data_emissao=None, xml="<x/>")
    db.add(nota_entrada)
    db.flush()
    # 30 sacas a 1.400 = 42.000, com 200 de desconto e 500 de frete => 42.300
    db.add(NotaItem(nota_id=nota_entrada.id, numero=1, descricao="CAFE CRU EM GRAO",
                    unidade="SC", quantidade=30, valor_unitario=1400, valor_total=42000,
                    desconto=200, frete=500, produto_id=cafe["id"]))
    db.add(NotaItem(nota_id=nota_entrada.id, numero=2, descricao="COMISSAO",
                    unidade="UN", quantidade=1, valor_unitario=500, valor_total=500,
                    produto_id=comissao["id"]))
    db.commit()
    nota_entrada_id = nota_entrada.id
finally:
    db.close()

ficha = api("GET", f"/api/notas/{nota_entrada_id}", None, t)["nota"]
checar("a nota de entrada mostra o botão de gerar estoque",
       ficha["estoque"]["pode_gerar"] is True and ficha["estoque"]["itens"] == 1,
       f'{ficha["estoque"]["itens"]} item(ns) — a comissão ficou de fora')

gerado = api("POST", f"/api/notas/{nota_entrada_id}/estoque", {}, t)
saldo_agora = gerado["movimentos"][0]
# 150 sc a 1.100 + 30 sc a (42.300/30 = 1.410) => (165.000 + 42.300) / 180 = 1.151,666...
checar("a nota põe 30 sacas no estoque",
       perto(saldo_agora["saldo"], 180), str(saldo_agora["saldo"]))
checar("com o custo do item: valor − desconto + frete = 42.300",
       perto(saldo_agora["custo_medio"], 207300 / 180, 3),
       f'custo médio {saldo_agora["custo_medio"]:.4f}')
checar("só o item de mercadoria entrou", len(gerado["movimentos"]) == 1)

repetir = api("POST", f"/api/notas/{nota_entrada_id}/estoque", {}, t, esperar_erro=True)
checar("gerar duas vezes a mesma nota é recusado",
       repetir.get("_status") == 400 and "estorne" in str(repetir.get("detail")).lower(),
       str(repetir.get("detail"))[:70])

estornado = api("POST", f"/api/notas/{nota_entrada_id}/estoque/estornar", {}, t)
checar("o estorno tira as 30 sacas de volta",
       perto(estornado["movimentos"][0]["saldo"], 150),
       str(estornado["movimentos"][0]["saldo"]))
extrato = api("GET", f"/api/estoque/extrato?empresa_id={eid}&produto_id={cafe['id']}", None, t)
checar("e nada é apagado: o extrato mostra a entrada e o estorno",
       any(m["origem"] == "NOTA" for m in extrato["movimentos"])
       and any(m["origem"] == "ESTORNO" for m in extrato["movimentos"]),
       str([m["origem"] for m in extrato["movimentos"]]))

api("POST", f"/api/notas/{nota_entrada_id}/estoque", {}, t)   # põe de volta: 180 sacas

# =========================================================================== #
print("\n=== 4. A venda baixa sozinha ===")
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "OLAM AGRICOLA LTDA",
    "cpf_cnpj": "07028528000894", "cidade": "Alfenas", "uf": "MG",
    "codigo_municipio": "3101607", "indicador_ie": "1",
    "inscricao_estadual": "0011223344556", "logradouro": "RUA A", "numero": "10",
    "bairro": "CENTRO", "cep": "37130000"}, t)


def rascunho(quantidade):
    return api("POST", "/api/nfe/rascunho", {
        "empresa_id": eid, "parceiro_id": cliente["id"], "ambiente": "2", "serie": "1",
        "natureza_operacao": "VENDA", "itens": [
            {"produto_id": cafe["id"], "quantidade": quantidade,
             "valor_unitario": 1500, "cfop": "5102"}]}, t)["nota"]["id"]


# ---- sem saldo, a transmissão é barrada ----
demais = rascunho(500)
barrada = api("POST", f"/api/nfe/{demais}/transmitir", {"empresa_id": eid}, t,
              esperar_erro=True)
checar("venda maior que o saldo é barrada antes da SEFAZ",
       barrada.get("_status") == 400 and "Falta estoque" in str(barrada.get("detail")),
       str(barrada.get("detail"))[:100])
checar("e a frase diz quanto tem e quanto a nota quer",
       "500" in str(barrada.get("detail")) and "180" in str(barrada.get("detail")))

series = api("GET", f"/api/nfe/series?empresa_id={eid}", None, t)
checar("a nota barrada não gastou número da série",
       all(s["proximo_numero"] == 1 for s in series),
       str([(s["serie"], s["proximo_numero"]) for s in series]))

# ---- com saldo: a baixa acontece na autorização ----
# (aqui a SEFAZ não é chamada; o que se testa é o motor, direto)
from backend import estoque as motor                 # noqa: E402

venda_id = rascunho(40)
db = SessionLocal()
try:
    nota = db.get(Nota, venda_id)
    nota.status_emissao = "AUTORIZADA"
    nota.numero = "000001"
    produto = db.get(Produto, cafe["id"])
    custo_antes = float(produto.custo_medio)
    retorno = motor.saida_da_nota(db, nota, None)
    db.commit()
    db.refresh(produto)
    saldo_depois = float(produto.estoque_atual)
    custo_depois = float(produto.custo_medio)
    marcada = nota.estoque_em is not None
finally:
    db.close()

checar("a venda de 40 sacas baixa o estoque sozinha",
       perto(saldo_depois, 140) and len(retorno["movimentos"]) == 1, str(saldo_depois))
checar("o custo médio não muda na saída", perto(custo_antes, custo_depois, 4),
       f"{custo_antes:.4f} -> {custo_depois:.4f}")
checar("a nota fica marcada como baixada", marcada)

extrato = api("GET", f"/api/estoque/extrato?empresa_id={eid}&origem=SAIDA", None, t)
checar("o movimento de saída sai com o custo médio do momento",
       extrato["movimentos"] and perto(extrato["movimentos"][0]["custo_unitario"],
                                       custo_antes, 4),
       str(extrato["movimentos"][0]["custo_unitario"]) if extrato["movimentos"] else "")

# ---- cancelar devolve ----
db = SessionLocal()
try:
    nota = db.get(Nota, venda_id)
    motor.estornar_nota(db, nota, None, motivo="nota cancelada no teste")
    db.commit()
    db.refresh(nota)
    produto = db.get(Produto, cafe["id"])
    db.refresh(produto)
    voltou = float(produto.estoque_atual)
finally:
    db.close()
checar("cancelar a venda devolve a mercadoria ao estoque", perto(voltou, 180), str(voltou))

# =========================================================================== #
print("\n=== 5. A posição ===")
api("POST", "/api/estoque/ajuste", {
    "empresa_id": eid, "produto_id": cafe["id"], "tipo": "S", "quantidade": 175,
    "historico": "venda no balcão, fora do sistema"}, t)
posicao = api("GET", f"/api/estoque?empresa_id={eid}", None, t)
linha = posicao["produtos"][0]
checar("o saldo desce para 5 sacas", perto(linha["saldo"], 5), str(linha["saldo"]))
checar("e acusa que está abaixo do mínimo de 20",
       linha["abaixo_do_minimo"] is True and posicao["resumo"]["abaixo_do_minimo"] == 1)
checar("o valor parado acompanha o custo médio",
       perto(linha["valor"], 5 * linha["custo_medio"], 1), str(linha["valor"]))

api("POST", "/api/estoque/ajuste", {
    "empresa_id": eid, "produto_id": cafe["id"], "tipo": "S", "quantidade": 8,
    "historico": "quebra de estoque apurada na contagem"}, t)
posicao = api("GET", f"/api/estoque?empresa_id={eid}", None, t)
checar("saldo negativo é acusado na posição",
       posicao["produtos"][0]["negativo"] is True and posicao["resumo"]["negativos"] == 1,
       str(posicao["produtos"][0]["saldo"]))

so_com_saldo = api("GET", f"/api/estoque?empresa_id={eid}&apenas_com_saldo=true", None, t)
checar("o filtro 'só quem tem saldo' funciona", len(so_com_saldo["produtos"]) == 1)

# =========================================================================== #
print("\n=== 6. A empresa do vizinho ===")
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"estoque-outro{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra Assessoria", "plano": "P4_SEMESTRAL"})
espiada = api("GET", f"/api/estoque?empresa_id={eid}", None, outra["token"],
              esperar_erro=True)
checar("estoque de outra conta não abre", espiada.get("_status") == 403,
       str(espiada.get("_status")))

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Estoque OK — entrada pela nota, baixa na venda e custo médio conferido.")
