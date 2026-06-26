# preparar_acceso_ray.ps1
# Genera una LLAVE SSH propia e INYECTA su pública (offline) en los qcow2 de las VMs
# Debian de Ray, para acceso por llave SIN contraseña (la contraseña del usuario `ray`
# no se conoce). Usa Docker + libguestfs (virt-customize --ssh-inject), igual que se
# hizo con el clúster Alpine. Correr UNA vez (re-correr duplicaría la línea de la llave).
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$Key        = Join-Path $env:USERPROFILE ".ssh\ray_cluster"
$SshDir     = Split-Path $Key -Parent
$Disks      = if ($env:RAY_DISKS) { $env:RAY_DISKS } else { "C:\qemu-cluster-demo\debian_disks" }
$Img        = "gato-libguestfs"
$Dockerfile = Join-Path $PSScriptRoot "preparar_acceso_ray.Dockerfile"

# 1) Llave propia (ed25519, sin passphrase). NO se toca qemu_cluster (es del lab Alpine).
if (-not (Test-Path $Key)) {
    Write-Host "Generando llave propia $Key ..." -ForegroundColor Cyan
    if (-not (Test-Path $SshDir)) { New-Item -ItemType Directory -Force $SshDir | Out-Null }
    ssh-keygen -t ed25519 -f $Key -N '' -C "ray-gato-tui"
    if ((ssh-keygen -y -f $Key 2>&1) -notmatch '^ssh-ed25519') {
        throw "La llave quedó con passphrase. Genérala manual: ssh-keygen -t ed25519 -f `"$Key`" -N `"`""
    }
} else {
    Write-Host "Llave ya existe: $Key" -ForegroundColor DarkGray
}

# 2) ¿Discos Debian extraídos?
if (-not (Test-Path (Join-Path $Disks "ray0.qcow2"))) {
    Write-Host "No existen los discos Debian en $Disks." -ForegroundColor Red
    Write-Host "Extrae primero:  .\extraer_debian_ray.ps1" -ForegroundColor Yellow
    exit 1
}

# 3) Imagen libguestfs (se construye una vez)
if (-not (docker images -q $Img)) {
    Write-Host "Construyendo imagen $Img (libguestfs)..." -ForegroundColor Cyan
    docker build -t $Img -f $Dockerfile $PSScriptRoot
}

# 4) Inyectar la pública en cada overlay POR SEPARADO (un solo -a por llamada: evita la
#    colisión de UUID de los overlays que comparten la misma base).
Write-Host "Inyectando la llave en ray0/ray1/ray2 (offline, vía libguestfs)..." -ForegroundColor Cyan
$bash = 'set -e; for d in ray0 ray1 ray2; do [ -f /disks/$d.qcow2 ] || continue; echo "  inject $d"; virt-customize -a /disks/$d.qcow2 --ssh-inject ray:file:/keys/ray_cluster.pub --ssh-inject root:file:/keys/ray_cluster.pub >/dev/null 2>&1 && echo "    ok"; done; echo "== verificacion (1 linea por disco) =="; for d in ray0 ray1 ray2; do [ -f /disks/$d.qcow2 ] || continue; printf "%s ray: " "$d"; virt-cat -a /disks/$d.qcow2 /home/ray/.ssh/authorized_keys 2>/dev/null | wc -l; done'
docker run --rm -v "${Disks}:/disks" -v "${SshDir}:/keys:ro" $Img bash -lc $bash

Write-Host ""
Write-Host "Listo. Acceso por llave configurado (sin contraseña)." -ForegroundColor Green
Write-Host "Prueba (con ray0 encendida):" -ForegroundColor Green
Write-Host "  ssh -i `"$Key`" -p 2320 ray@127.0.0.1" -ForegroundColor Green
