"""Teste do cupom fiscal eletrônico (NFC-e, modelo 65).

O que se confere
----------------
  * o CSC é guardado cifrado e **nunca volta** para a tela;
  * sem CSC o sistema recusa **antes** de gastar número de cupom;
  * o XML sai no modelo 65, passa no schema oficial 4.00 e traz o que só o
    cupom tem: tpImp 4, indPres 1, indFinal 1, idDest 1 e o infNFeSupl;
  * o **QR Code** bate com o cálculo feito à mão (SHA-1 da chave + CSC);
  * o destinatário é opcional: sem CPF não sai bloco `dest`; com CPF, sai sem
    endereço;
  * o troco entra no grupo de pagamento;
  * a numeração do cupom é **separada** da numeração da nota fiscal;
  * o cupom impresso traz os itens, o total, a chave, o QR Code e o consumidor;
  * UF sem cupom e prazo de cancelamento avisam com frase clara.

Uso:  python testes/teste_cupom.py   (com o servidor no ar)
"""
import hashlib
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from lxml import etree
except ImportError:                                  # pragma: no cover
    print("Este teste precisa do lxml para validar o schema. pip install lxml")
    sys.exit(0)

BASE = "http://127.0.0.1:8000"
XSD = pathlib.Path(__file__).parent / "xsd" / "nfe_v4.00.xsd"
NS = "http://www.portalfiscal.inf.br/nfe"
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


def pagina(caminho, token):
    req = urllib.request.Request(f"{BASE}{caminho}")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return r.read().decode("utf-8", "replace")


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


esquema = etree.XMLSchema(etree.parse(str(XSD)))
CSC = "GARIMPO-DE-TESTE-1234567890ABCDEF"

# =========================================================================== #
print("=== 1. Empresa, produto e o CSC ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"cupom{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock",
    # o cupom fiscal só existe nos planos que o incluem
    "plano": "P2_SEMESTRAL"})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "nome_fantasia": "AGRODOCK CAFES",
    "cnpj": "98765432000198", "inscricao_estadual": "0022334455001",
    "logradouro": "AVENIDA FARIA PEREIRA", "numero": "1250", "bairro": "CENTRO",
    "cidade": "Patrocínio", "uf": "MG", "cep": "38740108",
    "codigo_municipio": "3148004", "crt": "1", "telefone": "3439999999"}, t)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, t)
cafe = api("GET", f"/api/produtos?empresa_id={eid}", None, t)[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: v for k, v in cafe.items() if k in ("codigo", "nome", "unidade_id",
                                              "embalagem", "descricao")},
    "empresa_id": eid, "ncm": "09012100", "cfop_padrao": "5102",
    "unidade_comercial": "UN", "origem": "0", "ativo": True}, t)

vazio = api("GET", f"/api/cupom/config?empresa_id={eid}", None, t)
checar("empresa nova nasce sem CSC",
       vazio["tem_csc_homologacao"] is False and vazio["tem_csc_producao"] is False)
checar("e a tela sabe que MG emite cupom",
       vazio["uf_atendida"] is True and "MG" in vazio["ufs_com_cupom"])

sem_csc = api("POST", "/api/cupom/venda", {
    "empresa_id": eid, "ambiente": "2",
    "itens": [{"produto_id": cafe["id"], "quantidade": 1, "valor_unitario": 25}]},
    t, esperar_erro=True)
checar("sem CSC a venda é recusada com a frase certa",
       sem_csc.get("_status") == 400 and "CSC" in str(sem_csc.get("detail", "")),
       str(sem_csc.get("detail"))[:70])
series = api("GET", f"/api/nfe/series?empresa_id={eid}", None, t)
checar("e nenhum número de cupom foi gasto",
       all(s.get("modelo") != "65" for s in series) or
       all(s["proximo_numero"] == 1 for s in series if s.get("modelo") == "65"),
       str([(s.get("modelo"), s["proximo_numero"]) for s in series]))

