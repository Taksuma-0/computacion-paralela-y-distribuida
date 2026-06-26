# Extrae SOLO el clúster Debian/Ray (debian_disks/ + ray/) desde el ZIP del lab
# ray_qemu hacia C:\qemu-cluster-demo (one-time, ~3 GB). No re-extrae lo ya presente.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip  = Join-Path (Split-Path $PSScriptRoot -Parent) "qemu-cluster-demo.zip"
$dest = $env:QEMU_BASE; if (-not $dest) { $dest = "C:\qemu-cluster-demo" }

if (-not (Test-Path $zip)) { Write-Host "No existe el ZIP: $zip" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Force $dest | Out-Null }

Write-Host "Extrayendo debian_disks/ + ray/ desde $zip" -ForegroundColor Cyan
Write-Host "  hacia $dest (esto puede tardar; el disco base pesa ~3 GB)" -ForegroundColor Cyan

$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    foreach ($e in $archive.Entries) {
        if ($e.FullName -notmatch '^(debian_disks|ray)/') { continue }
        $target = Join-Path $dest ($e.FullName -replace '/', '\')
        if ($e.FullName.EndsWith("/")) {
            if (-not (Test-Path $target)) { New-Item -ItemType Directory -Force $target | Out-Null }
            continue
        }
        $dir = Split-Path $target -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
        if (Test-Path $target) {
            Write-Host ("  ya existe, se omite: " + $e.FullName) -ForegroundColor DarkGray
            continue
        }
        $mb = [math]::Round($e.Length / 1MB, 1)
        Write-Host ("  -> " + $e.FullName + "  (" + $mb + " MB)")
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $true)
    }
} finally {
    $archive.Dispose()
}

Write-Host "Listo. VMs Debian/Ray en $dest\debian_disks" -ForegroundColor Green
Get-ChildItem (Join-Path $dest "debian_disks") -ErrorAction SilentlyContinue |
    Select-Object Name, @{N='MB';E={[math]::Round($_.Length/1MB)}} | Format-Table -AutoSize
