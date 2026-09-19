"""Teste da emissão de NF-e — sem tocar na SEFAZ.

Parte 1 (motor, backend/emissao.py):
  * dígito e composição da chave de acesso;
  * XML no layout 4.00: ordem dos blocos, ide, emit, dest, det, total, transp, cobr, pag;
  * ICMS conforme o regime: CSOSN no Simples, CST no regime normal, diferimento (51);
  * homologação troca o nome do destinatário e a descrição do primeiro item;
  * assinatura conferida com a chave pública do certificado de teste;
  * leitura do retorno de autorização (autorizada, rejeitada e denegada) e do nfeProc;
  * as validações que barram a nota antes de sair (sem NCM, sem IE, CPF incompleto).

Parte 2 (com o servidor no ar): série e numeração, rascunho a partir de contrato de
venda, edição, prévia da DANFE, transmissão barrada sem certificado e exclusão.

Uso (com o servidor em http://127.0.0.1:8000):  python testes/teste_emissao.py
"""
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

BASE = os.getenv("FIN_BASE", "http://127.0.0.1:8000")
falhas = []


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


def api(metodo, caminho, dados=None, token=None, esperar_erro=False, bruto=False):
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
            corpo = r.read()
            return corpo.decode("utf-8", "replace") if bruto else json.loads(corpo or b"{}")
    except urllib.error.HTTPError as e:
        corpo = e.read()
        if esperar_erro:
            try:
                return {"_status": e.code, "_detalhe": json.loads(corpo or b"{}").get("detail", "")}
            except json.JSONDecodeError:
                return {"_status": e.code, "_detalhe": corpo.decode("utf-8", "replace")[:200]}
        raise AssertionError(f"{metodo} {caminho} -> HTTP {e.code}: {corpo[:300]}") from None


# =========================================================================== #
print("\n=== 1. Chave de acesso ===")
from backend import emissao as nfe  # noqa: E402
from backend import dfe as motor  # noqa: E402

NS = f"{{{nfe.NS}}}"
emissao_em = datetime(2026, 9, 19, 10, 30, tzinfo=motor.FUSO_BR)
chave = nfe.montar_chave("MG", emissao_em, "98765432000198", "55", "1", 45, 87654321)
checar("chave com 44 números", len(chave) == 44 and chave.isdigit(), chave)
checar("chave começa com o código de MG e o ano/mês", chave.startswith("312609"), chave[:6])
checar("CNPJ, modelo, série e número na posição certa",
       chave[6:20] == "98765432000198" and chave[20:22] == "55"
       and chave[22:25] == "001" and chave[25:34] == "000000045", chave[6:34])
checar("dígito verificador confere", nfe.digito_chave(chave[:43]) == chave[43])
checar("mudar um número muda o dígito",
       nfe.digito_chave("1" + chave[1:43]) != chave[43] or chave[0] == "1")

# =========================================================================== #
print("\n=== 2. XML da nota ===")


def empresa_teste(crt="1"):
    return SimpleNamespace(
        razao_social="ASSESSORIA AGRODOCK LTDA", nome_fantasia="AgroDock",
        cnpj="98.765.432/0001-98", inscricao_estadual="0022334455001",
        logradouro="AVENIDA FARIA PEREIRA", numero="1250", complemento="SALA 4",
        bairro="CENTRO", cidade="PATROCÍNIO", uf="MG", cep="38740-108",
        telefone="(34) 3831-8899", codigo_municipio="3148004", codigo_pais="1058",
        pais="BRASIL", crt=crt, texto_nota=None,
    )


def cliente_teste(**kw):
    dados = dict(
        nome="TORREFAÇÃO PAULISTA LTDA", cpf_cnpj="33.444.555/0001-66",
        rg_ie="123456789", indicador_ie="1", logradouro="RUA DO CAFE", numero="500",
        complemento=None, bairro="CENTRO", cidade="SANTOS", uf="SP", cep="11010-000",
        codigo_municipio="3548500", codigo_pais="1058", pais="BRASIL",
        telefone="1333334444", celular=None, email="compras@torrefacao.com.br",
    )
    dados.update(kw)
    return SimpleNamespace(**dados)


