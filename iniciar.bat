@echo off
REM Instala as dependencias (na primeira vez) e sobe o sistema financeiro.
cd /d "%~dp0"

if not exist ".venv" (
  echo Criando ambiente virtual...
  python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Instalando/atualizando dependencias...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo ======================================================
echo   AgroDock - Contratos e Gestao em http://localhost:8000
echo   Usuario: admin@financeiro.local    Senha: admin123
echo   (Ctrl+C para encerrar)
echo ======================================================
echo.

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
