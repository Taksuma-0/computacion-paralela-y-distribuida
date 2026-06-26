# Lanza la TUI del gato (Ray sobre QEMU). Instala dependencias si faltan.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot   # carpeta gato_demo/

$have = $false
try {
    python -c "import textual, rich, paramiko" 2>$null
    if ($LASTEXITCODE -eq 0) { $have = $true }
} catch {}

if (-not $have) {
    Write-Host "Instalando dependencias de la TUI (textual, rich, paramiko)..." -ForegroundColor Cyan
    python -m pip install -r requirements-tui.txt
}

Write-Host "Lanzando TUI: El gato que aprende solo (Ray sobre QEMU)..." -ForegroundColor Green
python -m tui_gato
