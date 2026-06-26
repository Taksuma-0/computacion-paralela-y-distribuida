# deploy_to_nodo0.ps1
# Copia la carpeta orquestador/ al nodo0 (coordinador) e instala paramiko en Alpine.
# Requisito: las VMs ya lanzadas con  C:\qemu-cluster-demo\scripts\start-all.ps1
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\scripts\deploy_to_nodo0.ps1

param(
    [int]$Port = 2220,
    [string]$User = "root"
)

$ErrorActionPreference = "Stop"
$Src = Split-Path -Parent $PSScriptRoot   # carpeta orquestador/

Write-Host "1) Copiando '$Src' -> nodo0 (127.0.0.1:$Port):/root/orchestrator ..."
scp -P $Port -r "$Src" "${User}@127.0.0.1:/root/orchestrator"

Write-Host "2) Instalando dependencias en nodo0 (apk add py3-paramiko) ..."
ssh -p $Port "${User}@127.0.0.1" "apk add --no-progress py3-paramiko python3 && python3 -c 'import paramiko, sys; print(\"paramiko\", paramiko.__version__, \"OK\")'"

Write-Host ""
Write-Host "Listo. Ahora entra al coordinador y ejecuta los jobs:" -ForegroundColor Green
Write-Host "  ssh -p $Port ${User}@127.0.0.1"
Write-Host "  cd /root/orchestrator"
Write-Host "  python3 coordinator_generic.py --task tasks/task_primes.py --payload '{\""upper\"":300000,\""n_chunks\"":24}' --workers workers.json --deploy"
