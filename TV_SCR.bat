@echo off
rem ====================================================================
rem  TV SCR - lancador da aplicacao de dimensionamento SCR-deNOx
rem
rem  Duplo clique neste ficheiro, ou correr num terminal qualquer.
rem  Procura sozinho um Python com numpy, scipy, pandas e tkinter, para
rem  nao depender do que estiver no PATH (no Windows, o "python" do PATH
rem  costuma ser o atalho da Microsoft Store, que nao serve).
rem ====================================================================
setlocal enabledelayedexpansion
title TV SCR - Dimensionamento de sistemas SCR-deNOx
cd /d "%~dp0"

set "PY="

rem --- 1. Instalacoes tipicas de Anaconda / Miniconda -------------------
for %%P in (
  "%USERPROFILE%\anaconda3\python.exe"
  "%USERPROFILE%\miniconda3\python.exe"
  "%LOCALAPPDATA%\anaconda3\python.exe"
  "C:\ProgramData\anaconda3\python.exe"
  "C:\ProgramData\miniconda3\python.exe"
) do (
  if not defined PY if exist %%P (
    %%P -c "import numpy, scipy, pandas, tkinter" >nul 2>&1 && set "PY=%%~P"
  )
)

rem --- 2. Python oficial instalado no utilizador ------------------------
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if not defined PY if exist "%%D\python.exe" (
      "%%D\python.exe" -c "import numpy, scipy, pandas, tkinter" >nul 2>&1 && set "PY=%%D\python.exe"
    )
  )
)

rem --- 3. O que estiver no PATH ----------------------------------------
if not defined PY (
  for %%C in (py python) do (
    if not defined PY (
      %%C -c "import numpy, scipy, pandas, tkinter" >nul 2>&1 && set "PY=%%C"
    )
  )
)

if not defined PY (
  echo.
  echo  Nao encontrei um Python com as bibliotecas necessarias.
  echo.
  echo  A aplicacao precisa de Python 3.9+ com numpy, scipy, pandas e tkinter.
  echo  Instale-as com:
  echo.
  echo      pip install -r requirements.txt
  echo.
  echo  Se usa Anaconda, abra o "Anaconda Prompt" e corra ai o comando
  echo  acima, nesta pasta.
  echo.
  pause
  exit /b 1
)

echo  A usar: !PY!
echo.
"!PY!" app.py
if errorlevel 1 (
  echo.
  echo  A aplicacao terminou com erro. A mensagem acima diz porque.
  pause
)
endlocal
