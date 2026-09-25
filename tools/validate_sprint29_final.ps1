param(
    [string]$NexyraRoot = "C:\Nexyra_CRM_Atlas",
    [switch]$Online
)
$ErrorActionPreference = "Stop"
$AtlasRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AtlasPython = Join-Path $AtlasRoot ".venv\Scripts\python.exe"
$NexyraPython = Join-Path $NexyraRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $AtlasPython)) { throw "Python do Atlas não encontrado: $AtlasPython" }
if (-not (Test-Path $NexyraPython)) { throw "Python do Nexyra não encontrado: $NexyraPython" }
Write-Host "[1/6] Configuração e tokens (sem exibir segredos)" -ForegroundColor Cyan
$argsConfig = @("tools\validate_sprint29_nexyra.py", "--nexyra-root", $NexyraRoot)
if ($Online) { $argsConfig += "--online" }
& $AtlasPython @argsConfig
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[2/6] Ruff Atlas" -ForegroundColor Cyan
& $AtlasPython -m ruff check atlas tests tools
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[3/6] Pytest Atlas" -ForegroundColor Cyan
& $AtlasPython -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[4/6] Ruff Nexyra + Atlas" -ForegroundColor Cyan
Push-Location $NexyraRoot
try {
    & $NexyraPython -m ruff check app tests alembic tools
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "[5/6] Pytest Nexyra + Atlas" -ForegroundColor Cyan
    & $NexyraPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "[6/6] Build frontend" -ForegroundColor Cyan
    Push-Location (Join-Path $NexyraRoot "frontend")
    try {
        $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npm) { throw "npm.cmd não encontrado no PATH." }
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally { Pop-Location }
} finally { Pop-Location }
Write-Host "Sprint 29 validada com sucesso." -ForegroundColor Green
