"""Teste dos quatro planos de assinatura e do que cada um libera.

O que se confere
----------------
  * a página inicial recebe os **quatro planos**, cada um com os dois prazos, os
    preços certos e a lista do que libera;
  * o **Plano 1** não abre cupom fiscal nem GTA — e a recusa vem do **servidor**,
    com a frase dizendo em que plano aquilo está;
  * o **Plano 2** abre o cupom e não a GTA; o **Plano 3**, o contrário;
  * o **Plano 4** abre os dois;
  * contrato, financeiro e NF-e funcionam em **todos** os planos;
  * a conta manda, junto com a situação, a lista de **rotas** que o menu usa para
    esconder o que não foi contratado;
  * trocar de plano troca os módulos na hora;
  * contas antigas (plano gravado como ``SEMESTRAL``/``ANUAL``, de quando não
    havia planos separados) continuam com **tudo**, sem perder nada;
  * o preço de cada plano é editável nas Configurações do site, e o que está
    guardado lá é o que vale.

Uso:  python testes/teste_planos.py   (com o servidor no ar)
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


def conta(plano, apelido=""):
    """Cria uma conta nova já nesse plano e devolve (token, empresa_id).

    O ``apelido`` só serve para criar uma segunda conta no mesmo plano sem
    repetir o e-mail.
    """
    marca = plano.lower().replace("_", "") + apelido
    dados = api("POST", "/api/publico/cadastro", {
        "nome": "Galba", "email": f"{marca}{sufixo}@teste.com", "senha": "123456",
        "empresa": f"Assessoria {plano} {apelido}".strip(), "plano": plano})
    return dados["token"], dados["empresa"]["id"]


def modulos(token):
    return api("GET", "/api/auth/me", None, token)["assinatura"]["modulos"]


def rotas(token):
    return api("GET", "/api/auth/me", None, token)["assinatura"]["rotas"]


# =========================================================================== #
print("=== 1. Os quatro planos na página inicial ===")
info = api("GET", "/api/publico/info")
planos = info["planos"]
checar("são quatro planos", len(planos) == 4, str([p["nome"] for p in planos]))

precos = {p["nome"]: (p["semestral"]["valor"], p["anual"]["valor"]) for p in planos}
esperado = {
    "Plano 1": (399.90, 699.90),
    "Plano 2": (459.90, 859.90),
    "Plano 3": (519.90, 969.90),
    "Plano 4": (579.90, 1069.90),
}
for nome, (sem, anual) in esperado.items():
    checar(f"{nome}: {sem:.2f} semestral e {anual:.2f} anual",
           precos.get(nome) == (sem, anual), str(precos.get(nome)))

por_nome = {p["nome"]: p for p in planos}
tem = lambda nome, modulo: modulo in [m["codigo"] for m in por_nome[nome]["modulos"]]  # noqa: E731
checar("todo plano tem contrato, financeiro e NF-e",
       all(tem(n, m) for n in esperado for m in ("CONTRATOS", "FINANCEIRO", "NFE")))
checar("o cupom fiscal está nos planos 2 e 4",
       tem("Plano 2", "CUPOM") and tem("Plano 4", "CUPOM")
       and not tem("Plano 1", "CUPOM") and not tem("Plano 3", "CUPOM"))
checar("a GTA está nos planos 3 e 4",
       tem("Plano 3", "GTA") and tem("Plano 4", "GTA")
       and not tem("Plano 1", "GTA") and not tem("Plano 2", "GTA"))
checar("o plano completo é o destacado",
       por_nome["Plano 4"]["destaque"] is True
       and not any(por_nome[n]["destaque"] for n in ("Plano 1", "Plano 2", "Plano 3")))
checar("o cartão mostra quanto dá por mês",
       por_nome["Plano 1"]["semestral"]["valor_mes"] == 66.65,
       str(por_nome["Plano 1"]["semestral"]["valor_mes"]))
# 399,90 x 2 = 799,80 contra 699,90 no anual
checar("e quanto o anual economiza", por_nome["Plano 1"]["economia"] == 99.90,
       str(por_nome["Plano 1"]["economia"]))

# =========================================================================== #
print("\n=== 2. O que cada conta enxerga ===")
p1, e1 = conta("P1_SEMESTRAL")
p2, e2 = conta("P2_SEMESTRAL")
p3, e3 = conta("P3_ANUAL")
p4, e4 = conta("P4_ANUAL")

checar("Plano 1: contrato, financeiro e NF-e",
       sorted(modulos(p1)) == ["CONTRATOS", "FINANCEIRO", "NFE"], str(modulos(p1)))
checar("Plano 2: mais o cupom", "CUPOM" in modulos(p2) and "GTA" not in modulos(p2))
checar("Plano 3: mais a GTA", "GTA" in modulos(p3) and "CUPOM" not in modulos(p3))
checar("Plano 4: os dois", {"CUPOM", "GTA"} <= set(modulos(p4)))

situacao = api("GET", "/api/auth/me", None, p1)["assinatura"]
checar("a conta sabe em que plano está",
       situacao["plano_nome"] == "Plano 1" and situacao["plano_periodo"] == "SEMESTRAL",
       situacao.get("plano_rotulo"))
checar("o valor gravado é o do plano escolhido", situacao["valor"] == 399.90,
       str(situacao["valor"]))
anual = api("GET", "/api/auth/me", None, p3)["assinatura"]
checar("e o prazo anual cobra o valor anual", anual["valor"] == 969.90, str(anual["valor"]))

# ------------------------------------------------------------------- o menu
livres = rotas(p1)
checar("o menu do Plano 1 não traz cupom nem GTA",
       "/cupom" not in livres and "/gta" not in livres, str(livres))
checar("mas traz painel, contratos, notas e relatórios",
       {"/painel", "/contratos", "/notas", "/relatorios"} <= set(livres))
checar("o menu do Plano 2 traz o cupom e não a GTA",
       "/cupom" in rotas(p2) and "/gta" not in rotas(p2))
checar("o menu do Plano 3 traz a GTA e não o cupom",
       "/gta" in rotas(p3) and "/cupom" not in rotas(p3))
checar("o menu do Plano 4 traz os dois", {"/cupom", "/gta"} <= set(rotas(p4)))

# =========================================================================== #
print("\n=== 3. O servidor barra, não só o menu ===")
sem_cupom = api("GET", f"/api/cupom/config?empresa_id={e1}", None, p1, esperar_erro=True)
checar("Plano 1 não abre o cupom fiscal", sem_cupom.get("_status") == 403,
       str(sem_cupom.get("_status")))
checar("e a frase diz em que planos ele está",
       "Plano 2" in str(sem_cupom.get("detail")) and "Plano 4" in str(sem_cupom.get("detail")),
       str(sem_cupom.get("detail"))[:90])

sem_gta = api("GET", f"/api/gta?empresa_id={e1}", None, p1, esperar_erro=True)
checar("Plano 1 não abre a GTA", sem_gta.get("_status") == 403)
checar("e a frase diz em que planos ela está",
       "Plano 3" in str(sem_gta.get("detail")) and "Plano 4" in str(sem_gta.get("detail")),
       str(sem_gta.get("detail"))[:90])
tabelas = api("GET", "/api/gta/tabelas", None, p1, esperar_erro=True)
checar("nem a lista de espécies da GTA", tabelas.get("_status") == 403)

venda = api("POST", "/api/cupom/venda", {
    "empresa_id": e2, "itens": [{"descricao": "CAFE", "quantidade": 1, "valor_unitario": 10}]},
    p2, esperar_erro=True)
# passa da porta do plano: o que barra agora é dado faltando, não o plano
checar("Plano 2 passa pela porta do cupom",
       venda.get("_status") == 400 and "plano" not in str(venda.get("detail")).lower(),
       str(venda.get("detail"))[:70])
checar("Plano 2 não abre a GTA",
       api("GET", f"/api/gta?empresa_id={e2}", None, p2,
           esperar_erro=True).get("_status") == 403)
checar("Plano 3 abre a GTA",
       "guias" in api("GET", f"/api/gta?empresa_id={e3}", None, p3))
checar("Plano 3 não abre o cupom",
       api("GET", f"/api/cupom/config?empresa_id={e3}", None, p3,
           esperar_erro=True).get("_status") == 403)
checar("Plano 4 abre os dois",
       "guias" in api("GET", f"/api/gta?empresa_id={e4}", None, p4)
       and "serie" in api("GET", f"/api/cupom/config?empresa_id={e4}", None, p4))

# ---------------------------------------------- o miolo funciona em todo plano
for nome, token, empresa in (("Plano 1", p1, e1), ("Plano 3", p3, e3)):
    api("POST", f"/api/cadastros-contrato/padrao?empresa_id={empresa}", None, token)
    checar(f"{nome} usa contratos", isinstance(
        api("GET", f"/api/contratos?empresa_id={empresa}", None, token), (list, dict)))
    checar(f"{nome} usa contas a receber", isinstance(
        api("GET", f"/api/lancamentos?empresa_id={empresa}&natureza=RECEBER", None, token),
        (list, dict)))
    checar(f"{nome} usa notas fiscais", isinstance(
        api("GET", f"/api/notas?empresa_id={empresa}", None, token), (list, dict)))

# =========================================================================== #
print("\n=== 4. Trocar de plano ===")
trocado = api("POST", "/api/assinatura/plano", {"plano": "P4_ANUAL"}, p1)
checar("trocar para o Plano 4 libera cupom e GTA na hora",
       {"CUPOM", "GTA"} <= set(trocado["situacao"]["modulos"]),
       str(trocado["situacao"]["modulos"]))
checar("e o valor passa a ser o do Plano 4 anual",
       trocado["situacao"]["valor"] == 1069.90, str(trocado["situacao"]["valor"]))
checar("a GTA abre logo depois da troca",
       "guias" in api("GET", f"/api/gta?empresa_id={e1}", None, p1))
de_volta = api("POST", "/api/assinatura/plano", {"plano": "P1_SEMESTRAL"}, p1)
checar("e voltar para o Plano 1 fecha outra vez",
       "GTA" not in de_volta["situacao"]["modulos"]
       and api("GET", f"/api/gta?empresa_id={e1}", None, p1,
               esperar_erro=True).get("_status") == 403)

# =========================================================================== #
print("\n=== 5. Contas de antes dos planos separados ===")
from backend.database import SessionLocal          # noqa: E402
from backend.models import Assinatura, Usuario     # noqa: E402

db = SessionLocal()
try:
    usuario = db.query(Usuario).filter(
        Usuario.email == f"p1semestral{sufixo}@teste.com").first()
    antiga = db.query(Assinatura).filter(Assinatura.usuario_id == usuario.id).first()
    antiga.plano = "ANUAL"          # como era gravado antes de existirem os planos
    db.commit()
finally:
    db.close()

velha = api("GET", "/api/auth/me", None, p1)["assinatura"]
checar("conta antiga continua com tudo — ninguém perde nada na atualização",
       {"CUPOM", "GTA"} <= set(velha["modulos"]), str(velha["modulos"]))
checar("e o sistema a mostra como Plano 4 anual",
       velha["plano_nome"] == "Plano 4" and velha["plano_periodo"] == "ANUAL",
       velha.get("plano_rotulo"))
checar("a GTA abre para ela", "guias" in api("GET", f"/api/gta?empresa_id={e1}", None, p1))

# =========================================================================== #
print("\n=== 6. O preço é editável, e o guardado é o que vale ===")
from backend import assinaturas as regras          # noqa: E402
from backend import planos as catalogo             # noqa: E402
from backend.models import Configuracao            # noqa: E402

checar("existe uma chave de preço por plano e prazo",
       all(f"plano{n}_{p}_valor" in regras.CONFIGURACOES_PADRAO
           for n in (1, 2, 3, 4) for p in ("semestral", "anual")))
checar("e as duas chaves antigas saíram do catálogo",
       "plano_semestral_valor" not in regras.CONFIGURACOES_PADRAO
       and "plano_anual_valor" not in regras.CONFIGURACOES_PADRAO)

db = SessionLocal()
try:
    guardadas = {c.chave for c in db.query(Configuracao).all()}
    checar("as chaves antigas também sumiram do banco",
           not ({"plano_semestral_valor", "plano_anual_valor"} & guardadas))
    chave = catalogo.chave_do_valor(2, "semestral")
    linha = db.query(Configuracao).filter(Configuracao.chave == chave).first()
    anterior = linha.valor
    linha.valor = "499,90"           # como o administrador digita, com vírgula
    db.commit()
finally:
    db.close()

novo = {p["nome"]: p["semestral"]["valor"] for p in api("GET", "/api/publico/info")["planos"]}
checar("mudar o valor guardado muda o preço do site", novo["Plano 2"] == 499.90,
       str(novo["Plano 2"]))

db = SessionLocal()
try:
    linha = db.query(Configuracao).filter(Configuracao.chave == chave).first()
    linha.valor = anterior
    db.commit()
finally:
    db.close()

# =========================================================================== #
print("\n=== 7. O administrador edita quais menus cada plano libera ===")
tm = api("POST", "/api/auth/login",
         {"email": "admin@financeiro.local", "senha": "admin123"})["token"]

grade = api("GET", "/api/admin/modulos", None, tm)
checar("o catálogo de menus tem os cinco módulos",
       {m["codigo"] for m in grade["modulos"]}
       == {"CONTRATOS", "FINANCEIRO", "NFE", "CUPOM", "GTA"},
       str([m["codigo"] for m in grade["modulos"]]))
checar("e cada módulo diz quais telas ele abre",
       "/notas" in next(m for m in grade["modulos"] if m["codigo"] == "NFE")["rotas"])
checar("a grade vem com os quatro planos", len(grade["planos"]) == 4)
p1_grade = next(p for p in grade["planos"] if p["nivel"] == 1)
checar("a grade do Plano 1 é a de fábrica enquanto ninguém mexeu",
       p1_grade["modulos"] == p1_grade["padrao"] == ["CONTRATOS", "FINANCEIRO", "NFE"],
       str(p1_grade["modulos"]))

pa, ea = conta("P1_ANUAL", "grade")
checar("a conta nova de Plano 1 não abre o cupom",
       api("GET", f"/api/cupom/config?empresa_id={ea}", None, pa,
           esperar_erro=True).get("_status") == 403)

# o administrador põe o cupom no Plano 1 — vale para todo assinante desse plano
api("PUT", "/api/admin/configuracoes",
    {"valores": {"plano1_modulos": "CONTRATOS,FINANCEIRO,NFE,CUPOM"}}, tm)
checar("editar a grade coloca o cupom no Plano 1", "CUPOM" in modulos(pa), str(modulos(pa)))
checar("e o menu da conta passa a trazer o cupom", "/cupom" in rotas(pa))
checar("o servidor abre a tela do cupom para ela",
       "serie" in api("GET", f"/api/cupom/config?empresa_id={ea}", None, pa))
checar("a página inicial anuncia o cupom no Plano 1",
       "CUPOM" in [m["codigo"] for m in
                   next(p for p in api("GET", "/api/publico/info")["planos"]
                        if p["nome"] == "Plano 1")["modulos"]])
checar("e a grade mostra que aquele plano saiu do padrão",
       next(p for p in api("GET", "/api/admin/modulos", None, tm)["planos"]
            if p["nivel"] == 1)["modulos"] != p1_grade["padrao"])

# e tira a nota fiscal do mesmo plano
api("PUT", "/api/admin/configuracoes",
    {"valores": {"plano1_modulos": "CONTRATOS,FINANCEIRO"}}, tm)
checar("tirar a NF-e da grade fecha a tela de notas",
       api("GET", f"/api/notas?empresa_id={ea}", None, pa,
           esperar_erro=True).get("_status") == 403)
checar("e o estoque, que mora no mesmo módulo, fecha junto",
       "/estoque" not in rotas(pa), str(rotas(pa)))

api("PUT", "/api/admin/configuracoes", {"valores": {"plano1_modulos": ""}}, tm)
checar("plano sem nenhum menu marcado é aceito", modulos(pa) == [], str(modulos(pa)))
checar("a conta continua entrando, só sem os menus do plano",
       api("GET", "/api/auth/me", None, pa)["assinatura"]["liberado"] is True)

api("PUT", "/api/admin/configuracoes",
    {"valores": {"plano1_modulos": "CONTRATOS,FINANCEIRO,NFE"}}, tm)
checar("devolver a grade de fábrica devolve os menus",
       sorted(modulos(pa)) == ["CONTRATOS", "FINANCEIRO", "NFE"], str(modulos(pa)))

# ---------------------------------------- a página inicial anuncia o que tem
recursos = api("GET", "/api/publico/info")
checar("o slogan da página inicial fala de nota fiscal, venda e estoque",
       all(palavra in recursos["slogan"].lower()
           for palavra in ("nota fiscal", "cupom fiscal", "balcão", "estoque")),
       recursos["slogan"][:80])

# =========================================================================== #
print("\n=== 8. Exceção combinada com um cliente ===")
pb, eb = conta("P1_SEMESTRAL", "excecao")
id_b = api("GET", "/api/auth/me", None, pb)["assinatura"]["assinatura_id"]
checar("a conta começa sem exceção nenhuma",
       api("GET", "/api/auth/me", None, pb)["assinatura"]["modulos_extras"] == [])

# "fechou o Plano 1 mas ficou combinado dar a nota fiscal" — aqui é a GTA, que
# o Plano 1 não tem de jeito nenhum
r = api("POST", f"/api/admin/assinaturas/{id_b}/modulos",
        {"extras": ["GTA"], "bloqueados": []}, tm)
checar("liberar a GTA só para essa conta funciona", r.get("ok") is True,
       str(r.get("mensagem"))[:80])
checar("a conta passa a enxergar a GTA", "GTA" in modulos(pb), str(modulos(pb)))
checar("o menu dela traz a GTA", "/gta" in rotas(pb))
checar("e a tela abre de verdade no servidor",
       "guias" in api("GET", f"/api/gta?empresa_id={eb}", None, pb))
situacao_b = api("GET", "/api/auth/me", None, pb)["assinatura"]
checar("a exceção fica registrada como extra",
       situacao_b["modulos_extras"] == ["GTA"]
       and "GTA" not in situacao_b["modulos_do_plano"], str(situacao_b["modulos_extras"]))
checar("o plano dela continua sendo o Plano 1",
       situacao_b["plano_nome"] == "Plano 1" and situacao_b["valor"] == 399.90)
checar("e o vizinho de plano não ganhou nada",
       "GTA" not in modulos(pa), str(modulos(pa)))

# o caminho contrário: tirar um menu que o plano dá
api("POST", f"/api/admin/assinaturas/{id_b}/modulos",
    {"extras": ["GTA"], "bloqueados": ["NFE"]}, tm)
checar("bloquear a NF-e dessa conta fecha a tela",
       api("GET", f"/api/notas?empresa_id={eb}", None, pb,
           esperar_erro=True).get("_status") == 403)
checar("e a GTA combinada continua aberta",
       "guias" in api("GET", f"/api/gta?empresa_id={eb}", None, pb))

conflito = api("POST", f"/api/admin/assinaturas/{id_b}/modulos",
               {"extras": ["CUPOM"], "bloqueados": ["CUPOM"]}, tm, esperar_erro=True)
checar("liberar e bloquear o mesmo menu é recusado",
       conflito.get("_status") == 400 and "mesmo tempo" in str(conflito.get("detail")),
       str(conflito.get("detail"))[:70])

api("POST", f"/api/admin/assinaturas/{id_b}/modulos",
    {"extras": ["CONTRATOS", "GTA"], "bloqueados": ["CUPOM"]}, tm)
depois = api("GET", "/api/auth/me", None, pb)["assinatura"]
checar("extra que o plano já dá não é guardado como exceção",
       depois["modulos_extras"] == ["GTA"], str(depois["modulos_extras"]))
checar("bloqueio de menu que o plano não dá também não é guardado",
       depois["modulos_bloqueados"] == [], str(depois["modulos_bloqueados"]))

api("POST", f"/api/admin/assinaturas/{id_b}/modulos", {"extras": [], "bloqueados": []}, tm)
checar("limpar as exceções devolve a conta ao plano",
       sorted(modulos(pb)) == ["CONTRATOS", "FINANCEIRO", "NFE"], str(modulos(pb)))
checar("e a GTA fecha outra vez",
       api("GET", f"/api/gta?empresa_id={eb}", None, pb,
           esperar_erro=True).get("_status") == 403)

negado = api("POST", f"/api/admin/assinaturas/{id_b}/modulos",
             {"extras": ["GTA"], "bloqueados": []}, pb, esperar_erro=True)
checar("só o administrador do site mexe nisso — o assinante recebe 403",
       negado.get("_status") == 403, str(negado.get("detail"))[:60])
checar("e o assinante nem lê o catálogo de menus",
       api("GET", "/api/admin/modulos", None, pb, esperar_erro=True).get("_status") == 403)

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Planos OK — cada conta enxerga só o que contratou.")
