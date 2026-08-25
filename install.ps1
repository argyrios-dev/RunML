$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "RunML v0.6.0 - Windows installer/updater"
Write-Host "----------------------------------------"
Write-Host ""

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python launcher 'py' was not found."
    Write-Host "Install Python 3.10+ and run this installer again."
    exit 1
}

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Join-Path $env:LOCALAPPDATA "RunML"
$RuntimeDir = Join-Path $InstallRoot "runtime"
$BinDir = Join-Path $InstallRoot "bin"
$Launcher = Join-Path $BinDir "runml.cmd"
$StateDir = Join-Path $env:APPDATA "RunML"
$PointerFile = Join-Path $StateDir "location.json"
$FirstStartMarker = Join-Path $StateDir "first-start.done"

$HadPreviousInstall = (Test-Path $RuntimeDir) -or (Test-Path $Launcher)

$DataDir = $null
if (Test-Path $PointerFile) {
    try {
        $DataDir = (Get-Content $PointerFile -Raw | ConvertFrom-Json).data_dir
    } catch {
        $DataDir = $null
    }
}

if ($HadPreviousInstall) {
    Write-Host "Previous RunML installation detected."
    try {
        $OldPython = Join-Path $RuntimeDir "Scripts\python.exe"
        if (Test-Path $OldPython) {
            $OldVersion = & $OldPython -m runml --version 2>$null
            if ($OldVersion) { Write-Host "Installed: $OldVersion" }
        }
    } catch {}
    Write-Host "It will be replaced by RunML v0.6.0."
    Write-Host ""
}

$HasLearningData = $false
if ($DataDir -and (Test-Path $DataDir)) {
    foreach ($name in @("data", "models", "reports")) {
        $candidate = Join-Path $DataDir $name
        if (Test-Path $candidate) {
            $item = Get-ChildItem -Force -Recurse -File $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($item) {
                $HasLearningData = $true
                break
            }
        }
    }
}

if ($HasLearningData) {
    Write-Host "Previous RunML learning data was found at:"
    Write-Host "  $DataDir"
    $answer = Read-Host "Delete previous TRAINED DATA/models/reports before upgrading? [y/N]"
    if ($answer.Trim().ToLower() -in @("y", "yes", "s", "si", "sí")) {
        foreach ($name in @("data", "models", "reports")) {
            $candidate = Join-Path $DataDir $name
            if (Test-Path $candidate) {
                Remove-Item -Recurse -Force $candidate
            }
            New-Item -ItemType Directory -Force -Path $candidate | Out-Null
        }
        Write-Host "Previous learning data removed. Settings were preserved."
    } else {
        Write-Host "Previous learning data will be preserved."
    }
    Write-Host ""
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

if (Test-Path $RuntimeDir) {
    Write-Host "Replacing private RunML runtime..."
    Remove-Item -Recurse -Force $RuntimeDir
}

Write-Host "Creating isolated Python runtime..."
py -m venv $RuntimeDir

$Python = Join-Path $RuntimeDir "Scripts\python.exe"

Write-Host "Installing RunML..."
& $Python -m pip install --disable-pip-version-check "$SourceDir"
if ($LASTEXITCODE -ne 0) {
    throw "RunML package installation failed."
}

$LauncherContent = @'
@echo off
"%LOCALAPPDATA%\RunML\runtime\Scripts\python.exe" -m runml %*
'@
Set-Content -Path $Launcher -Value $LauncherContent -Encoding ASCII

Copy-Item (Join-Path $SourceDir "uninstall.ps1") (Join-Path $InstallRoot "uninstall.ps1") -Force

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathParts = @()
if ($userPath) {
    $pathParts = @($userPath -split ";" | Where-Object { $_ -and $_.Trim() })
}

$alreadyInPath = $false
foreach ($part in $pathParts) {
    if ($part.TrimEnd("\") -ieq $BinDir.TrimEnd("\")) {
        $alreadyInPath = $true
        break
    }
}

if (-not $alreadyInPath) {
    [Environment]::SetEnvironmentVariable(
        "Path",
        (($pathParts + $BinDir) -join ";"),
        "User"
    )
    Write-Host "Added RunML to your user PATH."
}

# Fresh installs ask for a storage path on first `runml`.
# Upgrades with a valid previous data location keep that location/settings.
if ($DataDir -and (Test-Path $DataDir)) {
    Set-Content -Path $FirstStartMarker -Value "0.6.0" -Encoding ASCII
} else {
    if (Test-Path $FirstStartMarker) {
        Remove-Item -Force $FirstStartMarker
    }
}

Write-Host ""
Write-Host "RunML v0.6.0 installed successfully."
Write-Host "Open a new terminal and run:"
Write-Host "  runml"
Write-Host ""
if (-not ($DataDir -and (Test-Path $DataDir))) {
    Write-Host "The first start will require you to choose a data directory."
} else {
    Write-Host "Existing RunML settings/data location preserved:"
    Write-Host "  $DataDir"
}
