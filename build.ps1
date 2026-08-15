param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$repoRoot = $PSScriptRoot
$scratchRoot = $env:WS_DOWNLOADER_BUILD_ROOT
if (-not $scratchRoot) {
    $scratchRoot = Join-Path $repoRoot (".scratch_build\run-{0}" -f $PID)
}
$scratchRoot = [System.IO.Path]::GetFullPath($scratchRoot)
$scratchBuild = Join-Path $scratchRoot "build"
$scratchDist = Join-Path $scratchRoot "dist"

$requiredSources = @(
    (Join-Path $repoRoot "main.py"),
    (Join-Path $repoRoot "ws_downloader\installer.py"),
    (Join-Path $repoRoot "ws_downloader\steamcmd.py"),
    (Join-Path $repoRoot "ws_downloader\ui.py")
)
foreach ($source in $requiredSources) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required source file is missing: $source"
    }
}

python -B -c "import ws_downloader.installer; import ws_downloader.steamcmd; import ws_downloader.ui"
if ($LASTEXITCODE -ne 0) {
    throw "Application imports failed. Build aborted."
}

New-Item -ItemType Directory -Path $scratchBuild -Force | Out-Null
New-Item -ItemType Directory -Path $scratchDist -Force | Out-Null

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    try {
        python -m PyInstaller --version | Out-Null
    } catch {
        Write-Host "PyInstaller is not installed. Install it first with: python -m pip install -r requirements-build.txt" -ForegroundColor Yellow
        exit 1
    }
}

if ($Clean) {
    foreach ($target in @($scratchBuild, $scratchDist, (Join-Path $repoRoot "dist"))) {
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $scratchBuild -Force | Out-Null
    New-Item -ItemType Directory -Path $scratchDist -Force | Out-Null
}

$localesData = "$(Resolve-Path (Join-Path $repoRoot 'locales'));locales"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --add-data $localesData `
    --hidden-import ws_downloader.steamcmd `
    --name "WS Downloader" `
    --distpath $scratchDist `
    --workpath $scratchBuild `
    --specpath $scratchBuild `
    (Join-Path $repoRoot 'main.py')

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Path (Join-Path $repoRoot "dist") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $scratchDist 'WS Downloader.exe') -Destination (Join-Path $repoRoot 'dist\WS Downloader.exe') -Force
foreach ($doc in @("README.md", "README_SHORT.md", "CHANGELOG.md")) {
    $source = Join-Path $repoRoot $doc
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $repoRoot "dist\$doc") -Force
    }
}

Write-Host "Build finished. The executable is in .\dist\WS Downloader.exe" -ForegroundColor Green
