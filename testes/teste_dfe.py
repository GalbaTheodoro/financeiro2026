"""Teste do módulo DF-e (documentos fiscais eletrônicos).

Duas partes:

1. **Sem internet** — o motor (backend/dfe.py) lendo os XML gravados em
   testes/dados_dfe/: retorno da distribuição, resumo da nota, nota completa,
   resumo de evento, retorno da manifestação, e a assinatura do evento
   (conferida com a chave pública do certificado de teste).
2. **Com o servidor rodando** — certificado, envio de XML, lista, filtros,
   ficha, DANFE, download do XML, importação (itens, pagamentos, cadastro do
   fornecedor, produtos e conta a pagar) e isolamento entre contas.

Uso (com o servidor em http://127.0.0.1:8000):  python testes/teste_dfe.py
"""
import base64
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
DADOS = RAIZ / "testes" / "dados_dfe"

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
                detalhe = json.loads(corpo or b"{}").get("detail", "")
            except json.JSONDecodeError:
                detalhe = corpo.decode("utf-8", "replace")[:200]
            return {"_status": e.code, "_detalhe": detalhe}
        raise AssertionError(f"{metodo} {caminho} -> HTTP {e.code}: {corpo[:300]}") from None


def enviar_arquivo(caminho, campos, arquivo, token, esperar_erro=False):
    """POST multipart/form-data sem dependências externas."""
    limite = "----agrodock" + str(int(time.time() * 1000))
    partes = []
    for nome, valor in campos.items():
        partes.append(
            f"--{limite}\r\nContent-Disposition: form-data; name=\"{nome}\"\r\n\r\n{valor}\r\n"
            .encode()
        )
    nome_arquivo, conteudo, tipo = arquivo
    partes.append(
        f'--{limite}\r\nContent-Disposition: form-data; name="arquivo"; '
        f'filename="{nome_arquivo}"\r\nContent-Type: {tipo}\r\n\r\n'.encode()
        + conteudo + b"\r\n"
    )
    partes.append(f"--{limite}--\r\n".encode())
    corpo = b"".join(partes)
    req = urllib.request.Request(f"{BASE}{caminho}", data=corpo, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        if esperar_erro:
            try:
                return {"_status": e.code, "_detalhe": json.loads(bruto or b"{}").get("detail", "")}
            except json.JSONDecodeError:
                return {"_status": e.code, "_detalhe": bruto.decode("utf-8", "replace")[:200]}
        raise AssertionError(f"POST {caminho} -> HTTP {e.code}: {bruto[:300]}") from None


def certificado_de_teste(cnpj: str, nome: str, senha: str, dias: int = 200) -> bytes:
    """Gera um certificado A1 de mentira (.pfx) só para o teste, no formato ICP-Brasil."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    titular = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{nome}:{cnpj}")])
    agora = datetime.now(timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(titular).issuer_name(titular)
        .public_key(chave.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=dias))
        .sign(chave, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"teste", key=chave, cert=certificado, cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode()),
    )


# =========================================================================== #
print("\n=== 1. Motor DF-e (sem internet) ===")
from backend import danfe, dfe  # noqa: E402

nfe_xml = (DADOS / "nfe_completa.xml").read_text(encoding="utf-8")
resumo_xml = (DADOS / "nfe_resumo.xml").read_text(encoding="utf-8")
evento_xml = (DADOS / "evento_resumo.xml").read_text(encoding="utf-8")
CHAVE = "31260912345678000195550010000123451876543210"

nota = dfe.ler_documento(nfe_xml, "procNFe_v4.00")
checar("nota completa: chave, número e valor", nota["chave"] == CHAVE and nota["numero"] == "12345"
       and nota["valor_total"] == 438200.0, str(nota["valor_total"]))
checar("nota completa: 2 itens e 3 pagamentos/duplicatas",
       len(nota["itens"]) == 2 and len(nota["pagamentos"]) == 3)
checar("item 1: café com NCM, CFOP e ICMS de 12%",
       nota["itens"][0]["ncm"] == "09011110" and nota["itens"][0]["cfop"] == "5101"
       and nota["itens"][0]["icms_valor"] == 52272.0)
checar("item 2: GTIN e CEST lidos", nota["itens"][1]["gtin"] == "7891234567895"
       and nota["itens"][1]["cest"] == "2806400")
checar("'SEM GTIN' não vira código de barras", nota["itens"][0]["gtin"] == "")
duplicatas = [p for p in nota["pagamentos"] if p["origem"] == "DUPLICATA"]
checar("duplicatas com vencimento e valor", len(duplicatas) == 2
       and duplicatas[0]["vencimento"] == "2026-10-10" and duplicatas[0]["valor"] == 219100.0)

resumo = dfe.ler_documento(resumo_xml, "resNFe_v1.01")
checar("resumo: marcado como resumo e com a UF tirada da chave",
       resumo["resumo"] is True and resumo["emitente_uf"] == "MG" and resumo["valor_total"] == 4850.0)
checar("resumo: número e série vêm da chave de acesso",
       resumo["numero"] == "6789" and resumo["serie"] == "1", f"{resumo['numero']}/{resumo['serie']}")

evento = dfe.ler_documento(evento_xml, "resEvento_v1.01")
checar("evento de cancelamento reconhecido",
       evento["tipo"] == "EVENTO" and evento["codigo_evento"] == "110111" and evento["chave"] == CHAVE)

retorno = dfe.ler_retorno_distribuicao((DADOS / "retorno_distribuicao.xml").read_text(encoding="utf-8"))
checar("retorno da distribuição: 3 documentos descompactados",
       retorno["cstat"] == "138" and len(retorno["documentos"]) == 3, retorno["motivo"])
checar("NSU e maxNSU lidos com 15 dígitos",
       retorno["ultimo_nsu"] == "000000000000103" and len(retorno["max_nsu"]) == 15)

ret_evento = dfe.ler_retorno_evento((DADOS / "retorno_evento.xml").read_text(encoding="utf-8"))
checar("retorno da manifestação aceito (135)", ret_evento["ok"] and ret_evento["cstat"] == "135"
       and ret_evento["protocolo"] == "891260000123456")

print("\n=== 2. Assinatura do evento de manifestação ===")
SENHA_PFX = "teste123"
CNPJ_EMPRESA = "98765432000198"
pfx = certificado_de_teste(CNPJ_EMPRESA, "ASSESSORIA AGRODOCK LTDA", SENHA_PFX)
chave_privada, certificado, cadeia = dfe.abrir_pfx(pfx, SENHA_PFX)
dados_cert = dfe.dados_do_certificado(certificado)
checar("certificado de teste: CNPJ e titular lidos do nome",
       dados_cert["cnpj"] == CNPJ_EMPRESA and "AGRODOCK" in dados_cert["titular"], str(dados_cert))
senha_errada = None
try:
    dfe.abrir_pfx(pfx, "errada")
except dfe.ErroDFe as erro:
    senha_errada = str(erro)
checar("senha errada é recusada com mensagem clara", bool(senha_errada) and "senha" in senha_errada.lower())

inf = dfe.montar_inf_evento(CHAVE, CNPJ_EMPRESA, "CIENCIA", "1", 1)
checar("infEvento sai na forma canônica (xmlns antes do Id, sem espaços)",
       inf.startswith('<infEvento xmlns="http://www.portalfiscal.inf.br/nfe" Id="ID210210')
       and "> <" not in inf, inf[:90])
checar("infEvento traz o código do evento e a chave", "<tpEvento>210210</tpEvento>" in inf
       and f"<chNFe>{CHAVE}</chNFe>" in inf)

assinatura = dfe.assinar(inf, chave_privada, certificado)
envelope = dfe.montar_envelope_evento(inf, assinatura)
checar("envelope tem o evento e a assinatura", "<envEvento" in envelope
       and "<SignatureValue>" in envelope and inf in envelope)

# confere a assinatura do jeito que a SEFAZ confere: resumo do infEvento -> SignedInfo -> RSA
import hashlib  # noqa: E402
import re  # noqa: E402
from cryptography.hazmat.primitives import hashes as _h  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding as _p  # noqa: E402

resumo_esperado = base64.b64encode(hashlib.sha1(inf.encode()).digest()).decode()
digest_no_xml = re.search(r"<DigestValue>([^<]+)</DigestValue>", assinatura).group(1)
checar("DigestValue é o SHA-1 do infEvento assinado", digest_no_xml == resumo_esperado)
assinado = re.search(r"(<SignedInfo.*?</SignedInfo>)", assinatura, re.S).group(1)
valor_assinatura = base64.b64decode(
    re.search(r"<SignatureValue>([^<]+)</SignatureValue>", assinatura).group(1))
assinatura_confere = True
try:
    certificado.public_key().verify(valor_assinatura, assinado.encode(), _p.PKCS1v15(), _h.SHA1())
except Exception:  # noqa: BLE001
    assinatura_confere = False
checar("assinatura RSA-SHA1 do SignedInfo confere com o certificado", assinatura_confere)
sem_justificativa = None
try:
    dfe.montar_inf_evento(CHAVE, CNPJ_EMPRESA, "NAO_REALIZADA", "1", 1, "curta")
except dfe.ErroDFe as erro:
    sem_justificativa = str(erro)
checar("'Operação não realizada' exige justificativa de 15 letras", bool(sem_justificativa))

print("\n=== 3. DANFE ===")
folha = danfe.gerar(nfe_xml, "ASSESSORIA AGRODOCK LTDA")
checar("DANFE traz emitente, chave, itens e duplicatas",
       "FAZENDA SAO JOAQUIM" in folha and dfe.formatar_chave(CHAVE) in folha
       and "CAFE CRU EM GRAO" in folha and "219.100,00" in folha)
checar("DANFE marca saída e mostra o protocolo",
       "1 - SAÍDA" in folha and "131260099887766" in folha)
# 44 números = 22 pares + início + verificador + fim = 25 símbolos (76 barras pretas)
checar("código de barras Code128 desenhado", '<svg class="barras"' in folha
       and folha.count("<rect") == 76, str(folha.count("<rect")))
so_resumo = None
try:
    danfe.gerar(resumo_xml)
except ValueError as erro:
    so_resumo = str(erro)
checar("DANFE de nota só com resumo explica o que fazer",
       bool(so_resumo) and "ciência" in so_resumo.lower())

# =========================================================================== #
print("\n=== 4. Preparação da conta de teste ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Fiscal DF-e", "email": f"dfe{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock",
})
t = conta["token"]
eid = conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": CNPJ_EMPRESA,
    "cidade": "Patrocínio", "uf": "MG",
}, t)
empresa_salva = next(e for e in api("GET", "/api/empresas", token=t) if e["id"] == eid)
checar("empresa com o CNPJ do certificado", empresa_salva["cnpj"] == CNPJ_EMPRESA)

print("\n=== 5. Certificado digital ===")
vazio = api("GET", f"/api/dfe/certificado?empresa_id={eid}", token=t)
checar("sem certificado o sistema avisa", vazio["configurado"] is False)
erro_senha = enviar_arquivo(
    "/api/dfe/certificado", {"empresa_id": eid, "senha": "errada", "ambiente": "1"},
    ("teste.pfx", pfx, "application/x-pkcs12"), t, esperar_erro=True)
checar("senha errada não grava nada", erro_senha.get("_status") == 400, erro_senha.get("_detalhe", ""))

outro_pfx = certificado_de_teste("12345678000195", "OUTRA EMPRESA LTDA", SENHA_PFX)
erro_cnpj = enviar_arquivo(
    "/api/dfe/certificado", {"empresa_id": eid, "senha": SENHA_PFX, "ambiente": "1"},
    ("outro.pfx", outro_pfx, "application/x-pkcs12"), t, esperar_erro=True)
checar("certificado de outro CNPJ é recusado", erro_cnpj.get("_status") == 400
       and "CNPJ" in erro_cnpj.get("_detalhe", ""), erro_cnpj.get("_detalhe", ""))

salvo = enviar_arquivo(
    "/api/dfe/certificado",
    {"empresa_id": eid, "senha": SENHA_PFX, "ambiente": "1", "uf_autor": "MG"},
    ("agrodock.pfx", pfx, "application/x-pkcs12"), t)
checar("certificado aceito, com titular, CNPJ e validade",
       salvo["configurado"] and salvo["cnpj"] == "98.765.432/0001-98"
       and salvo["dias_para_vencer"] > 100, str(salvo.get("titular")))
texto_certificado = json.dumps(salvo)
checar("a resposta não devolve o arquivo nem a senha",
       SENHA_PFX not in texto_certificado and "conteudo" not in texto_certificado
       and base64.b64encode(pfx).decode()[:40] not in texto_certificado)
checar("ambiente de produção e UF do consulente guardados",
       salvo["ambiente"] == "1" and salvo["ambiente_nome"] == "Produção" and salvo["uf_autor"] == "MG")

print("\n=== 6. Entrada dos documentos ===")
enviado = enviar_arquivo("/api/dfe/enviar-xml", {"empresa_id": eid},
                         ("nota.xml", nfe_xml.encode(), "application/xml"), t)
checar("XML enviado por arquivo entra na lista", enviado["situacao"] == "nova"
       and enviado["nota"]["chave"] == CHAVE, enviado["mensagem"])
repetido = enviar_arquivo("/api/dfe/enviar-xml", {"empresa_id": eid},
                          ("nota.xml", nfe_xml.encode(), "application/xml"), t)
checar("o mesmo XML não duplica a nota", repetido["situacao"] == "atualizada")
so_resumo_env = enviar_arquivo("/api/dfe/enviar-xml", {"empresa_id": eid},
                               ("resumo.xml", resumo_xml.encode(), "application/xml"), t)
checar("resumo de outra nota também entra", so_resumo_env["nota"]["resumo"] is True)
nao_xml = enviar_arquivo("/api/dfe/enviar-xml", {"empresa_id": eid},
                         ("qualquer.xml", b"<a>oi</a>", "application/xml"), t, esperar_erro=True)
checar("arquivo que não é NF-e é recusado", nao_xml.get("_status") == 400)

notas = api("GET", f"/api/dfe/notas?empresa_id={eid}", token=t)
completa = next(n for n in notas if n["chave"] == CHAVE)
id_nota = completa["id"]
id_resumo = next(n["id"] for n in notas if n["resumo"])
checar("lista traz as duas notas, a mais nova primeiro", len(notas) == 2
       and notas[0]["chave"] == resumo["chave"], str([n["numero"] for n in notas]))
# a nota é do fornecedor (tpNF=1, saída para ele) — para a nossa empresa é ENTRADA
checar("lista mostra o documento do emitente e o sentido visto pela empresa",
       completa["emitente_documento"] == "12.345.678/0001-95"
       and completa["sentido"] == "Entrada", completa["sentido"])

so_com_xml = api("GET", f"/api/dfe/notas?empresa_id={eid}&formato=completo", token=t)
checar("filtro 'com XML completo' devolve só a nota inteira",
       len(so_com_xml) == 1 and so_com_xml[0]["id"] == id_nota)
por_periodo = api("GET", f"/api/dfe/notas?empresa_id={eid}&inicio=2026-09-11&fim=2026-09-30", token=t)
checar("filtro por período de emissão", len(por_periodo) == 1 and por_periodo[0]["id"] == id_resumo)
por_busca = api("GET", f"/api/dfe/notas?empresa_id={eid}&busca=SAO%20JOAQUIM", token=t)
checar("busca pelo nome do emitente", len(por_busca) == 1 and por_busca[0]["id"] == id_nota)
sem_manifesto = api("GET", f"/api/dfe/notas?empresa_id={eid}&manifestacao=SEM", token=t)
checar("filtro 'ainda sem manifestação' pega as duas", len(sem_manifesto) == 2)

kpis = api("GET", f"/api/dfe/resumo?empresa_id={eid}", token=t)
checar("resumo do topo da tela", kpis["documentos"] == 2 and kpis["somente_resumo"] == 1
       and kpis["nao_importadas"] == 2 and kpis["valor_total"] == 443050.0, str(kpis["valor_total"]))

print("\n=== 7. Ficha, XML e DANFE ===")
ficha = api("GET", f"/api/dfe/notas/{id_nota}", token=t)
checar("antes de importar, a ficha já mostra os itens do XML", len(ficha["itens"]) == 2
       and ficha["itens"][0]["descricao"].startswith("CAFE CRU"))
checar("a ficha oferece as quatro manifestações", len(ficha["manifestacoes"]) == 4
       and any(m["tipo"] == "NAO_REALIZADA" and m["exige_justificativa"] for m in ficha["manifestacoes"]))
xml_baixado = api("GET", f"/api/dfe/notas/{id_nota}/xml", token=t, bruto=True)
checar("download do XML devolve o arquivo original", "nfeProc" in xml_baixado
       and CHAVE in xml_baixado)
folha_servidor = api("GET", f"/api/dfe/notas/{id_nota}/danfe", token=t, bruto=True)
checar("DANFE vem pronta do servidor", "DANFE" in folha_servidor and "FAZENDA SAO JOAQUIM" in folha_servidor)
danfe_resumo = api("GET", f"/api/dfe/notas/{id_resumo}/danfe", token=t, esperar_erro=True)
checar("DANFE de nota só com resumo é recusada com explicação",
       danfe_resumo.get("_status") == 400, danfe_resumo.get("_detalhe", "")[:60])

print("\n=== 8. Importação para o sistema ===")
importar_resumo = api("POST", f"/api/dfe/notas/{id_resumo}/importar", {"empresa_id": eid},
                      t, esperar_erro=True)
checar("nota só com resumo não pode ser importada", importar_resumo.get("_status") == 400)

resultado = api("POST", f"/api/dfe/notas/{id_nota}/importar", {
    "empresa_id": eid, "criar_parceiro": True, "atualizar_produtos": True,
    "gerar_titulo": True,
}, t)
checar("importação concluída", resultado["ok"] and resultado["nota"]["importada"] is True,
       resultado["mensagem"])

ficha2 = api("GET", f"/api/dfe/notas/{id_nota}", token=t)
checar("itens gravados na tabela da nota", len(ficha2["itens"]) == 2
       and ficha2["itens"][0]["produto_id"], str(ficha2["itens"][0].get("produto_nome")))
checar("pagamentos e duplicatas gravados", len(ficha2["pagamentos"]) == 3
       and sum(1 for p in ficha2["pagamentos"] if p["origem"] == "DUPLICATA") == 2)
checar("valores do item conferem", ficha2["itens"][0]["valor_total"] == 435600.0
       and ficha2["itens"][0]["icms_aliquota"] == 12.0)

parceiros = api("GET", f"/api/parceiros?empresa_id={eid}", token=t)
fornecedor = next((p for p in parceiros if p["cpf_cnpj"] == "12345678000195"), None)
checar("fornecedor criado a partir do emitente", fornecedor is not None
       and fornecedor["nome"].startswith("FAZENDA SAO JOAQUIM"))
checar("dados fiscais do fornecedor preenchidos pelo XML",
       fornecedor["rg_ie"] == "0011223344009" and fornecedor["codigo_municipio"] == "3148004"
       and fornecedor["indicador_ie"] == "1" and fornecedor["cidade"] == "PATROCINIO",
       str(fornecedor.get("codigo_municipio")))
checar("endereço do emitente veio junto", fornecedor["uf"] == "MG"
       and fornecedor["cep"] == "38740000" and fornecedor["bairro"] == "CORREGO DO OURO")

produtos = api("GET", f"/api/produtos?empresa_id={eid}", token=t)
cafe = next((p for p in produtos if p["codigo"] == "CAF001"), None)
sacaria = next((p for p in produtos if p["codigo"] == "SAC010"), None)
checar("produtos da nota criados no cadastro", cafe is not None and sacaria is not None,
       str([p["codigo"] for p in produtos]))
checar("café com NCM, CFOP, CST e unidade do XML", cafe["ncm"] == "09011110"
       and cafe["cfop_padrao"] == "5101" and cafe["cst_icms"] == "00"
       and cafe["unidade_comercial"] == "SC" and cafe["aliquota_icms"] == 12.0)
checar("unidade SC criada com 60 kg por saca", cafe["unidade_id"]
       and next(u for u in api("GET", f"/api/unidades?empresa_id={eid}", token=t)
                if u["id"] == cafe["unidade_id"])["peso_conversao"] == 60)
checar("sacaria com CEST e GTIN", sacaria["cest"] == "2806400" and sacaria["gtin"] == "7891234567895")

titulos = api("GET", f"/api/lancamentos?empresa_id={eid}&tipo=PAGAR", token=t)
lista_titulos = titulos["itens"] if isinstance(titulos, dict) else titulos
titulo = next((x for x in lista_titulos if x["id"] == resultado["lancamento_id"]), None)
checar("conta a pagar gerada com o valor da nota", titulo is not None
       and titulo["valor_total"] == 438200.0 and titulo["tipo"] == "PAGAR",
       str(resultado["lancamento_id"]))
detalhe_titulo = api("GET", f"/api/lancamentos/{resultado['lancamento_id']}", token=t)
checar("título tem as 2 parcelas das duplicatas",
       len(detalhe_titulo["parcelas"]) == 2
       and detalhe_titulo["parcelas"][0]["data_vencimento"] == "2026-10-10"
       and detalhe_titulo["parcelas"][1]["valor"] == 219100.0,
       str([p["data_vencimento"] for p in detalhe_titulo["parcelas"]]))
checar("título ligado ao fornecedor do emitente", detalhe_titulo["parceiro_id"] == fornecedor["id"])

de_novo = api("POST", f"/api/dfe/notas/{id_nota}/importar", {"empresa_id": eid, "gerar_titulo": True},
              t, esperar_erro=True)
checar("não gera um segundo título para a mesma nota", de_novo.get("_status") == 400,
       de_novo.get("_detalhe", "")[:60])
reimportar = api("POST", f"/api/dfe/notas/{id_nota}/importar", {"empresa_id": eid}, t)
checar("reimportar sem título não duplica itens", reimportar["ok"]
       and len(api("GET", f"/api/dfe/notas/{id_nota}", token=t)["itens"]) == 2)

print("\n=== 9. Manifestação e segurança ===")
sem_rede = api("POST", f"/api/dfe/notas/{id_nota}/manifestar",
               {"empresa_id": eid, "tipo": "INVENTADA"}, t, esperar_erro=True)
checar("manifestação desconhecida é recusada antes de sair do sistema",
       sem_rede.get("_status") == 400, sem_rede.get("_detalhe", ""))

outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outro-dfe{sufixo}@teste.com", "senha": "123456", "empresa": "Outra"})
alheia = api("GET", f"/api/dfe/notas?empresa_id={eid}", token=outra["token"], esperar_erro=True)
checar("outra conta não vê os documentos", alheia.get("_status") == 403, str(alheia))
cert_alheio = api("GET", f"/api/dfe/certificado?empresa_id={eid}", token=outra["token"],
                  esperar_erro=True)
checar("outra conta não vê o certificado", cert_alheio.get("_status") == 403)
nota_alheia = api("GET", f"/api/dfe/notas/{id_nota}", token=outra["token"], esperar_erro=True)
checar("outra conta não abre a nota pelo id", nota_alheia.get("_status") == 403)

api("DELETE", f"/api/dfe/notas/{id_resumo}", token=t)
checar("excluir tira o documento da lista",
       len(api("GET", f"/api/dfe/notas?empresa_id={eid}", token=t)) == 1)
api("DELETE", f"/api/dfe/certificado?empresa_id={eid}", token=t)
checar("certificado removido",
       api("GET", f"/api/dfe/certificado?empresa_id={eid}", token=t)["configurado"] is False)
sem_cert = api("POST", "/api/dfe/buscar", {"empresa_id": eid}, t, esperar_erro=True)
checar("sem certificado a busca avisa o que falta", sem_cert.get("_status") == 400
       and "certificado" in sem_cert.get("_detalhe", "").lower(), sem_cert.get("_detalhe", "")[:60])

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    raise SystemExit(1)
print("DF-e OK.")
