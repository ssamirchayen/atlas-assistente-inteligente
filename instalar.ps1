$ErrorActionPreference = "Stop"

Write-Host "Criando ambiente Python 3.13..."
py -3.13 -m venv .venv

$Python = ".\.venv\Scripts\python.exe"

Write-Host "Atualizando o pip..."
& $Python -m pip install --upgrade pip

Write-Host "Instalando dependencias do Atlas..."
& $Python -m pip install -r requirements.txt

Write-Host "Instalando o Chromium usado pelo Playwright..."
& $Python -m playwright install chromium

Write-Host ""
Write-Host "Atlas instalado com sucesso."
Write-Host "Execute: .\.venv\Scripts\python.exe main.py"
