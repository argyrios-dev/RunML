$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "RunML v0.6.0 - Windows installer/updater"
Write-Host "----------------------------------------"
Write-Host ""

# ============================================================
# Locate Python
# ============================================================

$PythonCommand = $null
$PythonArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        $test = & py -3 -c "import sys; print(sys.executable)" 2>$null

        if ($LASTEXITCODE -eq 0 -and $test) {
            $PythonCommand = "py"
            $PythonArgs = @("-3")
        }
    }
    catch {}
}

if (-not $PythonCommand) {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            $test = & python -c "import sys; print(sys.executable)" 2>$null

            if ($LASTEXITCODE -eq 0 -and $test) {
                $PythonCommand = "python"
                $PythonArgs = @()
            }
        }
        catch {}
    }
}

if (-not $PythonCommand) {
    Write-Host "ERROR: Python was not found."
    Write-Host ""
    Write-Host "RunML requires Python 3.10 or newer."
    Write-Host ""
    Write-Host "Install Python and make sure the 'python' command is available in PATH."
    Write-Host ""
    exit 1
}

# ============================================================
# Verify Python version
# ============================================================

$VersionCheck = & $PythonCommand @PythonArgs -c "import sys; print('OK' if sys.version_info >= (3,10) else 'OLD')"

if ($LASTEXITCODE -ne 0 -or $VersionCheck.Trim() -ne "OK") {
    $CurrentVersion = & $PythonCommand @PythonArgs --version

    Write-Host "ERROR: RunML requires Python 3.10 or newer."
    Write-Host "Detected: $CurrentVersion"
    Write-Host ""
    exit 1
}

$PythonVersion = & $PythonCommand @PythonArgs --version
$PythonExecutable = & $PythonCommand @PythonArgs -c "import sys; print(sys.executable)"

Write-Host "Python detected:"
Write-Host "  Version : $PythonVersion"
Write-Host "  Path    : $PythonExecutable"
Write-Host ""

# ============================================================
# Paths
# ============================================================

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$InstallRoot = Join-Path $env:LOCALAPPDATA "RunML"
$RuntimeDir = Join-Path $InstallRoot "runtime"
$BinDir = Join-Path $InstallRoot "bin"
$Launcher = Join-Path $BinDir "runml.cmd"

$StateDir = Join-Path $env:APPDATA "RunML"
$PointerFile = Join-Path $StateDir "location.json"
$FirstStartMarker = Join-Path $StateDir "first-start.done"

# ============================================================
# Detect previous installation
# ============================================================

$HadPreviousInstall = (
    (Test-Path $RuntimeDir) -or
    (Test-Path $Launcher)
)

$DataDir = $null

if (Test-Path $PointerFile) {
    try {
        $Pointer = Get-Content $PointerFile -Raw | ConvertFrom-Json

        if ($Pointer.data_dir) {
            $DataDir = $Pointer.data_dir
        }
    }
    catch {
        $DataDir = $null
    }
}

if ($HadPreviousInstall) {
    Write-Host "Previous RunML installation detected."

    $OldPython = Join-Path $RuntimeDir "Scripts\python.exe"

    if (Test-Path $OldPython) {
        try {
            $OldVersion = & $OldPython -m runml --version 2>$null

            if ($OldVersion) {
                Write-Host "Installed version: $OldVersion"
            }
        }
        catch {}
    }

    Write-Host ""
    Write-Host "The previous runtime will be replaced by RunML v0.6.0."
    Write-Host ""
}

# ============================================================
# Detect existing learning data
# ============================================================

$HasLearningData = $false

if ($DataDir -and (Test-Path $DataDir)) {

    foreach ($FolderName in @("data", "models", "reports")) {

        $Candidate = Join-Path $DataDir $FolderName

        if (Test-Path $Candidate) {

            $ExistingFile = Get-ChildItem `
                -Path $Candidate `
                -File `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue |
                Select-Object -First 1

            if ($ExistingFile) {
                $HasLearningData = $true
                break
            }
        }
    }
}

# ============================================================
# Ask whether previous learning data should be removed
# ============================================================

if ($HasLearningData) {

    Write-Host "Existing RunML learning data was found:"
    Write-Host ""
    Write-Host "  $DataDir"
    Write-Host ""

    $Answer = Read-Host "Delete previous trained data/models/reports? [y/N]"

    $DeleteData = $false

    switch ($Answer.Trim().ToLower()) {
        "y"   { $DeleteData = $true }
        "yes" { $DeleteData = $true }
        "s"   { $DeleteData = $true }
        "si"  { $DeleteData = $true }
        "sí"  { $DeleteData = $true }
    }

    if ($DeleteData) {

        foreach ($FolderName in @("data", "models", "reports")) {

            $Candidate = Join-Path $DataDir $FolderName

            if (Test-Path $Candidate) {
                Remove-Item -Path $Candidate -Recurse -Force
            }

            New-Item `
                -ItemType Directory `
                -Force `
                -Path $Candidate |
                Out-Null
        }

        Write-Host ""
        Write-Host "Previous learning data removed."
        Write-Host "RunML settings and storage location were preserved."
    }
    else {
        Write-Host ""
        Write-Host "Previous learning data preserved."
    }

    Write-Host ""
}

