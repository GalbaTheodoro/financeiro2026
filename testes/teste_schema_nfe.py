"""Valida o XML da NF-e contra o schema oficial 4.00, antes de qualquer SEFAZ.

Por que existe
--------------
A SEFAZ devolve "Rejeição 225: Falha no Schema XML do lote de NFe" sem dizer qual
campo está errado — e cada tentativa dessas custa tempo. O schema oficial está em
`testes/xsd/`, então dá para descobrir o campo aqui, no computador, em um segundo.

Foi assim que apareceu o erro de `dhEmi` com fração de segundo
("2026-09-19T21:48:18.609636-03:00"): o schema aceita só até o segundo.

Uso:  python testes/teste_schema_nfe.py   (com o servidor no ar)
"""
import json
import pathlib
import re
import sys
import time
import urllib.request
from datetime import date

try:
    from lxml import etree
except ImportError:                                  # pragma: no cover
    print("Este teste precisa do lxml (só para validar o schema; o sistema não usa).")
    print("Instale com:  pip install lxml")
    sys.exit(0)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8000"
XSD = pathlib.Path(__file__).parent / "xsd" / "nfe_v4.00.xsd"
NS = "http://www.portalfiscal.inf.br/nfe"
erros = []


def api(metodo, caminho, dados=None, token=None):
    req = urllib.request.Request(
        f"{BASE}{caminho}",
        data=json.dumps(dados).encode() if dados is not None else None,
        method=metodo,
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"{}")


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


esquema = etree.XMLSchema(etree.parse(str(XSD)))


def validar(inf_nfe: str) -> list[str]:
    """Devolve a lista de problemas do schema (a assinatura é ignorada aqui)."""
    documento = etree.fromstring(f'<NFe xmlns="{NS}">{inf_nfe}</NFe>'.encode())
    esquema.validate(documento)
    return [f"{e.message}" for e in esquema.error_log if "Signature" not in e.message]


# =========================================================================== #
print("=== Preparando uma nota de verdade ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"schema{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock"})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "inscricao_estadual": "0022334455001", "logradouro": "AVENIDA FARIA PEREIRA",
    "numero": "1250", "complemento": "SALA 3", "bairro": "CENTRO",
    "cidade": "Patrocínio", "uf": "MG", "cep": "38740108",
    "codigo_municipio": "3148004", "crt": "1", "telefone": "3439999999"}, t)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, t)
cafe = api("GET", f"/api/produtos?empresa_id={eid}", None, t)[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: v for k, v in cafe.items() if k in ("codigo", "nome", "unidade_id",
                                              "embalagem", "descricao")},
    "empresa_id": eid, "ncm": "09011110", "cfop_padrao": "6102", "cst_icms": "102",
    "unidade_comercial": "SC", "origem": "0", "ativo": True}, t)
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "11444777000161", "rg_ie": "123456789", "indicador_ie": "1",
    "logradouro": "RUA DO CAFE", "numero": "500", "complemento": "GALPAO 2",
    "bairro": "CENTRO", "cidade": "Santos", "uf": "SP", "cep": "11010000",
    "codigo_municipio": "3548500", "email": "fiscal@torrefacao.com.br"}, t)
api("POST", "/api/nfe/series",
    {"empresa_id": eid, "serie": "1", "ambiente": "2", "proximo_numero": 1}, t)

from backend.database import SessionLocal          # noqa: E402
from backend.models import Nota                    # noqa: E402
from backend.routers.emissao import _montar        # noqa: E402


def montar(**extras):
    corpo = {"empresa_id": eid, "parceiro_id": cliente["id"], "ambiente": "2",
             "serie": "1", "itens": [{"produto_id": cafe["id"], "quantidade": 100,
                                      "valor_unitario": 1000}]}
    corpo.update(extras)
    nota_id = api("POST", "/api/nfe/rascunho", corpo, t)["nota"]["id"]
    db = SessionLocal()
    try:
        inf, _chave, _total = _montar(db, db.get(Nota, nota_id), 1)
    finally:
        db.close()
    return inf


# =========================================================================== #
print("\n=== 1. A nota simples passa no schema oficial ===")
simples = montar()
problemas = validar(simples)
checar("nota com um item passa no schema 4.00", not problemas,
       problemas[0][:120] if problemas else "")

print("\n=== 2. A nota completa (transporte, duplicatas e observações) ===")
completa = montar(frete_modalidade="1", peso_bruto=6050, peso_liquido=6000,
                  volumes=100, especie_volume="SACAS",
                  placa_veiculo="ABC1D23", uf_veiculo="MG",
                  informacoes_complementares="Contrato 4587 — cafe bica corrida",
                  parcelas=[{"vencimento": "2026-10-19", "valor": 50000},
                            {"vencimento": "2026-11-19", "valor": 50000}])
