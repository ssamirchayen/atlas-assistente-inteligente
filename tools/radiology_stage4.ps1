param()
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv-radiology\Scripts\python.exe"
foreach ($Required in @("requirements-radiology-dev.txt", "requirements-radiology.txt", "atlas\radiology\quality.py")) {
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
$Tests = @("atlas/tests/test_radiology_cases.py", "atlas/tests/test_radiology_imaging.py", "atlas/tests/test_radiology_privacy.py", "atlas/tests/test_radiology_quality.py")
& $Python -m pytest @Tests -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
& $Python -m ruff check atlas/radiology @Tests
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
$DemoPath = Join-Path $Root ("data\radiology-lab\etapa4-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology demo2d --output $DemoPath
if ($LASTEXITCODE -ne 0) { throw "Falha no LAB sintetico." }
$Manifest = Join-Path $DemoPath "case\case.json"
$Report = Join-Path $DemoPath "quality.json"
$Template = Join-Path $DemoPath "quality-review.json"
& $Python -m atlas.radiology quality $Manifest --output $Report --template $Template
if ($LASTEXITCODE -ne 0) { throw "Falha na triagem de qualidade." }
Write-Host "Etapa 4: testes concluidos. Revisao humana PENDENTE."
Write-Host ("LAB: " + $DemoPath)
Write-Host ("Relatorio: " + $Report)
Write-Host ("Modelo para revisao: " + $Template)
Write-Host "Os padroes sinteticos nao comprovam anatomia ou projecoes."
Start-Process -FilePath (Join-Path $DemoPath "viewer\index.html")
