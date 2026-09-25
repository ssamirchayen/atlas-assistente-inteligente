param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
foreach ($Required in @("requirements-radiology-dev.txt", "requirements-radiology.txt", "atlas\radiology\reference.py", "atlas\radiology\reference_lab.py")) {
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
$Tests = @("atlas/tests/test_radiology_cases.py", "atlas/tests/test_radiology_imaging.py", "atlas/tests/test_radiology_privacy.py", "atlas/tests/test_radiology_quality.py", "atlas/tests/test_radiology_geometry.py", "atlas/tests/test_radiology_annotations.py", "atlas/tests/test_radiology_reconstruction.py", "atlas/tests/test_radiology_reference.py")
& $Python -m pytest @Tests -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
& $Python -m ruff check atlas/radiology @Tests
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
$DemoPath = Join-Path $Root ("data\radiology-lab\etapa8-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology reference-demo --output $DemoPath
if ($LASTEXITCODE -ne 0) { throw "Falha no LAB de referencia." }
Write-Host "Etapa 8: infraestrutura de referencia e projecoes sinteticas conferida."
Write-Host ("Resultados: " + $DemoPath)
Write-Host "Nenhuma tomografia real foi usada e nenhum modelo neural foi treinado."
Get-Content -LiteralPath (Join-Path $DemoPath "baseline-comparison.json")
Start-Process -FilePath $DemoPath
