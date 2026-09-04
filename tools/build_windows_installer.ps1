[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$InstallBuildDependencies,
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "O Atlas.exe e o instalador Windows devem ser compilados no Windows."
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Spec = Join-Path $ProjectRoot "packaging\atlas.spec"
$Manifest = Join-Path $ProjectRoot "packaging\release_manifest.json"
$ReleaseDir = Join-Path $ProjectRoot "dist\Atlas"
$BuildDir = Join-Path $ProjectRoot "build\atlas"
$InstallerScript = Join-Path $ProjectRoot "packaging\windows\atlas.iss"
$InstallerDir = Join-Path $ProjectRoot "dist\installer"
$InstallerPath = Join-Path $InstallerDir "AtlasCoreSetup-1.0.0.exe"
$AtlasExe = Join-Path $ReleaseDir "Atlas.exe"
$VoiceRequirements = Join-Path $ProjectRoot "requirements-voice.txt"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Ambiente virtual não encontrado em .venv."
}

Push-Location $ProjectRoot
try {
    Write-Host "[1/10] Validando frontend Sprint 26..."
    & $Python -m tools.validate_sprint26_frontend
    if ($LASTEXITCODE -ne 0) {
        throw "A pré-validação da Sprint 26 falhou."
    }

    if (-not $SkipTests) {
        Write-Host "[2/10] Executando pytest..."
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "A suíte de testes falhou." }

        Write-Host "[3/10] Executando Ruff..."
        & $Python -m ruff check .
        if ($LASTEXITCODE -ne 0) { throw "O Ruff encontrou problemas." }
    }
    else {
        Write-Host "[2/10] Testes ignorados por -SkipTests."
        Write-Host "[3/10] Ruff ignorado por -SkipTests."
    }

    Write-Host "[4/10] Garantindo Voice Pack neural (Edge TTS)..."
    & $Python -c "import edge_tts"
    if ($LASTEXITCODE -ne 0) {
        if (-not (Test-Path -LiteralPath $VoiceRequirements -PathType Leaf)) {
            throw "requirements-voice.txt não encontrado."
        }
        & $Python -m pip install -r $VoiceRequirements
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar o Voice Pack neural." }
    }
    & $Python -m tools.validate_voice_pack
    if ($LASTEXITCODE -ne 0) { throw "Validação do Voice Pack falhou." }

    if ($InstallBuildDependencies) {
        Write-Host "[5/10] Instalando dependências de build..."
        & $Python -m pip install -r requirements-build.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao instalar dependências de build."
        }
    }
    else {
        Write-Host "[5/10] Verificando PyInstaller..."
    }

    & $Python -c "import PyInstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller ausente. Rode novamente com -InstallBuildDependencies."
    }

    Write-Host "[6/10] Limpando somente saídas antigas de build..."
    if (Test-Path -LiteralPath $ReleaseDir) {
        Remove-Item -LiteralPath $ReleaseDir -Recurse -Force
    }
    if (Test-Path -LiteralPath $BuildDir) {
        Remove-Item -LiteralPath $BuildDir -Recurse -Force
    }

    Write-Host "[7/10] Gerando Atlas.exe com frontend + Voice Pack..."
    & $Python -m PyInstaller --clean --noconfirm $Spec
    if ($LASTEXITCODE -ne 0) { throw "Falha no build do Atlas.exe." }
    if (-not (Test-Path -LiteralPath $AtlasExe -PathType Leaf)) {
        throw "Atlas.exe não foi criado no caminho esperado."
    }

    Write-Host "[8/10] Validando conteúdo da release..."
    & $Python -m tools.validate_release $ReleaseDir --manifest $Manifest
    if ($LASTEXITCODE -ne 0) {
        throw "A saída do PyInstaller foi rejeitada pelo validador."
    }

    Write-Host "[9/10] Testando Voice Pack dentro do Atlas.exe..."
    & $AtlasExe --voice-selftest
    if ($LASTEXITCODE -ne 0) {
        throw "O Atlas.exe foi criado sem o Voice Pack neural completo."
    }

    if (-not $IsccPath) {
        $Candidates = @(
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
        )
        $IsccPath = $Candidates |
            Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
            Select-Object -First 1
    }

    if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
        throw "Compilador Inno Setup 6 não encontrado. Informe -IsccPath."
    }

    Write-Host "[10/10] Gerando instalador Atlas Core 1.0.0..."
    & $IsccPath "/DSourceDir=$ReleaseDir" $InstallerScript
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }
    if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
        throw "O instalador não foi criado no caminho esperado."
    }

    $ExeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $AtlasExe).Hash
    $InstallerHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash

    Write-Host ""
    Write-Host "BUILD FINAL + VOICE PACK CONCLUÍDA" -ForegroundColor Green
    Write-Host "Atlas.exe: $AtlasExe"
    Write-Host "SHA256 EXE: $ExeHash"
    Write-Host "Instalador: $InstallerPath"
    Write-Host "SHA256 SETUP: $InstallerHash"
    Write-Host ""
    Write-Host "Próximo passo: testar o EXE e depois uma instalação limpa antes do GitHub."
}
finally {
    Pop-Location
}
