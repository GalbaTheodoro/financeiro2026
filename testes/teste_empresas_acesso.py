"""Teste do painel "Empresas e acessos" do administrador do site.

Confere:
  * o e-mail do dono (FIN_MASTER_EMAIL) vira administrador do site no login e o
    login de fábrica admin@financeiro.local é desligado;
  * limite padrão de 3 usuários por empresa, e aumento feito pelo administrador;
  * liberar a empresa até uma data, bloquear na hora e liberar de novo;
  * bloquear um usuário e dar prazo de acesso (data vencida não entra);
  * o admin da empresa não consegue reativar quem o administrador do site bloqueou;
  * a troca do padrão antigo (5) para 3 acontece uma vez só.

ATENÇÃO: rode por último — ele desliga o login admin@financeiro.local usado pelos
outros testes. O servidor precisa estar com a mesma FIN_MASTER_EMAIL:

  FIN_MASTER_EMAIL=dono.teste@agrodock.local uvicorn backend.main:app
  FIN_MASTER_EMAIL=dono.teste@agrodock.local python testes/teste_empresas_acesso.py
"""
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE = os.getenv("FIN_BASE", "http://127.0.0.1:8000")
MASTER_EMAIL = os.getenv("FIN_MASTER_EMAIL", "dono.teste@agrodock.local")
falhas = []
sufixo = str(int(time.time()))


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


def login(email, senha="123456", esperar_erro=False):
    return api("POST", "/api/auth/login", {"email": email, "senha": senha},
               esperar_erro=esperar_erro)


hoje = date.today()

print("\n=== 1. O dono do site vira administrador ===")
existe = login(MASTER_EMAIL, esperar_erro=True)
if existe.get("_status") in (401, 423) or "token" not in existe:
    api("POST", "/api/publico/cadastro", {
        "nome": "Galba Dono", "email": MASTER_EMAIL, "senha": "123456",
        "empresa": "Assessoria do Dono",
    })
dono = login(MASTER_EMAIL)
tm = dono["token"]
checar("e-mail do dono entra como MASTER", dono["usuario"]["perfil"] == "MASTER",
       dono["usuario"]["perfil"])
fabrica = login("admin@financeiro.local", "admin123", esperar_erro=True)
checar("login de fábrica admin@financeiro.local foi desligado", fabrica.get("_status") == 423,
       str(fabrica.get("_detalhe", ""))[:60])
me = api("GET", "/api/auth/me", token=tm)
checar("administrador não fica preso a assinatura", me["assinatura"]["liberado"] is True)

print("\n=== 2. Empresa cliente com limite padrão de 3 usuários ===")
cliente_email = f"cliente{sufixo}@teste.com"
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Cliente Teste", "email": cliente_email, "senha": "123456",
    "empresa": f"Cafés Teste {sufixo}", "documento": "12.345.678/0001-90",
})
tc = conta["token"]
eid = conta["empresa"]["id"]
minha = api("GET", "/api/assinatura/minha", token=tc)
checar("limite padrão é 3", minha["usuarios"]["limite"] == 3, str(minha["usuarios"]["limite"]))

ops = []
for i in (2, 3):
    ops.append(api("POST", "/api/usuarios", {
        "nome": f"Operador {i}", "email": f"op{i}.{sufixo}@teste.com", "senha": "123456",
        "perfil": "OPERADOR", "empresa_id": eid,
    }, tc))
quarto = api("POST", "/api/usuarios", {
    "nome": "Operador 4", "email": f"op4.{sufixo}@teste.com", "senha": "123456",
    "perfil": "OPERADOR", "empresa_id": eid,
}, tc, esperar_erro=True)
checar("quarto usuário é barrado", quarto.get("_status") == 400,
       str(quarto.get("_detalhe", ""))[:70])

print("\n=== 3. Lista de empresas do administrador ===")
proibido = api("GET", "/api/admin/empresas", token=tc, esperar_erro=True)
checar("cliente não vê a lista de empresas", proibido.get("_status") == 403)
lista = api("GET", "/api/admin/empresas", token=tm)
linha = next((l for l in lista["linhas"] if l["usuario_email"] == cliente_email), None)
checar("empresa aparece na lista", linha is not None)
checar("nome e CNPJ da empresa", linha and linha["empresa_nome"].startswith("Cafés Teste")
       and linha["cnpj"] == "12.345.678/0001-90", linha and linha["cnpj"])
checar("usuários em uso 3 de 3", linha and linha["usuarios_em_uso"] == 3
       and linha["limite_usuarios"] == 3)
checar("lista traz os usuários da empresa", linha and len(linha["usuarios"]) == 3)
checar("resumo com total de empresas", lista["resumo"]["total"] >= 1, str(lista["resumo"]))
checar("empresa do próprio administrador fica fora da lista",
       all(l["usuario_email"] != MASTER_EMAIL for l in lista["linhas"]))
aid = linha["id"]

print("\n=== 4. Aumentar o limite depois do pagamento ===")
novo = api("POST", f"/api/admin/empresas/{aid}/limite", {"limite": 5}, tm)
checar("limite passou para 5", novo["limite_usuarios"] == 5 and novo["limite_personalizado"])
quarto = api("POST", "/api/usuarios", {
    "nome": "Operador 4", "email": f"op4.{sufixo}@teste.com", "senha": "123456",
    "perfil": "OPERADOR", "empresa_id": eid,
}, tc)
checar("quarto usuário criado com o novo limite", quarto["id"] > 0)
invalido = api("POST", f"/api/admin/empresas/{aid}/limite", {"limite": 9999}, tm, esperar_erro=True)
checar("limite absurdo é recusado", invalido.get("_status") == 400)

