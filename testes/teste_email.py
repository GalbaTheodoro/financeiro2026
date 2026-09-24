"""Teste do envio de nota por e-mail, com um servidor SMTP de mentira.

O que se confere
----------------
  * a configuração de e-mail da empresa é salva e **a senha nunca volta** para a tela;
  * o e-mail de teste sai com os dados certos;
  * a nota autorizada é enviada para o e-mail do cliente, com cópia para a
    empresa e para o contador;
  * vão dois anexos: o XML e a DANFE em PDF (e o PDF é um PDF de verdade);
  * senha errada, servidor errado e cliente sem e-mail dão mensagens que dizem
    o que fazer — e nenhuma delas derruba a nota já autorizada.

**Nenhum e-mail sai para a internet**: sobe-se um servidor SMTP falso em
127.0.0.1 que só guarda o que recebe.

Uso:  python testes/teste_email.py   (com o servidor no ar)
"""
import json
import sys
import time
import urllib.error
import urllib.request
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

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


from smtp_de_mentira import CaixaDeEntrada, subir_smtp   # noqa: E402

CAIXA = CaixaDeEntrada()
PORTA_SMTP = subir_smtp(CAIXA)
print(f"=== servidor SMTP de mentira na porta {PORTA_SMTP} ===")

# =========================================================================== #
print("\n=== 1. Empresa, cliente e configuração de e-mail ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"email{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock"})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "inscricao_estadual": "0022334455001", "logradouro": "AVENIDA FARIA PEREIRA",
    "numero": "1250", "bairro": "CENTRO", "cidade": "Patrocínio", "uf": "MG",
    "cep": "38740108", "codigo_municipio": "3148004", "crt": "3",
    "email": "financeiro@agrodock.com.br"}, t)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, t)
cafe = api("GET", f"/api/produtos?empresa_id={eid}", None, t)[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: v for k, v in cafe.items() if k in ("codigo", "nome", "unidade_id",
                                              "embalagem", "descricao")},
    "empresa_id": eid, "ncm": "09011110", "cfop_padrao": "6102",
    "unidade_comercial": "SC", "origem": "0", "ativo": True}, t)
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "11444777000161", "rg_ie": "123456789", "indicador_ie": "1",
    "logradouro": "RUA DO CAFE", "numero": "500", "bairro": "CENTRO",
    "cidade": "Santos", "uf": "SP", "cep": "11010000",
    "codigo_municipio": "3548500", "email": "fiscal@torrefacao.com.br"}, t)

vazia = api("GET", f"/api/email/config?empresa_id={eid}", None, t)
checar("empresa nova nasce sem e-mail configurado",
       vazia["configurado"] is False and vazia["tem_senha"] is False)
checar("e já vem com assunto, texto e sugestões de servidor prontos",
       "{numero}" in vazia["assunto"] and "XML" in vazia["texto"]
       and len(vazia["sugestoes"]) >= 3)

config = {
    "empresa_id": eid, "servidor": "127.0.0.1", "porta": PORTA_SMTP,
    "seguranca": "NENHUMA", "usuario": "financeiro@agrodock.com.br",
    "senha": CAIXA.senha_certa, "remetente_nome": "Assessoria AgroDock",
    "remetente_email": "financeiro@agrodock.com.br",
    "email_contador": "contador@escritorio.com.br",
    "copia_empresa": True, "enviar_ao_autorizar": True,
}
salvo = api("PUT", "/api/email/config", config, t)
checar("a configuração é salva", salvo["configurado"] is True and salvo["tem_senha"] is True)
checar("a senha NÃO volta para a tela",
       "senha" not in json.dumps(salvo) or CAIXA.senha_certa not in json.dumps(salvo),
       "a senha apareceu na resposta!" if CAIXA.senha_certa in json.dumps(salvo) else "")

de_novo = api("PUT", "/api/email/config", {**config, "senha": ""}, t)
checar("salvar com a senha em branco mantém a que já estava guardada",
       de_novo["tem_senha"] is True)

ruim = api("PUT", "/api/email/config",
           {**config, "remetente_email": "sem-arroba"}, t, esperar_erro=True)
checar("endereço inválido é recusado ao salvar", ruim.get("_status") == 400,
       str(ruim.get("detail"))[:60])

# =========================================================================== #
print("\n=== 2. E-mail de teste ===")
CAIXA.limpar()
teste = api("POST", "/api/email/teste", {"empresa_id": eid, "para": "galba@teste.com"}, t)
checar("o teste é enviado", teste["ok"] is True, teste["mensagem"])
checar("chegou no servidor", len(CAIXA.mensagens) == 1)
if CAIXA.ultima:
    m = CAIXA.ultima["mensagem"]
    checar("com o remetente da empresa",
           "financeiro@agrodock.com.br" in m["From"], m["From"])
    checar("e o nome da empresa aparece para quem recebe",
           "Assessoria AgroDock" in m["From"], m["From"])

