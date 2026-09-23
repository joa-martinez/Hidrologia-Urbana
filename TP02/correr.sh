#!/usr/bin/env bash
# Levanta el visualizador del balance. La primera vez crea el entorno e instala todo.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/streamlit ]; then
    echo "Primera vez: creando el entorno e instalando dependencias..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

echo "Abriendo el visualizador en http://localhost:8501 (Ctrl+C para cortar)"
exec .venv/bin/streamlit run app.py