print("\n=== 5. Bloquear e liberar a empresa por data ===")
api("POST", f"/api/admin/empresas/{aid}/acesso", {"acao": "BLOQUEAR"}, tm)
bloqueada = api("GET", "/api/auth/me", token=tc)
checar("empresa bloqueada fica sem acesso", bloqueada["assinatura"]["liberado"] is False,
       bloqueada["assinatura"].get("titulo", ""))
barrado = api("GET", f"/api/parceiros?empresa_id={eid}", token=tc, esperar_erro=True)
checar("API da empresa bloqueada responde 402", barrado.get("_status") == 402)

passado = api("POST", f"/api/admin/empresas/{aid}/acesso",
              {"acao": "LIBERAR", "ate": (hoje - timedelta(days=1)).isoformat()}, tm,
              esperar_erro=True)
checar("não libera com data no passado", passado.get("_status") == 400)
sem_data = api("POST", f"/api/admin/empresas/{aid}/acesso", {"acao": "LIBERAR"}, tm,
               esperar_erro=True)
checar("liberar exige a data", sem_data.get("_status") == 400)

ate = hoje + timedelta(days=10)
liberada = api("POST", f"/api/admin/empresas/{aid}/acesso",
               {"acao": "LIBERAR", "ate": ate.isoformat(), "observacao": "Pix de teste"}, tm)
checar("empresa liberada até a data", liberada["liberado"] and liberada["data_fim"] == ate.isoformat(),
       liberada["data_fim"])
checar("observação guardada", liberada["observacao_admin"] == "Pix de teste")
de_volta = api("GET", "/api/auth/me", token=tc)
checar("cliente volta a entrar", de_volta["assinatura"]["liberado"] is True,
       de_volta["assinatura"].get("mensagem", ""))
api("GET", f"/api/parceiros?empresa_id={eid}", token=tc)
checar("API da empresa liberada responde", True)

print("\n=== 6. Acesso por usuário ===")
op = ops[0]
api("POST", f"/api/admin/usuarios/{op['id']}/acesso",
    {"ativo": True, "acesso_ate": (hoje - timedelta(days=1)).isoformat()}, tm)
vencido = login(op["email"], esperar_erro=True)
checar("usuário com prazo vencido não entra", vencido.get("_status") == 423
       and "terminou" in str(vencido.get("_detalhe", "")), str(vencido.get("_detalhe", ""))[:60])

api("POST", f"/api/admin/usuarios/{op['id']}/acesso",
    {"ativo": True, "acesso_ate": (hoje + timedelta(days=5)).isoformat()}, tm)
ok = login(op["email"], esperar_erro=True)
checar("usuário com prazo em dia entra", "token" in ok)
token_op = ok.get("token")

api("POST", f"/api/admin/usuarios/{op['id']}/acesso", {"ativo": False, "acesso_ate": None}, tm)
bloqueado = login(op["email"], esperar_erro=True)
checar("usuário bloqueado não entra", bloqueado.get("_status") == 423,
       str(bloqueado.get("_detalhe", ""))[:50])
sessao = api("GET", "/api/auth/me", token=token_op, esperar_erro=True)
checar("sessão aberta do bloqueado é derrubada", sessao.get("_status") == 423)

reativar = api("PUT", f"/api/usuarios/{op['id']}", {
    "nome": op["nome"], "email": op["email"], "perfil": "OPERADOR", "ativo": True,
}, tc, esperar_erro=True)
checar("admin da empresa não reativa quem o site bloqueou", reativar.get("_status") == 403,
       str(reativar.get("_detalhe", ""))[:60])

mestre = api("POST", f"/api/admin/usuarios/{dono['usuario']['id']}/acesso",
             {"ativo": False}, tm, esperar_erro=True)
checar("administrador do site não pode ser bloqueado", mestre.get("_status") == 400)

api("POST", f"/api/admin/usuarios/{op['id']}/acesso", {"ativo": True, "acesso_ate": None}, tm)
checar("usuário liberado de novo entra", "token" in login(op["email"], esperar_erro=True))

print("\n=== 7. Voltar ao limite padrão ===")
padrao = api("POST", f"/api/admin/empresas/{aid}/limite", {"limite": None}, tm)
checar("limite volta ao padrão do plano", padrao["limite_usuarios"] == 3
       and not padrao["limite_personalizado"], str(padrao["limite_usuarios"]))

print("\n=== 8. Troca do padrão antigo (5 -> 3) acontece uma vez só ===")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pasta = tempfile.mkdtemp()
os.environ.pop("VERCEL", None)
os.environ["FIN_DATABASE_URL"] = ""
os.environ.pop("POSTGRES_URL", None)
import importlib  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend import models  # noqa: E402
from backend.assinaturas import config, garantir_configuracoes  # noqa: E402
from backend.database import Base  # noqa: E402

motor = create_engine(f"sqlite:///{pasta}/velho.db")
Base.metadata.create_all(motor)
Sessao = sessionmaker(bind=motor)
with Sessao() as db:
    db.add(models.Configuracao(chave="usuarios_incluidos", valor="5", descricao="", publica=True))
    db.commit()
    garantir_configuracoes(db)
    db.commit()
    checar("banco antigo com 5 passa para 3", config(db, "usuarios_incluidos") == "3",
           config(db, "usuarios_incluidos"))
    registro = db.query(models.Configuracao).filter_by(chave="usuarios_incluidos").first()
    registro.valor = "5"
    db.commit()
    garantir_configuracoes(db)
    db.commit()
    checar("se o dono voltar para 5 à mão, fica 5", config(db, "usuarios_incluidos") == "5")

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("Empresas e acessos OK.")
