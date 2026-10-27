param([Parameter(Mandatory = $true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$target = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $target) { throw "Destination already exists. Choose a new directory: $target" }
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $packageRoot 'delivery-manifest.json') | ConvertFrom-Json
foreach ($item in $manifest.files) {
    $source = [IO.Path]::GetFullPath((Join-Path $packageRoot $item.path))
    if (-not $source.StartsWith($packageRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest path escapes package: $($item.path)"
    }
    $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $item.sha256) { throw "Checksum mismatch: $($item.path)" }
}
& git clone --branch $manifest.branch (Join-Path $packageRoot 'ghj-project.bundle') $target
if ($LASTEXITCODE -ne 0) { throw 'Git clone failed.' }
$restoredCommit = & git -C $target rev-parse HEAD
if ($restoredCommit -ne $manifest.delivery_commit) { throw 'Restored commit mismatch.' }
foreach ($folder in @('artifacts', 'data/processed/hapt-v1')) {
    $source = Join-Path $packageRoot $folder
    $dest = Join-Path $target $folder
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $dest -Recurse
}
& git -C $target remote set-url origin 'https://github.com/EternalZCL/zzr-edgefl-client-selection.git'
if ($LASTEXITCODE -ne 0) { throw 'Could not set the original remote URL.' }
Write-Output "Verified and restored $($manifest.published_runs) runs at $target"
Write-Output 'Next: uv tool run --from uv==0.12.23 uv sync --locked'
Write-Output 'Then: uv tool run --from uv==0.12.23 uv run --locked --exact python scripts/check_repo.py --require-ready'
