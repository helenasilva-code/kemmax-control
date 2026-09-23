@echo off
rem Kemmax Control - abre o sistema no navegador, apenas neste computador.
cd /d "%~dp0"

if not exist .venv (
    echo Preparando o sistema pela primeira vez, aguarde...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Python nao encontrado. Instale o Python 3.11 ou mais novo em https://www.python.org/downloads/
        echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Falha ao instalar as dependencias. Verifique a internet e tente de novo.
    pause
    exit /b 1
)

echo.
echo Kemmax Control rodando em http://localhost:8501  (feche esta janela para encerrar)
python -m streamlit run app.py --server.address localhost --server.headless false
pause
