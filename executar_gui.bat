@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente virtual nao encontrado.
    echo Execute a instalacao descrita no README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" gui_main.py
pause
