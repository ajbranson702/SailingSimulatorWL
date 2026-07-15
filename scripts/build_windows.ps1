param(
    [switch]$InstallPyInstaller
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Spec = Join-Path $ProjectRoot "SailingRaceSimulator.spec"

if (!(Test-Path $Python)) {
    throw "Project venv not found at $Python"
}

if ($InstallPyInstaller) {
    & $Python -m pip install "pyinstaller>=6.0"
}

& $Python -m PyInstaller --clean --noconfirm $Spec

Write-Host "Built executable at:" -ForegroundColor Green
Write-Host (Join-Path $ProjectRoot "dist\SailingRaceSimulator.exe")
