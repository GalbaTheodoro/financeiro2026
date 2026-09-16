"""Teste da consulta de CEP.

Sobe um servidor local que imita a API oficial dos Correios (token pelo cartão
de postagem + /cep/v2/enderecos) e confere se o endereço chega normalizado.
Também testa o ViaCEP simulado e as validações.

Uso:  python testes/teste_cep.py
"""
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "http://127.0.0.1:8000"
PORTA_FALSA = 8097
falhas = []
chamadas = []

CEP = "13010100"

RESPOSTA_CORREIOS = {
    "cep": "13010100",
    "uf": "SP",
    "localidade": "Campinas",
    "bairro": "Centro",
    "logradouro": "Rua das Flores",
    "complemento": "de 200 a 400 - lado par",
    "tipoCEP": "1",
}


class Falso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, codigo, corpo):
        dados = json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(tamanho).decode() if tamanho else ""
        chamadas.append(("POST", self.path, dict(self.headers), corpo))
        if not self.headers.get("Authorization", "").startswith("Basic "):
            return self._json(401, {"erro": "sem credencial"})
        self._json(201, {"token": "token-correios", "expiraEm": "2030-01-01T00:00:00"})

    def do_GET(self):
        chamadas.append(("GET", self.path, dict(self.headers), ""))
        if self.headers.get("Authorization") != "Bearer token-correios":
            return self._json(401, {"erro": "token invalido"})
        if self.path.endswith("/99999999"):
            return self._json(404, {"msgs": ["CEP nao encontrado"]})
        self._json(200, RESPOSTA_CORREIOS)


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


servidor = HTTPServer(("127.0.0.1", PORTA_FALSA), Falso)
threading.Thread(target=servidor.serve_forever, daemon=True).start()

token = api("POST", "/api/auth/login", {"email": "admin@financeiro.local", "senha": "admin123"})["token"]
originais = api("GET", "/api/admin/configuracoes", token=token)["valores"]

try:
    print("\n=== 1. Consulta pela API oficial dos Correios (simulada) ===")
    api("PUT", "/api/admin/configuracoes", {"valores": {
        "cep_provedor": "CORREIOS",
        "cep_endpoint": f"http://127.0.0.1:{PORTA_FALSA}",
        "cep_usuario": "usuario-teste",
        "cep_senha": "senha-teste",
        "cep_cartao_postagem": "0057018901",
    }}, token)

    situacao = api("GET", "/api/consulta/situacao", token=token)
    checar("serviço de CEP disponível pelos Correios",
           situacao["cep"]["disponivel"] and situacao["cep"]["provedor"] == "CORREIOS",
           situacao["cep"]["descricao"])
    checar("situação traz também o serviço de CNPJ", "cnpj" in situacao)

    d = api("GET", f"/api/consulta/cep/{CEP}", token=token)
    checar("CEP formatado", d["cep"] == "13010-100", d["cep"])
    checar("logradouro", d["logradouro"] == "Rua das Flores", d["logradouro"])
    checar("bairro", d["bairro"] == "Centro")
    checar("cidade", d["cidade"] == "Campinas")
    checar("UF", d["uf"] == "SP")
    checar("complemento", d["complemento"].startswith("de 200"))
    checar("fonte identificada", "Correios" in d["fonte"], d["fonte"])

    print("\n=== 2. Autenticação dos Correios ===")
    autenticacao = [c for c in chamadas if c[0] == "POST"]
    consultas = [c for c in chamadas if c[0] == "GET"]
    checar("token pedido no máximo uma vez", len(autenticacao) <= 1,
           f"{len(autenticacao)} chamada(s)")
    if autenticacao:
        checar("autenticou pelo cartão de postagem",
               "cartaopostagem" in autenticacao[0][1], autenticacao[0][1])
        checar("enviou o número do cartão no corpo",
               "0057018901" in autenticacao[0][3], autenticacao[0][3][:60])
    checar("consultou o endpoint /cep/v2/enderecos",
           any("/cep/v2/enderecos/" in c[1] for c in consultas),
           consultas[0][1] if consultas else "")

    print("\n=== 3. CEP inexistente e validações ===")
    inexistente = api("GET", "/api/consulta/cep/99999999", token=token, esperar_erro=True)
    checar("CEP inexistente devolve mensagem clara", inexistente.get("_status") == 404,
           str(inexistente.get("_detalhe"))[:60])
    curto = api("GET", "/api/consulta/cep/1234", token=token, esperar_erro=True)
    checar("CEP com menos de 8 dígitos é recusado", curto.get("_status") == 400)
    zerado = api("GET", "/api/consulta/cep/00000000", token=token, esperar_erro=True)
    checar("CEP zerado é recusado", zerado.get("_status") == 400)
    sem_login = urllib.request.Request(f"{BASE}/api/consulta/cep/{CEP}")
    try:
        urllib.request.urlopen(sem_login)
        checar("consulta de CEP exige login", False)
    except urllib.error.HTTPError as e:
        checar("consulta de CEP exige login", e.code == 401)

    print("\n=== 4. Sem contrato dos Correios e serviço desligado ===")
    api("PUT", "/api/admin/configuracoes",
        {"valores": {"cep_usuario": "", "cep_senha": ""}}, token)
    sem_credencial = api("GET", "/api/consulta/cep/99999999", token=token, esperar_erro=True)
    checar("sem credencial avisa para configurar", sem_credencial.get("_status") == 400,
           str(sem_credencial.get("_detalhe"))[:60])

    api("PUT", "/api/admin/configuracoes", {"valores": {"cep_provedor": "AUTO"}}, token)
    auto = api("GET", "/api/consulta/situacao", token=token)["cep"]
    checar("sem contrato, AUTO usa o ViaCEP",
           auto["disponivel"] and auto["provedor"] == "VIACEP", auto["descricao"])

    api("PUT", "/api/admin/configuracoes", {"valores": {"cep_provedor": "DESATIVADO"}}, token)
    desligado = api("GET", "/api/consulta/situacao", token=token)["cep"]
    checar("é possível desativar a busca de CEP", desligado["disponivel"] is False)

finally:
    api("PUT", "/api/admin/configuracoes", {"valores": {
        k: originais.get(k, "") for k in originais if k.startswith("cep_")
    }}, token)
    servidor.shutdown()

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("Consulta de CEP OK.")