salvo = api("PUT", "/api/cupom/config", {
    "empresa_id": eid, "serie": "1",
    "csc_homologacao": CSC, "csc_id_homologacao": "000001"}, t)
checar("o CSC é guardado", salvo["tem_csc_homologacao"] is True)
checar("e NÃO volta para a tela", CSC not in json.dumps(salvo))
de_novo = api("PUT", "/api/cupom/config",
              {"empresa_id": eid, "serie": "1", "csc_homologacao": ""}, t)
checar("salvar em branco mantém o CSC guardado", de_novo["tem_csc_homologacao"] is True)
ruim = api("PUT", "/api/cupom/config",
           {"empresa_id": eid, "csc_id_homologacao": "1234567"}, t, esperar_erro=True)
checar("idToken com mais de 6 dígitos é recusado", ruim.get("_status") == 400,
       str(ruim.get("detail"))[:60])

# =========================================================================== #
print("\n=== 2. O XML do cupom ===")
from backend.database import SessionLocal            # noqa: E402
from backend.models import Nota                      # noqa: E402
from backend.routers.emissao import _montar          # noqa: E402
from backend import cupom as nfce                    # noqa: E402
from backend.routers.cupom import config_do_cupom    # noqa: E402


def montar_cupom(**extras):
    """Cria o cupom como rascunho 65 e monta o XML, sem falar com a SEFAZ."""
    corpo = {"empresa_id": eid, "ambiente": "2", "serie": "1",
             "natureza_operacao": "VENDA AO CONSUMIDOR",
             "itens": [{"produto_id": cafe["id"], "quantidade": 2,
                        "valor_unitario": 25, "cfop": "5102"}]}
    nota_id = api("POST", "/api/nfe/rascunho", corpo, t)["nota"]["id"]
    db = SessionLocal()
    try:
        nota = db.get(Nota, nota_id)
        nota.modelo = "65"
        for campo, valor in extras.items():
            setattr(nota, campo, valor)
        db.commit()
        inf, chave, total = _montar(db, nota, 1)
        config = config_do_cupom(db, eid)
        csc, csc_id = nfce.csc_do_ambiente(config, "2")
    finally:
        db.close()
    supl = nfce.bloco_suplementar(chave, "2", csc, csc_id, "MG")
    return f'<NFe xmlns="{NS}">{inf}{supl}</NFe>', chave, total


def validar(xml):
    esquema.validate(etree.fromstring(xml.encode()))
    return [e.message for e in esquema.error_log if "Signature" not in e.message]


xml, chave, total = montar_cupom()
problemas = validar(xml)
checar("o cupom passa no schema oficial 4.00", not problemas,
       problemas[0][:120] if problemas else "")
checar("a chave leva o modelo 65", chave[20:22] == "65", chave[20:22])
checar("modelo 65 no XML", "<mod>65</mod>" in xml)
checar("tpImp 4 — é o cupom estreito, não a DANFE retrato", "<tpImp>4</tpImp>" in xml)
checar("indPres 1 — venda presencial", "<indPres>1</indPres>" in xml)
checar("indFinal 1 — consumidor final", "<indFinal>1</indFinal>" in xml)
checar("idDest 1 — operação dentro do estado", "<idDest>1</idDest>" in xml)
checar("não leva indIntermed (só a venda não presencial leva)",
       "<indIntermed>" not in xml)
checar("sem CPF não sai bloco de destinatário", "<dest>" not in xml)
checar("o cupom não leva duplicatas", "<cobr>" not in xml and "<dup>" not in xml)
checar("e leva o grupo de pagamento", "<pag>" in xml and "<detPag>" in xml)

print("\n--- o QR Code")
supl = re.search(r"<infNFeSupl>.*?</infNFeSupl>", xml, re.S).group(0)
checar("o infNFeSupl vem depois do infNFe",
       xml.index("</infNFe>") < xml.index("<infNFeSupl>"))
qr = re.search(r"<qrCode>(.*?)</qrCode>", supl, re.S).group(1)
checar("o QR Code aponta para o portal da SEFAZ-MG",
       qr.startswith("https://portalsped.fazenda.mg.gov.br"), qr[:50])
