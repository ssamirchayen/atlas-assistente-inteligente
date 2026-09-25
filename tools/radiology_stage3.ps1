param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
foreach ($Required in @("requirements-radiology-dev.txt", "requirements-radiology.txt", "atlas\radiology\privacy.py")) {
    if (!(Test-Path -LiteralPath (Join-Path $Root $Required))) { throw "Patch incompleto: $Required" }
}
if (!(Test-Path $Python)) {
    & py -3.13 -m venv (Join-Path $Root ".venv-radiology")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar ambiente." }
}
& $Python -m pip install -r (Join-Path $Root "requirements-radiology-dev.txt")
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependencias." }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependencias incompativeis." }
& $Python -m pytest atlas/tests/test_radiology_cases.py atlas/tests/test_radiology_imaging.py atlas/tests/test_radiology_privacy.py -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
& $Python -m ruff check atlas/radiology atlas/tests/test_radiology_cases.py atlas/tests/test_radiology_imaging.py atlas/tests/test_radiology_privacy.py
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
$DemoPath = Join-Path $Root ("data\radiology-lab\etapa3-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology demo2d --output $DemoPath
if ($LASTEXITCODE -ne 0) { throw "Falha no LAB sintetico." }
$PrivacyPath = Join-Path $DemoPath "privacy"
& $Python -m atlas.radiology privacy-prepare (Join-Path $DemoPath "case\case.json") --output $PrivacyPath
if ($LASTEXITCODE -ne 0) { throw "Falha na preparacao de privacidade." }
Write-Host "Etapa 3: testes concluidos. LAB sintetico preparado, revisao ainda PENDENTE."
Write-Host ("Pasta de revisao: " + $PrivacyPath)
Write-Host "Leia docs/RADIOLOGIA_ETAPA3.md para registrar a revisao e exportar."
Start-Process -FilePath (Join-Path $PrivacyPath "review.html")
