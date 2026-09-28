"""Capturas da tela do SPED Fiscal, com dados de verdade no mês.

Monta uma empresa com nota de entrada, NF-e emitida, cupom fiscal e uma nota que
ficou só como resumo, para as três situações da tela aparecerem na foto:
pendência, pronto para gerar e prévia do arquivo.

Uso:  python testes/capturar_sped.py   (com o servidor no ar)
"""
import json
import pathlib
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright          # noqa: E402

BASE = "http://127.0.0.1:8000"
SAIDA = pathlib.Path(__file__).parent / "capturas"
SAIDA.mkdir(exist_ok=True)


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


sufixo = str(int(time.time()))
email, senha = f"sped.foto{sufixo}@teste.com", "123456"
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": email, "senha": senha,
    "empresa": "Cafeeira Sul de Minas", "plano": "P4_ANUAL", "uf": "MG"})
t, eid = conta["token"], conta["empresa"]["id"]

api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "CAFEEIRA SUL DE MINAS LTDA", "nome_fantasia": "Cafeeira Sul de Minas",
    "cnpj": "12.345.678/0001-95", "inscricao_estadual": "0011223344556", "uf": "MG",
    "cidade": "VARGINHA", "codigo_municipio": "3170701", "cep": "37010-000",
    "logradouro": "AVENIDA PRINCIPAL", "numero": "1200", "bairro": "CENTRO",
    "regime_tributario": "LUCRO PRESUMIDO", "crt": "3",
    "email": "fiscal@cafeeirasul.com.br"}, t)

produtos = api("GET", f"/api/produtos?empresa_id={eid}", None, t)
cafe = produtos[0]
api("PUT", f"/api/produtos/{cafe['id']}", {
    **{k: cafe[k] for k in ("empresa_id", "codigo", "nome", "unidade_id",
                            "categoria_id", "marca_id")},
    "ncm": "09011110", "unidade_comercial": "SC", "controla_estoque": True,
    "aliquota_icms": 7, "tipo_item_sped": "00"}, t)

fornecedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "FORNECEDOR", "nome": "FAZENDA BOA VISTA LTDA",
    "cpf_cnpj": "98.765.432/0001-10", "rg_ie": "0012345678901", "cidade": "TRES PONTAS",
    "uf": "MG", "codigo_municipio": "3169307", "logradouro": "SITIO BOA VISTA",
    "numero": "S/N", "bairro": "ZONA RURAL"}, t)
cliente = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "TORREFACAO PAULISTA LTDA",
    "cpf_cnpj": "11.222.333/0001-44", "rg_ie": "111222333444", "cidade": "SAO PAULO",
    "uf": "SP", "codigo_municipio": "3550308"}, t)

from backend.database import SessionLocal                # noqa: E402
from backend.models import Nota, NotaItem, Produto       # noqa: E402

sessao = SessionLocal()
produto = sessao.get(Produto, cafe["id"])


def nota(chave, itens=(), **dados):
    n = Nota(empresa_id=eid, chave=chave, **dados)
    sessao.add(n)
    sessao.flush()
    for numero, item in enumerate(itens, start=1):
        sessao.add(NotaItem(nota_id=n.id, numero=numero, **item))
    sessao.flush()
    return n


nota("31260198765432000110" + "55" + "001" + "000000101" + "1" + "000001053",
     origem="DFE", tipo="NFE", resumo=False, modelo="55", serie="1", numero="101",
     data_emissao=datetime(2026, 1, 12, 9, 0), natureza_operacao="COMPRA DE CAFE",
     tipo_operacao="1", emitente_cnpj="98765432000110",
     emitente_nome="FAZENDA BOA VISTA LTDA", emitente_ie="0012345678901",
     emitente_uf="MG", destinatario_cnpj="12345678000195", valor_total=120000,
     valor_produtos=120000, valor_icms=8400, situacao="AUTORIZADA",
     parceiro_id=fornecedor["id"], importada=True, xml="<nfeProc/>",
     itens=[dict(codigo=produto.codigo, descricao="CAFE CRU EM GRAO", ncm="09011110",
                 cfop="1102", unidade="SC", quantidade=100, valor_unitario=1200,
                 valor_total=120000, icms_cst="00", icms_base=120000, icms_aliquota=7,
                 icms_valor=8400, origem_mercadoria="0", produto_id=produto.id)])

