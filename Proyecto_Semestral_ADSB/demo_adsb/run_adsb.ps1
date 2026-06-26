# run_adsb.ps1 - Lanzador de la TUI ADS-B (proyecto semestral, UTEM).
# Ejecuta el paquete (python -m tui) por los imports relativos de tui/.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot   # carpeta demo_adsb/

# Asegura las dependencias de la TUI (la tarea y el orquestador son stdlib puro).
$haveDeps = $false
try { python -c "import textual, rich, paramiko" 2>$null; if ($LASTEXITCODE -eq 0) { $haveDeps = $true } } catch {}
if (-not $haveDeps) {
    Write-Host "Instalando dependencias de la TUI (textual, rich, paramiko)..." -ForegroundColor Cyan
    python -m pip install -r requirements-tui.txt
}

Write-Host "Lanzando TUI ADS-B (deteccion distribuida de anomalias de vuelo)..." -ForegroundColor Green
python -m tui
