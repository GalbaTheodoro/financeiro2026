"""Teste do pedido de venda e do orçamento.

A tela de balcão monta o carrinho e grava um documento; o botão Finalizar decide
como o cliente paga e que documento fiscal sai.

O que se confere
----------------
  * a conta das **parcelas**: divide em partes iguais, joga a sobra dos centavos
    na primeira, e a soma fecha com o total — em 3x de 100,00 e nos casos feios;
  * o vencimento anda de **mês em mês**, não de 30 em 30 dias (31/01 → 28/02);
  * numeração por empresa, sequencial, compartilhada entre orçamento e pedido;
  * totais do pedido: item x quantidade, desconto do item e desconto do total;
  * **orçamento não vira venda direto** — tem de ser aprovado, e a aprovação
    mantém o número;
  * pedido finalizado não se edita, não se apaga e não se cancela;
  * a prévia das parcelas que a tela mostra é a mesma conta que grava;
  * **se a SEFAZ recusar, o pedido não se perde**: continua aberto, com o motivo;
  * concluída a venda **a prazo**, nasce a conta a receber com as parcelas
    certas; **à vista** não nasce título nenhum;
  * pedido de outra conta não abre.

Uso:  python testes/teste_pedidos.py   (com o servidor no ar)
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


from backend import pedidos as regras                # noqa: E402

# =========================================================================== #
print("=== 1. A conta das parcelas (a parte que mexe com dinheiro) ===")
checar("100,00 em 3x: a sobra do centavo vai para a primeira",
       regras.dividir(100, 3) == [33.34, 33.33, 33.33], str(regras.dividir(100, 3)))
checar("e a soma fecha com o total", sum(regras.dividir(100, 3)) == 100.0)
for total, vezes in ((0.03, 2), (10, 3), (999.99, 7), (1234.56, 12), (0.01, 1)):
    partes = regras.dividir(total, vezes)
    checar(f"{total} em {vezes}x fecha na soma",
           round(sum(partes), 2) == round(total, 2) and len(partes) == vezes,
           str(partes[:3]))
checar("parcela nenhuma fica negativa",
       all(v >= 0 for v in regras.dividir(0.01, 3)), str(regras.dividir(0.01, 3)))

datas = regras.datas_das_parcelas(3, date(2026, 1, 31))
checar("31/01 em 3x mensais cai em 28/02 e 31/03, não em 02/03",
       datas == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)], str(datas))
quinzenal = regras.datas_das_parcelas(3, date(2026, 1, 10), 15)
checar("quinzenal anda de 15 em 15 dias",
       quinzenal == [date(2026, 1, 10), date(2026, 1, 25), date(2026, 2, 9)], str(quinzenal))

parcelas = regras.montar_parcelas(100, 3, date(2026, 1, 31))
checar("a lista sai numerada 001, 002, 003",
       [p["numero"] for p in parcelas] == ["001", "002", "003"])
try:
    regras.montar_parcelas(100, 99, date.today())
    checar("passar de 36 parcelas é recusado", False, "não recusou")
except regras.ErroPedido as erro:
    checar("passar de 36 parcelas é recusado", "36" in str(erro), str(erro)[:50])
try:
    regras.montar_parcelas(0, 3, date.today())
    checar("pedido zerado não parcela", False, "não recusou")
except regras.ErroPedido:
    checar("pedido zerado não parcela", True)

# =========================================================================== #
print("\n=== 2. Montar o pedido ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"ped{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria Pedidos", "plano": "P4_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]
produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe, soja = produtos[0], produtos[2]
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "12.345.678/0001-90", "cidade": "SAO PAULO", "uf": "SP"}, t)

novo = api("POST", "/api/pedidos", {
    "empresa_id": eid, "tipo": "PEDIDO", "parceiro_id": cliente["id"],
    "itens": [
        {"produto_id": cafe["id"], "descricao": cafe["nome"], "quantidade": 10,
         "valor_unitario": 1320},
        {"produto_id": soja["id"], "descricao": soja["nome"], "quantidade": 5,
         "valor_unitario": 130, "desconto": 50},
    ],
    "desconto": 150}, t)
pedido = novo["pedido"]
checar("o pedido nasce numerado", pedido["numero"] == "000001", pedido["numero"])
checar("o total do item desconta o desconto do item",
       pedido["itens"][1]["valor_total"] == 600.0, str(pedido["itens"][1]["valor_total"]))
checar("o subtotal soma os itens", pedido["valor_produtos"] == 13800.0,
       str(pedido["valor_produtos"]))
checar("e o total tira o desconto do pedido", pedido["valor_total"] == 13650.0,
       str(pedido["valor_total"]))
checar("nasce aberto", pedido["situacao"] == "ABERTO")

segundo = api("POST", "/api/pedidos", {
    "empresa_id": eid, "tipo": "ORCAMENTO",
    "itens": [{"descricao": "SERVICO DE CLASSIFICACAO", "quantidade": 1,
               "valor_unitario": 200}]}, t)["pedido"]
checar("o número segue a sequência da empresa", segundo["numero"] == "000002",
       segundo["numero"])
checar("orçamento e pedido dividem a mesma sequência", segundo["tipo"] == "ORCAMENTO")

sem_item = api("POST", "/api/pedidos", {"empresa_id": eid, "itens": []}, t, esperar_erro=True)
checar("pedido sem item é recusado",
       sem_item.get("_status") == 400 and "sem itens" in str(sem_item.get("detail")),
       str(sem_item.get("detail"))[:60])
quantidade_zero = api("POST", "/api/pedidos", {
    "empresa_id": eid,
    "itens": [{"descricao": "NADA", "quantidade": 0, "valor_unitario": 10}]},
    t, esperar_erro=True)
checar("item com quantidade zero é recusado", quantidade_zero.get("_status") == 400)

editado = api("PUT", f"/api/pedidos/{pedido['id']}", {
    "empresa_id": eid, "tipo": "PEDIDO", "parceiro_id": cliente["id"],
    "itens": [{"produto_id": cafe["id"], "descricao": cafe["nome"], "quantidade": 20,
               "valor_unitario": 1320}],
    "desconto": 0}, t)["pedido"]
checar("editar troca os itens e refaz o total", editado["valor_total"] == 26400.0
       and len(editado["itens"]) == 1, str(editado["valor_total"]))

# =========================================================================== #
print("\n=== 3. Orçamento tem de ser aprovado ===")
direto = api("POST", f"/api/pedidos/{segundo['id']}/finalizar", {
    "condicao": "VISTA", "documento": "CUPOM"}, t, esperar_erro=True)
checar("orçamento não vira venda direto",
       direto.get("_status") == 400 and "Aprove" in str(direto.get("detail")),
       str(direto.get("detail"))[:70])
aprovado = api("POST", f"/api/pedidos/{segundo['id']}/aprovar", None, t)["pedido"]
checar("aprovar transforma em pedido", aprovado["tipo"] == "PEDIDO")
checar("e mantém o mesmo número", aprovado["numero"] == segundo["numero"])
de_novo = api("POST", f"/api/pedidos/{segundo['id']}/aprovar", None, t, esperar_erro=True)
checar("aprovar duas vezes é recusado", de_novo.get("_status") == 400)

# =========================================================================== #
print("\n=== 4. A prévia das parcelas é a conta que vale ===")
previa = api("POST", f"/api/pedidos/{editado['id']}/parcelas", {
    "condicao": "PRAZO", "parcelas": 3, "primeiro_vencimento": "2026-01-31",
    "intervalo_dias": 30, "documento": "NFE"}, t)
checar("a prévia traz as três parcelas", len(previa["parcelas"]) == 3)
checar("com os vencimentos de mês em mês",
       [p["vencimento"] for p in previa["parcelas"]]
       == ["2026-01-31", "2026-02-28", "2026-03-31"],
       str([p["vencimento"] for p in previa["parcelas"]]))
checar("e a soma das parcelas é o total do pedido",
       previa["total"] == editado["valor_total"],
       f'{previa["total"]} x {editado["valor_total"]}')

# =========================================================================== #
print("\n=== 5. Sem certificado, a venda não se perde ===")
tentativa = api("POST", f"/api/pedidos/{editado['id']}/finalizar", {
    "condicao": "PRAZO", "parcelas": 3, "primeiro_vencimento": "2026-01-31",
    "documento": "NFE", "ambiente": "2"}, t)
checar("a finalização responde que não deu", tentativa.get("ok") is False,
       str(tentativa.get("mensagem"))[:70])
checar("e diz o que falta (o certificado)",
       "certificado" in str(tentativa.get("mensagem")).lower(),
       str(tentativa.get("mensagem"))[:80])
ainda = api("GET", f"/api/pedidos/{editado['id']}", None, t)["pedido"]
checar("o pedido continua ABERTO — a venda montada não foi jogada fora",
       ainda["situacao"] == "ABERTO" and ainda["valor_total"] == 26400.0)
checar("e não ficou com documento nem título", not ainda["nota_id"] and not ainda["lancamento_id"])

sem_cliente = api("POST", "/api/pedidos", {
    "empresa_id": eid, "tipo": "PEDIDO",
    "itens": [{"produto_id": cafe["id"], "descricao": cafe["nome"], "quantidade": 1,
               "valor_unitario": 100}]}, t)["pedido"]
recusa = api("POST", f"/api/pedidos/{sem_cliente['id']}/finalizar", {
    "condicao": "VISTA", "documento": "NFE"}, t)
checar("NF-e sem cliente cadastrado avisa e sugere o cupom",
       recusa.get("ok") is False and "cupom" in str(recusa.get("mensagem")).lower(),
       str(recusa.get("mensagem"))[:80])

# =========================================================================== #
print("\n=== 6. Fechada a venda: a prazo gera as contas a receber ===")
# a emissão de verdade depende de certificado e da SEFAZ; o que se testa aqui é
# o que acontece DEPOIS que o documento saiu autorizado — que é onde mora o dinheiro
from backend.database import SessionLocal            # noqa: E402
from backend.models import Lancamento, Nota, NotaItem, NotaPagamento, Pedido  # noqa: E402


def nota_autorizada(db, pedido, parcelas):
    """Uma nota como a SEFAZ devolve, para exercitar o fecho da venda."""
    nota = Nota(empresa_id=pedido.empresa_id, chave=f"P{pedido.id}{sufixo}".ljust(44, "0"),
                tipo="NFE", modelo="55", serie="1", numero=str(1000 + pedido.id),
                resumo=False, tipo_operacao="1", situacao="AUTORIZADA",
                origem="EMITIDA", status_emissao="AUTORIZADA",
                data_emissao=datetime.utcnow(), parceiro_id=pedido.parceiro_id,
                valor_total=float(pedido.valor_total or 0))
    db.add(nota)
    db.flush()
    db.add(NotaItem(nota_id=nota.id, numero=1, descricao=pedido.itens[0].descricao,
                    produto_id=pedido.itens[0].produto_id,
                    quantidade=float(pedido.itens[0].quantidade),
                    valor_unitario=float(pedido.itens[0].valor_unitario),
                    valor_total=float(pedido.valor_total or 0)))
    for p in parcelas:
        db.add(NotaPagamento(nota_id=nota.id, origem="DUPLICATA", numero=p["numero"],
                             vencimento=p["vencimento"], valor=p["valor"]))
    db.flush()
    return nota


db = SessionLocal()
try:
    from backend.models import Usuario

    usuario = db.query(Usuario).filter(Usuario.email == f"ped{sufixo}@teste.com").first()
    alvo = db.get(Pedido, editado["id"])
    parcelas = regras.montar_parcelas(float(alvo.valor_total), 3, date(2026, 1, 31), 30)
    nota = nota_autorizada(db, alvo, parcelas)
    mensagem = regras.concluir(db, alvo, nota, "PRAZO", 3, date(2026, 1, 31), 30,
                               "NFE", "15", usuario)
    db.commit()
    checar("a mensagem conta o que foi feito", "3 parcela" in mensagem, mensagem[:80])
    checar("o pedido fica finalizado e guarda a nota",
           alvo.situacao == "FINALIZADO" and alvo.nota_id == nota.id)
    titulo = db.get(Lancamento, alvo.lancamento_id)
    checar("nasceu a conta a receber", titulo is not None and titulo.tipo == "RECEBER",
           getattr(titulo, "tipo", None))
    valores = sorted(float(p.valor) for p in titulo.parcelas)
    checar("com as três parcelas", len(titulo.parcelas) == 3, str(len(titulo.parcelas)))
    checar("a soma das parcelas é o total do pedido",
           round(sum(valores), 2) == 26400.0, str(round(sum(valores), 2)))
    vencimentos = sorted(p.data_vencimento for p in titulo.parcelas)
    checar("e os vencimentos são os que a tela mostrou",
           vencimentos == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)],
           str(vencimentos))

    # ------------------------------------------------------- à vista não gera título
    avista = db.get(Pedido, sem_cliente["id"])
    nota2 = nota_autorizada(db, avista, [])
    regras.concluir(db, avista, nota2, "VISTA", 1, date.today(), 30, "CUPOM", "01", usuario)
    db.commit()
    checar("à vista o pedido finaliza sem conta a receber",
           avista.situacao == "FINALIZADO" and avista.lancamento_id is None)
finally:
    db.close()

# =========================================================================== #
print("\n=== 7. Pedido finalizado não se mexe ===")
travado = api("PUT", f"/api/pedidos/{editado['id']}", {
    "empresa_id": eid, "tipo": "PEDIDO",
    "itens": [{"descricao": "OUTRA COISA", "quantidade": 1, "valor_unitario": 1}]},
    t, esperar_erro=True)
checar("não dá para editar", travado.get("_status") == 400
       and "finalizado" in str(travado.get("detail")).lower(),
       str(travado.get("detail"))[:60])
checar("não dá para apagar",
       api("DELETE", f"/api/pedidos/{editado['id']}", None, t,
           esperar_erro=True).get("_status") == 400)
checar("não dá para cancelar",
       api("POST", f"/api/pedidos/{editado['id']}/cancelar", None, t,
           esperar_erro=True).get("_status") == 400)
checar("e nem finalizar de novo",
       api("POST", f"/api/pedidos/{editado['id']}/finalizar",
           {"condicao": "VISTA", "documento": "CUPOM"}, t,
           esperar_erro=True).get("_status") == 400)

lista = api("GET", f"/api/pedidos?empresa_id={eid}", None, t)
checar("a lista mostra o resumo certo",
       lista["resumo"]["finalizados"] == 2, str(lista["resumo"]))
finalizado = next(l for l in lista["linhas"] if l["id"] == editado["id"])
checar("e a linha conta como a venda foi paga",
       finalizado["condicao_rotulo"] == "A prazo" and finalizado["parcelas"] == 3,
       str(finalizado["condicao_rotulo"]))

# =========================================================================== #
print("\n=== 8. A conta do vizinho não enxerga ===")
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Vizinho", "email": f"vizped{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria Vizinha", "plano": "P4_ANUAL"})
checar("pedido de outra conta não abre",
       api("GET", f"/api/pedidos/{editado['id']}", None, outra["token"],
           esperar_erro=True).get("_status") == 403)
checar("nem a lista da empresa alheia",
       api("GET", f"/api/pedidos?empresa_id={eid}", None, outra["token"],
           esperar_erro=True).get("_status") == 403)

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Pedidos OK — carrinho, parcelas certas e a venda que não se perde.")
