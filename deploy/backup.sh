#!/usr/bin/env bash
# =============================================================================
#  Backup do banco do AgroDock
#
#  Usa o comando .backup do SQLite, que copia o banco com segurança mesmo com
#  o sistema rodando (uma cópia simples do arquivo pode sair pela metade).
#  Guarda os últimos 30 dias e apaga os mais antigos.
#
#  Uso:   bash deploy/backup.sh
#  Roda sozinho todo dia às 3h (instalado pelo instalar.sh).
# =============================================================================
set -euo pipefail

PASTA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BANCO="$PASTA/dados/financeiro.db"
DESTINO="$PASTA/backups"
DIAS=30

[ -f "$BANCO" ] || { echo "$(date '+%d/%m %H:%M') banco ainda não existe, nada a fazer"; exit 0; }
mkdir -p "$DESTINO"

ARQUIVO="$DESTINO/financeiro-$(date +%Y-%m-%d_%H%M).db"
sqlite3 "$BANCO" ".backup '$ARQUIVO'"
gzip -f "$ARQUIVO"

# guarda só os últimos 30 dias
find "$DESTINO" -name 'financeiro-*.db.gz' -mtime +$DIAS -delete

TAMANHO="$(du -h "$ARQUIVO.gz" | cut -f1)"
QUANTOS="$(find "$DESTINO" -name 'financeiro-*.db.gz' | wc -l)"
echo "$(date '+%d/%m %H:%M') backup feito: $(basename "$ARQUIVO.gz") ($TAMANHO) — $QUANTOS cópias guardadas"
