"""Gera o Manual da GTA em PDF a partir de `manual-gta.html`.

    python docs/manual/pdf_gta.py

O PDF sai em `frontend/manual/Manual-GTA.pdf`, que é o arquivo oferecido para
download na tela da GTA.
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI.parent.parent / "frontend" / "manual" / "Manual-GTA.pdf"

RODAPE = (
    '<div style="font-size:8px;width:100%;padding:0 16mm;color:#5b6a61;display:flex;'
    'justify-content:space-between;font-family:Arial">'
    '<span>AgroDock — Manual da GTA (Guia de Trânsito Animal)</span>'
    '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
)


async def main():
    async with async_playwright() as p:
        navegador = await p.chromium.launch()
        pagina = await navegador.new_page()
        await pagina.goto((AQUI / "manual-gta.html").as_uri())
        await pagina.wait_for_timeout(1500)
        SAIDA.parent.mkdir(parents=True, exist_ok=True)
        await pagina.pdf(
            path=str(SAIDA), format="A4", print_background=True,
            prefer_css_page_size=True, display_header_footer=True,
            header_template="<span></span>", footer_template=RODAPE,
        )
        await navegador.close()


asyncio.run(main())
print(f"gerado: {SAIDA}")
