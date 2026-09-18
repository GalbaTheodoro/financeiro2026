"""Capturas do módulo DF-e para o manual."""
import asyncio, json
from playwright.async_api import async_playwright
B = "http://127.0.0.1:8000"; T = json.load(open('/home/claude/manual/tokens.json')); D = '/home/claude/manual/img/'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--lang=pt-BR"])
        ctx = await b.new_context(viewport={"width": 1366, "height": 820}, locale="pt-BR")
        pg = await ctx.new_page(); erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        async def shot(nome, full=False):
            await pg.wait_for_timeout(900)
            await pg.screenshot(path=D + nome + ".jpg", type="jpeg", quality=82, full_page=full)
        async def modal(nome):
            await pg.wait_for_timeout(900)
            await pg.locator("#modal").screenshot(path=D + nome + ".jpg", type="jpeg", quality=82)

        await pg.goto(B + "/")
        await pg.evaluate(f"localStorage.setItem('fin_token','{T['t']}');localStorage.setItem('fin_empresa','{T['eid']}')")
        await pg.goto(B + "/#/dfe"); await pg.reload(wait_until="networkidle"); await pg.wait_for_timeout(2500)
        await shot("dfe-lista")

        # buscar na SEFAZ
        await pg.click("#btn-buscar-sefaz"); await modal("dfe-buscar")
        await pg.evaluate("UI.fecharModal()"); await pg.wait_for_timeout(500)

        # ficha da nota completa
        indice = await pg.evaluate("""async()=>{const l=await Api.get('/api/dfe/notas',{empresa_id:Estado.empresaId});
            return l.findIndex(n=>!n.resumo)}""")
        await pg.click(f'[data-ficha="{indice}"]'); await modal("dfe-ficha")

        # manifestação
        await pg.click("#modal-rodape >> text=Manifestar"); await pg.wait_for_timeout(700)
        await modal("dfe-manifestar")
        await pg.click("#modal-rodape >> text=Cancelar"); await pg.wait_for_timeout(1400)

        # importar
        botao = pg.locator("#modal-rodape button").filter(has_text="Importar").first
        await botao.click(); await pg.wait_for_timeout(800)
        await pg.check("#modal [name=gerar_titulo]"); await pg.wait_for_timeout(400)
        await modal("dfe-importar")
        await pg.evaluate("UI.fecharModal()"); await pg.wait_for_timeout(500)

        # certificado
        await pg.evaluate("location.hash='#/dfe/certificado'"); await pg.wait_for_timeout(2000)
        await shot("dfe-certificado")

        # DANFE (página inteira, recortada no topo)
        dados = await pg.evaluate("""async()=>{const l=await Api.get('/api/dfe/notas',{empresa_id:Estado.empresaId});
            const n=l.find(x=>!x.resumo); const r=await fetch(`/api/dfe/notas/${n.id}/danfe`,
              {headers:{Authorization:'Bearer '+Estado.token}}); return await r.text()}""")
        folha = await b.new_page(viewport={"width": 900, "height": 1400})
        await folha.set_content(dados); await folha.wait_for_timeout(700)
        await folha.evaluate("document.querySelector('.barra').remove()")
        caixa = await folha.evaluate("""()=>{const f=document.querySelector('.folha').getBoundingClientRect();
            const t=[...document.querySelectorAll('.titulo-secao')].find(x=>/produtos/i.test(x.textContent));
            const tab=t.parentElement.nextElementSibling.getBoundingClientRect();
            return {x:f.left,y:f.top,w:f.width,h:tab.bottom-f.top+10}}""")
        await folha.screenshot(path=D + "dfe-danfe.jpg", type="jpeg", quality=84,
                               clip={"x": caixa["x"], "y": caixa["y"], "width": caixa["w"], "height": caixa["h"]})
        await folha.close()

        # produto com os campos fiscais
        await pg.evaluate("location.hash='#/cadastros/produtos'"); await pg.wait_for_timeout(2000)
        linha = pg.locator("tr", has_text="CAF001").first
        if await linha.count():
            await linha.locator("[data-editar]").first.click()
        else:
            await pg.click('[data-editar="0"]')
        await modal("dfe-produto-fiscal")
        await pg.evaluate("UI.fecharModal()")

        # celular
        cel = await ctx.new_page()
        await cel.set_viewport_size({"width": 390, "height": 844})
        await cel.goto(B + "/")
        await cel.evaluate(f"localStorage.setItem('fin_token','{T['t']}');localStorage.setItem('fin_empresa','{T['eid']}')")
        await cel.goto(B + "/#/dfe"); await cel.reload(wait_until="networkidle"); await cel.wait_for_timeout(3000)
        # sem a faixa de cotações (ela fica fixa no rodapé e atravessaria a captura)
        await cel.evaluate("document.querySelector('.faixa-cotacoes')?.remove()")
        alvo = await cel.evaluate("""()=>{const t=document.querySelector('.tabela-cartoes');
            return t? t.getBoundingClientRect().top + window.scrollY - 60 : 0}""")
        await cel.screenshot(path=D + "dfe-celular.jpg", type="jpeg", quality=82, full_page=True,
                             clip={"x": 0, "y": alvo, "width": 390, "height": 1100})
        print("erros:", erros)
        await b.close()

asyncio.run(main())
