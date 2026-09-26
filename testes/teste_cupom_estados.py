"""Teste do cupom fiscal (NFC-e) em mais de um estado.

Até aqui o cupom só saía em Minas. Agora a tabela de endereços da SEFAZ é por
estado **e editável na tela** — porque esses endereços mudam (Goiás trocou a URL
do QR Code em 2025) e o cliente não pode ficar esperando versão nova do sistema.

O que se confere
----------------
  * o padrão de fábrica traz MG, SP, GO e TO;
  * cada estado monta o **QR Code com a URL dele** — e a URL entra no texto que
    vai impresso, não em outro lugar;
  * o **hash do QR Code não muda** de estado para estado: ele é do CSC e da
    chave, não do endereço (senão o cupom seria recusado);
  * estado sem endereço **não emite**, e a mensagem diz o que falta e onde
    preencher — em vez de chutar uma URL e levar rejeição 395 da SEFAZ;
  * o **prazo de cancelamento é de cada estado**: Minas 30 minutos, Tocantins
    24 horas;
  * o administrador **edita um endereço** e o QR Code sai com o novo na hora;
  * editar com o mesmo valor do padrão não grava nada — o estado continua
    acompanhando as atualizações do sistema;
  * **voltar ao padrão** desfaz a edição;
  * endereço sem https:// é recusado;
  * só o administrador do site mexe nisso.

Uso:  python testes/teste_cupom_estados.py   (com o servidor no ar)
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


from backend import cupom as nfce                    # noqa: E402
from backend import sefaz_enderecos as enderecos     # noqa: E402
from backend.database import SessionLocal            # noqa: E402

sufixo = str(int(time.time()))
tm = api("POST", "/api/auth/login",
         {"email": "admin@financeiro.local", "senha": "admin123"})["token"]

CHAVE = "31250712345678000190650010000000011000000017"   # 44 números
CSC = "CODIGO-SECRETO-DE-TESTE"
CSC_ID = "000001"

# =========================================================================== #
print("=== 0. A NF-e já atendia os quatro estados ===")
from backend import emissao as nfe                   # noqa: E402

for uf, esperado in (("MG", "fazenda.mg.gov.br"), ("SP", "fazenda.sp.gov.br"),
                     ("GO", "sefaz.go.gov.br")):
    url = nfe._endereco(nfe.AUTORIZACAO, uf, "1")
    checar(f"NF-e de {uf} vai para o servidor do próprio estado", esperado in url, url)
url_to = nfe._endereco(nfe.AUTORIZACAO, "TO", "1")
checar("NF-e do Tocantins cai no SVRS, que é quem autoriza para ele",
       "svrs.rs.gov.br" in url_to, url_to)
checar("e o evento (cancelamento) da NF-e segue o mesmo caminho",
       "svrs.rs.gov.br" in nfe._endereco(nfe.EVENTO, "TO", "1")
       and "fazenda.sp.gov.br" in nfe._endereco(nfe.EVENTO, "SP", "1"))
# a chave de acesso começa pelo código do estado: errar isso invalida a nota
from backend.dfe import CODIGO_UF                    # noqa: E402

checar("cada estado tem o código certo na chave de acesso",
       CODIGO_UF["MG"] == "31" and CODIGO_UF["SP"] == "35"
       and CODIGO_UF["GO"] == "52" and CODIGO_UF["TO"] == "17",
       f'MG={CODIGO_UF["MG"]} SP={CODIGO_UF["SP"]} GO={CODIGO_UF["GO"]} TO={CODIGO_UF["TO"]}')

# =========================================================================== #
print("\n=== 1. O padrão de fábrica do cupom ===")
quadro = api("GET", "/api/admin/sefaz?modelo=65", None, tm)
ufs = {l["uf"]: l for l in quadro["linhas"]}
checar("a tabela traz MG, SP, GO e TO", {"MG", "SP", "GO", "TO"} <= set(ufs), str(sorted(ufs)))
checar("Minas e São Paulo emitem", ufs["MG"]["emite"] and ufs["SP"]["emite"])
checar("Goiás emite (autorização pelo SVRS e QR Code próprio)", ufs["GO"]["emite"],
       str(ufs["GO"]["faltando"]))
checar("o Tocantins ainda não emite: falta o QR Code, e a tela diz isso",
       ufs["TO"]["emite"] is False
       and any("QR Code" in f for f in ufs["TO"]["faltando"]), str(ufs["TO"]["faltando"]))
checar("cada estado mostra de onde veio o padrão",
       all(l["fonte"] for l in quadro["linhas"]))
checar("São Paulo aponta para o webservice da NFC-e paulista, não o da NF-e",
       "nfce.fazenda.sp.gov.br" in ufs["SP"]["campos"]["autorizacao_producao"]["valor"],
       ufs["SP"]["campos"]["autorizacao_producao"]["valor"])
checar("Goiás e Tocantins autorizam pelo SVRS",
       "nfce.svrs.rs.gov.br" in ufs["GO"]["campos"]["autorizacao_producao"]["valor"]
       and "nfce.svrs.rs.gov.br" in ufs["TO"]["campos"]["autorizacao_producao"]["valor"])

# =========================================================================== #
print("\n=== 2. O QR Code sai com a URL de cada estado ===")
db = SessionLocal()
try:
    textos = {}
    for uf in ("MG", "SP", "GO"):
        textos[uf] = nfce.texto_qrcode(CHAVE, "1", CSC, CSC_ID, uf, db)
        checar(f"{uf}: o QR Code começa pela URL do estado",
               textos[uf].startswith(enderecos.endereco(db, "65", uf, "qrcode", "1")),
               textos[uf][:58])
    checar("e as três URLs são diferentes entre si",
           len({t.split("?")[0] for t in textos.values()}) == 3)

    # o hash é do CSC + chave; trocar de estado não pode mudá-lo, senão a SEFAZ recusa
    assinaturas = {uf: t.split("|")[-1] for uf, t in textos.items()}
    checar("o hash do QR Code é o mesmo nos três — ele é do CSC, não do endereço",
           len(set(assinaturas.values())) == 1, str(list(assinaturas.values())[0])[:16])
    checar("e o CSC não aparece no texto do QR Code",
           all(CSC not in t for t in textos.values()))

    # o bloco que vai dentro do XML leva a URL de consulta daquele estado
    supl = nfce.bloco_suplementar(CHAVE, "1", CSC, CSC_ID, "SP", db)
    checar("o infNFeSupl de SP leva a consulta pública paulista",
           "nfce.fazenda.sp.gov.br" in supl and "<urlChave>" in supl)

    # =====================================================================
    print("\n=== 3. Estado sem endereço não emite (e diz o que falta) ===")
    try:
        nfce.texto_qrcode(CHAVE, "1", CSC, CSC_ID, "TO", db)
        checar("Tocantins sem QR Code deveria recusar", False, "emitiu")
    except nfce.ErroCupom as erro:
        checar("Tocantins recusa, diz o serviço que falta e onde preencher",
               "QR Code" in str(erro) and "Endereços da SEFAZ" in str(erro), str(erro)[:80])
    try:
        nfce.url_autorizacao("", "1", db)
        checar("empresa sem UF deveria recusar", False, "não recusou")
    except nfce.ErroCupom as erro:
        checar("empresa sem UF é avisada para preencher o estado",
               "sem UF" in str(erro), str(erro)[:60])

    # =====================================================================
    print("\n=== 4. O prazo de cancelamento é de cada estado ===")
    checar("Minas: 30 minutos", nfce.minutos_para_cancelar("MG", db) == 30)
    checar("Tocantins: 24 horas", nfce.minutos_para_cancelar("TO", db) == 1440)
    checar("estado desconhecido usa o prazo mais curto — errar para o lado seguro",
           nfce.minutos_para_cancelar("AC", db) == 30)
finally:
    db.close()

# =========================================================================== #
print("\n=== 5. O administrador conserta um endereço sem versão nova ===")
novo_qr = "https://nfeweb2.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
api("PUT", "/api/admin/sefaz/65/GO", {"qrcode_producao": novo_qr}, tm)
db = SessionLocal()
try:
    checar("o QR Code de Goiás passa a usar o endereço novo na hora",
           nfce.texto_qrcode(CHAVE, "1", CSC, CSC_ID, "GO", db).startswith(novo_qr))
finally:
    db.close()
linha = next(l for l in api("GET", "/api/admin/sefaz?modelo=65", None, tm)["linhas"]
             if l["uf"] == "GO")
checar("a tela marca o campo como editado por você",
       linha["campos"]["qrcode_producao"]["editado"] is True)
checar("e guarda qual era o padrão de fábrica",
       "nfeweb.sefaz.go.gov.br" in linha["campos"]["qrcode_producao"]["padrao"])

# ligar o Tocantins é preencher dois campos
api("PUT", "/api/admin/sefaz/65/TO", {
    "qrcode_producao": "https://apps.sefaz.to.gov.br/portal-nfce/qrcode",
    "qrcode_homologacao": "https://apps.sefaz.to.gov.br/portal-nfce/qrcode",
    "consulta_producao": "https://apps.sefaz.to.gov.br/portal-nfce/consultarNFCe.jsf",
    "consulta_homologacao": "https://apps.sefaz.to.gov.br/portal-nfce/consultarNFCe.jsf"}, tm)
to = next(l for l in api("GET", "/api/admin/sefaz?modelo=65", None, tm)["linhas"]
          if l["uf"] == "TO")
checar("preenchendo o QR Code, o Tocantins passa a emitir",
       to["emite"] is True and to["faltando"] == [], str(to["faltando"]))
db = SessionLocal()
try:
    checar("e o cupom do Tocantins monta o QR Code",
           "apps.sefaz.to.gov.br" in nfce.texto_qrcode(CHAVE, "1", CSC, CSC_ID, "TO", db))
finally:
    db.close()

# ------------------------------------------------------------ o que é recusado
ruim = api("PUT", "/api/admin/sefaz/65/GO", {"qrcode_producao": "sefaz.go.gov.br/qrcode"},
           tm, esperar_erro=True)
checar("endereço sem https:// é recusado", ruim.get("_status") == 400
       and "https" in str(ruim.get("detail")), str(ruim.get("detail"))[:60])
uf_ruim = api("PUT", "/api/admin/sefaz/65/GOI", {"qrcode_producao": novo_qr},
              tm, esperar_erro=True)
checar("sigla de estado inválida é recusada", uf_ruim.get("_status") == 400)

# --------------------------------------------- salvar o padrão não grava nada
padrao_sp = next(l for l in api("GET", "/api/admin/sefaz?modelo=65", None, tm)["linhas"]
                 if l["uf"] == "SP")["campos"]["qrcode_producao"]["padrao"]
api("PUT", "/api/admin/sefaz/65/SP", {"qrcode_producao": padrao_sp}, tm)
sp = next(l for l in api("GET", "/api/admin/sefaz?modelo=65", None, tm)["linhas"]
          if l["uf"] == "SP")
checar("salvar o mesmo valor do padrão não marca como editado",
       sp["campos"]["qrcode_producao"]["editado"] is False)

# ------------------------------------------------------------ voltar ao padrão
api("DELETE", "/api/admin/sefaz/65/GO", None, tm)
go = next(l for l in api("GET", "/api/admin/sefaz?modelo=65", None, tm)["linhas"]
          if l["uf"] == "GO")
checar("voltar ao padrão desfaz a edição",
       go["campos"]["qrcode_producao"]["editado"] is False
       and "nfeweb.sefaz.go.gov.br" in go["campos"]["qrcode_producao"]["valor"],
       go["campos"]["qrcode_producao"]["valor"])

# =========================================================================== #
print("\n=== 5b. Conferir o QR Code antes da primeira venda ===")
previa = api("GET", "/api/admin/sefaz/previa/SP?ambiente=1", None, tm)
checar("a prévia monta o QR Code de São Paulo",
       previa["ok"] is True and previa["texto"].startswith("https://www.nfce.fazenda.sp.gov.br"),
       previa["texto"][:56])
checar("e mostra também a consulta pela chave daquele estado",
       "nfce.fazenda.sp.gov.br" in previa["consulta"], previa["consulta"])
homolog = api("GET", "/api/admin/sefaz/previa/SP?ambiente=2", None, tm)
checar("produção e homologação dão endereços diferentes",
       homolog["texto"] != previa["texto"]
       and "homologacao" in homolog["texto"], homolog["texto"][:56])
sem_qr = api("GET", "/api/admin/sefaz/previa/AC?ambiente=1", None, tm)
checar("estado sem endereço não finge que dá — diz o que falta",
       sem_qr["ok"] is False and "QR Code" in sem_qr["mensagem"],
       str(sem_qr.get("mensagem"))[:70])
checar("o assinante não vê a prévia",
       api("GET", "/api/admin/sefaz/previa/SP", None, None, esperar_erro=True)
       .get("_status") == 401)

# ------------------------------------------------- o Tocantins diz onde copiar
to_linha = next(l for l in api("GET", "/api/admin/sefaz?modelo=65", None, tm)["linhas"]
                if l["uf"] == "TO")
checar("o Tocantins diz que a autorização é do SVRS",
       "SVRS" in to_linha["fonte"], to_linha["fonte"][:60])
checar("e a tela diz onde copiar o que falta",
       "to.gov.br/sefaz" in to_linha["onde"], to_linha["onde"][:60])
checar("todo estado do padrão diz de onde vem e onde copiar",
       all(l["fonte"] and l["onde"] for l in api(
           "GET", "/api/admin/sefaz?modelo=65", None, tm)["linhas"]))

# =========================================================================== #
print("\n=== 6. A tela do cliente enxerga o estado dele ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"sp{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria SP", "plano": "P4_ANUAL", "uf": "SP"})
tc, ec = conta["token"], conta["empresa"]["id"]
config = api("GET", f"/api/cupom/config?empresa_id={ec}", None, tc)
checar("empresa de SP vê que o estado dela emite cupom",
       config["uf_atendida"] is True and "SP" in config["ufs_com_cupom"],
       str(config["ufs_com_cupom"]))
checar("e o prazo de cancelamento mostrado é o de SP",
       config["minutos_para_cancelar"] == 30)

api("PUT", f"/api/empresas/{ec}", {"uf": "AC", "razao_social": "Assessoria SP"}, tc)
config_ac = api("GET", f"/api/cupom/config?empresa_id={ec}", None, tc)
checar("empresa do Acre vê que falta endereço, e o que falta",
       config_ac["uf_atendida"] is False and config_ac["falta_endereco"],
       str(config_ac["falta_endereco"])[:80])
venda = api("POST", "/api/cupom/venda", {
    "empresa_id": ec, "ambiente": "2",
    "itens": [{"descricao": "CAFE", "quantidade": 1, "valor_unitario": 10}]},
    tc, esperar_erro=True)
checar("e a venda no Acre é recusada antes de gastar número de cupom",
       venda.get("_status") == 400 and "SEFAZ" in str(venda.get("detail")),
       str(venda.get("detail"))[:80])

# =========================================================================== #
print("\n=== 7. Só o administrador do site mexe nos endereços ===")
checar("o assinante não lê a tabela",
       api("GET", "/api/admin/sefaz", None, tc, esperar_erro=True).get("_status") == 403)
checar("o assinante não edita endereço",
       api("PUT", "/api/admin/sefaz/65/SP", {"qrcode_producao": "https://x.com"}, tc,
           esperar_erro=True).get("_status") == 403)
checar("o assinante não restaura o padrão",
       api("DELETE", "/api/admin/sefaz/65/SP", None, tc,
           esperar_erro=True).get("_status") == 403)

# limpa o que este teste editou
for uf in ("SP", "TO", "GO"):
    api("DELETE", f"/api/admin/sefaz/65/{uf}", None, tm)

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Cupom em vários estados OK — cada UF com o seu QR Code, e corrigível na tela.")
