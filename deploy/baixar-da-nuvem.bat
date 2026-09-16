@echo off
REM ==========================================================================
REM  Traz uma copia do banco da nuvem para o seu PC (backup).
REM  A copia fica em backups\, com a data no nome. O banco da nuvem nao muda.
REM ==========================================================================
cd /d "%~dp0.."

if not exist "deploy\nuvem.txt" (
  echo Falta o arquivo deploy\nuvem.txt com o endereco do banco na nuvem.
  pause
  exit /b 1
)
set /p NUVEM=<deploy\nuvem.txt

if not exist "backups" mkdir backups
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set HOJE=%%c-%%b-%%a

if not exist ".venv" (
  echo Criando ambiente virtual...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Conferindo as bibliotecas (inclui o driver do PostgreSQL)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo Nao consegui instalar as bibliotecas. Confira a internet e tente de novo.
  pause
  exit /b 1
)
python deploy\migrar_para_postgres.py "%NUVEM%" --baixar --limpar ^
       --origem "backups\nuvem-%HOJE%.db"

echo.
echo Copia guardada na pasta backups.
pause
