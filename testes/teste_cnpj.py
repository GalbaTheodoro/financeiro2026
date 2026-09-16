"""Teste da consulta de CNPJ na API do governo.

Sobe um servidor local que imita o Conecta Gov (token OAuth2 + endpoints
basica/qsa/empresa), aponta o sistema para ele e confere se os dados chegam
normalizados no formato usado pelo cadastro de cliente/fornecedor.

Uso:  python testes/teste_cnpj.py
"""
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "http://127.0.0.1:8000"
PORTA_FALSA = 8099
falhas = []
chamadas = []

CNPJ = "19131243000197"  # CNPJ válido (dígitos verificadores corretos)

RESPOSTA_BASICA = {
    "cnpj": CNPJ,
    "nomeEmpresarial": "ASSOCIACAO BRASILEIRA DE TESTES LTDA",
    "nomeFantasia": "ABT TESTES",
    "dataAbertura": "2013-10-03",
    "correioEletronico": "CONTATO@ABTTESTES.ORG.BR",
    "situacaoCadastral": {"codigo": "2", "data": "2013-10-03", "descricao": "ATIVA"},
    "naturezaJuridica": {"codigo": "2062", "descricao": "Sociedade Empresaria Limitada"},
    "porte": {"codigo": "03", "descricao": "DEMAIS"},
    "capitalSocial": "150000.00",
    "cnaePrincipal": {"codigo": "6201501", "descricao": "Desenvolvimento de programas de computador"},
    "endereco": {
        "tipoLogradouro": "AVENIDA",
        "logradouro": "PAULISTA",
        "numero": "1000",
        "complemento": "SALA 42",
        "bairro": "BELA VISTA",
        "cep": "01310100",
        "municipio": {"codigo": "7107", "descricao": "SAO PAULO"},
        "uf": "SP",
    },
    "telefones": [{"ddd": "11", "numero": "30001000"}],
}

RESPOSTA_QSA = {
    "cnpj": CNPJ,
    "socios": [
        {"nome": "MARIA DA SILVA", "qualificacao": {"codigo": "49", "descricao": "Socio-Administrador"},
         "cpfCnpj": "***123456**", "dataEntrada": "2013-10-03"},
        {"nome": "JOAO PEREIRA", "qualificacao": {"codigo": "22", "descricao": "Socio"},
         "cpfCnpj": "***654321**", "dataEntrada": "2015-02-11"},
    ],
}