partes = qr.split("?p=")[1].split("|")
checar("o parâmetro p tem chave, versão 2, ambiente, idToken e hash",
       len(partes) == 5 and partes[0] == chave and partes[1] == "2"
       and partes[2] == "2" and partes[3] == "1", str(partes[:4]))
# a conta refeita à mão, sem usar o código do sistema
esperado = hashlib.sha1(f"{chave}|2|2|1{CSC}".encode()).hexdigest().upper()
checar("o hash bate com o SHA-1 da chave com o CSC colado no fim",
       partes[4] == esperado, f"{partes[4][:12]}... x {esperado[:12]}...")
checar("o CSC NÃO aparece no XML — só o hash", CSC not in xml)
checar("o urlChave é o de homologação",
       "hportalsped" in re.search(r"<urlChave>(.*?)</urlChave>", supl).group(1))

print("\n--- consumidor e troco")
com_cpf, _chave2, _t2 = montar_cupom(consumidor_documento="11144477735",
                                     consumidor_nome="JOAO DA SILVA", troco=15)
checar("com CPF sai o bloco de destinatário", "<dest>" in com_cpf)
checar("com o CPF dentro", "<CPF>11144477735</CPF>" in com_cpf)
checar("sem endereço — o cupom não exige", "<enderDest>" not in com_cpf)
checar("como não contribuinte (indIEDest 9)", "<indIEDest>9</indIEDest>" in com_cpf)
checar("em homologação o nome vira o aviso da SEFAZ",
       "HOMOLOGACAO" in com_cpf and "JOAO DA SILVA" not in com_cpf)
checar("o troco entra no grupo de pagamento", "<vTroco>15.00</vTroco>" in com_cpf)
checar("e o cupom com CPF continua válido no schema", not validar(com_cpf),
       (validar(com_cpf) or [""])[0][:120])

documento_ruim = api("POST", "/api/cupom/venda", {
    "empresa_id": eid, "ambiente": "2", "consumidor_documento": "123",
    "itens": [{"produto_id": cafe["id"], "quantidade": 1, "valor_unitario": 10}]},
    t, esperar_erro=True)
checar("CPF pela metade é recusado com frase clara",
       documento_ruim.get("_status") == 400
       and "incompleto" in str(documento_ruim.get("detail", "")),
       str(documento_ruim.get("detail"))[:70])

# =========================================================================== #
print("\n=== 3. Numeração separada da nota fiscal ===")
db = SessionLocal()
try:
    from backend.routers.emissao import _reservar_numero    # noqa: E402
    n1 = _reservar_numero(db, eid, "1", "2", modelo="65")
    n2 = _reservar_numero(db, eid, "1", "2", modelo="65")
    nota_numero = _reservar_numero(db, eid, "1", "2", modelo="55")
    db.commit()
finally:
    db.close()
checar("o cupom tem a própria sequência", n2 == n1 + 1, f"{n1} -> {n2}")
checar("e a nota fiscal continua na dela", nota_numero == 1, str(nota_numero))

# =========================================================================== #
print("\n=== 4. O cupom impresso ===")
autorizado = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "ambiente": "2", "serie": "1",
    "natureza_operacao": "VENDA AO CONSUMIDOR",
    "itens": [{"produto_id": cafe["id"], "quantidade": 3, "valor_unitario": 18,
               "cfop": "5102"}]}, t)["nota"]["id"]
