"""Porta de entrada do AgroDock no Vercel.

O Vercel procura um arquivo app.py na raiz com uma variável ``app``. O sistema
de verdade está em backend/main.py — aqui só apontamos para ele.
No PC nada muda: continua sendo  uvicorn backend.main:app  (iniciar.bat).
"""
from backend.main import app  # noqa: F401
