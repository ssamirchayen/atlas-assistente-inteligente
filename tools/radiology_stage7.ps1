param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
foreach ($Required in @("requirements-radiology-dev.txt", "requirements-radiology.txt", "atlas\radiology\reconstruction.py")) {
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
$Tests = @("atlas/tests/test_radiology_cases.py", "atlas/tests/test_radiology_imaging.py", "atlas/tests/test_radiology_privacy.py", "atlas/tests/test_radiology_quality.py", "atlas/tests/test_radiology_geometry.py", "atlas/tests/test_radiology_annotations.py", "atlas/tests/test_radiology_reconstruction.py")
& $Python -m pytest @Tests -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
& $Python -m ruff check atlas/radiology @Tests
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
$DemoPath = Join-Path $Root ("data\radiology-lab\etapa7-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology reconstruction-demo --output $DemoPath
if ($LASTEXITCODE -ne 0) { throw "LAB rejeitado ou volume tocando o limite da regiao." }
Write-Host "Etapa 7: testes e reconstrucao geometrica sintetica concluidos."
Write-Host ("Resultados: " + (Join-Path $DemoPath "result"))
Write-Host "O objeto do LAB e um elipsoide, nao osso, RX ou tomografia."
Get-Content -LiteralPath (Join-Path $DemoPath "synthetic-comparison.json")
Start-Process -FilePath (Join-Path $DemoPath "result")