# =========================================================================== #
print("\n=== 3. A nota autorizada vai para o cliente ===")
nota = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "parceiro_id": cliente["id"], "ambiente": "2", "serie": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1000,
               "cfop": "6102"}]}, t)["nota"]["id"]

# põe a nota no estado de autorizada, com XML, como a SEFAZ devolveria
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from backend.database import SessionLocal            # noqa: E402
from backend.models import Nota                      # noqa: E402
from backend.routers.emissao import _montar          # noqa: E402

db = SessionLocal()
linha = db.get(Nota, nota)
inf, chave, _total = _montar(db, linha, 1)
linha.numero = "1"
linha.chave = chave
linha.status_emissao = "AUTORIZADA"
linha.situacao = "AUTORIZADA"
linha.protocolo = "131260000000001"
linha.xml = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
             f'<NFe>{inf}</NFe>'
             '<protNFe versao="4.00"><infProt><chNFe>' + chave + '</chNFe>'
             '<dhRecbto>2026-09-23T10:00:00-03:00</dhRecbto>'
             '<nProt>131260000000001</nProt><cStat>100</cStat>'
             '<xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe></nfeProc>')
db.commit()
db.close()

CAIXA.limpar()
envio = api("POST", f"/api/nfe/{nota}/enviar-email?empresa_id={eid}", None, t)
checar("o envio responde que deu certo", envio["ok"] is True, envio["mensagem"])
checar("foi para o e-mail do cliente", envio["para"] == ["fiscal@torrefacao.com.br"],
       str(envio["para"]))
checar("com cópia para a empresa e para o contador",
       set(envio["copia"]) == {"financeiro@agrodock.com.br", "contador@escritorio.com.br"},
       str(envio["copia"]))

recebida = CAIXA.ultima
checar("o servidor recebeu a mensagem", recebida is not None)
if recebida:
    checar("os três endereços entraram no envelope", len(recebida["para"]) == 3,
           str(recebida["para"]))
    mensagem = recebida["mensagem"]
    checar("o assunto traz o número da nota e a empresa",
           "NF-e 1" in mensagem["Subject"] and "AGRODOCK" in mensagem["Subject"].upper(),
           mensagem["Subject"])
    anexos = list(mensagem.iter_attachments())
    nomes = [a.get_filename() for a in anexos]
    checar("vão dois anexos: o XML e o PDF", len(anexos) == 2, str(nomes))
    checar("os dois têm o nome da chave de acesso",
           all(n and n.startswith(chave) for n in nomes), str(nomes))
    xml_anexo = next((a for a in anexos if (a.get_filename() or "").endswith(".xml")), None)
    pdf_anexo = next((a for a in anexos if (a.get_filename() or "").endswith(".pdf")), None)
    checar("o XML anexado é a nota inteira",
           xml_anexo is not None and b"infNFe" in xml_anexo.get_payload(decode=True))
    conteudo_pdf = pdf_anexo.get_payload(decode=True) if pdf_anexo else b""
    checar("o PDF anexado é um PDF de verdade",
           conteudo_pdf.startswith(b"%PDF-") and len(conteudo_pdf) > 2000,
           f"{len(conteudo_pdf)} bytes")
    checar("o texto do e-mail explica os dois arquivos",
           "XML" in mensagem.get_body(("plain",)).get_content()
           and "DANFE" in mensagem.get_body(("plain",)).get_content())

guardado = api("GET", f"/api/nfe/{nota}", None, t)["nota"]
checar("a nota guarda quando e para quem foi enviada",
       guardado["email_enviado_em"] and "fiscal@torrefacao.com.br"
       in (guardado["email_destinatarios"] or ""),
       str(guardado["email_destinatarios"]))
lista = api("GET", f"/api/notas?empresa_id={eid}", None, t)
checar("a lista de notas também mostra o envio",
       any(n["id"] == nota and n["email_enviado_em"] for n in lista["linhas"]))

# =========================================================================== #
print("\n=== 3b. Sem a biblioteca do PDF, o aviso não pode sumir ===")
# Foi o que aconteceu de verdade: a biblioteca não estava instalada, o e-mail
# saiu só com o XML e ninguém ficou sabendo, porque o sistema dizia "enviado".
# Aqui a falta é simulada dentro do processo, chamando a função que a rota chama.
import backend.danfe as _danfe                       # noqa: E402
from backend.routers.emissao import _enviar_por_email  # noqa: E402

_original = _danfe.pdf_disponivel
_danfe.pdf_disponivel = lambda: (False, "Falta a biblioteca que desenha a DANFE em PDF.")
CAIXA.limpar()
db = SessionLocal()
try:
    sem_pdf = _enviar_por_email(db, db.get(Nota, nota), automatico=False)
finally:
    _danfe.pdf_disponivel = _original
    db.close()

