param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
foreach ($Required in @("requirements-radiology-dev.txt", "requirements-radiology.txt", "atlas\radiology\geometry.py")) {
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
$Tests = @("atlas/tests/test_radiology_cases.py", "atlas/tests/test_radiology_imaging.py", "atlas/tests/test_radiology_privacy.py", "atlas/tests/test_radiology_quality.py", "atlas/tests/test_radiology_geometry.py")
& $Python -m pytest @Tests -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
& $Python -m ruff check atlas/radiology @Tests
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
$DemoPath = Join-Path $Root ("data\radiology-lab\etapa5-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $DemoPath | Out-Null
$Config = Join-Path $DemoPath "geometry.json"
$Report = Join-Path $DemoPath "geometry-report.json"
& $Python -m atlas.radiology geometry-demo --output $Config
if ($LASTEXITCODE -ne 0) { throw "Falha no LAB geometrico." }
& $Python -m atlas.radiology geometry-check $Config --output $Report
if ($LASTEXITCODE -ne 0) { throw "Falha na consistencia geometrica sintetica." }
Write-Host "Etapa 5: testes e geometria sintetica conferidos."
Write-Host ("Relatorio: " + $Report)
Write-Host "Este teste nao calibra equipamento real e nao gera reconstrucoes osseas."
Get-Content -LiteralPath $Report
