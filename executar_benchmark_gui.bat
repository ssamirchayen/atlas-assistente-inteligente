@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual nao encontrado em .venv\Scripts\python.exe
    pause
    exit /b 1
)

".venv\Scripts\python.exe" benchmark_gui.py
if errorlevel 1 (
    echo.
    echo [ERRO] O Atlas Benchmark encerrou com erro.
    pause
)
endlocal
