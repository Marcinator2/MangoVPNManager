[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$Start,
    [switch]$StagingOnly,
    [string]$PythonExecutable = "",
    [string]$ReleaseVersion = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$iconFile = Join-Path $projectRoot "icons\mb-soft.ico"
$iconData = "$(Join-Path $projectRoot 'icons');icons"
$buildDir = Join-Path $projectRoot "build"
$stagingDist = Join-Path $buildDir "package-staging"
$targetDist = Join-Path $projectRoot "dist\MangoVPNManager"

if ($Start -and ($Clean -or $StagingOnly)) {
    throw "Use -Start to run from source; it cannot be combined with -Clean or -StagingOnly."
}

if ($PythonExecutable) {
    $pythonExe = (Get-Item -LiteralPath $PythonExecutable -ErrorAction Stop).FullName
} elseif (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $pythonExe = $venvPython
} else {
    if (Test-Path -LiteralPath (Join-Path $projectRoot ".venv")) {
        throw "The existing .venv is incomplete. Repair it or rename it before retrying."
    }
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Install Python 3.14 with the Python launcher, then run this script again."
    }
    & py -3.14 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Install Python 3.14, then run this script again." }
    Write-Host "Creating the Python 3.14 environment..."
    & py -3.14 -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create .venv." }
    $pythonExe = $venvPython
}

& $pythonExe -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "The selected environment must use Python 3.14. Repair it or pass -PythonExecutable."
}
Write-Host "Checking and installing project dependencies..."
& $pythonExe -m pip install -r (Join-Path $projectRoot "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check the pip output above." }
& $pythonExe -m pip check
if ($LASTEXITCODE -ne 0) { throw "The Python environment has incompatible dependencies." }

if ($Start) {
    Write-Host "Starting from source (using the repository data directory)..."
    & $pythonExe (Join-Path $projectRoot "src\main.py")
    if ($LASTEXITCODE -ne 0) { throw "Application exited with code $LASTEXITCODE." }
    return
}

if ($Clean) {
    if (Test-Path -LiteralPath $buildDir) { Remove-Item -LiteralPath $buildDir -Recurse -Force }
}

$metadataDir = Join-Path $buildDir "metadata"
New-Item -ItemType Directory -Path $metadataDir -Force | Out-Null
$buildType = "development"
$version = "development"
if ($ReleaseVersion) {
    if ($ReleaseVersion -cnotmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {
        throw "ReleaseVersion must be a stable vX.Y.Z tag."
    }
    $buildType = "stable"
    $version = $ReleaseVersion
}
$commit = (& git -C $projectRoot rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { $commit = "unknown" }
$metadataFile = Join-Path $metadataDir "build-info.json"
@{ version = $version; build_type = $buildType; commit = "$commit" } |
    ConvertTo-Json | Set-Content -LiteralPath $metadataFile -Encoding utf8

# The independent helper can replace Qt and Python DLLs from a temporary copy.
& $pythonExe -m PyInstaller `
    --clean --noconfirm --onefile --windowed `
    --name MangoVPNUpdater `
    --icon $iconFile `
    --paths (Join-Path $projectRoot "src") `
    --distpath (Join-Path $buildDir "helper-staging") `
    --workpath (Join-Path $buildDir "helper-work") `
    --specpath $buildDir `
    (Join-Path $projectRoot "src\updater\helper.py")
if ($LASTEXITCODE -ne 0) { throw "Updater build failed." }

& $pythonExe -m PyInstaller `
    --clean `
    --noconfirm `
    --windowed `
    --name MangoVPNManager `
    --icon $iconFile `
    --add-data $iconData `
    --add-data "$metadataFile;." `
    --paths (Join-Path $projectRoot "src") `
    --distpath $stagingDist `
    --workpath (Join-Path $buildDir "application-work") `
    --specpath $buildDir `
    (Join-Path $projectRoot "src\main.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$stagedApp = Join-Path $stagingDist "MangoVPNManager"
$stagedExe = Join-Path $stagedApp "MangoVPNManager.exe"
$stagedInternal = Join-Path $stagedApp "_internal"
$stagedUpdater = Join-Path $stagedApp "MangoVPNUpdater.exe"
Copy-Item -LiteralPath (Join-Path $buildDir "helper-staging\MangoVPNUpdater.exe") -Destination $stagedUpdater
if (-not (Test-Path -LiteralPath $stagedExe) -or -not (Test-Path -LiteralPath $stagedInternal)) {
    throw "Staged PyInstaller output is incomplete."
}

if ($StagingOnly) {
    Write-Host "Build complete (deployment skipped): $stagedApp"
    return
}

$runningApp = Get-Process -Name "MangoVPNManager", "MangoVPNUpdater" -ErrorAction SilentlyContinue |
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
$targetUpdater = Join-Path $targetDist "MangoVPNUpdater.exe"
if (Test-Path -LiteralPath $targetExe) {
    Remove-Item -LiteralPath $targetExe -Force
}
if (Test-Path -LiteralPath $targetInternal) {
    Remove-Item -LiteralPath $targetInternal -Recurse -Force
}
Copy-Item -LiteralPath $stagedUpdater -Destination $targetUpdater -Force
Copy-Item -LiteralPath $stagedExe -Destination $targetExe
Copy-Item -LiteralPath $stagedInternal -Destination $targetInternal -Recurse

Write-Host "Build complete: $targetDist"
if (Test-Path -LiteralPath (Join-Path $targetDist "data")) {
    Write-Host "Preserved existing packaged-application data directory."
}

