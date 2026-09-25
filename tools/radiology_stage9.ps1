param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
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
$Tests = @("atlas/tests/test_radiology_cases.py", "atlas/tests/test_radiology_imaging.py", "atlas/tests/test_radiology_privacy.py", "atlas/tests/test_radiology_quality.py", "atlas/tests/test_radiology_geometry.py", "atlas/tests/test_radiology_annotations.py", "atlas/tests/test_radiology_reconstruction.py", "atlas/tests/test_radiology_reference.py", "atlas/tests/test_radiology_linked_viewer.py")
& $Python -m pytest @Tests -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
& $Python -m ruff check atlas/radiology @Tests
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
$DemoPath = Join-Path $Root ("data\radiology-lab\etapa9-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology linked-demo --output $DemoPath
if ($LASTEXITCODE -ne 0) { throw "Falha no visualizador integrado." }
$Viewer = Join-Path $DemoPath "linked-viewer\index.html"
Write-Host "Etapa 9: testes concluidos e visualizador preparado."
Write-Host ("Visualizador: " + $Viewer)
Write-Host "Gire a malha e clique para conferir as projecoes nas tres vistas."
Write-Host "LAB sintetico: o elipsoide nao representa osso real."
Start-Process -FilePath $Viewer
