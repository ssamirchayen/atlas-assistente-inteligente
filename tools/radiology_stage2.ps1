param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
if (!(Test-Path $Python)) {
    & py -3.13 -m venv (Join-Path $Root ".venv-radiology")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar ambiente Python 3.13." }
}
foreach ($Required in @("requirements-radiology.txt", "requirements-radiology-dev.txt", "atlas\radiology\viewer.html")) {
    if (!(Test-Path -LiteralPath (Join-Path $Root $Required))) { throw "Patch incompleto. Extraia todos os arquivos na raiz do Atlas: $Required" }
}
& $Python -m pip install -r (Join-Path $Root "requirements-radiology-dev.txt")
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependencias." }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependencias incompativeis." }
& $Python -m pytest atlas/tests/test_radiology_cases.py atlas/tests/test_radiology_imaging.py -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest da Radiologia." }
& $Python -m ruff check atlas/radiology atlas/tests/test_radiology_cases.py atlas/tests/test_radiology_imaging.py
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff da Radiologia." }
$DemoPath = Join-Path $Root ("data\radiology-lab\etapa2-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology demo2d --output $DemoPath
if ($LASTEXITCODE -ne 0) { throw "Falha na demonstracao 2D." }
$ViewerPath = Join-Path $DemoPath "viewer\index.html"
Write-Host ("Etapa 2 validada. Visualizador: " + $ViewerPath)
Start-Process -FilePath $ViewerPath
