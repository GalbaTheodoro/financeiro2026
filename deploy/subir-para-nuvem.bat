@echo off
REM ==========================================================================
REM  Leva os dados que estao no seu PC (dados\financeiro.db) para o banco
REM  na nuvem. Faca isso UMA VEZ, quando o banco novo ainda esta vazio.
REM
REM  Precisa do arquivo deploy\nuvem.txt com o endereco do banco.
REM ==========================================================================
cd /d "%~dp0.."

if not exist "deploy\nuvem.txt" (
  echo Falta o arquivo deploy\nuvem.txt com o endereco do banco na nuvem.
  pause
  exit /b 1
)
set /p NUVEM=<deploy\nuvem.txt

if not exist ".venv" (
  echo Criando ambiente virtual...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Conferindo as bibliotecas (inclui o driver do PostgreSQL)...
python -m pip install --quiet --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Nao consegui instalar as bibliotecas. Confira a internet e tente de novo.
  pause
  exit /b 1
)
python deploy\migrar_para_postgres.py "%NUVEM%" %*

echo.
pause