nota("31260112345678000195" + "55" + "001" + "000000201" + "1" + "000002386",
     origem="EMITIDA", tipo="NFE", resumo=False, modelo="55", serie="1", numero="201",
     data_emissao=datetime(2026, 1, 20, 14, 0), natureza_operacao="VENDA DE MERCADORIA",
     tipo_operacao="1", emitente_cnpj="12345678000195",
     emitente_nome="CAFEEIRA SUL DE MINAS LTDA", emitente_uf="MG",
     destinatario_cnpj="11222333000144", destinatario_nome="TORREFACAO PAULISTA LTDA",
     valor_total=66000, valor_produtos=66000, valor_icms=4620, situacao="AUTORIZADA",
     status_emissao="AUTORIZADA", ambiente="1", parceiro_id=cliente["id"],
     cfop="6102", frete_modalidade="1",
     itens=[dict(codigo=produto.codigo, descricao="CAFE CRU EM GRAO", ncm="09011110",
                 cfop="6102", unidade="SC", quantidade=50, valor_unitario=1320,
                 valor_total=66000, icms_cst="00", icms_base=66000, icms_aliquota=7,
                 icms_valor=4620, origem_mercadoria="0", produto_id=produto.id)])

for i, (numero, codigo, valor) in enumerate(
        (("301", "000003719", 340), ("302", "000004842", 180)), start=0):
    nota("31260112345678000195" + "65" + "001" + f"00000{numero}" + "1" + codigo,
         origem="EMITIDA", tipo="NFE", resumo=False, modelo="65", serie="1",
         numero=numero, data_emissao=datetime(2026, 1, 22 + i, 11, 30),
         natureza_operacao="VENDA AO CONSUMIDOR", tipo_operacao="1",
         emitente_cnpj="12345678000195", emitente_nome="CAFEEIRA SUL DE MINAS LTDA",
         emitente_uf="MG", valor_total=valor, valor_produtos=valor,
         valor_icms=round(valor * 0.18, 2), situacao="AUTORIZADA",
         status_emissao="AUTORIZADA", ambiente="1", cfop="5102",
         itens=[dict(codigo=produto.codigo, descricao="CAFE TORRADO 500G",
                     ncm="09012100", cfop="5102", unidade="UN",
                     quantidade=valor / 17, valor_unitario=17, valor_total=valor,
                     icms_cst="00", icms_base=valor, icms_aliquota=18,
                     icms_valor=round(valor * 0.18, 2), origem_mercadoria="0",
                     produto_id=produto.id)])

# a nota que a SEFAZ entregou só como resumo: é a pendência que a tela mostra
pendente = nota("31260198765432000110" + "55" + "001" + "000000777" + "1" + "000005175",
                origem="DFE", tipo="NFE", resumo=True, modelo="55", serie="1",
                numero="777", data_emissao=datetime(2026, 1, 28, 10, 0),
                emitente_cnpj="98765432000110", emitente_nome="COOPERATIVA DOS CAFEICULTORES",
                emitente_uf="MG", destinatario_cnpj="12345678000195",
                valor_total=43500, situacao="AUTORIZADA")
sessao.commit()

with sync_playwright() as p:
    navegador = p.chromium.launch()
    pagina = navegador.new_page(viewport={"width": 1440, "height": 1100})
    pagina.goto(BASE)
    pagina.wait_for_selector("#site:not(.oculto)", timeout=15000)
    pagina.click("#btn-entrar")
    pagina.wait_for_timeout(400)
    pagina.fill("input[name=email]", email)
    pagina.fill("input[name=senha]", senha)
    pagina.click("#modal-rodape >> text=Entrar")
    pagina.wait_for_selector("#app:not(.oculto)", timeout=15000)
    pagina.wait_for_timeout(1200)

    pagina.goto(f"{BASE}/#/sped")
    pagina.wait_for_timeout(1500)
    pagina.fill("input[name=mes]", "2026-01")
    pagina.dispatch_event("input[name=mes]", "change")
    pagina.wait_for_timeout(1800)
    pagina.screenshot(path=SAIDA / "sped-pendencia.png", full_page=True)
    print("sped-pendencia.png")

    # tira a pendência e fotografa a tela liberada
    sessao.delete(pendente)
    sessao.commit()
    pagina.click("#btn-conferir")
    pagina.wait_for_timeout(1800)
    pagina.screenshot(path=SAIDA / "sped-pronto.png", full_page=True)
    print("sped-pronto.png")

    pagina.click("#btn-previa")
    pagina.wait_for_timeout(2000)
    pagina.screenshot(path=SAIDA / "sped-previa.png", full_page=True)
    print("sped-previa.png")

    pagina.goto(f"{BASE}/#/sped/config")
    pagina.wait_for_timeout(1500)
    pagina.screenshot(path=SAIDA / "sped-config.png", full_page=True)
    print("sped-config.png")

    navegador.close()

sessao.close()
print("Capturas em", SAIDA)
