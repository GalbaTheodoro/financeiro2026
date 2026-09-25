"""Capturas do manual da GTA.

Rodar depois de `servidor_demo.py` e `gta_demo.py`, nesta ordem. As imagens vão
para `docs/manual/img/` com o prefixo `gta-`.
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

B = "http://127.0.0.1:8000"
AQUI = Path(__file__).resolve().parent
IMG = AQUI / "img"
T = json.loads((AQUI / "tokens-gta.json").read_text(encoding="utf-8"))


async def main():
    async with async_playwright() as p:
        nav = await p.chromium.launch(args=["--lang=pt-BR"])
        ctx = await nav.new_context(viewport={"width": 1366, "height": 860},
                                    locale="pt-BR", device_scale_factor=1)
        pg = await ctx.new_page()
        erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))

        async def tirar(nome, full=False, modal=False, alvo=None):
            await pg.wait_for_timeout(900)
            caminho = str(IMG / f"gta-{nome}.jpg")
            if modal:
                await pg.locator("#modal").screenshot(path=caminho, type="jpeg", quality=84)
            elif alvo:
                await pg.locator(alvo).screenshot(path=caminho, type="jpeg", quality=84)
            else:
                await pg.screenshot(path=caminho, type="jpeg", quality=84, full_page=full)

        async def fechar():
            await pg.evaluate("UI.fecharModal()")
            await pg.wait_for_timeout(400)

        async def ir(hash_):
            await pg.evaluate(f"location.hash='{hash_}'")
            await pg.wait_for_timeout(1600)

        await pg.goto(B + "/")
        await pg.wait_for_timeout(1200)
        await pg.evaluate(
            f"localStorage.setItem('fin_token','{T['t']}');"
            f"localStorage.setItem('fin_empresa','{T['eid']}')")
        await pg.goto(B + "/#/painel")
        await pg.reload()
        await pg.wait_for_timeout(2600)

        # ------------------------------------------------ o cadastro do produtor
        await ir("#/cadastros/parceiros")
        await tirar("cadastro-lista")
        await pg.locator("tr", has_text="ROSALINA").locator("[data-editar]").first.click()
        await tirar("cadastro-produtor", modal=True)
        await fechar()

        # ------------------------------------------------------- a tela da GTA
        await ir("#/gta")
        await tirar("tela")
        await tirar("resumo", alvo=".grade.g6")

        # ------------------------------------------- a guia nova, etapa por etapa
        await pg.click("#btn-nova-gta")
        await pg.wait_for_timeout(900)
        await tirar("nova-vazia", modal=True)
        await fechar()

        # a guia em preparo que ainda tem pendências: mostra a conferência
        await pg.locator("#lista-gta tr", has_text="Em preparo").last.locator(
            "[data-abrir]").click()
        await pg.wait_for_timeout(1200)
        await tirar("conferencia", alvo="#faltas-gta")
        await tirar("form-animais", modal=True)
        await fechar()

        # a guia completa: conferência verde e o formulário inteiro
        await pg.evaluate(
            "(async()=>{const r=await Api.get('/api/gta/%s'); GTA.formulario(r.guia);})()"
            % T["pronta"])
        await pg.wait_for_timeout(1500)
        await tirar("form-completo", modal=True)
        await tirar("conferencia-ok", alvo="#faltas-gta")
        # o fim do formulário: onde se anota o que saiu do portal, com os botões
        await pg.evaluate(
            "document.querySelector('[name=\"data_validade\"]')"
            ".scrollIntoView({block:'end'})")
        await pg.wait_for_timeout(600)
        await tirar("anotar", modal=True)
        await fechar()

        # ---------------------------------------------------- a ficha de preparo
        async with ctx.expect_page() as nova:
            # a guia completa, ainda em preparo: a folha sai com os campos do
            # número e da validade em branco, que é como ela vai para o portal
            await pg.evaluate("GTA.preparo(%s)" % T["pronta"])
        folha = await nova.value
        await folha.wait_for_timeout(1400)
        await folha.screenshot(path=str(IMG / "gta-ficha.jpg"), type="jpeg",
                               quality=84, full_page=True)
        await folha.close()
        await pg.wait_for_timeout(500)

        # ------------------------------------------- lista com validade e avisos
        await ir("#/gta")
        await tirar("lista", alvo="#lista-gta")

        # --------------------------------------------------------- no celular
        ctx2 = await nav.new_context(viewport={"width": 390, "height": 800},
                                     locale="pt-BR", is_mobile=True, has_touch=True,
                                     device_scale_factor=2)
        pg2 = await ctx2.new_page()
        await pg2.goto(B + "/")
        await pg2.wait_for_timeout(1200)
        await pg2.evaluate(
            f"localStorage.setItem('fin_token','{T['t']}');"
            f"localStorage.setItem('fin_empresa','{T['eid']}')")
        await pg2.goto(B + "/#/gta")
        await pg2.reload()
        await pg2.wait_for_timeout(2600)
        await pg2.screenshot(path=str(IMG / "gta-celular.jpg"), type="jpeg", quality=84)
        await ctx2.close()

        await nav.close()
        if erros:
            print("ERROS DE TELA:", erros[:3])


asyncio.run(main())
print("capturas em docs/manual/img/gta-*.jpg")
