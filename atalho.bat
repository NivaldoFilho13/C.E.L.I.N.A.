@echo off
chcp 65001 >nul
title Celina
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo ERRO: ambiente virtual "venv" nao encontrado nesta pasta.
    echo Rode primeiro: python -m venv venv ^&^& venv\Scripts\activate ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

:menu
cls
echo ============================
echo           CELINA
echo ============================
echo.
echo 1 - Abrir interface web (recomendado)
echo 2 - Abrir chat no terminal
echo 3 - Extrair PDFs da pasta "pdfs"
echo 4 - Construir indice de busca
echo 5 - Sair
echo.
set /p opcao="Escolha uma opcao: "

if "%opcao%"=="1" goto web
if "%opcao%"=="2" goto terminal
if "%opcao%"=="3" goto extrair
if "%opcao%"=="4" goto indice
if "%opcao%"=="5" goto fim

echo Opcao invalida.
pause
goto menu

:web
streamlit run app.py
pause
goto menu

:terminal
python chat.py
pause
goto menu

:extrair
python extract_pdfs.py
pause
goto menu

:indice
python build_index.py
pause
goto menu

:fim
exit /b 0