def item_teste(**kw):
    dados = dict(
        numero=1, codigo="CAF001", gtin="", descricao="CAFE CRU EM GRAO ARABICA TIPO 6/7",
        ncm="09011110", cest=None, cfop="6101", unidade="SC", quantidade=330,
        valor_unitario=1320, valor_total=435600, desconto=0, frete=0,
        icms_cst="102", icms_base=435600, icms_aliquota=0, icms_valor=0, icms_reducao=0,
        origem_mercadoria="0", cst_pis=None, aliquota_pis=0, pis_valor=0,
        cst_cofins=None, aliquota_cofins=0, cofins_valor=0, cst_ipi=None,
        aliquota_ipi=0, ipi_valor=0,
    )
    dados.update(kw)
    return SimpleNamespace(**dados)


cabecalho = {
    "natureza_operacao": "VENDA DE MERCADORIA", "tipo_operacao": "1", "finalidade": "1",
    "consumidor_final": "0", "presenca": "9", "ambiente": "1", "destinatario_uf": "SP",
    "frete_modalidade": "1", "placa_veiculo": "HAB-1C23", "uf_veiculo": "MG",
    "volumes": 330, "especie_volume": "SACAS", "peso_liquido": 19800, "peso_bruto": 19965,
    "informacoes_complementares": "Contrato 2026/118. Café com umidade de 11,5%.",
}
duplicatas = [
    SimpleNamespace(numero="001", vencimento=date(2026, 10, 19), valor=217800),
    SimpleNamespace(numero="002", vencimento=date(2026, 11, 19), valor=217800),
]
pagamentos = [SimpleNamespace(origem="PAGAMENTO", codigo="15", valor=435600)]

inf, chave_nota, total = nfe.montar_nfe(
    empresa_teste(), cabecalho, [item_teste()], cliente_teste(), None,
    duplicatas, pagamentos, 45, "1", emissao_em)

checar("XML abre com infNFe, Id e versão 4.00",
       inf.startswith(f'<infNFe xmlns="{nfe.NS}" Id="NFe{chave_nota}" versao="4.00">'),
       inf[:70])
checar("valor total bate com os itens", total == 435600.0, str(total))

raiz = ET.fromstring(inf)
ordem = [filho.tag.split("}")[-1] for filho in raiz]
checar("blocos na ordem que o schema exige",
       ordem == ["ide", "emit", "dest", "det", "total", "transp", "cobr", "pag", "infAdic"],
       str(ordem))

ide = raiz.find(f"{NS}ide")
checar("ide: cUF de MG, modelo 55, série e número",
       ide.findtext(f"{NS}cUF") == "31" and ide.findtext(f"{NS}mod") == "55"
       and ide.findtext(f"{NS}serie") == "1" and ide.findtext(f"{NS}nNF") == "45")
checar("ide: operação interestadual (idDest = 2)", ide.findtext(f"{NS}idDest") == "2")
checar("ide: dígito verificador igual ao da chave",
       ide.findtext(f"{NS}cDV") == chave_nota[-1])
checar("ide: ambiente de produção e finalidade normal",
       ide.findtext(f"{NS}tpAmb") == "1" and ide.findtext(f"{NS}finNFe") == "1")

emit = raiz.find(f"{NS}emit")
checar("emit: CNPJ só com números e sem acento no nome",
       emit.findtext(f"{NS}CNPJ") == "98765432000198"
       and emit.find(f"{NS}enderEmit").findtext(f"{NS}xMun") == "PATROCINIO",
       emit.find(f"{NS}enderEmit").findtext(f"{NS}xMun"))
checar("emit: CRT do Simples Nacional", emit.findtext(f"{NS}CRT") == "1")

dest = raiz.find(f"{NS}dest")
checar("dest: CNPJ, indicador de IE e a inscrição",
       dest.findtext(f"{NS}CNPJ") == "33444555000166"
       and dest.findtext(f"{NS}indIEDest") == "1"
       and dest.findtext(f"{NS}IE") == "123456789")
