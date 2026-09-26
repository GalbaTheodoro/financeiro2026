"""Teste da interface no celular (Playwright, tela de 390x844).

Confere o que muda no telefone:
  * o menu vira gaveta, abre e fecha;
  * nenhuma tela estoura para o lado (rolagem horizontal);
  * as listas viram cartões, com o nome da coluna ao lado de cada valor;
  * o contrato é lançado inteiro pelas etapas, com o resumo do cálculo à vista.

Uso:  python testes/teste_celular.py   (com o servidor no ar)
"""
import json
import pathlib
import sys
import time
import urllib.request
from datetime import date

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SAIDA = pathlib.Path(__file__).parent / "capturas"
SAIDA.mkdir(exist_ok=True)
TELA = {"width": 390, "height": 844}      # iPhone 14 / Android comum
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


sufixo = str(int(time.time()))
hoje = date.today()

conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba no celular", "email": f"celular{sufixo}@teste.com", "senha": "123456",
    "empresa": "Brascafé Assessoria",
    # plano completo: assim o teste passa também pelo cupom fiscal e pela GTA
    "plano": "P4_SEMESTRAL",
})
token = conta["token"]
eid = conta["empresa"]["id"]
api("POST", "/api/parceiros",
    {"empresa_id": eid, "tipo": "AMBOS", "nome": "OLAM AGRICOLA LTDA"}, token)
api("POST", "/api/parceiros",
    {"empresa_id": eid, "tipo": "AMBOS", "nome": "ROSALINA SILVEIRA FARIA"}, token)
api("POST", "/api/bancos",
    {"empresa_id": eid, "nome": "Banco do Brasil", "tipo": "CORRENTE", "saldo_inicial": 5000},
    token)

