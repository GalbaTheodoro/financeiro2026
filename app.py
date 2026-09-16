"""Porta de entrada do AgroDock no Vercel.

O Vercel procura um arquivo app.py na raiz com uma variável ``app``. O sistema
de verdade está em backend/main.py — aqui só apontamos para ele.
No PC nada muda: continua sendo  uvicorn backend.main:app  (iniciar.bat).

Se o sistema nem conseguir carregar (por exemplo, faltou uma variável no Vercel),
em vez do "500 FUNCTION_INVOCATION_FAILED" sem explicação aparece uma página
dizendo o que faltou e como resolver.
"""
try:
    from backend.main import app  # noqa: F401
except Exception as _erro:  # noqa: BLE001
    import logging
    import traceback

    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    from backend.diagnostico import pagina_html, resumo_erro

    logging.getLogger("financeiro").error("AgroDock não carregou:\n%s", traceback.format_exc())
    _texto = resumo_erro(_erro)
    app = FastAPI()

    @app.api_route("/{caminho:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def _sem_sistema(caminho: str = ""):
        if caminho.startswith("api/"):
            return JSONResponse(status_code=503, content={"detail": _texto})
        return HTMLResponse(pagina_html(_texto), status_code=503)
