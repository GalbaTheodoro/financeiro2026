"""Capturas dos contratos de compra e de venda para o manual."""
import asyncio, json
from playwright.async_api import async_playwright
B="http://127.0.0.1:8000"; T=json.load(open('/home/claude/manual/tokens.json')); D='/home/claude/manual/img/'
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--lang=pt-BR"])
        ctx=await b.new_context(viewport={"width":1366,"height":820},locale="pt-BR")
        pg=await ctx.new_page(); erros=[]
        pg.on("pageerror", lambda e: erros.append(str(e)))
        await pg.goto(B+"/")
        await pg.evaluate(f"localStorage.setItem('fin_token','{T['t']}');localStorage.setItem('fin_empresa','{T['eid']}')")
        await pg.goto(B+"/#/contratos"); await pg.reload(wait_until="networkidle"); await pg.wait_for_timeout(2500)
        async def modal(nome):
            await pg.wait_for_timeout(800)
            await pg.locator("#modal").screenshot(path=D+nome+".jpg", type="jpeg", quality=82)
        # formulário de compra
        await pg.click("#btn-novo-contrato"); await pg.wait_for_timeout(900)
        await pg.select_option("#modal select[name=tipo]","COMPRA"); await pg.wait_for_timeout(400)
        await modal("11e-contrato-tipo")
        await pg.click("#modal [data-etapa='1']"); await pg.wait_for_timeout(500)
        opcoes = await pg.eval_on_selector_all("#modal select[name=vendedor_id] option", "os=>os.map(o=>[o.value,o.textContent])")
        fornecedor = next(v for v, txt in opcoes if 'SANTA LUZIA' in (txt or ''))
        agente = next(v for v, txt in opcoes if 'AGENTE' in (txt or ''))
        await pg.select_option("#modal select[name=vendedor_id]", fornecedor)
        await pg.select_option("#modal select[name=agente_id]", agente)
        await pg.fill("#modal input[name=agente_percentual]","1")
        await pg.dispatch_event("#modal input[name=agente_percentual]","input")
        await modal("11f-compra-partes")
        await pg.click("#modal [data-etapa='2']"); await pg.wait_for_timeout(400)
        await pg.fill("#modal input[name=quantidade]","200"); await pg.fill("#modal input[name=preco_unitario]","1300")
        await pg.dispatch_event("#modal input[name=preco_unitario]","input")
        await modal("11g-compra-resumo")
        await pg.evaluate("UI.fecharModal()"); await pg.wait_for_timeout(400)
        # ficha da compra já gerada (vem do demo.py) e da venda
        async def ficha(numero, nome):
            await pg.goto(B+"/#/contratos"); await pg.reload(wait_until="networkidle"); await pg.wait_for_timeout(2500)
            await pg.locator("tr", has_text=numero).locator("[data-ver]").first.click()
            await pg.wait_for_timeout(1800)
            await pg.locator("#modal").screenshot(path=D+nome+".jpg", type="jpeg", quality=82)
            await pg.evaluate("UI.fecharModal()")
        linhas = await pg.evaluate("""async()=>{const l=await Api.get('/api/contratos',{empresa_id:Estado.empresaId});
            return l.linhas.map(c=>[c.numero,c.tipo])}""")
        numero_compra = next(n for n, tp in linhas if tp=="COMPRA")
        numero_venda = next(n for n, tp in linhas if tp=="VENDA")
        await ficha(numero_compra, "11h-compra-ficha")
        await ficha(numero_venda, "11i-venda-ficha")
        # folha impressa da compra (recorte: partes + pagamento)
        html = await pg.evaluate("""async(numero)=>{const l=await Api.get('/api/contratos',{empresa_id:Estado.empresaId});
            const c=l.linhas.find(x=>x.numero===numero); const d=await Api.get(`/api/contratos/${c.id}/impressao`);
            return `<!doctype html><html><head><meta charset="utf-8"><style>${Impressao.estilo()} body{background:#fff}.folha{box-shadow:none;margin:0 auto}</style></head><body><div class="folha">${Impressao.folha(d)}</div></body></html>`}""",
            numero_compra)
        f = await b.new_page(viewport={"width":900,"height":1400})
        await f.set_content(html); await f.wait_for_timeout(500)
        caixa = await f.evaluate("""()=>{const t=document.querySelector('.titulo-documento').getBoundingClientRect();
            const hs=[...document.querySelectorAll('h2')]; const alvo=hs.find(h=>/PAGAMENTO|RECEBIMENTO/i.test(h.textContent));
            const tab=alvo.nextElementSibling.getBoundingClientRect();
            return {x:t.left-8,y:t.top-6,w:t.width+16,h:tab.bottom-t.top+14}}""")
        await f.screenshot(path=D+"11j-compra-impressao.jpg", type="jpeg", quality=84,
                           clip={"x":caixa["x"],"y":caixa["y"],"width":caixa["w"],"height":caixa["h"]})
        await f.close()
        print("erros:", erros)
        await b.close()
asyncio.run(main())