checar("dest: código do município do IBGE",
       dest.find(f"{NS}enderDest").findtext(f"{NS}cMun") == "3548500")

det = raiz.find(f"{NS}det")
prod = det.find(f"{NS}prod")
checar("det: item 1 com NCM, CFOP e 'SEM GTIN' quando não tem código de barras",
       det.get("nItem") == "1" and prod.findtext(f"{NS}NCM") == "09011110"
       and prod.findtext(f"{NS}CFOP") == "6101" and prod.findtext(f"{NS}cEAN") == "SEM GTIN")
checar("det: quantidade com 4 casas e unitário com 10",
       prod.findtext(f"{NS}qCom") == "330.0000"
       and prod.findtext(f"{NS}vUnCom") == "1320.0000000000",
       prod.findtext(f"{NS}vUnCom"))
icmssn = det.find(f".//{NS}ICMSSN102")
checar("Simples Nacional usa CSOSN (ICMSSN102)", icmssn is not None
       and icmssn.findtext(f"{NS}CSOSN") == "102")
checar("Simples: PIS e COFINS saem como 'outras' (CST 49)",
       det.find(f".//{NS}PISOutr") is not None
       and det.find(f".//{NS}PISOutr").findtext(f"{NS}CST") == "49")

total_xml = raiz.find(f".//{NS}ICMSTot")
checar("total: vProd e vNF batem", total_xml.findtext(f"{NS}vProd") == "435600.00"
       and total_xml.findtext(f"{NS}vNF") == "435600.00")

transp = raiz.find(f"{NS}transp")
checar("transp: modalidade, placa sem traço e volumes",
       transp.findtext(f"{NS}modFrete") == "1"
       and transp.find(f"{NS}veicTransp").findtext(f"{NS}placa") == "HAB1C23"
       and transp.find(f"{NS}vol").findtext(f"{NS}qVol") == "330")

cobr = raiz.find(f"{NS}cobr")
checar("cobr: duas duplicatas com vencimento e valor",
       len(cobr.findall(f"{NS}dup")) == 2
       and cobr.findall(f"{NS}dup")[0].findtext(f"{NS}dVenc") == "2026-10-19")
checar("pag: forma de pagamento da nota",
       raiz.find(f".//{NS}detPag").findtext(f"{NS}tPag") == "15")
checar("infAdic: informações complementares sem acento",
       "umidade de 11,5%" in raiz.find(f".//{NS}infCpl").text)

print("\n=== 3. Regime normal e diferimento ===")
inf_normal, _c, _t = nfe.montar_nfe(
    empresa_teste(crt="3"), cabecalho,
    [item_teste(icms_cst="00", icms_aliquota=12, icms_valor=52272)], cliente_teste(), None,
    [], [], 46, "1", emissao_em)
raiz_normal = ET.fromstring(inf_normal)
icms00 = raiz_normal.find(f".//{NS}ICMS00")
checar("regime normal usa CST (ICMS00) com base e valor",
       icms00 is not None and icms00.findtext(f"{NS}CST") == "00"
       and icms00.findtext(f"{NS}vICMS") == "52272.00")
checar("total do ICMS entra no ICMSTot",
       raiz_normal.find(f".//{NS}ICMSTot").findtext(f"{NS}vICMS") == "52272.00")

inf_dif, _c, _t = nfe.montar_nfe(
    empresa_teste(crt="3"), cabecalho,
    [item_teste(icms_cst="51", icms_aliquota=12, icms_valor=0)], cliente_teste(), None,
    [], [], 47, "1", emissao_em)
icms51 = ET.fromstring(inf_dif).find(f".//{NS}ICMS51")
checar("diferimento (CST 51) com 100% diferido e ICMS zero",
       icms51 is not None and icms51.findtext(f"{NS}pDif") == "100.0000"
       and icms51.findtext(f"{NS}vICMS") == "0.00"
       and icms51.findtext(f"{NS}vICMSDif") == "52272.00",
       icms51.findtext(f"{NS}vICMSDif") if icms51 is not None else "")

