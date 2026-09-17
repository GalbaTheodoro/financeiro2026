# Manual do AgroDock — como atualizar

O PDF que o site oferece para download fica em `frontend/manual/Manual-AgroDock.pdf`
(link no menu **Ajuda** e no rodapé do site). Esta pasta guarda a fonte dele.

- `manual.html` — texto do manual (HTML + CSS de impressão A4).
- `img/` — capturas de tela usadas no manual.
- `servidor_demo.py` — sobe o sistema em http://127.0.0.1:8000 com banco vazio, dono
  `dono@agrodock.com.br` e cotações/notícias lidas das respostas gravadas em `testes/`
  (não precisa de internet).
- `demo.py` — cria os dados de demonstração (inclui comprador em SP e tabela de ICMS de MG).
- `shots.py`, `ficha.py`, `folha.py` (ICMS na folha impressa), `cfg.py` (grupo de cotações
  em Config. do site) e `cv.py` (contratos de compra e de venda) — tiram as capturas
  (precisa de `playwright`).
- `pdf.py` — gera `Manual-AgroDock.pdf` a partir do `manual.html`.

Os scripts usam o caminho `/home/claude/manual`; ajuste para a sua pasta antes de rodar.
Depois de gerar, copie o PDF para `frontend/manual/` e rode `publicar.bat`.
A pasta `docs/` não vai para o Vercel (`.vercelignore`).
