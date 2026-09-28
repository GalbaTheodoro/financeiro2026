"""Teste de **quando** o estoque baixa: pelo documento fiscal ou pelo pedido.

A escolha é da empresa (Cadastros → Empresas → Quando o estoque baixa), porque
depende de quando a mercadoria sai da prateleira:

  DOCUMENTO  sai quando a SEFAZ autoriza a nota ou o cupom (o padrão de sempre);
  PEDIDO     sai quando a venda é fechada no balcão, com ou sem documento.

O que se confere
----------------
  * a empresa nasce no **DOCUMENTO** — quem já usava o sistema não vê o estoque
    mudar de comportamento numa atualização;
  * no DOCUMENTO, finalizar **sem documento** não mexe no saldo;
  * no PEDIDO, finalizar **sem documento** baixa na hora;
  * **baixa uma vez só**: emitindo a nota depois, no modo PEDIDO, o saldo não
    cai de novo — e no modo DOCUMENTO cai exatamente aí;
  * **falta de saldo barra a venda** antes de ela acontecer, e o pedido continua
    aberto, sem ter gasto número de nota nem gerado título;
  * o movimento do pedido fica no extrato com a origem certa e o número do
    pedido;
  * **cancelar a nota devolve** a mercadoria nos dois modos — inclusive quando
    quem baixou foi o pedido;
  * valor inventado no campo é recusado, em vez de a empresa parar de baixar
    estoque em silêncio.

Uso:  python testes/teste_baixa_estoque.py   (com o servidor no ar)
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


from backend import estoque as motor                          # noqa: E402
from backend.database import SessionLocal                      # noqa: E402
from backend.models import Empresa, Pedido, Produto            # noqa: E402

# =========================================================================== #
print("=== 1. Os dois momentos ===")
checar("são dois: pelo documento e pelo pedido",
       set(motor.MOMENTOS) == {"DOCUMENTO", "PEDIDO"}, str(list(motor.MOMENTOS)))
checar("o padrão é pelo documento — ninguém muda de comportamento numa atualização",
       motor.MOMENTO_PADRAO == "DOCUMENTO")
checar("a origem PEDIDO existe no extrato", "PEDIDO" in motor.ORIGENS)

# =========================================================================== #
print("\n=== 2. Montar a empresa e o produto com saldo ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"baixa{sufixo}@teste.com", "senha": "123456",
    "empresa": "Balcao do Cafe", "plano": "P4_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]

empresa = api("GET", f"/api/empresas", None, t)[0]
checar("a empresa nasce baixando pelo documento fiscal",
       empresa.get("estoque_baixa") == "DOCUMENTO", str(empresa.get("estoque_baixa")))

produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe = produtos[0]
base = {k: cafe[k] for k in ("empresa_id", "codigo", "nome", "unidade_id",
                             "categoria_id", "marca_id")}
api("PUT", f"/api/produtos/{cafe['id']}", {
    **base, "ncm": "09011110", "unidade_comercial": "SC", "controla_estoque": True,
    "preco_venda": 1300}, t)

# saldo inicial pela tela de estoque (é o caminho de quem começa a controlar)
api("POST", "/api/estoque/ajuste", {
    "empresa_id": eid, "produto_id": cafe["id"], "tipo": "E", "quantidade": 100,
    "custo_unitario": 1000, "unidade": "SC", "historico": "Saldo inicial do teste"}, t)


def saldo():
    ficha = api("GET", f"/api/estoque?empresa_id={eid}", None, t)
    linha = next(p for p in ficha["produtos"] if p["produto_id"] == cafe["id"])
    return linha["saldo"]


checar("o saldo inicial entrou", saldo() == 100, str(saldo()))


def novo_pedido(quantidade=10):
    return api("POST", "/api/pedidos", {
        "empresa_id": eid, "tipo": "PEDIDO",
        "itens": [{"produto_id": cafe["id"], "descricao": cafe["nome"],
                   "unidade": "SC", "quantidade": quantidade,
                   "valor_unitario": 1300}]}, t)["pedido"]


def modo(valor):
    atual = api("GET", "/api/empresas", None, t)[0]
    api("PUT", f"/api/empresas/{eid}", {**{k: atual[k] for k in (
        "razao_social", "nome_fantasia", "cnpj", "uf", "cidade", "crt")},
        "estoque_baixa": valor}, t)


# =========================================================================== #
print("\n=== 3. Pelo documento (o padrão): venda sem nota não mexe no saldo ===")
antes = saldo()
pedido = novo_pedido(10)
retorno = api("POST", f"/api/pedidos/{pedido['id']}/finalizar",
              {"condicao": "VISTA", "documento": "SEM"}, t)
checar("a venda fecha sem documento", retorno.get("ok") is True,
       str(retorno.get("mensagem"))[:70])
checar("e o saldo NÃO muda — a mercadoria sai quando o documento sair",
       saldo() == antes, f"{antes} -> {saldo()}")
checar("a mensagem avisa disso",
       "estoque só baixa quando" in str(retorno.get("mensagem")),
       str(retorno.get("mensagem"))[-80:])

sessao = SessionLocal()
guardado = sessao.get(Pedido, pedido["id"])
checar("e o pedido não ficou marcado como quem baixou estoque",
       guardado.estoque_em is None)
sessao.close()

# =========================================================================== #
print("\n=== 4. Pelo pedido: a venda sem nota baixa na hora ===")
modo("PEDIDO")
antes = saldo()
pedido2 = novo_pedido(10)
retorno = api("POST", f"/api/pedidos/{pedido2['id']}/finalizar",
              {"condicao": "VISTA", "documento": "SEM"}, t)
checar("a venda fecha", retorno.get("ok") is True, str(retorno.get("mensagem"))[:60])
checar("e o saldo cai agora", saldo() == antes - 10, f"{antes} -> {saldo()}")
checar("a mensagem conta quantos produtos saíram",
       "saíram do estoque" in str(retorno.get("mensagem")),
       str(retorno.get("mensagem"))[-90:])

extrato = api("GET", f"/api/estoque/extrato?empresa_id={eid}&produto_id={cafe['id']}",
              None, t)
ultimo = extrato["movimentos"][0] if extrato["movimentos"] else {}
checar("o movimento fica no extrato com a origem PEDIDO",
       ultimo.get("origem") == "PEDIDO", str(ultimo.get("origem")))
checar("e com o número do pedido, para saber de que venda veio",
       pedido2["numero"] in str(ultimo.get("documento", "")),
       str(ultimo.get("documento")))

# =========================================================================== #
print("\n=== 5. Baixa uma vez só ===")
# emitir o documento depois NÃO pode baixar de novo
antes = saldo()
emissao = api("POST", f"/api/pedidos/{pedido2['id']}/documento",
              {"condicao": "VISTA", "documento": "CUPOM", "ambiente": "2"}, t)
checar("sem certificado a emissão não vai, e isso não mexe no estoque",
       saldo() == antes, f"{antes} -> {saldo()}")

sessao = SessionLocal()
p2 = sessao.get(Pedido, pedido2["id"])
checar("o pedido continua marcado como quem baixou", p2.estoque_em is not None)
sessao.close()

# =========================================================================== #
print("\n=== 6. Falta de saldo barra a venda antes de ela acontecer ===")
disponivel = saldo()
demais = novo_pedido(disponivel + 50)
recusa = api("POST", f"/api/pedidos/{demais['id']}/finalizar",
             {"condicao": "VISTA", "documento": "SEM"}, t, esperar_erro=True)
checar("a finalização é recusada", recusa.get("_status") == 400,
       str(recusa.get("detail"))[:80])
checar("a frase diz o produto, quanto tem e quanto a venda quer",
       "estoque tem" in str(recusa.get("detail")),
       str(recusa.get("detail"))[:110])
checar("e o saldo não mudou", saldo() == disponivel)
ainda = api("GET", f"/api/pedidos/{demais['id']}", None, t)["pedido"]
checar("o pedido continua ABERTO — a venda montada não se perdeu",
       ainda["situacao"] == "ABERTO")
checar("sem documento e sem título", not ainda["nota_id"] and not ainda["lancamento_id"])

# no modo DOCUMENTO essa mesma venda fecha (o saldo só será conferido na nota)
modo("DOCUMENTO")
passa = api("POST", f"/api/pedidos/{demais['id']}/finalizar",
            {"condicao": "VISTA", "documento": "SEM"}, t)
checar("no modo DOCUMENTO a mesma venda fecha — quem confere saldo é a nota",
       passa.get("ok") is True, str(passa.get("mensagem"))[:60])
checar("e o saldo continua intocado", saldo() == disponivel)

# =========================================================================== #
print("\n=== 7. A empresa só aceita os dois valores ===")
atual = api("GET", "/api/empresas", None, t)[0]
invalido = api("PUT", f"/api/empresas/{eid}", {
    "razao_social": atual["razao_social"], "uf": atual["uf"],
    "estoque_baixa": "QUANDO_EU_QUISER"}, t, esperar_erro=True)
checar("valor inventado é recusado", invalido.get("_status") == 400,
       str(invalido.get("detail"))[:70])
depois = api("GET", "/api/empresas", None, t)[0]
checar("e a empresa fica como estava, sem parar de baixar estoque em silêncio",
       depois["estoque_baixa"] == "DOCUMENTO", str(depois["estoque_baixa"]))

# =========================================================================== #
print("\n=== 8. O estorno acha a baixa, tenha ela vindo de onde vier ===")
sessao = SessionLocal()
p2 = sessao.get(Pedido, pedido2["id"])
produto = sessao.get(Produto, cafe["id"])
antes = float(produto.estoque_atual or 0)
devolvido = motor.estornar_pedido(sessao, p2, None, motivo="Teste de devolução")
sessao.commit()
sessao.refresh(produto)
checar("estornar o pedido devolve a mercadoria",
       float(produto.estoque_atual or 0) == antes + 10,
       f"{antes} -> {produto.estoque_atual}")
checar("e o pedido deixa de estar marcado", p2.estoque_em is None)
checar("sem apagar nada: o estorno é uma linha nova",
       len(devolvido["movimentos"]) == 1)
de_novo = None
try:
    motor.estornar_pedido(sessao, p2, None)
    de_novo = "passou"
except motor.ErroEstoque as erro:
    de_novo = str(erro)
checar("estornar duas vezes é recusado", "não mexeu no estoque" in str(de_novo),
       str(de_novo)[:60])
sessao.rollback()
sessao.close()

# =========================================================================== #
print("\n=== 9. A nota emitida fora de pedido baixa sempre ===")
# no modo PEDIDO, quem vende pela tela de notas ou de cupom continua baixando na
# autorização — senão o saldo nunca andaria por lá
sessao = SessionLocal()
empresa_obj = sessao.get(Empresa, eid)
empresa_obj.estoque_baixa = "PEDIDO"
sessao.commit()
checar("o momento lido do banco é o que a empresa escolheu",
       motor.momento_da_baixa(sessao, eid) == "PEDIDO")

from backend.models import Nota, NotaItem                      # noqa: E402
nota = Nota(empresa_id=eid, chave=f"AVULSA-{sufixo}", origem="EMITIDA", tipo="NFE",
            modelo="55", serie="1", numero="9001", status_emissao="AUTORIZADA",
            situacao="AUTORIZADA", valor_total=2600)
sessao.add(nota)
sessao.flush()
sessao.add(NotaItem(nota_id=nota.id, numero=1, descricao="CAFE", unidade="SC",
                    quantidade=2, valor_unitario=1300, valor_total=2600,
                    produto_id=cafe["id"]))
sessao.flush()
produto = sessao.get(Produto, cafe["id"])
antes = float(produto.estoque_atual or 0)
motor.saida_da_nota(sessao, nota, None)
sessao.commit()
sessao.refresh(produto)
checar("nota sem pedido baixa mesmo no modo PEDIDO",
       float(produto.estoque_atual or 0) == antes - 2,
       f"{antes} -> {produto.estoque_atual}")

# e a nota que veio de um pedido não baixa
nota2 = Nota(empresa_id=eid, chave=f"DOPEDIDO-{sufixo}", origem="EMITIDA", tipo="NFE",
             modelo="55", serie="1", numero="9002", status_emissao="AUTORIZADA",
             situacao="AUTORIZADA", valor_total=1300, pedido_id=pedido2["id"])
sessao.add(nota2)
sessao.flush()
sessao.add(NotaItem(nota_id=nota2.id, numero=1, descricao="CAFE", unidade="SC",
                    quantidade=1, valor_unitario=1300, valor_total=1300,
                    produto_id=cafe["id"]))
sessao.flush()
antes = float(produto.estoque_atual or 0)
motor.saida_da_nota(sessao, nota2, None)
sessao.commit()
sessao.refresh(produto)
checar("nota que nasceu de um pedido não baixa de novo",
       float(produto.estoque_atual or 0) == antes,
       f"{antes} -> {produto.estoque_atual}")
checar("e ela fica sem marca de estoque, porque não mexeu em nada",
       nota2.estoque_em is None)

# no modo DOCUMENTO essa mesma nota baixaria
empresa_obj.estoque_baixa = "DOCUMENTO"
sessao.commit()
antes = float(produto.estoque_atual or 0)
motor.saida_da_nota(sessao, nota2, None)
sessao.commit()
sessao.refresh(produto)
checar("no modo DOCUMENTO a nota do pedido baixa normalmente",
       float(produto.estoque_atual or 0) == antes - 1,
       f"{antes} -> {produto.estoque_atual}")
sessao.close()

# =========================================================================== #
print("\n=== 10. Cancelar a nota devolve, mesmo quando quem baixou foi o pedido ===")
sessao = SessionLocal()
empresa_obj = sessao.get(Empresa, eid)
empresa_obj.estoque_baixa = "PEDIDO"
sessao.commit()

pedido3 = novo_pedido(5)
api("POST", f"/api/pedidos/{pedido3['id']}/finalizar",
    {"condicao": "VISTA", "documento": "SEM"}, t)
produto = sessao.get(Produto, cafe["id"])
sessao.refresh(produto)
apos_venda = float(produto.estoque_atual or 0)

# a nota sai depois, ligada ao pedido; depois ela é cancelada
nota3 = Nota(empresa_id=eid, chave=f"CANCELA-{sufixo}", origem="EMITIDA", tipo="NFE",
             modelo="55", serie="1", numero="9003", status_emissao="AUTORIZADA",
             situacao="AUTORIZADA", valor_total=6500, pedido_id=pedido3["id"])
sessao.add(nota3)
sessao.commit()
devolvido = motor.estornar_venda(sessao, nota3, None, motivo="Nota cancelada")
sessao.commit()
sessao.refresh(produto)
checar("o estorno encontrou a baixa que estava no pedido", devolvido is not None,
       str(devolvido and len(devolvido["movimentos"])))
checar("e a mercadoria voltou ao estoque",
       float(produto.estoque_atual or 0) == apos_venda + 5,
       f"{apos_venda} -> {produto.estoque_atual}")
checar("nada a estornar devolve vazio, sem quebrar",
       motor.estornar_venda(sessao, nota3, None) is None)
sessao.close()

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Todos os testes da baixa de estoque passaram.")