print("\n=== 4. Homologação ===")
inf_homo, _c, _t = nfe.montar_nfe(
    empresa_teste(), {**cabecalho, "ambiente": "2"}, [item_teste()], cliente_teste(), None,
    [], [], 48, "1", emissao_em)
raiz_homo = ET.fromstring(inf_homo)
checar("homologação: nome do destinatário é o aviso da SEFAZ",
       raiz_homo.find(f"{NS}dest").findtext(f"{NS}xNome")
       == "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL")
checar("homologação: primeiro item também leva o aviso",
       "HOMOLOGACAO" in raiz_homo.find(f".//{NS}xProd").text)
checar("homologação: tpAmb = 2", raiz_homo.find(f"{NS}ide").findtext(f"{NS}tpAmb") == "2")

print("\n=== 5. O que barra a nota antes de sair ===")


def recusa(descricao, **kw):
    try:
        nfe.montar_nfe(kw.get("empresa", empresa_teste()), kw.get("cabecalho", cabecalho),
                       kw.get("itens", [item_teste()]), kw.get("cliente", cliente_teste()),
                       None, [], [], 50, "1", emissao_em)
    except nfe.ErroEmissao as erro:
        checar(descricao, True, str(erro)[:60])
        return
    checar(descricao, False, "passou sem reclamar")


recusa("item sem NCM é barrado", itens=[item_teste(ncm=None)])
recusa("item sem CFOP é barrado", itens=[item_teste(cfop=None)])
recusa("nota sem itens é barrada", itens=[])
recusa("cliente com CPF/CNPJ incompleto é barrado", cliente=cliente_teste(cpf_cnpj="123"))
recusa("cliente sem código do município é barrado", cliente=cliente_teste(codigo_municipio=None))
recusa("contribuinte de ICMS sem inscrição estadual é barrado",
       cliente=cliente_teste(rg_ie=None, indicador_ie="1"))
empresa_sem_ie = empresa_teste()
empresa_sem_ie.inscricao_estadual = ""
recusa("empresa sem inscrição estadual é barrada", empresa=empresa_sem_ie)
empresa_sem_ibge = empresa_teste()
empresa_sem_ibge.codigo_municipio = ""
recusa("empresa sem código do município é barrada", empresa=empresa_sem_ibge)

print("\n=== 6. Assinatura ===")
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

chave_rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
titular = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AGRODOCK:98765432000198")])
agora = datetime.now(timezone.utc)
certificado = (
    x509.CertificateBuilder().subject_name(titular).issuer_name(titular)
    .public_key(chave_rsa.public_key()).serial_number(x509.random_serial_number())
    .not_valid_before(agora - timedelta(days=1)).not_valid_after(agora + timedelta(days=200))
    .sign(chave_rsa, hashes.SHA256())
)

assinada = nfe.assinar_nfe(inf, chave_rsa, certificado)
checar("NFe assinada tem o infNFe e a assinatura",
       assinada.startswith(f'<NFe xmlns="{nfe.NS}">') and inf in assinada
       and "<SignatureValue>" in assinada)
resumo_esperado = base64.b64encode(hashlib.sha1(inf.encode()).digest()).decode()
checar("DigestValue é o SHA-1 do infNFe",
       re.search(r"<DigestValue>([^<]+)</DigestValue>", assinada).group(1) == resumo_esperado)
checar("Reference aponta para o Id da nota",
       f'URI="#NFe{chave_nota}"' in assinada)
assinado = re.search(r"(<SignedInfo.*?</SignedInfo>)", assinada, re.S).group(1)
valor = base64.b64decode(
    re.search(r"<SignatureValue>([^<]+)</SignatureValue>", assinada).group(1))
confere = True
try:
    certificado.public_key().verify(valor, assinado.encode(), padding.PKCS1v15(), hashes.SHA1())
except Exception:  # noqa: BLE001
    confere = False
checar("assinatura RSA-SHA1 confere com o certificado", confere)

lote = nfe.montar_lote(assinada)
checar("lote síncrono (indSinc = 1) com a nota dentro",
       "<indSinc>1</indSinc>" in lote and assinada in lote and lote.startswith("<enviNFe"))

