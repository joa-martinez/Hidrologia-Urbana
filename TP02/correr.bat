@echo off
rem Levanta el visualizador del balance en Windows.
rem La primera vez crea el entorno e instala las dependencias.
cd /d "%~dp0"

if not exist ".venv\Scripts\streamlit.exe" (
    echo Primera vez: creando el entorno e instalando dependencias...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo No se encontro Python. Instalalo desde https://www.python.org/downloads/
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\pip.exe" install -r requirements.txt
    if errorlevel 1 (
        echo Fallo la instalacion de dependencias.
        pause
        exit /b 1
    )
)

echo Abriendo el visualizador en http://localhost:8501 (Ctrl+C para cortar)
".venv\Scripts\streamlit.exe" run app.py
pause
