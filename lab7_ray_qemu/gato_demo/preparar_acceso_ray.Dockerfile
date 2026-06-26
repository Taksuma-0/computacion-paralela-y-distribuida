# Imagen libguestfs para inyectar la llave SSH en los qcow2 de las VMs Debian de Ray
# (sin contraseña, offline). Se usa desde preparar_acceso_ray.ps1.
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends libguestfs-tools linux-image-amd64 \
 && rm -rf /var/lib/apt/lists/*
# Sin KVM dentro de Docker Desktop: forzar backend directo (qemu TCG).
ENV LIBGUESTFS_BACKEND=direct
