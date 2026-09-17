import asyncio, json
from playwright.async_api import async_playwright
B="http://127.0.0.1:8000"; T=json.load(open('tokens.json'))
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await (await b.new_context(viewport={"width":1366,"height":900},locale="pt-BR")).new_page()
        await pg.goto(B+"/"); await pg.evaluate(f"localStorage.setItem('fin_token','{T['tm']}')")
        await pg.goto(B+"/#/configuracoes"); await pg.reload(); await pg.wait_for_timeout(2500)
        await pg.evaluate("document.getElementById('faixa-cotacoes').style.display='none'")
        card=pg.locator(".cartao", has_text="Faixa de cotações e painel").first
        await card.scroll_into_view_if_needed(); await pg.wait_for_timeout(300)
        await card.screenshot(path="img/26b-config-cotacoes.jpg",type="jpeg",quality=85)
        await b.close()
asyncio.run(main())
