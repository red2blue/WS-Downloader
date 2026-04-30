param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    try {
        python -m PyInstaller --version | Out-Null
    } catch {
        Write-Host "PyInstaller is not installed. Install it first with: python -m pip install -r requirements-build.txt" -ForegroundColor Yellow
        exit 1
    }
}

if ($Clean) {
    foreach ($target in @(".\build", ".\dist", ".\build\WS Downloader.spec")) {
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "WS Downloader" `
    --distpath dist `
    --workpath build `
    --specpath build `
    main.py

Write-Host "Build finished. The executable is in .\dist\WS Downloader.exe" -ForegroundColor Green
