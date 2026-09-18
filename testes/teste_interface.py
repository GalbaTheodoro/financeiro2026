"""Teste automatizado da interface web (Playwright).

Percorre o site público, o cadastro de um novo assinante, a tela de pagamento
Pix e todas as telas internas do sistema, verificando erros de console.
As capturas ficam em testes/capturas/.

Uso:  python testes/teste_interface.py
"""
import json
import pathlib
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SAIDA = pathlib.Path(__file__).parent / "capturas"
SAIDA.mkdir(exist_ok=True)

TELAS = [
    ("painel", "Painel"),
    ("receber", "Contas a Receber"),
    ("pagar", "Contas a Pagar"),
    ("caixa", "Caixa e Bancos"),
    ("contratos", "Contratos"),
    ("dfe", "DF-e"),
    ("dfe/certificado", "DF-e"),
    ("relatorios", "Relatórios"),
    ("cadastros/parceiros", "Cadastros"),
    ("cadastros/produtos", "Cadastros"),
    ("cadastros/unidades", "Cadastros"),
    ("cadastros/modalidades", "Cadastros"),
    ("cadastros/bancos", "Cadastros"),
    ("cadastros/centros-custo", "Cadastros"),
    ("cadastros/operacoes", "Cadastros"),
    ("cadastros/plano-contas", "Cadastros"),
    ("cadastros/empresas", "Cadastros"),
    ("cadastros/usuarios", "Cadastros"),
    ("cadastros/parametros", "Cadastros"),
]

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


# garante que a chave Pix esteja configurada para a tela de pagamento aparecer completa
master = api("POST", "/api/auth/login", {"email": "admin@financeiro.local", "senha": "admin123"})
api("PUT", "/api/admin/configuracoes", {"valores": {
    "pix_chave": "financeiro@minhaempresa.com.br",
    "pix_titular": "Minha Assessoria Financeira",
    "empresa_titular": "Minha Assessoria",
    "contato_whatsapp": "(11) 90000-0000",
    "contato_email": "contato@minhaempresa.com.br",
}}, master["token"])

email_novo = f"visitante{int(time.time())}@teste.com"

# ----------------------------------------------------------------------------
# Servidor local que imita a API de CNPJ do governo, para testar a busca na tela
# ----------------------------------------------------------------------------
CNPJ_TESTE = "19131243000197"
EMPRESA_FALSA = {
    "cnpj": CNPJ_TESTE,
    "nomeEmpresarial": "COMERCIO DE PAPELARIA MODELO LTDA",
    "nomeFantasia": "PAPELARIA MODELO",
    "correioEletronico": "FINANCEIRO@PAPELARIAMODELO.COM.BR",
    "situacaoCadastral": {"codigo": "2", "descricao": "ATIVA"},
    "naturezaJuridica": {"codigo": "2062", "descricao": "Sociedade Empresaria Limitada"},
    "cnaePrincipal": {"codigo": "4761003", "descricao": "Comercio varejista de artigos de papelaria"},
    "endereco": {"tipoLogradouro": "RUA", "logradouro": "DAS FLORES", "numero": "250",
                 "complemento": "LOJA 2", "bairro": "CENTRO", "cep": "13010100",
                 "municipio": {"descricao": "CAMPINAS"}, "uf": "SP"},
    "telefones": [{"ddd": "19", "numero": "32221100"}],
    "socios": [{"nome": "ANA MARTINS", "qualificacao": {"descricao": "Socio-Administrador"}}],
}

CEP_TESTE = "13010100"
ENDERECO_FALSO = {
    "cep": CEP_TESTE, "uf": "SP", "localidade": "Campinas", "bairro": "Centro",
    "logradouro": "Rua das Flores", "complemento": "de 200 a 400 - lado par",
}


class ApiFalsa(BaseHTTPRequestHandler):
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
        self._json(200, {"access_token": "token-de-teste", "token": "token-de-teste",
                         "expires_in": 3600})

    def do_GET(self):
        if "/cep/v2/enderecos/" in self.path:
            return self._json(200, ENDERECO_FALSO)
        self._json(200, EMPRESA_FALSA)


