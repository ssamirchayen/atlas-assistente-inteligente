param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
if (!(Test-Path -LiteralPath (Join-Path $Root "atlas\radiology\export_bundle.py"))) { throw "Patch incompleto: export_bundle.py" }
if (!(Test-Path -LiteralPath (Join-Path $Root "atlas\radiology\uncertainty.py"))) { throw "Patch incompleto: uncertainty.py" }
foreach ($Required in @("requirements-radiology-dev.txt", "requirements-radiology.txt", "atlas\radiology\linked_viewer.py", "atlas\radiology\linked_viewer.html", "atlas\radiology\linked_math.js", "tools\radiology_linked_math_test.cjs")) {
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
$Tests = @("atlas/tests/test_radiology_cases.py", "atlas/tests/test_radiology_imaging.py", "atlas/tests/test_radiology_privacy.py", "atlas/tests/test_radiology_quality.py", "atlas/tests/test_radiology_geometry.py", "atlas/tests/test_radiology_annotations.py", "atlas/tests/test_radiology_reconstruction.py", "atlas/tests/test_radiology_reference.py", "atlas/tests/test_radiology_linked_viewer.py", "atlas/tests/test_radiology_uncertainty.py", "atlas/tests/test_radiology_export.py")
& $Python -m pytest @Tests -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
& $Python -m ruff check atlas/radiology @Tests
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
$DemoPath = Join-Path $Root ("data\radiology-lab\etapa11-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology export-demo --output $DemoPath
$ExportExit = $LASTEXITCODE
if ($ExportExit -ne 0 -and $ExportExit -ne 2) { throw "Falha na exportacao." }
if ($ExportExit -eq 2) { Write-Host "LAB rejeitado: malhas somente no pacote diagnostico, marcadas REJECTED." }
Write-Host ("Resultados: " + $DemoPath)
Write-Host "Etapa 11 executada. Confira blocked-export e diagnostic-export. Sem aprovacao clinica."
exit 0