problemas = validar(completa)
checar("nota com transporte e duplicatas passa no schema", not problemas,
       problemas[0][:120] if problemas else "")
checar("as duas duplicatas entraram no XML", completa.count("<dup>") == 2)
checar("o transporte entrou com placa e volumes",
       "<placa>ABC1D23</placa>" in completa.replace(" ", "")
       or "ABC1D23" in completa)

print("\n=== 3. Notas que já quebraram antes ===")
# data de emissão escolhida na tela (o bug do dhEmi com fração de segundo)
com_data = montar(data_emissao=str(date.today()))
problemas = validar(com_data)
checar("data de emissão escolhida na tela não quebra o schema", not problemas,
       problemas[0][:140] if problemas else "")
momento = re.search(r"<dhEmi>([^<]+)</dhEmi>", com_data).group(1)
checar("dhEmi vai até o segundo, sem fração", "." not in momento, momento)

# a prova ao contrário: com fração de segundo o schema reprova
quebrado = re.sub(r"(<dhEmi>[^<]+?)(-03:00)", r"\g<1>.123456\g<2>", com_data)
checar("e com fração de segundo o schema reprovaria (é a rejeição 225)",
       any("dhEmi" in p for p in validar(quebrado)))

# nome comprido, acento e símbolo no texto livre
longo = montar(natureza_operacao="VENDA DE CAFÉ ARÁBICA — SAFRA 2026/2027 & COMISSÃO",
               informacoes_complementares="Observação com acento, & e <sinais>. " * 20)
problemas = validar(longo)
checar("acento, & e sinais no texto livre não quebram o schema", not problemas,
       problemas[0][:140] if problemas else "")

print("\n=== 4. Regime normal e o diferimento do café (CST 51) ===")
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "inscricao_estadual": "0022334455001", "logradouro": "AVENIDA FARIA PEREIRA",
    "numero": "1250", "bairro": "CENTRO", "cidade": "Patrocínio", "uf": "MG",
    "cep": "38740108", "codigo_municipio": "3148004", "crt": "3"}, t)
for cst, rotulo in (("00", "tributada integralmente"), ("20", "com redução de base"),
                    ("51", "diferimento (café em MG)"), ("40", "isenta"),
                    ("60", "ICMS já cobrado por substituição")):
    xml_cst = montar(itens=[{"produto_id": cafe["id"], "quantidade": 100,
                             "valor_unitario": 1000, "icms_cst": cst,
                             "icms_aliquota": 18, "icms_reducao": 30 if cst == "20" else 0}])
    problemas = validar(xml_cst)
    checar(f"CST {cst} — {rotulo}", not problemas,
           problemas[0][:120] if problemas else "")

print("\n=== 5. O XML assinado (é ele que vai para a SEFAZ) ===")
from backend import emissao as nfe                 # noqa: E402
from cryptography import x509                      # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa         # noqa: E402
from cryptography.x509.oid import NameOID          # noqa: E402
from datetime import datetime, timedelta           # noqa: E402

chave_rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ASSESSORIA AGRODOCK LTDA")])
certificado = (
    x509.CertificateBuilder()
    .subject_name(nome).issuer_name(nome).public_key(chave_rsa.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.utcnow() - timedelta(days=1))
    .not_valid_after(datetime.utcnow() + timedelta(days=365))
    .sign(chave_rsa, hashes.SHA256())
)
assinada = nfe.assinar_nfe(simples, chave_rsa, certificado)
documento = etree.fromstring(assinada.encode())
esquema.validate(documento)
problemas = [e.message for e in esquema.error_log]
checar("a nota assinada passa no schema, assinatura incluída", not problemas,
       problemas[0][:140] if problemas else "")
checar("a assinatura aponta para o Id da nota",
       f'URI="#NFe' in assinada and "<Signature" in assinada)

print("\n=== 6. O lote inteiro, do jeito que vai para a SEFAZ ===")
lote = nfe.montar_lote(assinada, 1)
checar("o lote sai com idLote e indSinc=1",
       "<idLote>1</idLote>" in lote and "<indSinc>1</indSinc>" in lote)
checar("e o lote leva a nota inteira dentro", "<infNFe" in lote)

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} falha(s): " + "; ".join(erros))
    sys.exit(1)
print("Schema da NF-e OK — o XML passa na validação oficial 4.00.")
