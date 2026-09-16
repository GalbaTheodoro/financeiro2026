@echo off
REM ==========================================================================
REM  AgroDock no seu PC, usando o banco que esta na nuvem.
REM
REM  Abre o sistema aqui no computador, mas lendo e gravando no mesmo banco
REM  do site. O que voce lanca aqui aparece no celular na hora, e vice-versa.
REM
REM  Antes de usar: crie o arquivo deploy\nuvem.txt com UMA linha, o endereco
REM  do banco (Neon, com "Connection pooling" ligado). Exemplo:
REM      postgresql://neondb_owner:SENHA@ep-xxxx-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require
REM ==========================================================================
cd /d "%~dp0"

if not exist "deploy\nuvem.txt" (
  echo.
  echo  Falta o arquivo deploy\nuvem.txt com o endereco do banco na nuvem.
  echo  Abra o Bloco de Notas, cole o endereco que o Neon deu e salve com
  echo  esse nome dentro da pasta deploy.
  echo.
  pause
  exit /b 1
)

set /p FIN_DATABASE_URL=<deploy\nuvem.txt

if not exist ".venv" (
  echo Criando ambiente virtual...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo ======================================================
echo   AgroDock ligado no BANCO DA NUVEM
echo   Aqui no PC: http://localhost:8000
echo   (Ctrl+C para encerrar)
echo ======================================================
echo.

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
