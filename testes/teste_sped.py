"""Teste do SPED Fiscal — o arquivo da EFD ICMS/IPI.

Este arquivo não é um relatório: é um leiaute fechado que o PVA da Receita abre e
valida campo por campo. Então o que se confere aqui é **o formato**, não a
aparência.

O que se confere
----------------
  * **a estrutura**: todo bloco abre e fecha (0001/0990, C001/C990, ...), na
    ordem, e o 0000 vem primeiro e o 9999 por último;
  * **as contagens do bloco 9**, que é onde erra quem escreve isso na mão: o
    9900 conta as próprias linhas 9900, o 9990 conta o 9999 (que nem é do bloco
    dele) e o 9999 conta o arquivo inteiro;
  * **as três fontes entram**: nota importada vira entrada, NF-e emitida vira
    saída e cupom fiscal vira saída modelo 65;
  * **o cupom sai sem participante** e sem os campos de ST/IPI/PIS/COFINS, que é
    o que o Guia Prático manda para o modelo 65;
  * **nota cancelada leva só o cabeçalho** — sem C170 e sem C190;
  * **C190 não repete** a combinação CST + CFOP + alíquota dentro do documento;
  * **CSOSN vira CST**: item de empresa do Simples sai com código da tabela do
    SPED, não com o 102 da nota;
  * **a versão do leiaute sai do ano do período** — arquivo de 2025 é 019;
  * **a apuração**: regime normal calcula débito das saídas menos crédito das
    entradas; Simples Nacional sai zerado, de propósito;
  * **a conferência barra o que o PVA recusaria**: nota só com resumo, item sem
    CFOP, empresa sem inscrição estadual;
  * o arquivo sai em **ISO-8859-1** e com CRLF;
  * **o inventário** (bloco H) só aparece quando pedido, e o item inventariado
    também ganha a linha 0200;
  * SPED de outra conta não abre.

Uso:  python testes/teste_sped.py   (com o servidor no ar)
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8000"
erros = []


def api(metodo, caminho, dados=None, token=None, esperar_erro=False, cru=False):
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
            bruto = r.read()
            return bruto if cru else json.loads(bruto or b"{}")
    except urllib.error.HTTPError as erro:
        if not esperar_erro:
            raise
        corpo = erro.read()
        try:
            dados = json.loads(corpo or b"{}")
        except ValueError:
            dados = {"detail": corpo.decode("utf-8", "replace")[:300]}
        dados["_status"] = erro.code
        return dados


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


from backend import sped as regras                            # noqa: E402
from backend.database import SessionLocal                      # noqa: E402
from backend.models import Empresa, Nota, NotaItem, Parceiro, Produto  # noqa: E402


def campos(linha):
    """Os campos de uma linha do SPED, sem os pipes das pontas.

    Tira **um** pipe de cada ponta, não todos: linha que acaba em campo vazio
    acaba em "||", e um strip() comeria o campo vazio junto — justamente o que
    este teste precisa ver (o cupom tem de sair com os campos de imposto vazios).
    """
    linha = linha.strip("\r\n")
    if linha.startswith("|"):
        linha = linha[1:]
    if linha.endswith("|"):
        linha = linha[:-1]
    return linha.split("|")


def linhas_de(texto, registro):
    return [c for c in (campos(l) for l in texto.splitlines())
            if c and c[0] == registro]


# =========================================================================== #
print("=== 1. A versão do leiaute vem do ano do período ===")
checar("2026 é o leiaute 020", regras.versao_do_layout(date(2026, 9, 30)) == "020")
checar("2025 é o 019 — quem entrega mês atrasado precisa do código daquele ano",
       regras.versao_do_layout(date(2025, 3, 31)) == "019")
checar("ano mais novo que a tabela cai no último conhecido",
       regras.versao_do_layout(date(2033, 1, 31)) == "020")
checar("ano anterior à tabela cai no primeiro",
       regras.versao_do_layout(date(2015, 1, 31)) == "014")

print("\n=== 2. CSOSN vira CST (empresa do Simples) ===")
padrao = regras.ler_depara(None)
checar("CSOSN 500 tem equivalência limpa: CST 60",
       regras._cst_do_sped("500", "0", padrao) == "060",
       regras._cst_do_sped("500", "0", padrao))
checar("os outros CSOSN vão para 90 (Outras), que não afirma benefício nenhum",
       regras._cst_do_sped("102", "0", padrao) == "090",
       regras._cst_do_sped("102", "0", padrao))
checar("CST de 2 dígitos ganha a origem na frente",
       regras._cst_do_sped("00", "1", padrao) == "100",
       regras._cst_do_sped("00", "1", padrao))
checar("CST que já veio com 3 dígitos passa direto",
       regras._cst_do_sped("041", "0", padrao) == "041")
meu = regras.ler_depara("102=20;500=60")
checar("o de/para da empresa manda mais que o padrão",
       regras._cst_do_sped("102", "0", meu) == "020",
       regras._cst_do_sped("102", "0", meu))
checar("item sem CST sai vazio, não sai chutado",
       regras._cst_do_sped("", "0", padrao) == "")

print("\n=== 3. Formatação dos campos ===")
checar("valor usa vírgula decimal e não tem separador de milhar",
       regras._numero(1234.5) == "1234,50", regras._numero(1234.5))
checar("campo de valor opcional zerado sai vazio",
       regras._numero(0, vazio_se_zero=True) == "")
checar("campo de valor obrigatório zerado sai 0,00", regras._numero(0) == "0,00")
checar("data sai ddmmaaaa", regras._data(date(2026, 3, 7)) == "07032026",
       regras._data(date(2026, 3, 7)))
checar("pipe dentro de texto é trocado — senão quebra o arquivo",
       "|" not in regras._texto("CAFE | CRU"))

# =========================================================================== #
print("\n=== 4. Montar a empresa e as três fontes de nota ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"sped{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria SPED", "plano": "P4_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]

api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA SPED LTDA", "cnpj": "12.345.678/0001-95",
    "inscricao_estadual": "0011223344556", "uf": "MG", "cidade": "VARGINHA",
    "codigo_municipio": "3170701", "cep": "37010-000",
    "logradouro": "RUA DO CAFE", "numero": "100", "bairro": "CENTRO",
    "regime_tributario": "LUCRO PRESUMIDO", "crt": "3"}, t)

produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe = produtos[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: cafe[k] for k in ("empresa_id", "codigo", "nome", "unidade_id",
                            "categoria_id", "marca_id")},
    "ncm": "09011110", "unidade_comercial": "SC", "cest": "",
    "controla_estoque": True, "aliquota_icms": 7, "tipo_item_sped": "00"}, t)

fornecedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "FORNECEDOR", "nome": "FAZENDA BOA VISTA LTDA",
    "cpf_cnpj": "98.765.432/0001-10", "rg_ie": "0012345678901",
    "cidade": "TRES PONTAS", "uf": "MG", "codigo_municipio": "3169307",
    "logradouro": "SITIO BOA VISTA", "numero": "S/N", "bairro": "ZONA RURAL"}, t)
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "11.222.333/0001-44", "rg_ie": "111222333444",
    "cidade": "SAO PAULO", "uf": "SP", "codigo_municipio": "3550308"}, t)

# As notas são gravadas direto no banco: emitir de verdade exige certificado
# digital e a SEFAZ no ar, e o que este teste confere é o arquivo, não a emissão.
CHAVES = {
    "entrada": "31" + "2601" + "98765432000110" + "55" + "001" + "000000101" + "1" + "000001053",
    "saida": "31" + "2601" + "12345678000195" + "55" + "001" + "000000201" + "1" + "000002386",
    "cupom": "31" + "2601" + "12345678000195" + "65" + "001" + "000000301" + "1" + "000003719",
    "cancelada": "31" + "2601" + "12345678000195" + "55" + "001" + "000000202" + "1" + "000004842",
}
for nome, chave in CHAVES.items():
    assert len(chave) == 44, (nome, len(chave))

sessao = SessionLocal()
produto = sessao.get(Produto, cafe["id"])


def gravar_nota(**dados):
    itens = dados.pop("itens", [])
    nota = Nota(empresa_id=eid, **dados)
    sessao.add(nota)
    sessao.flush()
    for numero, item in enumerate(itens, start=1):
        sessao.add(NotaItem(nota_id=nota.id, numero=numero, **item))
    sessao.flush()
    return nota


item_entrada = dict(
    codigo=produto.codigo, descricao="CAFE CRU EM GRAO", ncm="09011110",
    cfop="1102", unidade="SC", quantidade=100, valor_unitario=1200,
    valor_total=120000, icms_cst="00", icms_base=120000, icms_aliquota=7,
    icms_valor=8400, origem_mercadoria="0", produto_id=produto.id,
)
entrada = gravar_nota(
    chave=CHAVES["entrada"], origem="DFE", tipo="NFE", resumo=False,
    modelo="55", serie="1", numero="101", data_emissao=datetime(2026, 1, 12, 9, 0),
    natureza_operacao="COMPRA", tipo_operacao="1", emitente_cnpj="98765432000110",
    emitente_nome="FAZENDA BOA VISTA LTDA", emitente_ie="0012345678901",
    emitente_uf="MG", destinatario_cnpj="12345678000195",
    valor_total=120000, valor_produtos=120000, valor_icms=8400,
    situacao="AUTORIZADA", parceiro_id=fornecedor["id"], importada=True,
    xml="<nfeProc/>", itens=[item_entrada],
)

saida = gravar_nota(
    chave=CHAVES["saida"], origem="EMITIDA", tipo="NFE", resumo=False,
    modelo="55", serie="1", numero="201", data_emissao=datetime(2026, 1, 20, 14, 0),
    natureza_operacao="VENDA", tipo_operacao="1", emitente_cnpj="12345678000195",
    emitente_nome="ASSESSORIA SPED LTDA", emitente_uf="MG",
    destinatario_cnpj="11222333000144", destinatario_nome="TORREFACAO PAULISTA LTDA",
    valor_total=66000, valor_produtos=66000, valor_icms=4620,
    situacao="AUTORIZADA", status_emissao="AUTORIZADA", ambiente="1",
    parceiro_id=cliente["id"], cfop="6102", frete_modalidade="1",
    itens=[
        dict(codigo=produto.codigo, descricao="CAFE CRU EM GRAO", ncm="09011110",
             cfop="6102", unidade="SC", quantidade=40, valor_unitario=1320,
             valor_total=52800, icms_cst="00", icms_base=52800, icms_aliquota=7,
             icms_valor=3696, origem_mercadoria="0", produto_id=produto.id),
        # mesmo CST, CFOP e alíquota do item acima: no C190 os dois viram UMA linha
        dict(codigo=produto.codigo, descricao="CAFE CRU EM GRAO", ncm="09011110",
             cfop="6102", unidade="SC", quantidade=10, valor_unitario=1320,
             valor_total=13200, icms_cst="00", icms_base=13200, icms_aliquota=7,
             icms_valor=924, origem_mercadoria="0", produto_id=produto.id),
    ],
)

cupom = gravar_nota(
    chave=CHAVES["cupom"], origem="EMITIDA", tipo="NFE", resumo=False,
    modelo="65", serie="1", numero="301", data_emissao=datetime(2026, 1, 22, 11, 30),
    natureza_operacao="VENDA AO CONSUMIDOR", tipo_operacao="1",
    emitente_cnpj="12345678000195", emitente_nome="ASSESSORIA SPED LTDA",
    emitente_uf="MG", consumidor_documento="12345678909",
    valor_total=340, valor_produtos=340, valor_icms=61.2,
    situacao="AUTORIZADA", status_emissao="AUTORIZADA", ambiente="1", cfop="5102",
    itens=[dict(codigo=produto.codigo, descricao="CAFE TORRADO 500G", ncm="09012100",
                cfop="5102", unidade="UN", quantidade=20, valor_unitario=17,
                valor_total=340, icms_cst="00", icms_base=340, icms_aliquota=18,
                icms_valor=61.2, origem_mercadoria="0", produto_id=produto.id)],
)

cancelada = gravar_nota(
    chave=CHAVES["cancelada"], origem="EMITIDA", tipo="NFE", resumo=False,
    modelo="55", serie="1", numero="202", data_emissao=datetime(2026, 1, 25, 8, 0),
    natureza_operacao="VENDA", tipo_operacao="1", emitente_cnpj="12345678000195",
    emitente_nome="ASSESSORIA SPED LTDA", emitente_uf="MG",
    destinatario_cnpj="11222333000144", destinatario_nome="TORREFACAO PAULISTA LTDA",
    valor_total=1000, valor_produtos=1000, situacao="CANCELADA",
    status_emissao="CANCELADA", parceiro_id=cliente["id"], cfop="6102",
    itens=[dict(codigo=produto.codigo, descricao="CAFE CRU EM GRAO", cfop="6102",
                unidade="SC", quantidade=1, valor_unitario=1000, valor_total=1000,
                icms_cst="00", icms_valor=70, produto_id=produto.id)],
)
sessao.commit()
checar("as quatro notas do mês foram gravadas",
       all(n.id for n in (entrada, saida, cupom, cancelada)))

# =========================================================================== #
print("\n=== 5. A conferência aponta antes do PVA ===")
conf = api("GET", f"/api/sped/conferir?empresa_id={eid}&de=2026-01-01", None, t)
checar("o período vira o mês fechado sozinho",
       conf["de"] == "2026-01-01" and conf["ate"] == "2026-01-31",
       f'{conf["de"]} a {conf["ate"]}')
checar("contou 3 saídas (NF-e, cupom e a cancelada)", conf["notas"]["saidas"] == 3,
       str(conf["notas"]))
checar("e 1 entrada", conf["notas"]["entradas"] == 1)
checar("reconheceu o cupom entre as saídas", conf["notas"]["cupons"] == 1)
checar("e a nota cancelada", conf["notas"]["canceladas"] == 1)
checar("sem pendência, libera a geração", conf["pode_gerar"] is True,
       str(conf["impedimentos"]))
checar("avisa que falta o contabilista do registro 0100",
       any("contabilista" in a for a in conf["avisos"]), str(conf["avisos"]))
checar("empresa de regime normal não recebe o aviso do Simples",
       conf["simples"] is False)

# uma nota só com resumo derruba o arquivo — e a conferência diz isso
resumo = gravar_nota(
    chave="31" + "2601" + "98765432000110" + "55" + "001" + "000000999" + "1" + "000005175",
    origem="DFE", tipo="NFE", resumo=True, modelo="55", serie="1", numero="999",
    data_emissao=datetime(2026, 1, 28, 10, 0), emitente_cnpj="98765432000110",
    emitente_nome="FAZENDA BOA VISTA LTDA", emitente_uf="MG",
    destinatario_cnpj="12345678000195", valor_total=5000, situacao="AUTORIZADA",
)
sessao.commit()
conf2 = api("GET", f"/api/sped/conferir?empresa_id={eid}&de=2026-01-01", None, t)
checar("nota só com resumo vira impedimento",
       conf2["pode_gerar"] is False
       and any("resumo" in i for i in conf2["impedimentos"]),
       str(conf2["impedimentos"])[:90])
checar("e a nota aparece na lista, para saber qual é",
       len(conf2["resumos"]) == 1 and conf2["resumos"][0]["numero"] == "999")
barrado = api(f"GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01",
              None, t, esperar_erro=True)
checar("com impedimento, o download é recusado", barrado.get("_status") == 400,
       str(barrado.get("detail"))[:70])
forcado = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01&forcar=true",
              None, t, cru=True)
checar("mas dá para forçar, para o contador olhar", len(forcado) > 500)

sessao.delete(resumo)
sessao.commit()

# item sem CFOP também derruba: é a chave do C190
sem_cfop = sessao.query(NotaItem).filter(NotaItem.nota_id == saida.id).first()
guardado, sem_cfop.cfop = sem_cfop.cfop, None
sessao.commit()
conf3 = api("GET", f"/api/sped/conferir?empresa_id={eid}&de=2026-01-01", None, t)
checar("item sem CFOP vira impedimento",
       conf3["pode_gerar"] is False and any("CFOP" in i for i in conf3["impedimentos"]),
       str(conf3["impedimentos"])[:80])
sem_cfop.cfop = guardado
sessao.commit()

# =========================================================================== #
print("\n=== 6. A estrutura do arquivo ===")
bruto = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01", None, t, cru=True)
checar("o arquivo sai em ISO-8859-1 (não em UTF-8)",
       bruto.decode("iso-8859-1") and b"\xc3\xa9" not in bruto)
texto = bruto.decode("iso-8859-1")
checar("cada linha termina em CRLF, como o Guia pede", "\r\n" in texto)
linhas = texto.splitlines()
checar("a primeira linha é o 0000", campos(linhas[0])[0] == "0000")
checar("a última é o 9999", campos(linhas[-1])[0] == "9999")
checar("toda linha começa e termina com pipe",
       all(l.startswith("|") and l.endswith("|") for l in linhas))

presentes = [campos(l)[0] for l in linhas]
for abre, fecha in (("0001", "0990"), ("C001", "C990"), ("D001", "D990"),
                    ("E001", "E990"), ("G001", "G990"), ("H001", "H990"),
                    ("K001", "K990"), ("1001", "1990"), ("9001", "9990")):
    checar(f"o bloco {abre[0]} abre em {abre} e fecha em {fecha}",
           abre in presentes and fecha in presentes
           and presentes.index(abre) < presentes.index(fecha))
checar("empresa de MG não leva o bloco B (é só do Distrito Federal)",
       "B001" not in presentes)

print("\n=== 7. As contagens do bloco 9 — onde todo mundo erra ===")
r0000 = linhas_de(texto, "0000")[0]
checar("o 0000 leva o leiaute 020", r0000[1] == "020", r0000[1])
checar("com finalidade 0 (remessa original)", r0000[2] == "0")
checar("o período no 0000 é o mês inteiro",
       r0000[3] == "01012026" and r0000[4] == "31012026", f"{r0000[3]}-{r0000[4]}")
checar("o CNPJ vai só com dígitos", r0000[6] == "12345678000195", r0000[6])
checar("a inscrição estadual está lá", r0000[9] == "0011223344556", r0000[9])
checar("o código do município também", r0000[10] == "3170701", r0000[10])
checar("e o perfil é A", r0000[13] == "A", r0000[13])

contagem = {c[1]: int(c[2]) for c in linhas_de(texto, "9900")}
reais = {}
for linha in linhas:
    registro = campos(linha)[0]
    reais[registro] = reais.get(registro, 0) + 1
divergentes = {r: (contagem.get(r), reais[r]) for r in reais if contagem.get(r) != reais[r]}
checar("o 9900 conta certo TODOS os registros — inclusive os dele mesmo",
       not divergentes, str(divergentes)[:120])
checar("todo registro que existe no arquivo tem a sua linha 9900",
       set(reais) <= set(contagem), str(set(reais) - set(contagem)))
r9990 = linhas_de(texto, "9990")[0]
checar("o 9990 conta as linhas do bloco 9 mais o 9999, que nem é do bloco dele",
       int(r9990[1]) == contagem["9900"] + 3, f'{r9990[1]} x {contagem["9900"] + 3}')
r9999 = linhas_de(texto, "9999")[0]
checar("o 9999 conta o arquivo inteiro", int(r9999[1]) == len(linhas),
       f"{r9999[1]} x {len(linhas)}")
r0990 = linhas_de(texto, "0990")[0]
checar("o 0990 conta o bloco 0 inteiro, o 0000 e ele próprio incluídos",
       int(r0990[1]) == sum(q for r, q in reais.items() if r.startswith("0")),
       r0990[1])

# =========================================================================== #
print("\n=== 8. As três fontes viraram documento ===")
c100 = linhas_de(texto, "C100")
checar("saíram 4 documentos no bloco C", len(c100) == 4, str(len(c100)))
por_numero = {c[7]: c for c in c100}

nota_entrada = por_numero["101"]
checar("a nota importada é entrada (IND_OPER 0) de terceiro (IND_EMIT 1)",
       nota_entrada[1] == "0" and nota_entrada[2] == "1",
       f"{nota_entrada[1]}/{nota_entrada[2]}")
checar("e aponta o fornecedor pelo CNPJ no COD_PART",
       nota_entrada[3] == "98765432000110", nota_entrada[3])
checar("na entrada a data de entrada é obrigatória e está preenchida",
       nota_entrada[10] == "12012026", nota_entrada[10])

nota_saida = por_numero["201"]
checar("a NF-e emitida é saída (1) de emissão própria (0)",
       nota_saida[1] == "1" and nota_saida[2] == "0")
checar("modelo 55", nota_saida[4] == "55")
checar("situação 00 — documento regular", nota_saida[5] == "00")
checar("a chave de 44 dígitos está no lugar", len(nota_saida[8]) == 44)
checar("o valor do documento sai com vírgula decimal", nota_saida[11] == "66000,00",
       nota_saida[11])
checar("frete por conta do destinatário virou IND_FRT 1", nota_saida[16] == "1",
       nota_saida[16])

nota_cupom = por_numero["301"]
checar("o cupom entra como modelo 65", nota_cupom[4] == "65", nota_cupom[4])
checar("e sem participante — o Guia manda omitir COD_PART no cupom",
       nota_cupom[3] == "", repr(nota_cupom[3]))
checar("o cupom sai sem os campos de ST, IPI, PIS e COFINS",
       nota_cupom[23] == "" and nota_cupom[24] == ""
       and nota_cupom[25] == "" and nota_cupom[26] == "",
       str(nota_cupom[23:27]))

nota_cancelada = por_numero["202"]
checar("a nota cancelada sai com situação 02", nota_cancelada[5] == "02",
       nota_cancelada[5])
checar("e leva só a identificação — 9 campos, nada de valor",
       len(nota_cancelada) == 9, str(len(nota_cancelada)))

print("\n=== 9. Itens (C170) e analítico (C190) ===")
c170 = linhas_de(texto, "C170")
checar("no perfil A a nota de ENTRADA leva os itens", len(c170) == 1, str(len(c170)))
checar("a NF-e de emissão própria NÃO leva item — o Guia manda não informar, "
       "a SEFAZ já tem o XML", not [c for c in c170 if c[10] == "6102"])
checar("e o cupom fiscal nunca leva item: o C170 é dos modelos 01, 1B, 04 e 55",
       not [c for c in c170 if c[10] == "5102"])
item = next(c for c in c170 if c[10] == "1102")     # o item da nota de compra
checar("o item aponta o código do produto do cadastro", item[2] == cafe["codigo"],
       item[2])
checar("a quantidade sai com 5 casas, como o leiaute manda",
       item[4] == "100,00000", item[4])
checar("o CST do item é origem + CST", item[9] == "000", item[9])
checar("e o CFOP tem 4 dígitos, sem o ponto", len(item[10]) == 4, item[10])
checar("a unidade do item é a que está no 0190", item[5] == "SC", item[5])
checar("nota cancelada não gera item nenhum",
       not [c for c in c170 if c[2] and c[1] == "202"])

# o estado que exige o item da saída: o interruptor da configuração
api("PUT", "/api/sped/config", {"empresa_id": eid, "perfil": "A",
                                "itens_das_saidas": True}, t)
com_saidas = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01", None, t,
                 cru=True).decode("iso-8859-1")
itens_saida = linhas_de(com_saidas, "C170")
checar("ligando o interruptor, a NF-e emitida passa a levar os itens",
       len([c for c in itens_saida if c[10] == "6102"]) == 2,
       str(len(itens_saida)))
checar("mas o cupom continua sem item, ligado ou desligado",
       not [c for c in itens_saida if c[10] == "5102"])
api("PUT", "/api/sped/config", {"empresa_id": eid, "perfil": "A",
                                "itens_das_saidas": False}, t)

c190 = linhas_de(texto, "C190")
checar("todo documento não cancelado tem C190", len(c190) == 3, str(len(c190)))
grupos_da_saida = [c for c in c190 if c[2] == "6102" and c[1] == "000"]
checar("os dois itens de mesmo CST/CFOP/alíquota viraram UMA linha de C190",
       len(grupos_da_saida) == 1, str(len(grupos_da_saida)))
checar("e essa linha soma os dois: 52.800 + 13.200 = 66.000",
       grupos_da_saida[0][4] == "66000,00", grupos_da_saida[0][4])
checar("com o ICMS somado também: 3.696 + 924 = 4.620",
       grupos_da_saida[0][6] == "4620,00", grupos_da_saida[0][6])
chaves_c190 = [(c[1], c[2], c[3]) for c in c190]
checar("nenhuma combinação CST+CFOP+alíquota repetida no arquivo",
       len(chaves_c190) == len(set(chaves_c190)), str(chaves_c190))

print("\n=== 10. Participantes (0150), unidades (0190) e itens (0200) ===")
r0150 = linhas_de(texto, "0150")
codigos = {c[1] for c in r0150}
checar("o fornecedor e o cliente estão no cadastro de participantes",
       {"98765432000110", "11222333000144"} <= codigos, str(codigos))
checar("participante não repete", len(r0150) == len(codigos))
fornecedor_0150 = next(c for c in r0150 if c[1] == "98765432000110")
checar("pessoa jurídica preenche CNPJ e deixa o CPF vazio",
       fornecedor_0150[4] == "98765432000110" and fornecedor_0150[5] == "",
       f"{fornecedor_0150[4]}/{fornecedor_0150[5]}")
checar("e leva a inscrição estadual e o município",
       fornecedor_0150[6] == "0012345678901" and fornecedor_0150[7] == "3169307",
       f"{fornecedor_0150[6]}/{fornecedor_0150[7]}")

r0190 = linhas_de(texto, "0190")
unidades = {c[1] for c in r0190}
checar("a unidade usada no arquivo está no 0190", "SC" in unidades, str(unidades))
checar("e o 0190 não repete unidade", len(r0190) == len(unidades))
# a regra de verdade: nenhuma unidade citada no arquivo pode faltar no 0190
usadas = {c[5] for c in linhas_de(texto, "C170") if c[5]} \
    | {c[5] for c in linhas_de(texto, "0200") if c[5]} \
    | {c[2] for c in linhas_de(texto, "H010") if c[2]}
checar("nenhuma unidade citada no arquivo ficou de fora do 0190",
       usadas <= unidades, str(usadas - unidades))
r0200 = linhas_de(texto, "0200")
checar("o produto está no 0200", any(c[1] == cafe["codigo"] for c in r0200))
produto_0200 = next(c for c in r0200 if c[1] == cafe["codigo"])
checar("com o NCM", produto_0200[7] == "09011110", produto_0200[7])
checar("o tipo do item (00 = mercadoria para revenda)", produto_0200[6] == "00",
       produto_0200[6])
checar("e o gênero, que sai dos dois primeiros dígitos do NCM",
       produto_0200[9] == "09", produto_0200[9])
checar("todo item usado no C170 existe no 0200",
       {c[2] for c in c170} <= {c[1] for c in r0200},
       str({c[2] for c in c170} - {c[1] for c in r0200}))
checar("toda unidade usada no C170 existe no 0190",
       {c[5] for c in c170 if c[5]} <= unidades)

# =========================================================================== #
print("\n=== 11. A apuração do ICMS (bloco E) ===")
e110 = linhas_de(texto, "E110")[0]
checar("o débito é o ICMS das saídas: 4.620 da NF-e + 61,20 do cupom",
       e110[1] == "4681,20", e110[1])
checar("o crédito é o ICMS das entradas: 8.400", e110[5] == "8400,00", e110[5])
checar("com mais crédito que débito, não há ICMS a recolher",
       e110[12] == "0,00", e110[12])
checar("e o saldo credor de 3.718,80 é transportado para o mês seguinte",
       e110[13] == "3718,80", e110[13])
e100 = linhas_de(texto, "E100")[0]
checar("o E100 traz o período da apuração",
       e100[1] == "01012026" and e100[2] == "31012026")

previa = api("GET", f"/api/sped/previa?empresa_id={eid}&de=2026-01-01", None, t)
checar("a prévia confere com o arquivo: mesmo número de linhas",
       previa["linhas"] == len(linhas), f'{previa["linhas"]} x {len(linhas)}')
checar("e o resumo bate o crédito", previa["resumo"]["icms_credito"] == 8400.0,
       str(previa["resumo"]["icms_credito"]))
checar("o nome do arquivo leva o CNPJ e o mês",
       previa["nome"] == "SPED-FISCAL-12345678000195-202601.txt", previa["nome"])

print("\n=== 12. Simples Nacional: documentos sim, apuração não ===")
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA SPED LTDA", "cnpj": "12.345.678/0001-95",
    "inscricao_estadual": "0011223344556", "uf": "MG", "cidade": "VARGINHA",
    "codigo_municipio": "3170701", "regime_tributario": "SIMPLES NACIONAL",
    "crt": "1"}, t)
simples = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01",
              None, t, cru=True).decode("iso-8859-1")
e110_simples = linhas_de(simples, "E110")[0]
checar("no Simples o bloco E sai zerado — quem apura é o PGDAS-D",
       e110_simples[1] == "0,00" and e110_simples[5] == "0,00"
       and e110_simples[12] == "0,00", str(e110_simples[1:6]))
checar("mas os documentos continuam todos lá",
       len(linhas_de(simples, "C100")) == 4, str(len(linhas_de(simples, "C100"))))
conf_simples = api("GET", f"/api/sped/conferir?empresa_id={eid}&de=2026-01-01", None, t)
checar("e a conferência explica por que o bloco E está zerado",
       conf_simples["simples"] is True
       and any("Simples" in a for a in conf_simples["avisos"]),
       str(conf_simples["avisos"])[:90])

# =========================================================================== #
print("\n=== 13. O inventário (bloco H) ===")
sem_h = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01", None, t,
            cru=True).decode("iso-8859-1")
checar("sem marcar, o bloco H sai vazio (IND_MOV 1)",
       linhas_de(sem_h, "H001")[0][1] == "1" and not linhas_de(sem_h, "H010"))

produto = sessao.get(Produto, cafe["id"])
produto.controla_estoque = True
produto.estoque_atual = 250
produto.estoque_unidade = "SC"
produto.custo_medio = 1180.50
sessao.commit()
com_h = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01&inventario=true",
            None, t, cru=True).decode("iso-8859-1")
h010 = linhas_de(com_h, "H010")
checar("marcando, o saldo do estoque virou linha de inventário", len(h010) == 1,
       str(len(h010)))
if h010:
    checar("com a quantidade em 3 casas", h010[0][3] == "250,000", h010[0][3])
    checar("o custo médio em 6 casas", h010[0][4] == "1180,500000", h010[0][4])
    checar("e o valor do item = quantidade x custo",
           h010[0][5] == "295125,00", h010[0][5])
h005 = linhas_de(com_h, "H005")
checar("o H005 fecha o total do inventário na data do período",
       h005 and h005[0][1] == "31012026" and h005[0][2] == "295125,00",
       str(h005[0][1:3]) if h005 else "sem H005")
checar("o item inventariado também existe no 0200",
       any(c[1] == cafe["codigo"] for c in linhas_de(com_h, "0200")))
contagem_h = {c[1]: int(c[2]) for c in linhas_de(com_h, "9900")}
reais_h = {}
for linha in com_h.splitlines():
    r = campos(linha)[0]
    reais_h[r] = reais_h.get(r, 0) + 1
checar("e o bloco 9 continua contando certo com o inventário dentro",
       all(contagem_h.get(r) == q for r, q in reais_h.items()),
       str({r: (contagem_h.get(r), q) for r, q in reais_h.items()
            if contagem_h.get(r) != q})[:100])

# =========================================================================== #
print("\n=== 14. Perfil, finalidade e configuração ===")
config = api("PUT", "/api/sped/config", {
    "empresa_id": eid, "perfil": "B", "atividade": "1",
    "contador_nome": "ESCRITORIO CONTA CERTA", "contador_crc": "MG-012345",
    "contador_cpf": "111.444.777-35", "contador_email": "contato@contacerta.com.br",
    "contador_codigo_municipio": "3170701"}, t)
checar("a configuração salva o perfil", config["config"]["perfil"] == "B")
perfil_b = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01", None, t,
               cru=True).decode("iso-8859-1")
checar("o perfil salvo entra no 0000", linhas_de(perfil_b, "0000")[0][13] == "B")
checar("no perfil B (consolidado) o item do documento não sai",
       not linhas_de(perfil_b, "C170"))
checar("o interruptor dos itens da saída também salva",
       config["config"]["itens_das_saidas"] is False)
checar("mas o analítico C190 continua — é ele que o estado soma",
       len(linhas_de(perfil_b, "C190")) == 3)
checar("o contabilista virou registro 0100", len(linhas_de(perfil_b, "0100")) == 1)
r0100 = linhas_de(perfil_b, "0100")[0]
checar("com nome, CPF e CRC", r0100[1] == "ESCRITORIO CONTA CERTA"
       and r0100[2] == "11144477735" and r0100[3] == "MG-012345",
       str(r0100[1:4]))
conf_com_contador = api("GET", f"/api/sped/conferir?empresa_id={eid}&de=2026-01-01",
                        None, t)
checar("e o aviso do contabilista sumiu",
       not any("contabilista" in a for a in conf_com_contador["avisos"]))

perfil_ruim = api("PUT", "/api/sped/config",
                  {"empresa_id": eid, "perfil": "Z"}, t, esperar_erro=True)
checar("perfil que não existe é recusado", perfil_ruim.get("_status") == 400)

substituto = api("GET",
                 f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01&finalidade=1",
                 None, t, cru=True).decode("iso-8859-1")
checar("o arquivo substituto sai com COD_FIN 1",
       linhas_de(substituto, "0000")[0][2] == "1")
final_ruim = api("GET",
                 f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01&finalidade=7",
                 None, t, esperar_erro=True)
checar("finalidade fora de 0 e 1 é recusada", final_ruim.get("_status") == 400)

mes_partido = api("GET",
                  f"/api/sped/conferir?empresa_id={eid}&de=2026-01-15&ate=2026-02-10",
                  None, t, esperar_erro=True)
checar("período que atravessa o mês é recusado — a EFD é mensal",
       mes_partido.get("_status") == 400 and "mês" in str(mes_partido.get("detail")),
       str(mes_partido.get("detail"))[:60])

vazio = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-05-01", None, t,
            cru=True).decode("iso-8859-1")
checar("mês sem nota nenhuma ainda gera arquivo válido",
       linhas_de(vazio, "C001")[0][1] == "1"
       and campos(vazio.splitlines()[-1])[0] == "9999")
checar("e o 9999 do arquivo vazio também fecha",
       int(linhas_de(vazio, "9999")[0][1]) == len(vazio.splitlines()))

# =========================================================================== #
print("\n=== 15. Completar as notas de entrada ===")
falta = gravar_nota(
    chave="31" + "2603" + "98765432000110" + "55" + "001" + "000000777" + "1" + "000006238",
    origem="DFE", tipo="NFE", resumo=True, modelo="55", serie="1", numero="777",
    data_emissao=datetime(2026, 3, 10, 9, 0), emitente_cnpj="98765432000110",
    emitente_nome="FAZENDA BOA VISTA LTDA", emitente_uf="MG",
    destinatario_cnpj="12345678000195", valor_total=7000, situacao="AUTORIZADA",
)
sessao.commit()
pendencia = api("POST", "/api/sped/completar",
                {"empresa_id": eid, "de": "2026-03-01"}, t)
checar("completar responde mesmo sem certificado, sem derrubar a tela",
       pendencia.get("ok") is True, str(pendencia.get("mensagem"))[:70])
checar("e a nota continua pendente, com o motivo listado",
       pendencia["faltam"] == 1 and pendencia["falhas"],
       str(pendencia.get("falhas"))[:90])
checar("a frase diz o que fazer (certificado)",
       "certificado" in " ".join(pendencia["falhas"]).lower(),
       " ".join(pendencia["falhas"])[:80])

# =========================================================================== #
print("\n=== 16. SPED de outra conta não abre ===")
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outrosped{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra SPED", "plano": "P1_ANUAL", "uf": "MG"})
invasao = api("GET", f"/api/sped/conferir?empresa_id={eid}&de=2026-01-01",
              None, outra["token"], esperar_erro=True)
checar("conferir empresa de outra conta é recusado", invasao.get("_status") == 403,
       str(invasao.get("_status")))
invasao_arquivo = api("GET", f"/api/sped/arquivo?empresa_id={eid}&de=2026-01-01",
                      None, outra["token"], esperar_erro=True)
checar("e baixar o arquivo de outra conta também",
       invasao_arquivo.get("_status") == 403)

sessao.close()

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Todos os testes do SPED Fiscal passaram.")
