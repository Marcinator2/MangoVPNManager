[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$iconFile = Join-Path $projectRoot "icons\mb-soft.ico"
$iconData = "$(Join-Path $projectRoot 'icons');icons"
$buildDir = Join-Path $projectRoot "build"
$stagingDist = Join-Path $buildDir "dist-staging"
$targetDist = Join-Path $projectRoot "dist\MangoVPNManager"

if ($PythonExecutable) {
    $pythonExe = (Get-Item -LiteralPath $PythonExecutable -ErrorAction Stop).FullName
} elseif (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $pythonExe = $venvPython
} else {
    throw "Missing .venv. Create it with: py -3.14 -m venv .venv, or pass -PythonExecutable explicitly."
}

if ($Clean) {
    if (Test-Path -LiteralPath $buildDir) { Remove-Item -LiteralPath $buildDir -Recurse -Force }
}

& $pythonExe -m PyInstaller `
    --noconfirm `
    --windowed `
    --name MangoVPNManager `
    --icon $iconFile `
    --add-data $iconData `
    --paths (Join-Path $projectRoot "src") `
    --distpath $stagingDist `
    --workpath $buildDir `
    --specpath $buildDir `
    (Join-Path $projectRoot "src\main.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$stagedApp = Join-Path $stagingDist "MangoVPNManager"
$stagedExe = Join-Path $stagedApp "MangoVPNManager.exe"
$stagedInternal = Join-Path $stagedApp "_internal"
if (-not (Test-Path -LiteralPath $stagedExe) -or -not (Test-Path -LiteralPath $stagedInternal)) {
    throw "Staged PyInstaller output is incomplete."
}

$runningApp = Get-Process -Name "MangoVPNManager" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($targetDist, [System.StringComparison]::OrdinalIgnoreCase) }
if ($runningApp) {
    throw "MangoVPNManager is running from the target directory. Close it before updating the build."
}

New-Item -ItemType Directory -Path $targetDist -Force | Out-Null
$resolvedProject = [System.IO.Path]::GetFullPath($projectRoot).TrimEnd('\')
$resolvedTarget = [System.IO.Path]::GetFullPath($targetDist).TrimEnd('\')
if (-not $resolvedTarget.StartsWith("$resolvedProject\dist\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing unsafe build target: $resolvedTarget"
}

$targetExe = Join-Path $targetDist "MangoVPNManager.exe"
$targetInternal = Join-Path $targetDist "_internal"
if (Test-Path -LiteralPath $targetExe) {
    Remove-Item -LiteralPath $targetExe -Force
}
if (Test-Path -LiteralPath $targetInternal) {
    Remove-Item -LiteralPath $targetInternal -Recurse -Force
}
Copy-Item -LiteralPath $stagedExe -Destination $targetExe
Copy-Item -LiteralPath $stagedInternal -Destination $targetInternal -Recurse

Write-Host "Build complete: $targetDist"
if (Test-Path -LiteralPath (Join-Path $targetDist "data")) {
    Write-Host "Preserved existing packaged-application data directory."
}

