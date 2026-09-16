#!/usr/bin/env bash
# =============================================================================
#  Atualizar o AgroDock no servidor
#
#  Rode DEPOIS de copiar os arquivos novos para a pasta (pelo WinSCP, scp ou
#  descompactando o zip por cima). Ele faz backup, instala o que mudou nas
#  dependências e reinicia o sistema.
#
#  Uso:   bash deploy/atualizar.sh
#
#  O banco (dados/financeiro.db) nunca é tocado: o próprio sistema atualiza
#  o formato das tabelas ao subir.
# =============================================================================
set -euo pipefail

PASTA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PASTA"

echo "→ Backup antes de mexer..."
bash deploy/backup.sh

echo "→ Atualizando dependências..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo "→ Reiniciando o sistema..."
sudo systemctl restart agrodock
sleep 3

if systemctl is-active --quiet agrodock; then
  VERSAO="$(curl -s --max-time 5 http://127.0.0.1:8000/api/health || true)"
  echo "✓ No ar. $VERSAO"
  echo "  (se o navegador ainda mostrar a versão antiga, aperte Ctrl+F5 uma vez)"
else
  echo "✗ Não subiu. Veja o motivo:"
  journalctl -u agrodock -n 30 --no-pager
  exit 1
fi
