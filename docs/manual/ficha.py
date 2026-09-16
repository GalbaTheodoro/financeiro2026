import asyncio, json
from playwright.async_api import async_playwright
B="http://127.0.0.1:8000"; T=json.load(open('tokens.json'))
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--lang=pt-BR"]); pg=await (await b.new_context(viewport={"width":1366,"height":900},locale="pt-BR")).new_page()
        await pg.goto(B+"/"); await pg.evaluate(f"localStorage.setItem('fin_token','{T['t']}');localStorage.setItem('fin_empresa','{T['eid']}')")
        await pg.goto(B+"/#/contratos"); await pg.reload(); await pg.wait_for_timeout(2500)
        await pg.locator("tr", has_text="00000001").locator("[data-ver]").first.click(); await pg.wait_for_timeout(1500)
        await pg.locator("#modal").screenshot(path="img/10b-contrato-ficha.jpg",type="jpeg",quality=82)
        await pg.evaluate("UI.fecharModal()")
        await pg.locator("tr", has_text="00000003").locator("[data-ver]").first.click(); await pg.wait_for_timeout(1500)
        await pg.locator("#modal").screenshot(path="img/10c-contrato-ficha-aberto.jpg",type="jpeg",quality=82)
        await b.close()
asyncio.run(main())
