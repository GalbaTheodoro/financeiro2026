"""Porta de entrada do AgroDock no Vercel.

O Vercel procura um arquivo app.py na raiz com uma variável ``app`` importada ou
criada no nível de cima do arquivo (ele lê o arquivo antes de rodar — não coloque
este import dentro de try/if). O sistema de verdade está em backend/main.py.
No PC nada muda: continua sendo  uvicorn backend.main:app  (iniciar.bat).

Se faltar variável no Vercel ou o banco não abrir, o próprio sistema mostra uma
página explicando o que fazer (backend/diagnostico.py).
"""
from backend.main import app  # noqa: F401
