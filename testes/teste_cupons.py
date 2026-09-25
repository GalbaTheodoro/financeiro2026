"""Teste dos cupons de desconto da assinatura.

Não é o cupom fiscal (NFC-e) — é o desconto de venda, o "PRIMAVERA10" que o
cliente digita e paga menos.

O que se confere
----------------
  * só o administrador do site cadastra, edita, liga, desliga e apaga cupom;
  * código é guardado sem espaço e em maiúsculas: "  primavera 10 " acha o mesmo;
  * porcentagem fora de 0 a 100 e código repetido são recusados;
  * cupom errado e cupom **desligado** dão a mesma resposta — quem está de fora
    não descobre que o cupom existe e foi desligado;
  * quem digita no **cadastro** já entra com o desconto; código errado no
    cadastro não derruba a conta, só avisa;
  * quem digita na **tela de pagamento** vê o valor cair, e o **Pix copia e cola
    e o QR Code saem com o valor com desconto** (é o ponto todo);
  * a conta troca de cupom e tira o cupom;
  * **pacote de usuários não tem desconto**: o cupom é do plano;
  * mudar a porcentagem do cupom depois **não mexe** em quem já aplicou;
  * ao confirmar o Pix o cupom é gasto: some da conta, o contador sobe e a
    renovação volta ao preço cheio.

Uso:  python testes/teste_cupons.py   (com o servidor no ar)
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


def valor_no_pix(copia_e_cola):
    """Lê o campo 54 (valor) de dentro do payload Pix — é o que o banco cobra.

    O payload é uma sequência de (id, tamanho, conteúdo); o 54 é o valor da
    transação. Ler daqui, e não do JSON, é o que prova que o desconto chegou
    mesmo no código que a pessoa cola no aplicativo.
    """
    i = 0
    while i + 4 <= len(copia_e_cola):
        ident = copia_e_cola[i:i + 2]
        tamanho = int(copia_e_cola[i + 2:i + 4])
        conteudo = copia_e_cola[i + 4:i + 4 + tamanho]
        if ident == "54":
            return float(conteudo)
        i += 4 + tamanho
    return None


sufixo = str(int(time.time()))
tm = api("POST", "/api/auth/login",
         {"email": "admin@financeiro.local", "senha": "admin123"})["token"]


def conta(apelido, plano="P1_SEMESTRAL", cupom=None):
    corpo = {"nome": "Galba", "email": f"{apelido}{sufixo}@teste.com", "senha": "123456",
             "empresa": f"Assessoria {apelido}", "plano": plano}
    if cupom is not None:
        corpo["cupom"] = cupom
    return api("POST", "/api/publico/cadastro", corpo)


def pagamento(token):
    return api("GET", "/api/assinatura/minha", None, token)["pagamento"]


# =========================================================================== #
print("=== 1. Cadastro do cupom (só o administrador) ===")
novo = api("POST", "/api/admin/cupons",
           {"codigo": " primavera 10 ", "percentual": 10,
            "descricao": "campanha da feira"}, tm)
checar("código é guardado sem espaço e em maiúsculas", novo["codigo"] == "PRIMAVERA10",
       novo["codigo"])
checar("nasce ativo e sem uso", novo["ativo"] is True and novo["usos"] == 0)

meio = api("POST", "/api/admin/cupons", {"codigo": "METADE", "percentual": 50}, tm)
desligado = api("POST", "/api/admin/cupons",
                {"codigo": "ACABOU", "percentual": 30, "ativo": False}, tm)
checar("dá para nascer já desligado", desligado["ativo"] is False)

repetido = api("POST", "/api/admin/cupons", {"codigo": "primavera10", "percentual": 5},
               tm, esperar_erro=True)
checar("código repetido é recusado", repetido.get("_status") == 400
       and "Já existe" in str(repetido.get("detail")), str(repetido.get("detail"))[:60])
for ruim in (0, -5, 120, "abc"):
    r = api("POST", "/api/admin/cupons", {"codigo": f"RUIM{ruim}", "percentual": ruim},
            tm, esperar_erro=True)
    checar(f"porcentagem {ruim!r} é recusada", r.get("_status") == 400)
sem_codigo = api("POST", "/api/admin/cupons", {"codigo": "   ", "percentual": 10},
                 tm, esperar_erro=True)
checar("cupom sem código é recusado", sem_codigo.get("_status") == 400)

# =========================================================================== #
print("\n=== 2. O que o cliente vê antes de se cadastrar ===")
confere = api("GET", "/api/publico/cupom?codigo=primavera10")
checar("o site confere o cupom e diz a porcentagem",
       confere["codigo"] == "PRIMAVERA10" and confere["percentual"] == 10.0)
errado = api("GET", "/api/publico/cupom?codigo=NAOEXISTE", esperar_erro=True)
checar("código que não existe é recusado", errado.get("_status") == 400)
fora = api("GET", "/api/publico/cupom?codigo=ACABOU", esperar_erro=True)
checar("cupom desligado dá a MESMA resposta do inexistente — não denuncia que existe",
       fora.get("_status") == 400 and fora.get("detail") == errado.get("detail"),
       str(fora.get("detail"))[:60])

# =========================================================================== #
print("\n=== 3. Cupom digitado no cadastro ===")
nova = conta("comcupom", "P1_SEMESTRAL", "primavera10")
tc = nova["token"]
checar("a mensagem de boas-vindas avisa o desconto",
       "PRIMAVERA10" in nova["mensagem"], nova["mensagem"][-70:])
p = nova["pagamento"]
checar("o valor cheio do Plano 1 semestral é 399,90", p["valor_cheio"] == 399.90,
       str(p["valor_cheio"]))
checar("o desconto de 10% é 39,99", p["cupom_desconto"] == 39.99, str(p["cupom_desconto"]))
checar("e o valor a pagar fica 359,91", p["valor_cobranca"] == 359.91,
       str(p["valor_cobranca"]))

ruim = conta("cupomruim", "P1_SEMESTRAL", "NAOEXISTE")
checar("cupom errado no cadastro NÃO derruba a conta — ela é criada assim mesmo",
       bool(ruim.get("token")))
checar("mas a mensagem avisa que o cupom não vale",
       "não encontrado" in ruim["mensagem"].lower(), ruim["mensagem"][-60:])
checar("e a conta fica sem desconto", ruim["pagamento"]["cupom_desconto"] == 0)

# =========================================================================== #
print("\n=== 4. O Pix sai com o valor com desconto (o ponto todo) ===")
api("PUT", "/api/admin/configuracoes", {"valores": {
    "pix_chave": "financeiro@minhaempresa.com.br", "pix_titular": "Minha Assessoria",
    "pix_cidade": "SAO PAULO"}}, tm)

p = pagamento(tc)
checar("a chave Pix está configurada, então o código é montado", bool(p["copia_e_cola"]))
checar("o valor DENTRO do código copia e cola é o com desconto",
       valor_no_pix(p["copia_e_cola"]) == 359.91, str(valor_no_pix(p["copia_e_cola"])))
checar("e o QR Code é gerado", p["qrcode_svg"].lstrip().startswith("<svg"),
       p["qrcode_svg"][:30])

# o QR tem de ser do MESMO código, senão o cliente paga um valor e o banco lê outro
sem_cupom = pagamento(conta("semcupom")["token"])
checar("conta sem cupom paga o valor cheio",
       valor_no_pix(sem_cupom["copia_e_cola"]) == 399.90,
       str(valor_no_pix(sem_cupom["copia_e_cola"])))
checar("e os dois códigos são diferentes — o desconto muda o payload",
       sem_cupom["copia_e_cola"] != p["copia_e_cola"])

# =========================================================================== #
print("\n=== 5. Cupom digitado na tela de pagamento ===")
depois = conta("depois")
td = depois["token"]
checar("a conta começa sem cupom", pagamento(td)["cupom"] is None)

r = api("POST", "/api/assinatura/cupom", {"codigo": "metade"}, td)
checar("aplicar METADE responde com o Pix já refeito",
       r["pagamento"]["valor_cobranca"] == 199.95, str(r["pagamento"]["valor_cobranca"]))
checar("e o código Pix novo já traz o valor novo",
       valor_no_pix(r["pagamento"]["copia_e_cola"]) == 199.95)
checar("a mensagem diz quanto abateu", "199,95" in r["mensagem"] or "R$" in r["mensagem"],
       r["mensagem"][:70])

trocado = api("POST", "/api/assinatura/cupom", {"codigo": "PRIMAVERA10"}, td)
checar("trocar de cupom vale o último digitado",
       trocado["pagamento"]["cupom"] == "PRIMAVERA10"
       and trocado["pagamento"]["valor_cobranca"] == 359.91)
tirado = api("POST", "/api/assinatura/cupom", {"codigo": ""}, td)
checar("mandar vazio tira o cupom e volta ao preço cheio",
       tirado["pagamento"]["cupom"] is None
       and tirado["pagamento"]["valor_cobranca"] == 399.90)

recusa = api("POST", "/api/assinatura/cupom", {"codigo": "ACABOU"}, td, esperar_erro=True)
checar("cupom desligado é recusado também aqui", recusa.get("_status") == 400)

# ------------------------------------------------- o pacote de usuários não tem
api("POST", "/api/assinatura/cupom", {"codigo": "METADE"}, td)
api("POST", "/api/assinatura/pacotes", {"quantidade": 1}, td)
minha = api("GET", "/api/assinatura/minha", None, td)
pacote = minha.get("pagamento_pacotes")
checar("o pedido de pacote de usuários gera um Pix próprio", pacote is not None)
if pacote:
    checar("e o pacote NÃO recebe o desconto do cupom",
           pacote["cupom_desconto"] == 0
           and valor_no_pix(pacote["copia_e_cola"]) == pacote["valor_cobranca"],
           str(pacote["valor_cobranca"]))
    checar("enquanto a cobrança do plano continua com o desconto",
           minha["pagamento"]["valor_cobranca"] == 199.95)

# =========================================================================== #
print("\n=== 6. Mudar o cupom depois não mexe em quem já aplicou ===")
api("PUT", f"/api/admin/cupons/{novo['id']}", {"percentual": 5}, tm)
checar("quem já tinha aplicado os 10% continua com 39,99 de desconto",
       pagamento(tc)["cupom_desconto"] == 39.99, str(pagamento(tc)["cupom_desconto"]))
outra = conta("depoisdamudanca", "P1_SEMESTRAL", "PRIMAVERA10")
checar("e quem aplica agora pega os 5%", outra["pagamento"]["cupom_desconto"] == 20.0,
       str(outra["pagamento"]["cupom_desconto"]))
api("PUT", f"/api/admin/cupons/{novo['id']}", {"percentual": 10}, tm)

apagar = api("POST", "/api/admin/cupons", {"codigo": "SOMEM", "percentual": 15}, tm)
usa_apagado = conta("usouapagado", "P1_SEMESTRAL", "SOMEM")
api("DELETE", f"/api/admin/cupons/{apagar['id']}", None, tm)
checar("apagar o cupom não tira o desconto de quem já aplicou",
       pagamento(usa_apagado["token"])["cupom_desconto"] == 59.99,
       str(pagamento(usa_apagado["token"])["cupom_desconto"]))

# =========================================================================== #
print("\n=== 7. O cupom é gasto na confirmação do Pix ===")
linhas = api("GET", "/api/admin/assinaturas", None, tm)["linhas"]
alvo = next(a for a in linhas if a["usuario_email"] == f"comcupom{sufixo}@teste.com")
checar("a lista do administrador mostra o cupom da conta",
       alvo["cupom"] == "PRIMAVERA10" and alvo["valor_cobranca"] == 359.91,
       str(alvo.get("valor_cobranca")))

antes = next(c for c in api("GET", "/api/admin/cupons", None, tm)["linhas"]
             if c["codigo"] == "PRIMAVERA10")["usos"]
api("POST", f"/api/admin/assinaturas/{alvo['id']}/confirmar", {"meses": 6}, tm)
agora = next(c for c in api("GET", "/api/admin/cupons", None, tm)["linhas"]
             if c["codigo"] == "PRIMAVERA10")["usos"]
checar("o contador de usos sobe uma vez", agora == antes + 1, f"{antes} -> {agora}")

depois_pago = pagamento(tc)
checar("o cupom sai da conta: a renovação é pelo preço cheio",
       depois_pago["cupom"] is None and depois_pago["valor_cobranca"] == 399.90,
       str(depois_pago["valor_cobranca"]))
checar("e o Pix da renovação já vem sem desconto",
       valor_no_pix(depois_pago["copia_e_cola"]) == 399.90)
linha = next(a for a in api("GET", "/api/admin/assinaturas", None, tm)["linhas"]
             if a["usuario_email"] == f"comcupom{sufixo}@teste.com")
checar("fica o histórico de qual cupom pagou a entrada",
       linha["cupom_usado_codigo"] == "PRIMAVERA10" and linha["cupom_usado_desconto"] == 39.99,
       str(linha.get("cupom_usado_desconto")))
checar("conta já ativa não aceita novo cupom",
       api("POST", "/api/assinatura/cupom", {"codigo": "METADE"}, tc,
           esperar_erro=True).get("_status") == 400)

# =========================================================================== #
print("\n=== 8. Só o administrador do site mexe nos cupons ===")
checar("o assinante não lista os cupons",
       api("GET", "/api/admin/cupons", None, td, esperar_erro=True).get("_status") == 403)
checar("o assinante não cria cupom",
       api("POST", "/api/admin/cupons", {"codigo": "MEU", "percentual": 99}, td,
           esperar_erro=True).get("_status") == 403)
checar("o assinante não edita cupom",
       api("PUT", f"/api/admin/cupons/{meio['id']}", {"percentual": 99}, td,
           esperar_erro=True).get("_status") == 403)
checar("o assinante não apaga cupom",
       api("DELETE", f"/api/admin/cupons/{meio['id']}", None, td,
           esperar_erro=True).get("_status") == 403)
checar("e sem login nem a lista abre",
       api("GET", "/api/admin/cupons", esperar_erro=True).get("_status") == 401)

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Cupons de desconto OK — o desconto chega no Pix copia e cola e no QR Code.")