class Falso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _responder(self, codigo, corpo):
        dados = json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_POST(self):
        chamadas.append(("POST", self.path, dict(self.headers)))
        if self.path.endswith("/oauth2/jwt-token"):
            if not self.headers.get("Authorization", "").startswith("Basic "):
                return self._responder(401, {"erro": "sem credencial"})
            return self._responder(200, {"access_token": "token-de-teste", "expires_in": 3600})
        self._responder(404, {"erro": "nao encontrado"})

    def do_GET(self):
        chamadas.append(("GET", self.path, dict(self.headers)))
        if self.headers.get("Authorization") != "Bearer token-de-teste":
            return self._responder(401, {"erro": "token invalido"})
        if "/api-cnpj-basica/v2/basica/" in self.path:
            return self._responder(200, RESPOSTA_BASICA)
        if "/api-cnpj-qsa/v2/qsa/" in self.path:
            return self._responder(200, RESPOSTA_QSA)
        if "/api-cnpj-empresa/v2/empresa/" in self.path:
            return self._responder(200, {**RESPOSTA_BASICA, **RESPOSTA_QSA})
        self._responder(404, {"erro": "cnpj nao encontrado"})


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
    print("\n=== 1. Consulta pela API do governo (Conecta Gov simulado) ===")
    api("PUT", "/api/admin/configuracoes", {"valores": {
        "cnpj_provedor": "CONECTA_GOV",
        "cnpj_endpoint": f"http://127.0.0.1:{PORTA_FALSA}",
        "cnpj_tipo_consulta": "basica",
        "cnpj_consumer_key": "chave-de-teste",
        "cnpj_consumer_secret": "segredo-de-teste",
        "cnpj_cpf_usuario": "12345678909",
        "cnpj_incluir_socios": "1",
    }}, token)

    situacao = api("GET", "/api/consulta/situacao", token=token)["cnpj"]
    checar("serviço disponível pelo Conecta Gov",
           situacao["disponivel"] and situacao["provedor"] == "CONECTA_GOV", situacao["descricao"])

    d = api("GET", f"/api/consulta/cnpj/{CNPJ}", token=token)
    checar("razão social", d["razao_social"] == "ASSOCIACAO BRASILEIRA DE TESTES LTDA")
    checar("nome fantasia", d["nome_fantasia"] == "ABT TESTES")
    checar("CNPJ formatado", d["cnpj"] == "19.131.243/0001-97", d["cnpj"])
    checar("situação cadastral", "ATIVA" in d["situacao"], d["situacao"])
    checar("logradouro com tipo", d["logradouro"] == "AVENIDA PAULISTA", d["logradouro"])
    checar("número e complemento", d["numero"] == "1000" and d["complemento"] == "SALA 42")
    checar("bairro", d["bairro"] == "BELA VISTA")
    checar("cidade e UF", d["cidade"] == "SAO PAULO" and d["uf"] == "SP")
    checar("CEP formatado", d["cep"] == "01310-100", d["cep"])
    checar("telefone com DDD", d["telefone"] == "(11) 30001000", d["telefone"])
    checar("e-mail em minúsculas", d["email"] == "contato@abttestes.org.br", d["email"])
    checar("CNAE principal", d["cnae_principal"].startswith("6201501"), d["cnae_principal"])
    checar("natureza jurídica", "Limitada" in d["natureza_juridica"])
    checar("sócios do QSA vieram junto", len(d["socios"]) == 2,
           ", ".join(s["nome"] for s in d["socios"]))
    checar("qualificação do sócio", d["socios"][0]["qualificacao"].endswith("Socio-Administrador"))

    print("\n=== 2. Autenticação e cabeçalhos enviados ===")
    autenticacao = [c for c in chamadas if c[0] == "POST" and "jwt-token" in c[1]]
    consultas = [c for c in chamadas if c[0] == "GET"]
    checar("token reaproveitado (no máximo uma autenticação)", len(autenticacao) <= 1,
           f"{len(autenticacao)} chamada(s) ao /oauth2/jwt-token")
    checar("consultou basica e qsa", len(consultas) == 2, " · ".join(c[1] for c in consultas))
    cabecalhos = {k.lower(): v for k, v in consultas[0][2].items()}
    checar("enviou o CPF do usuário no cabeçalho",
           cabecalhos.get("x-cpf-usuario") == "12345678909",
           cabecalhos.get("x-cpf-usuario", "ausente"))

    print("\n=== 3. Endpoint 'empresa' (básica + QSA numa chamada) ===")
    api("PUT", "/api/admin/configuracoes",
        {"valores": {"cnpj_tipo_consulta": "empresa"}}, token)
    d2 = api("GET", f"/api/consulta/cnpj/{CNPJ}", token=token)
    checar("consulta empresa traz dados e sócios",
           d2["razao_social"] and len(d2["socios"]) == 2)
    checar("fonte identificada", "empresa" in d2["fonte"], d2["fonte"])

    print("\n=== 4. Validações ===")
    invalido = api("GET", "/api/consulta/cnpj/11111111111111", token=token, esperar_erro=True)
    checar("CNPJ inválido é recusado antes de consultar", invalido.get("_status") == 400,
           str(invalido.get("_detalhe"))[:50])
    cpf = api("GET", "/api/consulta/cnpj/12345678909", token=token, esperar_erro=True)
    checar("CPF avisa que a busca é só para CNPJ", cpf.get("_status") == 400)
    sem_login = urllib.request.Request(f"{BASE}/api/consulta/cnpj/{CNPJ}")
    try:
        urllib.request.urlopen(sem_login)
        checar("consulta exige login", False)
    except urllib.error.HTTPError as e:
        checar("consulta exige login", e.code == 401)

    print("\n=== 5. Credenciais erradas e serviço desligado ===")
    api("PUT", "/api/admin/configuracoes",
        {"valores": {"cnpj_tipo_consulta": "basica", "cnpj_consumer_key": ""}}, token)
    sem_credencial = api("GET", f"/api/consulta/cnpj/{CNPJ}", token=token, esperar_erro=True)
    checar("sem credencial, avisa para configurar", sem_credencial.get("_status") == 400,
           str(sem_credencial.get("_detalhe"))[:60])

    api("PUT", "/api/admin/configuracoes", {"valores": {"cnpj_provedor": "DESATIVADO"}}, token)
    desligado = api("GET", "/api/consulta/situacao", token=token)["cnpj"]
    checar("é possível desativar a consulta", desligado["disponivel"] is False)

finally:
    api("PUT", "/api/admin/configuracoes", {"valores": {
        k: originais.get(k, "") for k in originais if k.startswith("cnpj_")
    }}, token)
    servidor.shutdown()

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("Consulta de CNPJ OK.")
