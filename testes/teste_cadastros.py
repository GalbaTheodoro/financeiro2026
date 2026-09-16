"""Teste dos cadastros de apoio ao contrato e do limite de usuários.

Cobre:
  * unidades (com peso de conversão), modalidades e produtos criados na abertura da conta;
  * CRUD dos três cadastros;
  * numeração automática do contrato;
  * contrato preenchido pelos cadastros (produto, modalidade, unidade, representante)
    com o cálculo do peso total;
  * limite de 5 usuários no plano e a venda de pacotes de +5 com 65% de desconto.

Uso:  python testes/teste_cadastros.py   (com o servidor no ar)
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
falhas = []


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
    except urllib.error.HTTPError as e:
        corpo = json.loads(e.read() or b"{}")
        if esperar_erro:
            return {"_status": e.code, "_detalhe": corpo.get("detail", "")}
        raise AssertionError(f"{metodo} {caminho} -> HTTP {e.code}: {corpo}") from None


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


sufixo = str(int(time.time()))

print("\n=== 1. Cadastros criados junto com a conta ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Corretor Cadastros", "email": f"cadastro{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria de Cafés",
})
t = conta["token"]
eid = conta["empresa"]["id"]

unidades = api("GET", f"/api/unidades?empresa_id={eid}", token=t)
modalidades = api("GET", f"/api/modalidades?empresa_id={eid}", token=t)
produtos = api("GET", f"/api/produtos?empresa_id={eid}", token=t)
saca = next((u for u in unidades if u["codigo"] == "SC"), None)
checar("unidades padrão criadas", len(unidades) >= 5, f"{len(unidades)} unidade(s)")
checar("saca de 60 kg com peso de conversão", saca and abs(saca["peso_conversao"] - 60) < 0.001)
checar("modalidades padrão criadas", len(modalidades) >= 5, f"{len(modalidades)} modalidade(s)")
checar("produtos padrão criados", len(produtos) >= 3, f"{len(produtos)} produto(s)")
checar("produto já vem com a unidade e a embalagem",
       all(p["unidade_id"] for p in produtos),
       produtos[0]["unidade_nome"] if produtos else "")

print("\n=== 2. Cadastro próprio de unidade, modalidade e produto ===")
unidade = api("POST", "/api/unidades", {
    "empresa_id": eid, "codigo": "BAG", "nome": "Big bag de 1.200 kg", "peso_conversao": 1200,
}, t)
checar("unidade nova gravada", unidade["codigo"] == "BAG" and unidade["peso_conversao"] == 1200)

duplicada = api("POST", "/api/unidades", {
    "empresa_id": eid, "codigo": "BAG", "nome": "Repetida", "peso_conversao": 1,
}, t, esperar_erro=True)
checar("código de unidade não se repete", duplicada.get("_status") == 400,
       str(duplicada.get("_detalhe", ""))[:60])

modalidade = api("POST", "/api/modalidades", {
    "empresa_id": eid, "codigo": "006", "nome": "ENTREGA FUTURA",
    "descricao": "Entrega combinada para safra seguinte",
}, t)
produto = api("POST", "/api/produtos", {
    "empresa_id": eid, "codigo": "010", "nome": "CAFE CONILON",
    "unidade_id": unidade["id"], "embalagem": "BIG BAG",
}, t)
checar("modalidade nova gravada", modalidade["nome"] == "ENTREGA FUTURA")
checar("produto novo gravado com a unidade", produto["unidade_id"] == unidade["id"],
       produto.get("unidade_nome", ""))

produto = api("PUT", f"/api/produtos/{produto['id']}", {
    "empresa_id": eid, "codigo": "010", "nome": "CAFE CONILON TIPO 7",
    "unidade_id": saca["id"], "embalagem": "A GRANEL",
}, t)
checar("produto alterado", produto["nome"] == "CAFE CONILON TIPO 7"
       and produto["unidade_id"] == saca["id"])

api("DELETE", f"/api/modalidades/{modalidade['id']}", token=t)
restantes = api("GET", f"/api/modalidades?empresa_id={eid}", token=t)
checar("modalidade excluída", all(m["id"] != modalidade["id"] for m in restantes))

print("\n=== 3. Numeração automática do contrato ===")
comprador = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "COMPRADOR AUTOMATICO LTDA",
}, t)
vendedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "VENDEDOR AUTOMATICO LTDA",
}, t)
sugestao = api("GET", f"/api/contratos/proximo-numero?empresa_id={eid}", token=t)
checar("número sugerido antes do primeiro contrato", sugestao["numero"] == "00000001",
       sugestao["numero"])

base = {
    "empresa_id": eid, "data": "2026-09-10",
    "comprador_id": comprador["id"], "vendedor_id": vendedor["id"],
    "quantidade": 330, "preco_unitario": 1320,
    "comissao_comprador_percentual": 0.5, "comissao_vendedor_percentual": 0.5,
}
primeiro = api("POST", "/api/contratos", dict(base, produto_id=produtos[0]["id"]), t)
segundo = api("POST", "/api/contratos", dict(base, produto_id=produtos[0]["id"]), t)
checar("primeiro contrato numerado automaticamente", primeiro["numero"] == "00000001",
       primeiro["numero"])
checar("segundo contrato segue a sequência", segundo["numero"] == "00000002", segundo["numero"])

manual = api("POST", "/api/contratos", dict(base, numero="00000295",
                                            produto_id=produtos[0]["id"]), t)
seguinte = api("GET", f"/api/contratos/proximo-numero?empresa_id={eid}", token=t)
checar("número digitado é respeitado", manual["numero"] == "00000295")
checar("sequência continua do maior número", seguinte["numero"] == "00000296",
       seguinte["numero"])

print("\n=== 4. Contrato montado pelos cadastros ===")
eu = conta["usuario"]
completo = api("POST", "/api/contratos", dict(
    base,
    produto_id=produtos[0]["id"],
    modalidade_id=api("GET", f"/api/modalidades?empresa_id={eid}", token=t)[0]["id"],
    unidade_id=saca["id"],
    representante_id=eu["id"],
), t)
checar("produto copiado do cadastro", completo["produto"] == produtos[0]["nome"],
       completo["produto"])
checar("modalidade copiada do cadastro", bool(completo["modalidade"]), completo["modalidade"])
checar("unidade copiada do cadastro", completo["unidade"] == "SC", completo["unidade"])
checar("peso total calculado (330 x 60 kg)",
       abs(completo["peso_total"] - 19800) < 0.001, f"{completo['peso_total']} kg")
checar("representante é o usuário da empresa",
       completo["representante_nome"] == eu["nome"], completo.get("representante_nome", ""))

ficha = api("GET", f"/api/contratos/{completo['id']}", token=t)
checar("ficha traz os nomes dos cadastros",
       ficha["produto_nome"] and ficha["modalidade_nome"] and ficha["unidade_nome"],
       ficha["unidade_nome"])

alheio = api("POST", "/api/contratos", dict(base, unidade_id=999999), t, esperar_erro=True)
checar("unidade de outra conta é recusada", alheio.get("_status") == 400,
       str(alheio.get("_detalhe", ""))[:50])

print("\n=== 5. Limite de usuários do plano ===")
minha = api("GET", "/api/assinatura/minha", token=t)
u = minha["usuarios"]
checar("5 usuários inclusos no plano", u["incluidos"] == 5, str(u["incluidos"]))
checar("pacotes vendidos de 5 em 5", u["por_pacote"] == 5, str(u["por_pacote"]))
checar("desconto de 65% no pacote", abs(u["desconto_percentual"] - 65) < 0.01,
       f"{u['desconto_percentual']}%")
esperado = round(u["plano_valor"] * 0.35, 2)
checar("valor do pacote = plano - 65%", abs(u["valor_pacote"] - esperado) < 0.01,
       f"{brl(u['valor_pacote'])} sobre {brl(u['plano_valor'])}")
checar("já conta o dono da conta", u["usados"] == 1, str(u["usados"]))

for i in range(2, 6):
    api("POST", "/api/usuarios", {
        "nome": f"Operador {i}", "email": f"op{i}.{sufixo}@teste.com", "senha": "123456",
        "perfil": "OPERADOR", "empresa_id": eid,
    }, t)
minha = api("GET", "/api/assinatura/minha", token=t)
checar("5 usuários cadastrados sem custo extra", minha["usuarios"]["usados"] == 5,
       str(minha["usuarios"]["usados"]))
checar("nenhuma vaga disponível", minha["usuarios"]["disponiveis"] == 0)

sexto = api("POST", "/api/usuarios", {
    "nome": "Operador 6", "email": f"op6.{sufixo}@teste.com", "senha": "123456",
    "perfil": "OPERADOR", "empresa_id": eid,
}, t, esperar_erro=True)
checar("sexto usuário é barrado", sexto.get("_status") == 400)
checar("mensagem indica o preço do pacote",
       brl(u["valor_pacote"]) in str(sexto.get("_detalhe", "")),
       str(sexto.get("_detalhe", ""))[:90])

print("\n=== 6. Compra de um pacote de usuários ===")
pedido = api("POST", "/api/assinatura/pacotes", {"quantidade": 1}, t)
checar("pedido registrado", pedido["usuarios"]["pacotes_solicitados"] == 1)
minha = api("GET", "/api/assinatura/minha", token=t)
checar("Pix do pacote gerado com o valor do pacote",
       abs(minha["pagamento_pacotes"]["valor_cobranca"] - u["valor_pacote"]) < 0.01,
       brl(minha["pagamento_pacotes"]["valor_cobranca"]))
checar("limite ainda não subiu antes da confirmação",
       minha["usuarios"]["limite"] == 5, str(minha["usuarios"]["limite"]))

master = api("POST", "/api/auth/login",
             {"email": "admin@financeiro.local", "senha": "admin123"})["token"]
lista = api("GET", "/api/admin/assinaturas", token=master)["linhas"]
linha = next(a for a in lista if a["usuario_email"] == f"cadastro{sufixo}@teste.com")
checar("administrador vê o pedido pendente", linha["pacotes_solicitados"] == 1)
api("POST", f"/api/admin/assinaturas/{linha['id']}/pacotes", {"quantidade": 1}, master)

minha = api("GET", "/api/assinatura/minha", token=t)
checar("limite subiu para 10 após a confirmação", minha["usuarios"]["limite"] == 10,
       str(minha["usuarios"]["limite"]))
checar("pedido pendente zerado", minha["usuarios"]["pacotes_solicitados"] == 0)

sexto = api("POST", "/api/usuarios", {
    "nome": "Operador 6", "email": f"op6.{sufixo}@teste.com", "senha": "123456",
    "perfil": "OPERADOR", "empresa_id": eid,
}, t)
checar("sexto usuário criado depois do pacote", sexto["id"] > 0)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("Cadastros, numeração automática e limite de usuários OK.")
