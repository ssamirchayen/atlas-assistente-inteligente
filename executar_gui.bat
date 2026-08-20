@echo off
setlocal

set "ATLAS_ROOT=%~dp0"
set "ATLAS_PYTHON=%ATLAS_ROOT%.venv\Scripts\python.exe"

if not exist "%ATLAS_PYTHON%" (
    echo [ERRO] Ambiente virtual nao encontrado em:
    echo %ATLAS_PYTHON%
    pause
    exit /b 1
)

if not exist "%ATLAS_ROOT%gui_main.py" (
    echo [ERRO] gui_main.py nao encontrado em:
    echo %ATLAS_ROOT%gui_main.py
    pause
    exit /b 1
)

echo Iniciando o Atlas pelo PowerShell...

powershell.exe -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; Set-Location -LiteralPath '%ATLAS_ROOT%'; & '%ATLAS_PYTHON%' '%ATLAS_ROOT%gui_main.py'; exit $LASTEXITCODE"

set "ATLAS_EXIT_CODE=%ERRORLEVEL%"

if not "%ATLAS_EXIT_CODE%"=="0" (
    echo.
    echo [ERRO] O Atlas foi encerrado com o codigo %ATLAS_EXIT_CODE%.
    pause
)

exit /b %ATLAS_EXIT_CODE%
