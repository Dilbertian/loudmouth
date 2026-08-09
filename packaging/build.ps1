<#
.SYNOPSIS
    Build the Loudmouth Windows consumer package: PyInstaller onedir app,
    then (optionally) the Inno Setup installer, signing, and checksums.

.DESCRIPTION
    Repeatable, CI-ready build. Steps:
      1. Read the version from server.py (single source of truth)
      2. Run the test suite (skip with -SkipTests)
      3. PyInstaller onedir/noconsole/noupx build -> dist\Loudmouth\
      4. Sign loudmouth.exe            (only if signing env is configured)
      5. Inno Setup -> dist\LoudmouthSetup-<version>.exe  (skip with -SkipInstaller)
      6. Sign LoudmouthSetup.exe       (only if signing env is configured)
      7. SHA-256 checksums -> dist\SHA256SUMS.txt

    Unsigned builds are fine for internal testing (Pegasus/fleet);
    sign from first external beta. See sign.ps1 for signing config.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipTests -SkipInstaller
#>
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# --- 1. Version from server.py -------------------------------------------
$versionLine = Select-String -Path "server.py" -Pattern '^__version__\s*=\s*"([^"]+)"'
if (-not $versionLine) { throw "Could not find __version__ in server.py" }
$Version = $versionLine.Matches[0].Groups[1].Value
Write-Host "== Loudmouth build $Version ==" -ForegroundColor Cyan

# --- 2. Tests --------------------------------------------------------------
if (-not $SkipTests) {
    Write-Host "-- Running tests" -ForegroundColor Cyan
    python -m pytest test_server.py -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed - aborting build" }
}

# --- 3. PyInstaller ---------------------------------------------------------
Write-Host "-- PyInstaller (onedir, noconsole, noupx)" -ForegroundColor Cyan
if (Test-Path "dist\Loudmouth") { Remove-Item -Recurse -Force "dist\Loudmouth" }
python -m PyInstaller --clean --noconfirm "packaging\loudmouth.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
if (-not (Test-Path "dist\Loudmouth\loudmouth.exe")) { throw "dist\Loudmouth\loudmouth.exe not produced" }

# --- 4. Sign the app exe ----------------------------------------------------
& "$PSScriptRoot\sign.ps1" -Path "dist\Loudmouth\loudmouth.exe"

# --- 5. Inno Setup installer ------------------------------------------------
if (-not $SkipInstaller) {
    $iscc = Get-Command "iscc" -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $defaultIscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        if (Test-Path $defaultIscc) { $iscc = Get-Command $defaultIscc }
    }
    if (-not $iscc) { throw "Inno Setup (iscc) not found - install Inno Setup 6 or pass -SkipInstaller" }

    Write-Host "-- Inno Setup installer" -ForegroundColor Cyan
    & $iscc.Source "/DAppVersion=$Version" "packaging\loudmouth.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed" }

    $setupExe = "dist\LoudmouthSetup-$Version.exe"
    if (-not (Test-Path $setupExe)) { throw "$setupExe not produced" }

    # --- 6. Sign the installer (both layers get signed + timestamped) ------
    & "$PSScriptRoot\sign.ps1" -Path $setupExe

    # --- 7. Checksums -------------------------------------------------------
    Write-Host "-- SHA-256 checksums" -ForegroundColor Cyan
    $hash = (Get-FileHash $setupExe -Algorithm SHA256).Hash.ToLower()
    "$hash  LoudmouthSetup-$Version.exe" | Out-File -Encoding ascii "dist\SHA256SUMS.txt"
    Get-Content "dist\SHA256SUMS.txt"
}

Write-Host "== Build complete ==" -ForegroundColor Green
