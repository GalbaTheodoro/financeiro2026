"""AgroDock — Contratos e Gestão (aplicação FastAPI)."""
import logging
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import EM_VERCEL, FRONTEND_DIR
from .diagnostico import pagina_html, resumo_erro
from .migracao import preparar_banco
from .routers import (
    assinatura,
    auth,
    cadastros,
    caixa,
    consulta,
    contratos,
    lancamentos,
    publico,
    relatorios,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("financeiro")


# Se o banco não abrir na subida (endereço errado, banco suspenso...), o sistema
# continua de pé mostrando a causa, e tenta de novo a cada 15 segundos.
_BANCO = {"erro": None, "ultima_tentativa": 0.0}


def _tentar_preparar_banco() -> bool:
    _BANCO["ultima_tentativa"] = time.monotonic()
    try:
        modo = preparar_banco()
    except Exception as erro:  # noqa: BLE001 — qualquer falha vira tela de diagnóstico
        _BANCO["erro"] = resumo_erro(erro)
        log.exception("Não foi possível preparar o banco")
        return False
    _BANCO["erro"] = None
    if EM_VERCEL:
        log.info("AgroDock pronto no Vercel (conferência do banco: %s)", modo)
    else:
        log.info("AgroDock pronto — abra http://localhost:8000")
    return True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # cria/atualiza tabelas e dados iniciais (no banco da nuvem, só quando o código muda)
    _tentar_preparar_banco()
    yield


app = FastAPI(
    title="AgroDock — Contratos e Gestão",
    version="1.0.0",
    description="Contratos de assessoria, comissões, contas a pagar e a receber, caixa, DRE e balancete.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def banco_indisponivel(request: Request, chamar):
    if _BANCO["erro"] and request.url.path != "/api/health":
        if time.monotonic() - _BANCO["ultima_tentativa"] > 15:
            _tentar_preparar_banco()
        if _BANCO["erro"]:
            if request.url.path.startswith("/api/"):
                return JSONResponse(status_code=503, content={
                    "detail": f"O sistema não conseguiu abrir o banco de dados. {_BANCO['erro']}"})
            return HTMLResponse(pagina_html(_BANCO["erro"]), status_code=503)
    return await chamar(request)


app.include_router(publico.router)
app.include_router(auth.router)
app.include_router(assinatura.router)
app.include_router(cadastros.router)
app.include_router(consulta.router)
app.include_router(contratos.router)
app.include_router(lancamentos.router)
app.include_router(caixa.router)
app.include_router(relatorios.router)


@app.exception_handler(Exception)
async def erro_generico(request: Request, exc: Exception):  # pragma: no cover
    log.exception("Erro não tratado em %s", request.url.path)
    return JSONResponse(
        status_code=500, content={"detail": f"Erro interno do servidor: {exc}"}
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok" if not _BANCO["erro"] else "erro_banco",
        "versao": versao_frontend(),
        "banco": "ok" if not _BANCO["erro"] else _BANCO["erro"],
    }


# --------------------------------------------------------------------------- #
# Front-end
#
# O navegador guarda o JavaScript em cache e, sem isto, continuaria mostrando a
# versão antiga do sistema depois de uma atualização. Duas medidas resolvem:
#   1. cada arquivo estático é pedido com ?v=<versão>, que muda quando o arquivo muda;
#   2. os estáticos vão com "no-cache", então o navegador sempre confirma se mudou
#      (a resposta é um 304 curtinho quando não mudou — não fica lento).
# --------------------------------------------------------------------------- #
class EstaticosSemCache(StaticFiles):
    """StaticFiles que pede revalidação ao navegador em vez de cache cego."""

    def file_response(self, *args, **kwargs):
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resposta


def versao_frontend() -> str:
    """Carimbo que muda sempre que qualquer arquivo do front-end é atualizado."""
    try:
        arquivos = [a for a in FRONTEND_DIR.rglob("*") if a.is_file()]
        return str(int(max(a.stat().st_mtime for a in arquivos)))
    except ValueError:
        return "0"


def versao_arquivos() -> str:
    """O que vai no ?v= dos arquivos estáticos.

    No Vercel a data dos arquivos não é confiável (o pacote pode chegar com
    todas as datas iguais), então usamos o código do deploy, que muda a cada
    publicação. No PC continua sendo a data do arquivo mais novo.
    """
    import os

    return (os.getenv("VERCEL_DEPLOYMENT_ID") or os.getenv("VERCEL_GIT_COMMIT_SHA", "")[:12]
            or versao_frontend())


if FRONTEND_DIR.exists():
    app.mount("/static", EstaticosSemCache(directory=FRONTEND_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        """Entrega o index.html com a versão colada em cada arquivo estático."""
        versao = versao_arquivos()
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        html = re.sub(
            r'(src|href)="(/static/[^"?]+)"',
            lambda m: f'{m.group(1)}="{m.group(2)}?v={versao}"',
            html,
        )
        return HTMLResponse(
            html, headers={"Cache-Control": "no-store"}
        )