checar("o e-mail ainda sai (o XML é o documento fiscal)", sem_pdf["ok"] is True)
checar("mas a resposta avisa que foi só o XML",
       bool(sem_pdf.get("aviso")) and sem_pdf["anexos"] == ["XML"]
       and "só com o XML" in sem_pdf["mensagem"], sem_pdf["mensagem"][:70])
so_xml = CAIXA.ultima
nomes = [a.get_filename() for a in so_xml["mensagem"].iter_attachments()] if so_xml else []
checar("e de fato foi um anexo só", len(nomes) == 1 and nomes[0].endswith(".xml"),
       str(nomes))
marcada = api("GET", f"/api/nfe/{nota}", None, t)["nota"]
checar("a nota guarda que o cliente recebeu sem a DANFE",
       "sem a DANFE" in (marcada["email_erro"] or ""), str(marcada["email_erro"])[:60])

# a tela de e-mail precisa avisar ANTES de a próxima nota sair
_danfe.pdf_disponivel = lambda: (False, "Falta a biblioteca que desenha a DANFE em PDF.")
try:
    from backend.routers.correio import _ficha, config_da_empresa   # noqa: E402
    from backend.models import Empresa                              # noqa: E402
    db = SessionLocal()
    aviso_tela = _ficha(config_da_empresa(db, eid), db.get(Empresa, eid))
    db.close()
finally:
    _danfe.pdf_disponivel = _original
checar("a tela de e-mail avisa que a DANFE não vai sair",
       aviso_tela["pdf_ok"] is False and "biblioteca" in aviso_tela["pdf_motivo"],
       str(aviso_tela.get("pdf_motivo"))[:60])

CAIXA.limpar()
de_volta = api("POST", f"/api/nfe/{nota}/enviar-email?empresa_id={eid}", None, t)
checar("com a biblioteca no lugar, o PDF volta sozinho",
       not de_volta.get("aviso") and de_volta["anexos"] == ["XML", "DANFE em PDF"],
       str(de_volta.get("anexos")))
limpa = api("GET", f"/api/nfe/{nota}", None, t)["nota"]
checar("e o aviso some da nota", not limpa["email_erro"], str(limpa["email_erro"]))
checar("a conferência da biblioteca acha ela instalada aqui",
       _danfe.pdf_disponivel()[0] is True)

# =========================================================================== #
print("\n=== 4. Quando dá errado, a mensagem diz o que fazer ===")
sem_email = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "CLIENTE SEM E-MAIL",
    "cpf_cnpj": "33444555000166", "cidade": "Uberlândia", "uf": "MG",
    "codigo_municipio": "3170206", "logradouro": "R", "numero": "1",
    "bairro": "C", "cep": "38400000", "indicador_ie": "9"}, t)
api("PUT", "/api/email/config", {**config, "senha": "", "copia_empresa": False,
                                 "email_contador": ""}, t)
outra = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "parceiro_id": sem_email["id"], "ambiente": "2", "serie": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 1, "valor_unitario": 10,
               "cfop": "5102"}]}, t)["nota"]["id"]
db = SessionLocal()
linha = db.get(Nota, outra)
linha.status_emissao = "AUTORIZADA"
linha.xml = '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe/></NFe></nfeProc>'
db.commit()
db.close()
falha = api("POST", f"/api/nfe/{outra}/enviar-email?empresa_id={eid}", None, t,
            esperar_erro=True)
checar("cliente sem e-mail avisa onde está faltando",
       falha.get("_status") == 400 and "sem e-mail" in str(falha.get("detail", "")),
       str(falha.get("detail"))[:80])

api("PUT", "/api/email/config", {**config, "senha": "senha-errada"}, t)
CAIXA.limpar()
recusada = api("POST", "/api/email/teste", {"empresa_id": eid, "para": "galba@teste.com"},
               t, esperar_erro=True)
checar("senha recusada explica a senha de app",
       recusada.get("_status") == 400 and "senha de app" in str(recusada.get("detail", "")),
       str(recusada.get("detail"))[:90])
checar("e nada foi entregue", not CAIXA.mensagens)

api("PUT", "/api/email/config", {**config, "senha": CAIXA.senha_certa,
                                 "servidor": "servidor.que.nao.existe.invalido"}, t)
sem_servidor = api("POST", "/api/email/teste", {"empresa_id": eid, "para": "galba@teste.com"},
                   t, esperar_erro=True)
checar("servidor que não existe diz para conferir o nome",
       sem_servidor.get("_status") == 400
       and "não foi encontrado" in str(sem_servidor.get("detail", "")),
       str(sem_servidor.get("detail"))[:80])

outra_conta = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outro{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra"})
alheio = api("GET", f"/api/email/config?empresa_id={eid}", None,
             outra_conta["token"], esperar_erro=True)
checar("outra conta não enxerga a configuração de e-mail",
       alheio.get("_status") in (403, 404), str(alheio.get("_status")))

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S): " + "; ".join(erros))
    sys.exit(1)
print("E-mail OK — a nota autorizada sai com o XML e a DANFE para o cliente.")
