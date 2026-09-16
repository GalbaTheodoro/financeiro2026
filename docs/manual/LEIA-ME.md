# Manual do AgroDock — como atualizar

O PDF que o site oferece para download fica em `frontend/manual/Manual-AgroDock.pdf`
(link no menu **Ajuda** e no rodapé do site). Esta pasta guarda a fonte dele.

- `manual.html` — texto do manual (HTML + CSS de impressão A4).
- `img/` — capturas de tela usadas no manual.
- `demo.py` — cria dados de demonstração num sistema rodando em http://127.0.0.1:8000
  (rode com `FIN_MASTER_EMAIL=dono@agrodock.com.br` e banco vazio).
- `shots.py` e `ficha.py` — tiram as capturas (precisa de `playwright`).
- `pdf.py` — gera `Manual-AgroDock.pdf` a partir do `manual.html`.

Os scripts usam o caminho `/home/claude/manual`; ajuste para a sua pasta antes de rodar.
Depois de gerar, copie o PDF para `frontend/manual/` e rode `publicar.bat`.
A pasta `docs/` não vai para o Vercel (`.vercelignore`).
