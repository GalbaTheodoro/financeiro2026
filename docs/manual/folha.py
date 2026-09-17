import asyncio, json
from playwright.async_api import async_playwright
B="http://127.0.0.1:8000"; T=json.load(open('tokens.json'))
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await (await b.new_context(viewport={"width":1366,"height":900},locale="pt-BR")).new_page()
        await pg.goto(B+"/"); await pg.evaluate(f"localStorage.setItem('fin_token','{T['t']}');localStorage.setItem('fin_empresa','{T['eid']}')")
        await pg.goto(B+"/#/contratos"); await pg.reload(); await pg.wait_for_timeout(2500)
        html=await pg.evaluate("""async()=>{const l=await Api.get('/api/contratos',{empresa_id:Estado.empresaId});
          const c=l.linhas.find(x=>x.numero==='00000001'); const d=await Api.get(`/api/contratos/${c.id}/impressao`);
          return `<!doctype html><html><head><meta charset="utf-8"><style>${Impressao.estilo()} body{background:#fff}.folha{box-shadow:none;margin:0 auto}</style></head><body><div class="folha">${Impressao.folha(d)}</div></body></html>`}""")
        f=await b.new_page(viewport={"width":900,"height":1200}); await f.set_content(html); await f.wait_for_timeout(500)
        caixa=await f.evaluate("""()=>{const hs=[...document.querySelectorAll('h2')]; const a=hs[0].getBoundingClientRect(); const g=hs[0].nextElementSibling.getBoundingClientRect(); return {x:g.left-8,y:a.top-6,w:g.width+16,h:g.bottom-a.top+14}}""")
        await f.screenshot(path="img/31-impressao-icms.jpg",type="jpeg",quality=88,clip={"x":caixa["x"],"y":caixa["y"],"width":caixa["w"],"height":caixa["h"]})
        await b.close()
asyncio.run(main())
