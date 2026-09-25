param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (!(Test-Path ".\atlas\radiology\__main__.py")) {
    throw "Extraia o patch na raiz do Atlas antes de executar."
}
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
if (!(Test-Path $Python)) {
    & py -3.13 -m venv (Join-Path $Root ".venv-radiology")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar ambiente. Confira a instalacao do Python 3.13." }
}
& $Python -m pip install -r requirements-radiology-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar ferramentas de teste." }

& $Python -m pytest atlas/tests/test_radiology_cases.py -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest da Radiologia." }
& $Python -m ruff check atlas/radiology atlas/tests/test_radiology_cases.py
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff da Radiologia." }

$DemoPath = Join-Path $Root ("data\radiology-lab\etapa1-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology demo --output $DemoPath
if ($LASTEXITCODE -ne 0) { throw "Falha ao criar demonstracao." }
& $Python -m atlas.radiology validate (Join-Path $DemoPath "case.json")
if ($LASTEXITCODE -ne 0) { throw "Falha ao validar demonstracao." }
Write-Host ("Fundacao validada. Caso sintetico: " + $DemoPath)
Write-Host "Esta etapa confere arquivos e metadados. Ainda nao gera reconstrucao 3D."