db = SessionLocal()
try:
    nota = db.get(Nota, autorizado)
    nota.modelo = "65"
    nota.consumidor_documento = "11144477735"
    from backend.models import NotaPagamento                # noqa: E402
    nota.pagamentos.append(NotaPagamento(origem="PAGAMENTO", codigo="01",
                                         descricao="Dinheiro", valor=60))
    nota.troco = 6
    db.commit()
    inf, chave_imp, _total = _montar(db, nota, 7)
    csc, csc_id = nfce.csc_do_ambiente(config_do_cupom(db, eid), "2")
    supl = nfce.bloco_suplementar(chave_imp, "2", csc, csc_id, "MG")
    nota.numero = "7"
    nota.chave = chave_imp
    nota.status_emissao = "AUTORIZADA"
    nota.situacao = "AUTORIZADA"
    nota.protocolo = "131260000000007"
    nota.xml = ('<?xml version="1.0" encoding="UTF-8"?>'
                f'<nfeProc xmlns="{NS}" versao="4.00"><NFe>{inf}{supl}</NFe>'
                f'<protNFe versao="4.00"><infProt><chNFe>{chave_imp}</chNFe>'
                '<dhRecbto>2026-09-24T10:00:00-03:00</dhRecbto>'
                '<nProt>131260000000007</nProt><cStat>100</cStat>'
                '<xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe></nfeProc>')
    db.commit()
finally:
    db.close()

folha = pagina(f"/api/cupom/{autorizado}/impressao", t)
checar("a folha diz o que é", "DANFE NFC-e" in folha
       and "Nota Fiscal de Consumidor Eletronica" in folha)
checar("sai no tamanho da bobina de 80 mm", "size: 80mm auto" in folha)
checar("avisa que é homologação, sem valor fiscal",
       "SEM VALOR FISCAL" in folha)
checar("traz o item vendido", "CAFE" in folha.upper())
checar("o total da venda", "54,00" in folha, "3 x 18,00")
checar("a forma de pagamento e o troco",
       "Dinheiro" in folha and "6,00" in folha)
checar("a chave de acesso para digitar", chave_imp[:12] in folha.replace(" ", ""))
checar("o QR Code desenhado", "<svg" in folha and "</svg>" in folha)
checar("e o consumidor identificado", "CONSUMIDOR" in folha)
checar("com o protocolo de autorização", "131260000000007" in folha)

saida = pathlib.Path(__file__).parent / "capturas"
saida.mkdir(exist_ok=True)
(saida / "cupom.html").write_text(folha, encoding="utf-8")
print(f"      (cupom gravado em {saida / 'cupom.html'})")

# =========================================================================== #
print("\n=== 5. Limites e recusas ===")
prazo = api("GET", f"/api/cupom/{autorizado}", None, t)["cupom"]
checar("o cupom sabe dizer se ainda dá para cancelar",
       "pode_cancelar" in prazo and "motivo_nao_cancela" in prazo)

outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outrocupom{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra"})
alheio = api("GET", f"/api/cupom/config?empresa_id={eid}", None,
             outra["token"], esperar_erro=True)
checar("outra conta não enxerga o CSC", alheio.get("_status") in (403, 404),
       str(alheio.get("_status")))
espiada = api("GET", f"/api/cupom/{autorizado}", None, outra["token"],
              esperar_erro=True)
checar("nem o cupom", espiada.get("_status") in (403, 404))

sem_itens = api("POST", "/api/cupom/venda",
                {"empresa_id": eid, "ambiente": "2", "itens": []}, t, esperar_erro=True)
checar("venda sem itens é recusada", sem_itens.get("_status") == 400,
       str(sem_itens.get("detail"))[:60])
pouco = api("POST", "/api/cupom/venda", {
    "empresa_id": eid, "ambiente": "2",
    "itens": [{"produto_id": cafe["id"], "quantidade": 1, "valor_unitario": 100}],
    "pagamentos": [{"codigo": "01", "valor": 10}]}, t, esperar_erro=True)
checar("pagamento menor que o total é recusado",
       pouco.get("_status") == 400 and "menor" in str(pouco.get("detail", "")),
       str(pouco.get("detail"))[:70])

try:
    nfce.url_autorizacao("SP", "2")
    checar("UF sem cupom avisa", False, "não avisou")
except nfce.ErroCupom as erro:
    checar("UF sem cupom avisa com a lista do que dá", "MG" in str(erro),
           str(erro)[:70])

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S): " + "; ".join(erros))
    sys.exit(1)
print("Cupom fiscal OK — modelo 65 válido no schema, com QR Code conferido.")
