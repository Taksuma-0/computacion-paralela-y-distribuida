# run_tui.ps1 - Lanzador del TUI del cluster QEMU (UTEM).
# Debe ejecutarse como paquete (python -m tui) por los imports relativos del paquete tui/.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot   # carpeta orquestador/

# Asegura las dependencias del TUI (el orquestador y las VMs siguen siendo stdlib puro).
$haveTextual = $false
try { python -c "import textual, rich, paramiko" 2>$null; if ($LASTEXITCODE -eq 0) { $haveTextual = $true } } catch {}
if (-not $haveTextual) {
    Write-Host "Instalando dependencias del TUI (textual, rich, paramiko)..." -ForegroundColor Cyan
    python -m pip install -r requirements-tui.txt
}

Write-Host "Lanzando TUI del cluster QEMU (UTEM)..." -ForegroundColor Green
python -m tui