print("\n=== 7. Retorno da SEFAZ ===")
RETORNO_OK = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body>
<nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">
<retEnviNFe xmlns="{nfe.NS}" versao="4.00">
<tpAmb>1</tpAmb><verAplic>MG_v4</verAplic><cStat>104</cStat>
<xMotivo>Lote processado</xMotivo><cUF>31</cUF><dhRecbto>2026-09-19T10:31:00-03:00</dhRecbto>
<protNFe versao="4.00"><infProt><tpAmb>1</tpAmb><verAplic>MG_v4</verAplic>
<chNFe>{chave_nota}</chNFe><dhRecbto>2026-09-19T10:31:05-03:00</dhRecbto>
<nProt>131260099887766</nProt><digVal>abc</digVal><cStat>100</cStat>
<xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe>
</retEnviNFe></nfeResultMsg></soap:Body></soap:Envelope>"""

retorno = nfe.ler_retorno_autorizacao(RETORNO_OK, assinada)
checar("retorno 100 = autorizada, com protocolo",
       retorno["autorizada"] and retorno["codigo"] == "100"
       and retorno["protocolo"] == "131260099887766")
checar("nfeProc montado com a nota e o protocolo",
       retorno["xml"].startswith('<?xml') and "<nfeProc" in retorno["xml"]
       and "<protNFe" in retorno["xml"] and f"NFe{chave_nota}" in retorno["xml"])
lido = motor.ler_documento(retorno["xml"], "procNFe_v4.00")
checar("o nfeProc gerado é lido de volta pelo próprio sistema",
       lido is not None and lido["chave"] == chave_nota
       and lido["valor_total"] == 435600.0 and len(lido["itens"]) == 1,
       str(lido["chave"]) if lido else "não leu")
from backend import danfe  # noqa: E402

folha = danfe.gerar(retorno["xml"], "ASSESSORIA AGRODOCK LTDA")
checar("a DANFE sai do XML autorizado",
       "DANFE" in folha and "131260099887766" in folha and "CAFE CRU" in folha)

RETORNO_REJEITA = RETORNO_OK.replace(
    "<cStat>100</cStat>", "<cStat>539</cStat>").replace(
    "<xMotivo>Autorizado o uso da NF-e</xMotivo>",
    "<xMotivo>Rejeicao: Duplicidade de NF-e</xMotivo>")
rejeitada = nfe.ler_retorno_autorizacao(RETORNO_REJEITA, assinada)
checar("rejeição é reconhecida e traz o motivo",
       not rejeitada["autorizada"] and rejeitada["codigo"] == "539"
       and "Duplicidade" in rejeitada["mensagem"] and not rejeitada["xml"])
RETORNO_DENEGA = RETORNO_OK.replace("<cStat>100</cStat>", "<cStat>302</cStat>")
denegada = nfe.ler_retorno_autorizacao(RETORNO_DENEGA, assinada)
checar("denegação é separada da rejeição comum",
       not denegada["autorizada"] and denegada["denegada"])

print("\n=== 8. Endereços dos webservices ===")
checar("MG tem endereço próprio de autorização",
       "fazenda.mg.gov.br" in nfe._endereco(nfe.AUTORIZACAO, "MG", "1")
       and "hnfe" in nfe._endereco(nfe.AUTORIZACAO, "MG", "2"))
checar("estado sem servidor próprio cai no SVRS",
       "svrs.rs.gov.br" in nfe._endereco(nfe.AUTORIZACAO, "TO", "1"))
checar("evento de cancelamento também tem endereço por UF",
       "fazenda.mg.gov.br" in nfe._endereco(nfe.EVENTO, "MG", "1"))

print("\n=== 9. Cancelamento (montagem) ===")
sem_justificativa = None
try:
    nfe.cancelar(chave_rsa, certificado, [], "MG", "2", chave_nota, "98765432000198",
                 "131260099887766", "curta")
except nfe.ErroEmissao as erro:
    sem_justificativa = str(erro)
checar("cancelamento exige justificativa de 15 letras", bool(sem_justificativa),
       (sem_justificativa or "")[:50])
sem_protocolo = None
try:
    nfe.cancelar(chave_rsa, certificado, [], "MG", "2", chave_nota, "98765432000198",
                 "", "Cancelamento por acordo entre as partes")
except nfe.ErroEmissao as erro:
    sem_protocolo = str(erro)
checar("cancelamento exige o protocolo de autorização", bool(sem_protocolo))

# =========================================================================== #
print("\n=== 10. Pela API (com o servidor no ar) ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Emissor", "email": f"emissao{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock",
})
t, eid = conta["token"], conta["empresa"]["id"]

falta = api("GET", f"/api/nfe/preparo?empresa_id={eid}", None, t)
checar("preparo lista o que falta para emitir", falta["pronto"] is False
       and any("Inscrição estadual" in p for p in falta["pendencias"]),
       str(falta["pendencias"][:3]))

api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "inscricao_estadual": "0022334455001", "logradouro": "AVENIDA FARIA PEREIRA",
    "numero": "1250", "bairro": "CENTRO", "cidade": "Patrocínio", "uf": "MG",
    "cep": "38740108", "codigo_municipio": "3148004", "crt": "1",
}, t)
falta2 = api("GET", f"/api/nfe/preparo?empresa_id={eid}", None, t)
checar("depois de completar a empresa só falta o certificado",
       falta2["pendencias"] == ["Certificado digital A1 (aba Certificado do DF-e)"],
       str(falta2["pendencias"]))
checar("preparo mostra o regime da empresa", falta2["empresa"]["crt"] == "1"
       and "Simples" in falta2["empresa"]["crt_nome"])

print("\n--- série e numeração")
serie = api("POST", "/api/nfe/series", {"empresa_id": eid, "serie": "1", "ambiente": "2",
                                        "proximo_numero": 120, "descricao": "Testes"}, t)
checar("série criada começando no número informado",
       serie["proximo_numero"] == 120 and serie["ambiente"] == "2")
invalido = api("POST", "/api/nfe/series", {"empresa_id": eid, "serie": "1", "ambiente": "2",
                                           "proximo_numero": 0}, t, esperar_erro=True)
checar("número inicial inválido é recusado", invalido.get("_status") == 400)

print("\n--- rascunho a partir de um contrato de venda")
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "33444555000166", "rg_ie": "123456789", "indicador_ie": "1",
    "logradouro": "RUA DO CAFE", "numero": "500", "bairro": "CENTRO",
    "cidade": "Santos", "uf": "SP", "cep": "11010000", "codigo_municipio": "3548500"}, t)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, t)
produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe = produtos[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: v for k, v in cafe.items() if k in (
        "codigo", "nome", "unidade_id", "embalagem", "descricao")},
    "empresa_id": eid, "ncm": "09011110", "cfop_padrao": "6101", "cst_icms": "102",
    "unidade_comercial": "SC", "origem": "0", "ativo": True}, t)
unidades = api("GET", f"/api/unidades?empresa_id={eid}", None, t)
modalidades = api("GET", f"/api/modalidades?empresa_id={eid}", None, t)
contrato = api("POST", "/api/contratos", {
    "empresa_id": eid, "tipo": "VENDA", "comprador_id": cliente["id"],
    "produto_id": cafe["id"], "unidade_id": unidades[0]["id"],
    "modalidade_id": modalidades[0]["id"], "quantidade": 330, "preco_unitario": 1320}, t)

rascunho = api("POST", "/api/nfe/rascunho", {
    "empresa_id": eid, "contrato_id": contrato["id"], "ambiente": "2", "serie": "1",
    "frete_modalidade": "1", "peso_bruto": 19965, "volumes": 330,
    "especie_volume": "SACAS",
    "parcelas": [{"vencimento": "2026-10-19", "valor": 217800},
                 {"vencimento": "2026-11-19", "valor": 217800}]}, t)
nota = rascunho["nota"]
checar("rascunho puxou cliente, produto e valores do contrato",
       nota["status_emissao"] == "RASCUNHO" and nota["parceiro_nome"].startswith("TORREFACAO")
       and rascunho["itens"][0]["quantidade"] == 330
       and nota["valor_total"] == 435600.0, str(nota["valor_total"]))
checar("o item nasceu com os dados fiscais do produto",
       rascunho["itens"][0]["ncm"] == "09011110" and rascunho["itens"][0]["cfop"] == "6101"
       and rascunho["itens"][0]["icms_cst"] == "102")
checar("as duas parcelas viraram duplicatas", len(rascunho["parcelas"]) == 2)
checar("rascunho não gastou número da série",
       api("GET", f"/api/nfe/series?empresa_id={eid}", None, t)[0]["proximo_numero"] == 120)
checar("rascunho ainda não tem chave de acesso", nota["chave"].startswith("RASCUNHO"))

editado = api("PUT", f"/api/nfe/{nota['id']}", {
    "empresa_id": eid, "parceiro_id": cliente["id"], "serie": "1",
    "natureza_operacao": "VENDA DE CAFE", "informacoes_complementares": "Pedido 4587",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1300,
               "cfop": "6101"}]}, t)
checar("edição recalcula o total", editado["nota"]["valor_total"] == 130000.0
       and editado["nota"]["natureza_operacao"] == "VENDA DE CAFE",
       str(editado["nota"]["valor_total"]))

# o ambiente é escolha de quem emite: salvar não pode trocar sozinho
producao = api("PUT", f"/api/nfe/{nota['id']}", {
    "empresa_id": eid, "parceiro_id": cliente["id"], "serie": "1", "ambiente": "1",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1300,
               "cfop": "6101"}]}, t)
checar("salvar guarda o ambiente escolhido (produção)",
       producao["nota"]["ambiente"] == "1"
       and api("GET", f"/api/nfe/{nota['id']}", None, t)["nota"]["ambiente"] == "1",
       producao["nota"]["ambiente_nome"])
homologacao = api("PUT", f"/api/nfe/{nota['id']}", {
    "empresa_id": eid, "parceiro_id": cliente["id"], "serie": "1", "ambiente": "2",
    "itens": [{"produto_id": cafe["id"], "quantidade": 100, "valor_unitario": 1300,
               "cfop": "6101"}]}, t)
checar("e volta para homologação quando é isso que se escolhe",
       homologacao["nota"]["ambiente"] == "2"
       and api("GET", f"/api/nfe/{nota['id']}", None, t)["nota"]["ambiente"] == "2",
       homologacao["nota"]["ambiente_nome"])

previa = api("GET", f"/api/nfe/{nota['id']}/previa", None, t, bruto=True)
checar("prévia da DANFE sai marcada como sem valor fiscal",
       "SEM VALOR FISCAL" in previa and "DANFE" in previa)

sem_certificado = api("POST", f"/api/nfe/{nota['id']}/transmitir", {"empresa_id": eid}, t,
                      esperar_erro=True)
checar("sem certificado a transmissão avisa o que falta",
       sem_certificado.get("_status") == 400
       and "certificado" in sem_certificado.get("_detalhe", "").lower(),
       sem_certificado.get("_detalhe", "")[:50])

nao_autorizada = api("POST", f"/api/nfe/{nota['id']}/cancelar",
                     {"empresa_id": eid, "justificativa": "Cancelamento por acordo comercial"},
                     t, esperar_erro=True)
checar("não cancela nota que ainda não foi autorizada", nao_autorizada.get("_status") == 400)

outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outro-nfe{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra"})
alheia = api("GET", f"/api/nfe/{nota['id']}", None, outra["token"], esperar_erro=True)
checar("outra conta não abre a nota", alheia.get("_status") == 403)

api("DELETE", f"/api/nfe/{nota['id']}", None, t)
sumiu = api("GET", f"/api/nfe/{nota['id']}", None, t, esperar_erro=True)
checar("rascunho apagado some", sumiu.get("_status") == 404)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    raise SystemExit(1)
print("Emissão de NF-e OK.")