with sync_playwright() as p:
    navegador = p.chromium.launch()
    ctx = navegador.new_context(viewport=TELA, device_scale_factor=2,
                                is_mobile=True, has_touch=True)
    pagina = ctx.new_page()
    pagina.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pagina.on("console", lambda m: erros.append(f"console: {m.text}")
              if m.type == "error" and "402" not in m.text else None)

    def sem_estouro(nome):
        sobra = pagina.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth")
        checar(f"{nome} cabe na largura do celular", sobra <= 1, f"sobra {sobra}px")

    print("\n=== 1. Site no celular ===")
    pagina.goto(BASE, wait_until="networkidle")
    pagina.wait_for_selector("#site:not(.oculto)", timeout=15000)
    pagina.wait_for_timeout(900)
    sem_estouro("site")
    checar("logotipo do AgroDock no topo",
           pagina.query_selector(".site-topo .logo-icone") is not None)
    checar("nome da marca no topo",
           "AgroDock" in pagina.inner_text(".site-topo .site-marca"))

    nav_escondido = pagina.evaluate(
        "() => getComputedStyle(document.querySelector('.site-nav')).display === 'none'")
    checar("menu do site começa fechado no celular", nav_escondido)
    pagina.click("#btn-menu-site")
    pagina.wait_for_timeout(400)
    nav_aberto = pagina.evaluate(
        "() => getComputedStyle(document.querySelector('.site-nav')).display !== 'none'")
    checar("botão ☰ abre o menu do site", nav_aberto)
    pagina.screenshot(path=SAIDA / "40-celular-site.png", full_page=True)

    print("\n=== 2. Gaveta do menu no sistema ===")
    pagina.evaluate(
        "([t, e]) => { localStorage.setItem('fin_token', t);"
        " localStorage.setItem('fin_empresa', String(e)); }", [token, eid])
    pagina.goto(f"{BASE}/#/painel")
    pagina.reload(wait_until="networkidle")
    pagina.wait_for_timeout(1800)
    sem_estouro("painel")

    fora = pagina.evaluate(
        "() => document.querySelector('.sidebar').getBoundingClientRect().right <= 1")
    checar("menu lateral começa recolhido", fora)
    pagina.click("#btn-abrir-menu")
    pagina.wait_for_timeout(500)
    dentro = pagina.evaluate(
        "() => document.querySelector('.sidebar').getBoundingClientRect().left >= -1")
    checar("botão ☰ abre a gaveta do menu", dentro)
    checar("a gaveta mostra a marca AgroDock",
           "AgroDock" in pagina.inner_text(".sidebar .marca"))
    pagina.screenshot(path=SAIDA / "41-celular-menu.png")
    pagina.click("#btn-fechar-menu")
    pagina.wait_for_timeout(500)
    fechou = pagina.evaluate(
        "() => document.querySelector('.sidebar').getBoundingClientRect().right <= 1")
    checar("o X fecha a gaveta", fechou)

    # Com a gaveta fechada, é a barra de cima que diz em que sistema a pessoa está.
    checar("a marca AgroDock aparece na barra de cima",
           "AgroDock" in pagina.inner_text(".topo .topo-marca"))
    encaixe = pagina.evaluate("""() => {
        const topo = document.querySelector('.topo').getBoundingClientRect();
        const titulo = document.querySelector('.topo-titulo').getBoundingClientRect();
        const marca = document.querySelector('.topo-marca').getBoundingClientRect();
        const primeiro = document.querySelector('#pagina .cartao, #pagina .kpi');
        const p = primeiro ? primeiro.getBoundingClientRect() : null;
        return {
          // marca e título em linhas diferentes: nada por cima de nada
          separados: titulo.top >= marca.bottom - 1,
          // a barra de cima não cobre o começo da página
          livre: !p || p.top >= topo.bottom - 1,
        };
    }""")
    checar("marca e nome da tela em linhas separadas", encaixe["separados"])
    checar("a barra de cima não cobre o conteúdo", encaixe["livre"])

    print("\n=== 3. Telas principais sem rolagem lateral ===")
    for rota, nome in [("receber", "contas a receber"), ("pagar", "contas a pagar"),
                       ("caixa", "caixa"), ("contratos", "contratos"),
                       ("notas", "notas fiscais"), ("cupom", "cupom fiscal"),
                       ("pedidos", "pedidos e vendas"),
                       ("gta", "GTA"), ("relatorios", "relatórios"),
                       ("cadastros/parceiros", "cadastros")]:
        pagina.goto(f"{BASE}/#/{rota}")
        pagina.wait_for_timeout(1300)
        sem_estouro(nome)
        titulo_inteiro = pagina.evaluate(
            "() => {const h = document.querySelector('#titulo-pagina');"
            " return h.scrollWidth <= h.clientWidth + 1;}")
        checar(f"{nome}: o nome da tela cabe sem cortar", titulo_inteiro)

    print("\n=== 4. Contrato lançado pelas etapas ===")
    pagina.goto(f"{BASE}/#/contratos")
    pagina.wait_for_timeout(1400)
    pagina.click("#btn-novo-contrato")
    pagina.wait_for_timeout(900)
    sem_estouro("formulário do contrato")

    etapas = pagina.eval_on_selector_all("#barra-etapas [data-etapa]", "els => els.length")
    checar("cinco etapas na trilha", etapas == 5, str(etapas))
    checar("só a etapa atual aparece",
           pagina.eval_on_selector_all(
               "[data-painel]", "els => els.filter(e => !e.classList.contains('oculto')).length") == 1)
    visivel = "[data-painel]:not(.oculto) .titulo-etapa"
    checar("primeira etapa é a identificação",
           "Identificação" in pagina.inner_text(visivel))
    pagina.screenshot(path=SAIDA / "42-celular-contrato-etapa1.png")

    produtos = pagina.eval_on_selector_all(
        'select[name=produto_id] option', "els => els.map(e => e.value).filter(Boolean)")
    pagina.select_option('select[name=produto_id]', produtos[0])

    # etapa 2 — partes
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    checar("segunda etapa é a das partes", "Partes" in pagina.inner_text(visivel),
           pagina.inner_text(visivel))
    partes = pagina.eval_on_selector_all(
        'select[name=comprador_id] option', "els => els.map(e => e.value).filter(Boolean)")
    pagina.select_option('select[name=comprador_id]', partes[0])
    pagina.select_option('select[name=vendedor_id]', partes[1])

    # etapa 3 — quantidade
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    unidades = pagina.eval_on_selector_all(
        'select[name=unidade_id] option', "els => els.map(e => e.value).filter(Boolean)")
    pagina.select_option('select[name=unidade_id]', unidades[0])
    pagina.fill('input[name=quantidade]', "330")
    pagina.fill('input[name=preco_unitario]', "1320")
    pagina.dispatch_event('input[name=preco_unitario]', "input")
    pagina.wait_for_timeout(400)
    resumo = pagina.inner_text("#resumo-calculo").replace(" ", " ")
    checar("resumo do cálculo visível na etapa da quantidade",
           "R$ 435.600,00" in resumo, resumo.split("\n")[1] if "\n" in resumo else "")
    pagina.screenshot(path=SAIDA / "43-celular-contrato-etapa3.png")

    # etapa 4 — corretagem
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    pagina.fill('input[name=comissao_comprador_percentual]', "0.5")
    pagina.dispatch_event('input[name=comissao_comprador_percentual]', "input")
    pagina.fill('input[name=comissao_vendedor_percentual]', "0.5")
    pagina.dispatch_event('input[name=comissao_vendedor_percentual]', "input")
    pagina.wait_for_timeout(400)
    resumo = pagina.inner_text("#resumo-calculo").replace(" ", " ")
    checar("comissão dos dois lados no resumo", resumo.count("R$ 2.178,00") >= 2)
    checar("total a receber calculado", "R$ 4.356,00" in resumo)
    pagina.screenshot(path=SAIDA / "44-celular-contrato-etapa4.png")

    # volta uma etapa e confere que o que foi digitado continua lá
    pagina.click("#modal-rodape >> text=Voltar")
    pagina.wait_for_timeout(400)
    checar("o botão Voltar mantém o que já foi digitado",
           pagina.input_value('input[name=quantidade]') == "330")
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(400)

    # etapa 5 e gravação
    pagina.click("#modal-rodape >> text=Próximo")
    pagina.wait_for_timeout(500)
    checar("última etapa tem embarque e classificação",
           pagina.query_selector('textarea[name=observacao]') is not None)
    pagina.screenshot(path=SAIDA / "45-celular-contrato-etapa5.png")
    pagina.click("#modal-rodape >> text=Salvar")
    pagina.wait_for_selector("text=Gerar contas a receber", timeout=15000)
    pagina.wait_for_timeout(900)
    ficha = pagina.inner_text("#modal-corpo").replace(" ", " ")
    checar("contrato salvo pelo celular", "R$ 4.356,00" in ficha)
    sem_estouro("ficha do contrato")
    pagina.screenshot(path=SAIDA / "46-celular-contrato-ficha.png", full_page=True)

    print("\n=== 5. Lista em cartões ===")
    pagina.evaluate("UI.fecharModal()")
    pagina.goto(f"{BASE}/#/painel")
    pagina.wait_for_timeout(700)
    pagina.goto(f"{BASE}/#/contratos")
    pagina.wait_for_timeout(1600)
    sem_estouro("lista de contratos")
    rotulo = pagina.evaluate(
        "() => { const td = document.querySelector('.tabela-cartoes tbody td');"
        " return td ? getComputedStyle(td, '::before').content : ''; }")
    checar("cada valor da lista mostra o nome da coluna", "CONTRATO" in rotulo.upper(), rotulo)
    empilhado = pagina.evaluate(
        "() => getComputedStyle(document.querySelector('.tabela-cartoes tbody tr')).display")
    checar("as linhas viram cartões empilhados", empilhado == "block", empilhado)
    cabecalho_oculto = pagina.evaluate(
        "() => getComputedStyle(document.querySelector('.tabela-cartoes thead')).display")
    checar("o cabeçalho da tabela some no celular", cabecalho_oculto == "none")
    pagina.screenshot(path=SAIDA / "47-celular-lista.png", full_page=True)

    navegador.close()

print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} problema(s):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("Celular OK — capturas em testes/capturas/")
