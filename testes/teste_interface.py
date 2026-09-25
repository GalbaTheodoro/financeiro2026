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
    ("notas", "Notas Fiscais"),
    ("cupom", "Cupom Fiscal"),
    ("gta", "GTA"),
    ("estoque", "Estoque"),
    ("estoque/extrato", "Estoque"),
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
    "ibge": "3509502",   # código do município, exigido na nota fiscal
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
                  "Balancete", "Planos", "Como funciona", "R$ 399,90", "R$ 1.069,90", "Plano 4",
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
    # o plano completo: é ele que faz o menu mostrar cupom fiscal e GTA
    pagina.select_option('select[name=plano]', "P4_ANUAL")
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

    # ----------------------------------------- o menu é o que o plano libera
    blocos = pagina.eval_on_selector_all(
        ".plano-bloco .forte", "els => els.map(e => e.innerText.trim())")
    ok_quatro = len([b for b in blocos if b.startswith("Plano ")]) == 4
    print(f"  [{'OK  ' if ok_quatro else 'FALHA'}] tela da assinatura com os quatro planos "
          f"({[b for b in blocos if b.startswith('Plano ')]})")
    if not ok_quatro:
        erros.append("a tela da assinatura não mostrou os quatro planos")

    rotas_menu = lambda: pagina.eval_on_selector_all(   # noqa: E731
        "#menu .menu-item", "els => els.map(e => e.dataset.rota)")
    com_tudo = rotas_menu()
    ok_p4 = "/cupom" in com_tudo and "/gta" in com_tudo
    print(f"  [{'OK  ' if ok_p4 else 'FALHA'}] no Plano 4 o menu traz cupom fiscal e GTA")
    if not ok_p4:
        erros.append("menu do Plano 4 sem cupom ou sem GTA")

    # troca para o Plano 1 pela própria tela e confere que os dois somem
    pagina.check('input[name=plano][value="P1_SEMESTRAL"]')
    pagina.wait_for_timeout(1500)
    so_basico = rotas_menu()
    ok_p1 = "/cupom" not in so_basico and "/gta" not in so_basico \
        and "/contratos" in so_basico and "/notas" in so_basico
    print(f"  [{'OK  ' if ok_p1 else 'FALHA'}] no Plano 1 eles somem do menu, o resto fica "
          f"({len(so_basico)} itens)")
    if not ok_p1:
        erros.append("menu do Plano 1 não escondeu cupom/GTA")
    pagina.screenshot(path=SAIDA / "03b-menu-plano-1.png", full_page=True)

    # e o endereço digitado à mão também é barrado
    pagina.goto(f"{BASE}/#/gta")
    pagina.wait_for_timeout(1200)
    titulo_atual = pagina.inner_text("#titulo-pagina")
    ok_barrado = "GTA" not in titulo_atual
    print(f"  [{'OK  ' if ok_barrado else 'FALHA'}] endereço da GTA digitado à mão é barrado "
          f"-> {titulo_atual}")
    if not ok_barrado:
        erros.append("rota fora do plano abriu ao ser digitada")

    pagina.goto(f"{BASE}/#/assinatura")
    pagina.wait_for_timeout(1200)
    pagina.check('input[name=plano][value="P4_ANUAL"]')
    pagina.wait_for_timeout(1500)
    voltou = rotas_menu()
    ok_volta = "/cupom" in voltou and "/gta" in voltou
    print(f"  [{'OK  ' if ok_volta else 'FALHA'}] voltando ao Plano 4 eles reaparecem")
    if not ok_volta:
        erros.append("menu não voltou ao trocar de plano")

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

    # ------------------------------------------- GTA — guia de trânsito animal
    # A tela não emite nada: ela confere o que o portal do estado vai cobrar e
    # imprime a ficha de preparo. É isso que se testa aqui.
    pagina.goto(f"{BASE}/#/gta")
    pagina.wait_for_timeout(1000)
    aviso_gta = pagina.inner_text("#pagina").lower()
    # o aviso tem de dizer as duas coisas: que a emissão é no portal do estado e
    # que o webservice que existe (o da PGA) não emite guia nenhuma
    ok_aviso = ("webservice para emitir" in aviso_gta and "siapec" in aviso_gta
                and "pga" in aviso_gta and "já emitida" in aviso_gta)
    print(f"  [{'OK  ' if ok_aviso else 'FALHA'}] tela da GTA explica que quem emite é o portal")
    if not ok_aviso:
        erros.append("tela da GTA não explica de onde sai a guia")

    pagina.click("#btn-nova-gta")
    pagina.wait_for_timeout(700)
    faltas = pagina.query_selector("#faltas-gta")
    pagina.select_option('#modal-corpo [name="especie"]', "BOVINO")
    pagina.wait_for_timeout(300)
    pagina.click("#btn-add-cat")
    pagina.wait_for_timeout(300)
    opcoes_faixa = pagina.eval_on_selector_all(
        '#modal-corpo [name="cat_faixa_0"] option', "els => els.map(e => e.value)")
    ok_faixas = "13 a 24 meses" in opcoes_faixa
    print(f"  [{'OK  ' if ok_faixas else 'FALHA'}] categorias com as faixas do bovino "
          f"({len(opcoes_faixa)})")
    if not ok_faixas:
        erros.append("faixas de idade do bovino não apareceram")

    # trocar a faixa redesenha a tabela das categorias — por isso vem antes da quantidade
    pagina.select_option('#modal-corpo [name="cat_faixa_0"]', "13 a 24 meses")
    pagina.wait_for_timeout(300)
    pagina.fill('#modal-corpo [name="cat_qtd_0"]', "12")
    pagina.select_option('#modal-corpo [name="finalidade"]', "ABATE")
    pagina.fill('#modal-corpo [name="origem_nome"]', "JOSE DA SILVA")
    pagina.fill('#modal-corpo [name="origem_propriedade"]', "FAZENDA BOA ESPERANCA")
    pagina.fill('#modal-corpo [name="origem_inscricao"]', "0011223344556")
    pagina.fill('#modal-corpo [name="origem_municipio"]', "Patrocínio")
    pagina.select_option('#modal-corpo [name="origem_uf"]', "MG")
    pagina.click('#modal-rodape button:text-is("Salvar")')
    pagina.wait_for_timeout(1200)

    texto_lista = pagina.inner_text("#lista-gta")
    ok_lista = "BOA ESPERANCA" in texto_lista.upper() and "12 animais" in texto_lista
    print(f"  [{'OK  ' if ok_lista else 'FALHA'}] guia gravada aparece na lista com os animais")
    if not ok_lista:
        erros.append("guia não apareceu na lista da GTA")

    pagina.click('#lista-gta [data-abrir="0"]')
    pagina.wait_for_timeout(800)
    conferencia = pagina.inner_text("#faltas-gta")
    ok_conferencia = "destino" in conferencia.lower() and "portal" in conferencia.lower()
    print(f"  [{'OK  ' if ok_conferencia else 'FALHA'}] a conferência cobra o que falta "
          f"-> {conferencia[:60].replace(chr(10), ' ')}")
    if not ok_conferencia:
        erros.append("conferência da GTA não listou as pendências")
    if faltas is None:
        erros.append("painel de conferência da GTA não existe no formulário")

    with pagina.context.expect_page() as nova:
        pagina.click('#modal-rodape button:text-is("Ficha de preparo")')
    folha = nova.value
    folha.wait_for_timeout(900)
    # os títulos das seções vão em maiúscula pelo CSS, então a conferência ignora caixa
    texto_folha = folha.inner_text("body").lower()
    ok_folha = "siapec" in texto_folha and "1. origem" in texto_folha \
        and "não é a gta" in texto_folha and "13 a 24 meses" in texto_folha
    print(f"  [{'OK  ' if ok_folha else 'FALHA'}] ficha de preparo abre com o portal de Minas")
    if not ok_folha:
        erros.append("ficha de preparo da GTA saiu incompleta")
    folha.screenshot(path=SAIDA / "90-gta-ficha-preparo.png", full_page=True)
    folha.close()
    pagina.evaluate("UI.fecharModal()")
    pagina.wait_for_timeout(400)
    pagina.screenshot(path=SAIDA / "91-gta.png", full_page=True)

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

    # ----------------------- o cupom de desconto na própria tela de pagamento
    api("POST", "/api/admin/cupons",
        {"codigo": "TELA20", "percentual": 20, "descricao": "teste de interface"},
        master["token"])
    antes_pix = pagina.evaluate("() => document.querySelector('#pix-codigo')?.value || ''")
    pagina.fill('[name=cupom]', "tela20")
    pagina.click("#btn-aplicar-cupom")
    pagina.wait_for_timeout(1800)
    cupom_tela = pagina.evaluate("""() => {
        const t = document.querySelector('#tela-pagamento').innerText;
        const valor = (p) => {  // lê o campo 54 (valor) de dentro do payload Pix
            let i = 0;
            while (i + 4 <= p.length) {
                const id = p.slice(i, i + 2), tam = Number(p.slice(i + 2, i + 4));
                if (id === '54') return Number(p.slice(i + 4, i + 4 + tam));
                i += 4 + tam;
            }
            return null;
        };
        return { texto: t.includes('TELA20') && t.includes('Valor a pagar'),
                 pix: valor(document.querySelector('#pix-codigo')?.value || ''),
                 qr: !!document.querySelector('.pix-qr svg') };
    }""")
    # 20% sobre o plano da conta de teste; o que importa é o Pix ter mudado junto
    ok_cupom = (cupom_tela["texto"] and cupom_tela["qr"] and cupom_tela["pix"]
                and antes_pix and antes_pix != pagina.evaluate(
                    "() => document.querySelector('#pix-codigo')?.value || ''"))
    print(f"  [{'OK  ' if ok_cupom else 'FALHA'}] cupom na tela de pagamento refaz o Pix {cupom_tela}")
    if not ok_cupom:
        erros.append("cupom não refez o Pix na tela de pagamento")
    pagina.screenshot(path=SAIDA / "24-cupom-pagamento.png", full_page=True)
    pagina.click("#btn-tirar-cupom")
    pagina.wait_for_timeout(1500)

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

    pagina.goto(f"{BASE}/#/admin-cupons")
    pagina.wait_for_timeout(1200)
    cupons = pagina.inner_text("#pagina")
    ok_cupons = ("TELA20" in cupons and "20%" in cupons and "0 vez(es)" in cupons
                 and "Cupons ativos".upper() in cupons.upper())
    print(f"  [{'OK  ' if ok_cupons else 'FALHA'}] tela de cupons do administrador")
    if not ok_cupons:
        erros.append("tela de cupons incompleta")
    pagina.screenshot(path=SAIDA / "25-admin-cupons.png", full_page=True)

    pagina.goto(f"{BASE}/#/configuracoes")
    pagina.wait_for_timeout(1000)
    ok_config = "Recebimento por Pix" in pagina.inner_text("#pagina")
    print(f"  [{'OK  ' if ok_config else 'FALHA'}] tela de configurações do site")
    if not ok_config:
        erros.append("tela de configurações incompleta")
    pagina.screenshot(path=SAIDA / "22-configuracoes.png", full_page=True)

    # ------------------------------- quadro de menus por plano (só o MASTER vê)
    quadro = pagina.evaluate("""() => {
        const marcada = (n) => document.querySelector(`[name="${n}"]`)?.checked;
        return {
            titulo: document.querySelector('#pagina').innerText.includes('Menus de cada plano'),
            caixas: document.querySelectorAll('[name^="mod_"]').length,
            nfe_no_1: marcada('mod_1_NFE'),
            gta_no_1: marcada('mod_1_GTA'),
            gta_no_4: marcada('mod_4_GTA'),
        };
    }""")
    ok_quadro = (quadro["titulo"] and quadro["caixas"] == 20 and quadro["nfe_no_1"]
                 and quadro["gta_no_1"] is False and quadro["gta_no_4"] is True)
    print(f"  [{'OK  ' if ok_quadro else 'FALHA'}] quadro de menus por plano {quadro}")
    if not ok_quadro:
        erros.append("quadro de menus por plano incompleto")

    # ------------------------- acessos combinados de um cliente (a negociação)
    pagina.goto(f"{BASE}/#/admin-assinaturas")
    pagina.wait_for_timeout(1200)
    pagina.click("[data-gerenciar]")
    pagina.wait_for_timeout(900)
    acessos = pagina.evaluate("""() => {
        const corpo = document.querySelector('#modal-corpo');
        const caixas = [...corpo.querySelectorAll('[name^="acesso_"]')].map((c) => ({
            codigo: c.name.replace('acesso_', ''),
            marcada: c.checked,
            origem: c.closest('tr').lastElementChild.innerText.trim(),
        }));
        return { titulo: corpo.innerText.includes('Acessos combinados'), caixas };
    }""")
    # a coluna "de onde vem" tem de contar a mesma história que a caixa marcada
    coerente = all(
        c["marcada"] == (c["origem"] == "vem do plano"
                         or "liberado só para esta conta" in c["origem"])
        for c in acessos["caixas"])
    nfe = next((c for c in acessos["caixas"] if c["codigo"] == "NFE"), None)
    ok_acessos = (acessos["titulo"] and len(acessos["caixas"]) == 5 and coerente
                  and nfe and nfe["marcada"] and nfe["origem"] == "vem do plano")
    print(f"  [{'OK  ' if ok_acessos else 'FALHA'}] acessos combinados por cliente {acessos}")
    if not ok_acessos:
        erros.append("bloco de acessos combinados incompleto")
    pagina.screenshot(path=SAIDA / "23-acessos-combinados.png", full_page=True)
    pagina.evaluate("UI.fecharModal()")
    pagina.wait_for_timeout(400)

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
        # o formulário tem dois botões Buscar (CNPJ e CEP): clica no do CEP
        pagina.evaluate(
            "document.querySelector('#modal-corpo [name=cep]')"
            ".closest('.campo-com-botao').querySelector('button').click()")
        pagina.wait_for_timeout(1400)
        endereco = pagina.evaluate("""() => {
            const v = (n) => document.querySelector(`#modal-corpo [name=${n}]`)?.value || '';
            return {cep: v('cep'), logradouro: v('logradouro'), bairro: v('bairro'),
                    cidade: v('cidade'), uf: v('uf'),
                    codigo_municipio: v('codigo_municipio')};
        }""")
        esperado_cep = {"cep": "13010-100", "logradouro": "Rua das Flores",
                        "bairro": "Centro", "cidade": "Campinas", "uf": "SP",
                        # o código do IBGE vem junto e é obrigatório na nota fiscal
                        "codigo_municipio": "3509502"}
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
