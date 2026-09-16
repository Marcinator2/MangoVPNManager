[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApplicationDirectory
)

$ErrorActionPreference = "Stop"
$application = Get-Item -LiteralPath $ApplicationDirectory -ErrorAction Stop
if (-not $application.PSIsContainer) {
    throw "ApplicationDirectory must be a directory: $ApplicationDirectory"
}

$executable = Join-Path $application.FullName "MangoVPNManager.exe"
$internalDirectory = Join-Path $application.FullName "_internal"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Release directory does not contain MangoVPNManager.exe."
}
if (-not (Test-Path -LiteralPath $internalDirectory -PathType Container)) {
    throw "Release directory does not contain the PyInstaller _internal directory."
}

$violations = [System.Collections.Generic.List[string]]::new()
$runtimeData = Join-Path $application.FullName "data"
if (Test-Path -LiteralPath $runtimeData) {
    $violations.Add("data/")
}

$forbiddenExtensions = @(
    ".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12", ".pfx",
    ".csr", ".req", ".crt", ".cer", ".ovpn"
)
Get-ChildItem -LiteralPath $application.FullName -Recurse -File | ForEach-Object {
    $lowerName = $_.Name.ToLowerInvariant()
    $lowerExtension = $_.Extension.ToLowerInvariant()
    if (
        $forbiddenExtensions -contains $lowerExtension -or
        $lowerName -eq "settings.json" -or
        $lowerName -eq "ta.key" -or
        $lowerName -like "*status*.tsv"
    ) {
        $violations.Add($_.FullName.Substring($application.FullName.Length + 1))
    }
}

if ($violations.Count -gt 0) {
    $details = ($violations | Sort-Object -Unique) -join [Environment]::NewLine
    throw "Release safety check failed. Remove these runtime or private files:`n$details"
}

Write-Host "Release safety check passed: $($application.FullName)"
