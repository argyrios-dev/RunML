$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "RunML Windows uninstaller"
Write-Host "-------------------------"

$InstallRoot = Join-Path $env:LOCALAPPDATA "RunML"
$BinDir = Join-Path $InstallRoot "bin"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $filtered = @(
        $userPath -split ";" |
        Where-Object {
            $_ -and $_.Trim() -and ($_.TrimEnd("\") -ine $BinDir.TrimEnd("\"))
        }
    )
    [Environment]::SetEnvironmentVariable("Path", ($filtered -join ";"), "User")
}

if (Test-Path $InstallRoot) {
    Remove-Item -Recurse -Force $InstallRoot
}

Write-Host ""
Write-Host "RunML runtime/terminal command removed."
Write-Host "Your selected data directory and settings were NOT deleted."
Write-Host "Open a new terminal to refresh PATH."