servidor_cnpj = HTTPServer(("127.0.0.1", 8098), ApiFalsa)
threading.Thread(target=servidor_cnpj.serve_forever, daemon=True).start()
configuracao_cnpj_original = api("GET", "/api/admin/configuracoes", token=master["token"])["valores"]
api("PUT", "/api/admin/configuracoes", {"valores": {
    "cnpj_provedor": "CONECTA_GOV",
    "cnpj_endpoint": "http://127.0.0.1:8098",
    "cnpj_tipo_consulta": "empresa",
    "cnpj_consumer_key": "chave-de-teste",
    "cnpj_consumer_secret": "segredo-de-teste",
    "cnpj_cpf_usuario": "12345678909",
    "cep_provedor": "CORREIOS",
    "cep_endpoint": "http://127.0.0.1:8098",
    "cep_usuario": "usuario-teste",
    "cep_senha": "senha-teste",
    "cep_cartao_postagem": "0057018901",
}}, master["token"])

with sync_playwright() as p:
    navegador = p.chromium.launch()
    pagina = navegador.new_page(viewport={"width": 1500, "height": 950})
    def registrar_console(m):
        # o 402 do bloqueio de assinatura é esperado no teste
        if m.type == "error" and "402" not in m.text:
            erros.append(f"console {m.type}: {m.text}")

    pagina.on("console", registrar_console)
    pagina.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))

    # ------------------------------------------------------------------ site
    pagina.goto(BASE)
    pagina.wait_for_selector("#site:not(.oculto)", timeout=15000)
    pagina.wait_for_timeout(900)
    texto = pagina.inner_text("#site").replace("\u00a0", " ")
    for termo in ["contratos de assessoria", "Contas a receber", "Contas a pagar", "DRE",
                  "Balancete", "Planos", "Como funciona", "R$ 350,00", "R$ 600,00",
                  "48 horas", "Fechado a Receber", "Recebido Total"]:
        ok = termo.lower() in texto.lower()
        print(f"  [{'OK  ' if ok else 'FALHA'}] site mostra “{termo}”")
        if not ok:
            erros.append(f"site sem o texto {termo}")
    secao = pagina.query_selector("#contratos-site")
    ok_secao = secao is not None and "corretagem" in secao.inner_text().lower()
    print(f"  [{'OK  ' if ok_secao else 'FALHA'}] site tem a seção do contrato de assessoria")
    if not ok_secao:
        erros.append("site sem a seção do contrato de assessoria")
    pagina.screenshot(path=SAIDA / "00-site.png", full_page=True)

    # ------------------------------------------------------------- cadastro
    pagina.click("#btn-criar-conta")
    pagina.wait_for_timeout(500)
    pagina.fill('input[name=nome]', "Visitante de Teste")
    pagina.fill('input[name=email]', email_novo)
    pagina.fill('input[name=senha]', "123456")
    pagina.fill('input[name=empresa]', "Empresa do Visitante")
    pagina.select_option('select[name=plano]', "ANUAL")
    pagina.screenshot(path=SAIDA / "01-cadastro.png")
    pagina.click("text=Criar conta e começar")
    pagina.wait_for_selector("#app:not(.oculto)", timeout=15000)
    pagina.wait_for_timeout(1200)
    boas_vindas = "Bem-vindo" in pagina.inner_text("#modal-titulo")
    print(f"  [{'OK  ' if boas_vindas else 'FALHA'}] cadastro cria a conta e entra no sistema")
    if not boas_vindas:
        erros.append("modal de boas-vindas não apareceu")
    pagina.screenshot(path=SAIDA / "02-boas-vindas.png")
    pagina.click("text=Começar a usar")
    pagina.wait_for_timeout(600)

    faixa = pagina.inner_text("#faixa-assinatura")
    ok_faixa = "teste" in faixa.lower()
    print(f"  [{'OK  ' if ok_faixa else 'FALHA'}] faixa de teste no topo -> {faixa[:60]}")
    if not ok_faixa:
        erros.append("faixa do período de teste ausente")

    # ------------------------------------------------------ minha assinatura
    pagina.goto(f"{BASE}/#/assinatura")
    pagina.wait_for_timeout(1200)
    conteudo = pagina.inner_text("#pagina")
    ok_pix = "Pix" in conteudo and "Já fiz o Pix" in conteudo
    tem_qr = pagina.query_selector("#area-pagamento svg") is not None
    print(f"  [{'OK  ' if ok_pix else 'FALHA'}] tela de assinatura com dados do Pix")
    print(f"  [{'OK  ' if tem_qr else 'FALHA'}] QR Code renderizado")
    if not ok_pix:
        erros.append("tela de assinatura incompleta")
    if not tem_qr:
        erros.append("QR Code não renderizado")
    pagina.screenshot(path=SAIDA / "03-assinatura.png", full_page=True)

    # ---------------------------------------------------------- telas do app
    for i, (rota, titulo) in enumerate(TELAS, start=4):
        pagina.goto(f"{BASE}/#/{rota}")
        pagina.wait_for_timeout(1000)
        atual = pagina.inner_text("#titulo-pagina")
        vazio = pagina.query_selector("#pagina .vazio")
        texto_vazio = vazio.inner_text() if vazio else ""
        ok = titulo.lower() in atual.lower() and "Carregando" not in texto_vazio
        print(f"  [{'OK  ' if ok else 'FALHA'}] tela {rota} -> {atual} {texto_vazio[:50]}")
        if not ok:
            erros.append(f"tela {rota} não carregou")
        pagina.screenshot(path=SAIDA / f"{i:02d}-{rota.replace('/', '-')}.png", full_page=True)

    # ------------------------------------------------ menu único de cadastros
    pagina.goto(f"{BASE}/#/cadastros")
    pagina.wait_for_timeout(1200)
    abas = pagina.eval_on_selector_all(".abas [data-cad]", "els => els.map(e => e.dataset.cad)")
    ok_abas = {"parceiros", "produtos", "unidades", "modalidades", "usuarios"} <= set(abas)
    print(f"  [{'OK  ' if ok_abas else 'FALHA'}] menu Cadastros com todas as abas ({len(abas)})")
    if not ok_abas:
        erros.append("menu de cadastros incompleto")

    itens_menu = pagina.eval_on_selector_all(
        "#menu .menu-item", "els => els.map(e => e.dataset.rota)")
    ok_menu = "/cadastros" in itens_menu and "/parceiros" not in itens_menu
    print(f"  [{'OK  ' if ok_menu else 'FALHA'}] barra lateral com um item único de cadastros")
    if not ok_menu:
        erros.append("barra lateral ainda tem os cadastros soltos")

    # unidade nova pela tela, já usada no contrato mais abaixo
    pagina.goto(f"{BASE}/#/cadastros/unidades")
    pagina.wait_for_timeout(1100)
    pagina.click("#btn-novo")
    pagina.wait_for_timeout(600)
    pagina.fill('input[name=codigo]', "BAG")
    pagina.fill('input[name=nome]', "Big bag de 1.200 kg")
    pagina.fill('input[name=peso_conversao]', "1200")
    pagina.click("#modal-rodape >> text=Salvar")
    pagina.wait_for_timeout(1300)
    lista_unidades = pagina.inner_text("#area-cadastro")
    ok_unidade = "BIG BAG" in lista_unidades.upper() and "1.200" in lista_unidades
    print(f"  [{'OK  ' if ok_unidade else 'FALHA'}] cadastro de unidade com peso de conversão")
    if not ok_unidade:
        erros.append("cadastro de unidade não gravou")
    pagina.screenshot(path=SAIDA / "20-cadastro-unidade.png", full_page=True)

    # ------------------------------- formas de pagamento do cliente/fornecedor
    pagina.goto(f"{BASE}/#/cadastros/parceiros")
    pagina.wait_for_timeout(1100)
    pagina.click("#btn-novo")
    pagina.wait_for_timeout(600)
    pagina.fill('input[name=nome]', "Fornecedor da Tela Ltda")
    pagina.select_option('select[name=tipo]', "FORNECEDOR")
    pagina.click("#modal-rodape >> text=Salvar")
    pagina.wait_for_timeout(1400)

    tem_botao_pagamento = pagina.query_selector('[data-acao="0"]') is not None
    print(f"  [{'OK  ' if tem_botao_pagamento else 'FALHA'}] botão de pagamento na lista de parceiros")
    if not tem_botao_pagamento:
        erros.append("botão de formas de pagamento ausente")
    else:
        pagina.click('[data-acao="0"]')
        pagina.wait_for_selector("#btn-nova-forma", timeout=15000)
        pagina.click("#btn-nova-forma")
        pagina.wait_for_timeout(500)
        pagina.fill('input[name=pix_chave]', "financeiro@fornecedordatela.com.br")
        pagina.fill('input[name=apelido]', "Pix da matriz")
        pagina.click("#btn-salvar-forma")
        pagina.wait_for_selector(".forma-cartao", timeout=15000)
        pagina.wait_for_timeout(500)

        # segunda forma: conta bancária
        pagina.click("#btn-nova-forma")
        pagina.wait_for_timeout(400)
        pagina.select_option('select[name=tipo]', "DEPOSITO")
        pagina.wait_for_timeout(300)
        pagina.fill('input[name=banco_codigo]', "341")
        pagina.fill('input[name=banco_nome]', "Itau")
        pagina.fill('input[name=agencia]', "1234")
        pagina.fill('input[name=conta]', "56789-0")
        pagina.click("#btn-salvar-forma")
        pagina.wait_for_timeout(1200)

        cartoes = pagina.query_selector_all(".forma-cartao")
        texto_formas = pagina.inner_text("#lista-formas")
        ok_duas = len(cartoes) == 2
        ok_conteudo = ("financeiro@fornecedordatela.com.br" in texto_formas
                       and "341 Itau" in texto_formas
                       and "principal" in texto_formas.lower())
        print(f"  [{'OK  ' if ok_duas else 'FALHA'}] duas formas cadastradas pela tela ({len(cartoes)})")
        print(f"  [{'OK  ' if ok_conteudo else 'FALHA'}] cartões mostram Pix, conta e a principal")
        if not ok_duas:
            erros.append("formas de pagamento não apareceram")
        if not ok_conteudo:
            erros.append("conteúdo das formas de pagamento incompleto")
        pagina.screenshot(path=SAIDA / "25-formas-pagamento.png", full_page=True)
        pagina.click("#modal-rodape >> text=Fechar")
        pagina.wait_for_timeout(1500)

        coluna = pagina.inner_text("#lista-cadastro")
        ok_coluna = "Pix" in coluna or "341" in coluna
        print(f"  [{'OK  ' if ok_coluna else 'FALHA'}] coluna “Onde pagar” na lista")
        if not ok_coluna:
            erros.append("coluna de formas de pagamento vazia")

    # ------------------------------------- contrato de intermediação na tela
    # o contrato precisa de duas partes: cria a segunda pela tela
    pagina.goto(f"{BASE}/#/cadastros/parceiros")
    pagina.wait_for_timeout(1000)
    pagina.click("#btn-novo")
    pagina.wait_for_timeout(600)
    pagina.fill('input[name=nome]', "Comprador da Tela Ltda")
    pagina.click("#modal-rodape >> text=Salvar")
    pagina.wait_for_timeout(1400)

    pagina.goto(f"{BASE}/#/contratos")
    pagina.wait_for_timeout(1100)
    pagina.click("#btn-novo-contrato")
    pagina.wait_for_timeout(800)

    # o formulário vem dividido em etapas: 1 Identificação ... 5 Embarque
    etapas = pagina.eval_on_selector_all(
        "#barra-etapas [data-etapa]", "els => els.map(e => e.innerText.trim())")
    ok_etapas = len(etapas) == 5
    print(f"  [{'OK  ' if ok_etapas else 'FALHA'}] contrato dividido em etapas ({len(etapas)})")
    if not ok_etapas:
        erros.append("formulário do contrato não está em etapas")

    numero_sugerido = pagina.input_value('input[name=numero]')
    ok_numero = numero_sugerido.isdigit() and len(numero_sugerido) == 8
    print(f"  [{'OK  ' if ok_numero else 'FALHA'}] número automático sugerido -> {numero_sugerido}")
    if not ok_numero:
        erros.append("numeração automática do contrato não apareceu")
    pagina.fill('input[name=numero]', "00000295")

    # etapa 1: produto, modalidade e representante
    for campo in ("produto_id", "modalidade_id", "representante_id"):
        valores = pagina.eval_on_selector_all(
            f'select[name={campo}] option', "els => els.map(e => e.value).filter(Boolean)")
        ok_campo = len(valores) > 0
        print(f"  [{'OK  ' if ok_campo else 'FALHA'}] {campo} com opções ({len(valores)})")
        if not ok_campo:
            erros.append(f"{campo} sem opções no contrato")
        else:
            pagina.select_option(f'select[name={campo}]', valores[0])
    pagina.screenshot(path=SAIDA / "26-contrato-etapa1.png", full_page=True)

    # a etapa das partes não deixa passar sem comprador e vendedor
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    barrou = pagina.query_selector('select[name=comprador_id]') is not None
    print(f"  [{'OK  ' if barrou else 'FALHA'}] etapa das partes exige comprador e vendedor")
    if not barrou:
        erros.append("etapa das partes deixou passar sem as partes")

    opcoes = pagina.eval_on_selector_all(
        'select[name=comprador_id] option', "els => els.map(e => e.value).filter(Boolean)")
    ok_partes = len(opcoes) >= 2
    print(f"  [{'OK  ' if ok_partes else 'FALHA'}] comprador e vendedor disponíveis ({len(opcoes)})")
    if not ok_partes:
        erros.append("faltam parceiros para montar o contrato")
    else:
        pagina.select_option('select[name=comprador_id]', opcoes[0])
        pagina.select_option('select[name=vendedor_id]', opcoes[1])

    # etapa 3: quantidade, unidade e preço
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    unidades = pagina.eval_on_selector_all(
        'select[name=unidade_id] option', "els => els.map(e => e.value).filter(Boolean)")
    ok_unidade = len(unidades) > 0
    print(f"  [{'OK  ' if ok_unidade else 'FALHA'}] unidade_id com opções ({len(unidades)})")
    if not ok_unidade:
        erros.append("unidade_id sem opções no contrato")
    else:
        pagina.select_option('select[name=unidade_id]', unidades[0])
    pagina.fill('input[name=quantidade]', "330")
    pagina.fill('input[name=preco_unitario]', "1320")
    pagina.dispatch_event('input[name=preco_unitario]', "input")
    pagina.wait_for_timeout(400)

    resumo = pagina.inner_text("#resumo-calculo").replace("\u00a0", " ")
    ok_peso = "Peso total" in resumo and "kg" in resumo
    print(f"  [{'OK  ' if ok_peso else 'FALHA'}] peso total pela unidade -> "
          f"{resumo[resumo.find('Peso total'):][:40]}")
    if not ok_peso:
        erros.append("peso total não calculado na tela do contrato")

    # etapa 4: corretagem dos dois lados
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    pagina.fill('input[name=comissao_comprador_percentual]', "0.5")
    pagina.dispatch_event('input[name=comissao_comprador_percentual]', "input")
    pagina.fill('input[name=comissao_vendedor_percentual]', "0.5")
    pagina.dispatch_event('input[name=comissao_vendedor_percentual]', "input")
    pagina.wait_for_timeout(400)
    resumo = pagina.inner_text("#resumo-calculo").replace("\u00a0", " ")
    ok_calculo = "R$ 435.600,00" in resumo and resumo.count("R$ 2.178,00") >= 2
    print(f"  [{'OK  ' if ok_calculo else 'FALHA'}] cálculo ao vivo do contrato -> "
          f"{resumo[:60].replace(chr(10), ' ')}")
    if not ok_calculo:
        erros.append("cálculo do contrato incorreto na tela")

    # etapa 5: embarque e classificação
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    ultima = pagina.query_selector('textarea[name=observacao]') is not None
    print(f"  [{'OK  ' if ultima else 'FALHA'}] última etapa com embarque e classificação")
    if not ultima:
        erros.append("última etapa do contrato não apareceu")
    pagina.screenshot(path=SAIDA / "27-contrato-form.png", full_page=True)

    if len(opcoes) >= 2:
        pagina.click("#modal-rodape >> text=Salvar e abrir")
        pagina.wait_for_selector("text=Gerar contas a receber", timeout=15000)
        pagina.wait_for_timeout(800)
        # impressão: o botão abre a folha do contrato numa janela nova
        with pagina.context.expect_page() as nova:
            pagina.click("#modal-rodape >> text=Imprimir")
        folha = nova.value
        folha.wait_for_load_state()
        folha.wait_for_timeout(700)
        texto_folha = folha.inner_text("body").replace("\u00a0", " ")
        # o t\u00edtulo sai em mai\u00fasculas por CSS (text-transform)
        ok_impressao = ("contrato de intermedia\u00e7\u00e3o" in texto_folha.lower()
                        and "00000295" in texto_folha
                        and "R$ 4.356,00" in texto_folha)
        print(f"  [{'OK  ' if ok_impressao else 'FALHA'}] folha de impress\u00e3o do contrato aberta")
        if not ok_impressao:
            erros.append("folha de impress\u00e3o do contrato n\u00e3o abriu")
        folha.screenshot(path=SAIDA / "30-contrato-impressao.png", full_page=True)
        folha.close()
        pagina.wait_for_timeout(400)

        ficha = pagina.inner_text("#modal-corpo").replace("\u00a0", " ")
        ok_ficha = "R$ 4.356,00" in ficha and "total a receber" in ficha.lower()
        print(f"  [{'OK  ' if ok_ficha else 'FALHA'}] ficha do contrato com a comissão total")
        if not ok_ficha:
            erros.append("ficha do contrato incompleta")
        pagina.screenshot(path=SAIDA / "28-contrato-ficha.png", full_page=True)

        pagina.click("#modal-rodape >> text=Gerar contas a receber")
        pagina.wait_for_timeout(1800)
        depois = pagina.inner_text("#modal-corpo").replace("\u00a0", " ")
        ok_gerado = ("fechado a receber" in depois.lower()
                     and depois.count("R$ 2.178,00") >= 2)
        print(f"  [{'OK  ' if ok_gerado else 'FALHA'}] contas a receber geradas pela tela")
        if not ok_gerado:
            erros.append("geração de recebíveis não refletiu na ficha")
        pagina.screenshot(path=SAIDA / "29-contrato-faturado.png", full_page=True)
        pagina.evaluate("UI.fecharModal()")
        pagina.wait_for_timeout(900)

        pagina.goto(f"{BASE}/#/receber")
        pagina.wait_for_timeout(1300)
        receber = pagina.inner_text("#lista-parcelas")
        ok_titulos = receber.count("00000295") >= 2 and "Corretagem" in receber
        print(f"  [{'OK  ' if ok_titulos else 'FALHA'}] títulos da corretagem em Contas a Receber")
        if not ok_titulos:
            erros.append("títulos do contrato não apareceram em contas a receber")

    pagina.evaluate("UI.fecharModal()")   # garante que nada fique aberto por cima
    pagina.wait_for_timeout(400)

    # ------------------------------------------------------ abas de relatório
    pagina.goto(f"{BASE}/#/relatorios")
    pagina.wait_for_timeout(900)
    for aba in ["dre", "balancete", "receber", "pagar", "fluxo", "contratos", "centro",
                "conta", "operacao", "parceiro", "razao"]:
        pagina.click(f'[data-aba="{aba}"]')
        pagina.wait_for_timeout(800)
        conteudo = pagina.inner_text("#area-relatorio")
        ok = "Gerando relatório" not in conteudo and len(conteudo) > 50
        print(f"  [{'OK  ' if ok else 'FALHA'}] relatório {aba}")
        if not ok:
            erros.append(f"relatório {aba} vazio")
    pagina.screenshot(path=SAIDA / "rel-dre.png", full_page=True)

    pagina.click('[data-aba="contratos"]')
    pagina.wait_for_timeout(1100)
    rel = pagina.inner_text("#area-relatorio").replace("\u00a0", " ")
    ok_rel = ("00000295" in rel and "R$ 4.356,00" in rel
              and "fechado a receber" in rel.lower())
    print(f"  [{'OK  ' if ok_rel else 'FALHA'}] relatório de contratos mostra situação e comissão")
    if not ok_rel:
        erros.append("relatório de contratos incompleto")
    pagina.screenshot(path=SAIDA / "31-relatorio-contratos.png", full_page=True)

    # --------------------------------------------------- bloqueio após teste
    assinaturas = api("GET", "/api/admin/assinaturas", token=master["token"])["linhas"]
    alvo = next(a for a in assinaturas if a["usuario_email"] == email_novo)
    api("POST", f"/api/admin/assinaturas/{alvo['id']}/status",
        {"status": "TESTE", "horas_teste": 0}, master["token"])
    pagina.goto(f"{BASE}/#/painel")
    pagina.wait_for_selector("#tela-pagamento:not(.oculto)", timeout=15000)
    pagina.wait_for_timeout(1200)
    bloqueio = pagina.inner_text("#tela-pagamento")
    ok_bloqueio = "teste" in bloqueio.lower() and "Já fiz o Pix" in bloqueio
    print(f"  [{'OK  ' if ok_bloqueio else 'FALHA'}] conta bloqueada mostra a tela de pagamento")
    if not ok_bloqueio:
        erros.append("tela de bloqueio não apareceu")
    pagina.screenshot(path=SAIDA / "20-bloqueio.png", full_page=True)

    # ------------------------------------------------- área do administrador
    pagina.evaluate("localStorage.removeItem('fin_token')")
    pagina.goto(BASE)
    pagina.wait_for_selector("#site:not(.oculto)", timeout=15000)
    pagina.click("#btn-entrar")
    pagina.wait_for_timeout(400)
    pagina.fill('input[name=email]', "admin@financeiro.local")
    pagina.fill('input[name=senha]', "admin123")
    pagina.click("#modal-rodape >> text=Entrar")
    pagina.wait_for_selector("#app:not(.oculto)", timeout=15000)
    pagina.wait_for_timeout(1000)

    pagina.goto(f"{BASE}/#/admin-assinaturas")
    pagina.wait_for_timeout(1200)
    admin_txt = pagina.inner_text("#pagina")
    ok_admin = "Assinantes" in admin_txt and "Confirmar Pix" in admin_txt
    print(f"  [{'OK  ' if ok_admin else 'FALHA'}] painel de assinaturas do administrador")
    if not ok_admin:
        erros.append("painel de assinaturas incompleto")
    pagina.screenshot(path=SAIDA / "21-admin-assinaturas.png", full_page=True)

    pagina.goto(f"{BASE}/#/configuracoes")
    pagina.wait_for_timeout(1000)
    ok_config = "Recebimento por Pix" in pagina.inner_text("#pagina")
    print(f"  [{'OK  ' if ok_config else 'FALHA'}] tela de configurações do site")
    if not ok_config:
        erros.append("tela de configurações incompleta")
    pagina.screenshot(path=SAIDA / "22-configuracoes.png", full_page=True)

    # ------------------------------------------- busca de CNPJ no cadastro
    pagina.goto(f"{BASE}/#/cadastros/parceiros")
    pagina.wait_for_timeout(1100)
    pagina.click("#btn-novo")
    pagina.wait_for_timeout(700)
    tem_botao = pagina.query_selector(".campo-com-botao button") is not None
    print(f"  [{'OK  ' if tem_botao else 'FALHA'}] botão Buscar ao lado do CPF/CNPJ")
    if not tem_botao:
        erros.append("botão de busca de CNPJ ausente")
    else:
        pagina.fill('input[name=cpf_cnpj]', CNPJ_TESTE)
        pagina.click(".campo-com-botao button")
        pagina.wait_for_selector(".resultado-consulta:not(.oculto)", timeout=15000)
        pagina.wait_for_timeout(600)
        valores = pagina.evaluate("""() => {
            const v = (n) => document.querySelector(`#modal-corpo [name=${n}]`)?.value || '';
            return {nome: v('nome'), fantasia: v('nome_fantasia'), logradouro: v('logradouro'),
                    numero: v('numero'), bairro: v('bairro'), cidade: v('cidade'),
                    uf: v('uf'), cep: v('cep'), telefone: v('telefone'), email: v('email'),
                    pessoa: v('pessoa')};
        }""")
        esperado = {
            "nome": "COMERCIO DE PAPELARIA MODELO LTDA", "fantasia": "PAPELARIA MODELO",
            "logradouro": "RUA DAS FLORES", "numero": "250", "bairro": "CENTRO",
            "cidade": "CAMPINAS", "uf": "SP", "cep": "13010-100",
            "telefone": "(19) 32221100", "email": "financeiro@papelariamodelo.com.br",
            "pessoa": "J",
        }
        for campo, valor in esperado.items():
            ok = valores.get(campo) == valor
            print(f"  [{'OK  ' if ok else 'FALHA'}] busca preencheu {campo} -> {valores.get(campo)!r}")
            if not ok:
                erros.append(f"campo {campo} não preenchido pela busca de CNPJ")
        resumo = pagina.inner_text(".resultado-consulta")
        ok_resumo = "ATIVA" in resumo and "ANA MARTINS" in resumo
        print(f"  [{'OK  ' if ok_resumo else 'FALHA'}] resumo mostra situação e sócios")
        if not ok_resumo:
            erros.append("resumo da consulta incompleto")
        pagina.screenshot(path=SAIDA / "23-busca-cnpj.png")
        pagina.evaluate("UI.fecharModal()")
        pagina.wait_for_timeout(400)

    # ---------------------------------------------- busca de CEP no cadastro
    pagina.goto(f"{BASE}/#/cadastros/empresas")
    pagina.wait_for_timeout(1100)
    pagina.click("#btn-novo")
    pagina.wait_for_timeout(700)
    tem_cep = pagina.query_selector(".campo-com-botao button") is not None
    print(f"  [{'OK  ' if tem_cep else 'FALHA'}] botão Buscar ao lado do CEP")
    if not tem_cep:
        erros.append("botão de busca de CEP ausente")
    else:
        pagina.fill('input[name=cep]', CEP_TESTE)
        pagina.click(".campo-com-botao button")
        pagina.wait_for_timeout(1400)
        endereco = pagina.evaluate("""() => {
            const v = (n) => document.querySelector(`#modal-corpo [name=${n}]`)?.value || '';
            return {cep: v('cep'), logradouro: v('logradouro'), bairro: v('bairro'),
                    cidade: v('cidade'), uf: v('uf')};
        }""")
        esperado_cep = {"cep": "13010-100", "logradouro": "Rua das Flores",
                        "bairro": "Centro", "cidade": "Campinas", "uf": "SP"}
        for campo, valor in esperado_cep.items():
            ok = endereco.get(campo) == valor
            print(f"  [{'OK  ' if ok else 'FALHA'}] CEP preencheu {campo} -> {endereco.get(campo)!r}")
            if not ok:
                erros.append(f"campo {campo} não preenchido pela busca de CEP")
        pagina.screenshot(path=SAIDA / "24-busca-cep.png")
        pagina.evaluate("UI.fecharModal()")

    api("PUT", "/api/admin/configuracoes", {"valores": {
        k: configuracao_cnpj_original.get(k, "")
        for k in configuracao_cnpj_original if k.startswith(("cnpj_", "cep_"))
    }}, master["token"])
    servidor_cnpj.shutdown()
    navegador.close()

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} problema(s):")
    for e in dict.fromkeys(erros):
        print("  -", e)
    sys.exit(1)
print("Interface OK — capturas em testes/capturas/")
