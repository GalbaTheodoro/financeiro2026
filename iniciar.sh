#!/usr/bin/env bash
# Instala as dependências (na primeira vez) e sobe o sistema financeiro.
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}

if [ ! -d ".venv" ]; then
  echo "→ Criando ambiente virtual..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ Instalando/atualizando dependências..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo
echo "======================================================"
echo "  AgroDock — Contratos e Gestão rodando em http://localhost:8000"
echo "  Usuário: admin@financeiro.local     Senha: admin123"
echo "  (Ctrl+C para encerrar)"
echo "======================================================"
echo

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORTA:-8000}"
