@echo off
setlocal EnableDelayedExpansion
REM ==========================================================================
REM  PUBLICAR O AGRODOCK
REM
REM  Manda as alteracoes desta pasta para o GitHub. O Vercel percebe sozinho
REM  e coloca a versao nova no ar em 1 a 3 minutos.
REM
REM  Nunca envia: dados\financeiro.db (seu banco), deploy\nuvem.txt (senha do
REM  banco) e a pasta .venv  -- o arquivo .gitignore cuida disso e este atalho
REM  confere antes de enviar.
REM ==========================================================================
cd /d "%~dp0"
title Publicar AgroDock

echo.
echo ======================================================
echo   Publicar o AgroDock (GitHub -^> Vercel)
echo ======================================================
echo.

if not exist "app.py" (
  echo [ERRO] Nao encontrei o app.py nesta pasta.
  echo        Coloque este arquivo na pasta do projeto, junto do app.py.
  goto :fim_erro
)

REM ---------------------------------------------------------------- 1. Git
set "GIT="
where git >nul 2>nul && set "GIT=git"
if not defined GIT (
  for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
    if exist "%%D\resources\app\git\cmd\git.exe" set "GIT=%%D\resources\app\git\cmd\git.exe"
  )
)
if not defined GIT (
  echo [ERRO] O Git nao esta instalado neste computador.
  echo.
  echo  Instale o "Git for Windows" uma vez so:
  echo     https://git-scm.com/download/win   ^(Next, Next, Finish^)
  echo  ou, no Prompt de Comando:   winget install --id Git.Git -e
  echo.
  echo  Depois feche esta janela e rode o publicar.bat de novo.
  goto :fim_erro
)
echo [1/5] Git encontrado.

"%GIT%" rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Esta pasta ainda nao esta ligada ao GitHub.
  echo        Abra o GitHub Desktop: File ^> Add local repository ^> esta pasta.
  goto :fim_erro
)
"%GIT%" remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo [ERRO] O repositorio nao tem o endereco do GitHub ^(origin^).
  echo        No GitHub Desktop: Repository ^> Repository settings ^> Remote.
  goto :fim_erro
)

REM ------------------------------------------- 2. nome/e-mail do autor (se faltar)
"%GIT%" config user.email >nul 2>nul
if errorlevel 1 (
  "%GIT%" config user.name "Galba"
  "%GIT%" config user.email "galbatheo@gmail.com"
)

REM --------------------------------------------- 3. nada de banco ou senha no envio
for %%A in ("dados/financeiro.db" "deploy/nuvem.txt") do (
  "%GIT%" ls-files --error-unmatch %%~A >nul 2>nul
  if not errorlevel 1 (
    echo  Tirando %%~A do GitHub ^(o arquivo continua no seu PC^)...
    "%GIT%" rm --cached --quiet %%~A
  )
)
"%GIT%" ls-files --error-unmatch .venv >nul 2>nul
if not errorlevel 1 "%GIT%" rm -r --cached --quiet .venv
echo [2/5] Conferido: banco, senha e .venv ficam fora do envio.

REM ------------------------------------------------ 4. o codigo abre sem erro?
set "PY="
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (
  where python >nul 2>nul && set "PY=python"
)
if defined PY (
  "%PY%" -m py_compile app.py backend\main.py backend\config.py backend\database.py backend\migracao.py backend\assinaturas.py backend\deps.py
  if errorlevel 1 (
    echo [ERRO] Ha um erro de digitacao no codigo Python ^(veja acima^). Nada foi enviado.
    goto :fim_erro
  )
  echo [3/5] Codigo conferido.
) else (
  echo [3/5] Python nao encontrado - pulando a conferencia do codigo.
)

REM ------------------------------------------------------------ 5. commit + push
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'dd/MM/yyyy HH:mm'"`) do set "AGORA=%%T"
"%GIT%" add -A
"%GIT%" diff --cached --quiet
if errorlevel 1 (
  "%GIT%" commit -q -m "Publicacao %AGORA%"
  if errorlevel 1 (
    echo [ERRO] Nao consegui registrar as alteracoes ^(commit^).
    goto :fim_erro
  )
  echo [4/5] Alteracoes registradas: "Publicacao %AGORA%".
) else (
  echo [4/5] Nenhuma alteracao nova nos arquivos - enviando o que estiver pendente.
)

"%GIT%" rev-parse --abbrev-ref HEAD > "%TEMP%\agrodock_ramo.txt"
set /p RAMO=<"%TEMP%\agrodock_ramo.txt"
if not defined RAMO set "RAMO=main"
echo [5/5] Enviando para o GitHub ^(ramo !RAMO!^)...
echo       Se abrir uma janela pedindo login do GitHub, entre com a sua conta.
"%GIT%" push -u origin !RAMO!
if errorlevel 1 (
  echo.
  echo [ERRO] O envio para o GitHub falhou.
  echo  - Se pediu usuario/senha no terminal: abra o GitHub Desktop e clique em
  echo    "Push origin" ^(as alteracoes ja estao registradas, e so enviar^).
  echo  - Se falou em "rejected" ou "fetch first": no GitHub Desktop clique em
  echo    "Fetch origin" / "Pull origin" e rode este atalho de novo.
  goto :fim_erro
)

echo.
echo ======================================================
echo   PRONTO! Enviado para o GitHub.
echo   O Vercel coloca a versao nova no ar em 1 a 3 minutos.
echo   Acompanhe em: vercel.com ^> seu projeto ^> Deployments
echo ======================================================
echo.
pause
exit /b 0

:fim_erro
echo.
pause
exit /b 1