# ============================================================
# Create installation directories
# ============================================================

New-Item `
    -ItemType Directory `
    -Force `
    -Path $InstallRoot |
    Out-Null

New-Item `
    -ItemType Directory `
    -Force `
    -Path $BinDir |
    Out-Null

New-Item `
    -ItemType Directory `
    -Force `
    -Path $StateDir |
    Out-Null

# ============================================================
# Remove previous runtime
# ============================================================

if (Test-Path $RuntimeDir) {

    Write-Host "Replacing previous private RunML runtime..."

    Remove-Item `
        -Path $RuntimeDir `
        -Recurse `
        -Force
}

# ============================================================
# Create private Python environment
# ============================================================

Write-Host "Creating isolated RunML Python environment..."

& $PythonCommand @PythonArgs -m venv "$RuntimeDir"

if ($LASTEXITCODE -ne 0) {
    throw "Failed to create RunML private Python environment."
}

$PrivatePython = Join-Path $RuntimeDir "Scripts\python.exe"

if (-not (Test-Path $PrivatePython)) {
    throw "RunML private Python executable was not created."
}

# ============================================================
# Install RunML
# ============================================================

Write-Host "Installing RunML..."

& $PrivatePython `
    -m pip `
    install `
    --disable-pip-version-check `
    "$SourceDir"

if ($LASTEXITCODE -ne 0) {
    throw "RunML package installation failed."
}

# ============================================================
# Create global runml command
# ============================================================

$LauncherContent = @'
@echo off
"%LOCALAPPDATA%\RunML\runtime\Scripts\python.exe" -m runml %*
'@

Set-Content `
    -Path $Launcher `
    -Value $LauncherContent `
    -Encoding ASCII

# ============================================================
# Copy uninstaller
# ============================================================

$UninstallerSource = Join-Path $SourceDir "uninstall.ps1"
$UninstallerDestination = Join-Path $InstallRoot "uninstall.ps1"

if (Test-Path $UninstallerSource) {
    Copy-Item `
        $UninstallerSource `
        $UninstallerDestination `
        -Force
}

# ============================================================
# Add RunML to user PATH
# ============================================================

$UserPath = [Environment]::GetEnvironmentVariable(
    "Path",
    "User"
)

$PathParts = @()

if ($UserPath) {

    $PathParts = @(
        $UserPath -split ";" |
        Where-Object {
            $_ -and $_.Trim()
        }
    )
}

$AlreadyInPath = $false

foreach ($Part in $PathParts) {

    if (
        $Part.TrimEnd("\") -ieq
        $BinDir.TrimEnd("\")
    ) {
        $AlreadyInPath = $true
        break
    }
}

if (-not $AlreadyInPath) {

    $NewUserPath = (
        ($PathParts + $BinDir) -join ";"
    )

    [Environment]::SetEnvironmentVariable(
        "Path",
        $NewUserPath,
        "User"
    )

    Write-Host "RunML added to your user PATH."
}
else {
    Write-Host "RunML is already present in your user PATH."
}

# Make runml usable immediately in this PowerShell too
$CurrentPathContainsRunML = $false

foreach ($Part in ($env:Path -split ";")) {

    if (
        $Part.TrimEnd("\") -ieq
        $BinDir.TrimEnd("\")
    ) {
        $CurrentPathContainsRunML = $true
        break
    }
}

if (-not $CurrentPathContainsRunML) {
    $env:Path = "$env:Path;$BinDir"
}

# ============================================================
# First-start behavior
# ============================================================

# Existing installation with a valid selected data location:
# preserve that configuration.
#
# Fresh installation:
# remove marker so first `runml` requires the user to explicitly
# choose a storage directory.

if ($DataDir -and (Test-Path $DataDir)) {

    Set-Content `
        -Path $FirstStartMarker `
        -Value "0.6.0" `
        -Encoding ASCII
}
else {

    if (Test-Path $FirstStartMarker) {
        Remove-Item `
            -Path $FirstStartMarker `
            -Force
    }
}

# ============================================================
# Verify installed RunML
# ============================================================

Write-Host ""
Write-Host "Verifying installation..."

$InstalledVersion = & $PrivatePython -m runml --version

if ($LASTEXITCODE -ne 0) {
    throw "RunML installation verification failed."
}

# ============================================================
# Done
# ============================================================

Write-Host ""
Write-Host "=========================================="
Write-Host " RunML installation complete"
Write-Host "=========================================="
Write-Host ""
Write-Host "Installed:"
Write-Host "  $InstalledVersion"
Write-Host ""
Write-Host "Runtime:"
Write-Host "  $RuntimeDir"
Write-Host ""
Write-Host "Global command:"
Write-Host "  runml"
Write-Host ""

if ($DataDir -and (Test-Path $DataDir)) {

    Write-Host "Existing data location preserved:"
    Write-Host "  $DataDir"
}
else {

    Write-Host "On the first start, RunML will ask you"
    Write-Host "where datasets, models, reports and settings"
    Write-Host "should be stored."
}

Write-Host ""
Write-Host "You can test it now with:"
Write-Host ""
Write-Host "  runml --version"
Write-Host "  runml doctor"
Write-Host ""
Write-Host "If another already-open terminal cannot find"
Write-Host "'runml', open a new terminal window."
Write-Host ""
