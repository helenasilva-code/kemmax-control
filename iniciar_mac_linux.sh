#!/usr/bin/env bash
# Kemmax Control - abre o sistema no navegador, apenas neste computador.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Preparando o sistema pela primeira vez, aguarde..."
    python3 -m venv .venv || { echo "Instale o Python 3.11+ em https://www.python.org/downloads/"; exit 1; }
fi

. .venv/bin/activate
python -m pip install --quiet --disable-pip-version-check -r requirements.txt

echo "Kemmax Control rodando em http://localhost:8501 (Ctrl+C para encerrar)"
python -m streamlit run app.py --server.address localhost
