# Acceso a las VMs del cluster QEMU (UTEM)

> **Importante:** estas VMs Alpine **no tienen una contraseña de root conocida**. El acceso
> quedó configurado por **llave SSH (ed25519)**. La llave pública ya está inyectada en
> `/root/.ssh/authorized_keys` de las 3 VMs (viene dentro de los discos `qcow2`), así que el
> acceso es inmediato y sin contraseña.

## Llave SSH

| | Ruta |
|---|---|
| Privada (host) | `C:\Users\welin\.ssh\qemu_cluster` |
| Pública (host) | `C:\Users\welin\.ssh\qemu_cluster.pub` |

Contenido de la pública:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIH+GCdEffghi+l6gFpDeZ3nQwpMj+keH6TckNsXQXC2A qemu-cluster-orquestador
```

## Topología y puertos (host → VM)

| Nodo  | Rol               | SSH (host → :22) | Servicio agente (host → :9000) |
|-------|-------------------|------------------|--------------------------------|
| nodo0 | coordinador\*     | 2220             | —                              |
| nodo1 | worker            | 2221             | 9001                           |
| nodo2 | worker            | 2222             | 9002                           |

\* nodo0 se usa como coordinador solo en el modo "fiel al enunciado" (CLI). En el TUI el
coordinador corre en el host y los workers son nodo1 y nodo2.

## Comandos SSH por nodo (con la llave)

```powershell
ssh -i C:\Users\welin\.ssh\qemu_cluster -p 2220 root@127.0.0.1   # nodo0
ssh -i C:\Users\welin\.ssh\qemu_cluster -p 2221 root@127.0.0.1   # nodo1
ssh -i C:\Users\welin\.ssh\qemu_cluster -p 2222 root@127.0.0.1   # nodo2
```

Ver en vivo lo que procesa un worker (su log de agente):

```powershell
ssh -i C:\Users\welin\.ssh\qemu_cluster -p 2221 root@127.0.0.1 "tail -F /tmp/worker_agent.log"
```

## Cómo levantar y usar

1. **Arrancar las VMs:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\qemu-cluster-demo\scripts\start-all.ps1
   ```
   (o desde el TUI: opción **"Levantar cluster"**).

   > El TUI lanza QEMU en **modo headless** (`-display none`): **no se abren ventanas de VM**
   > (antes se quedaban colgadas en `localhost login:` sin mostrar nada). Todo el procesamiento
   > de cada nodo se ve **dentro del dashboard** del TUI (tail SSH de `/tmp/worker_agent.log`).
2. **TUI:** `.\run_tui.ps1` → seguir el launcher (levantar → elegir tarea → ejecutar → apagar).
3. El coordinador despliega el agente y la tarea con `--ssh-key C:\Users\welin\.ssh\qemu_cluster`
   y el TUI hace `tail` de `/tmp/worker_agent.log` de cada worker.
4. **Apagar las VMs:**
   ```powershell
   Get-Process qemu-system-x86_64w | Stop-Process -Force
   ```
   (o desde el TUI: opción **"Apagar cluster"**).

## Cómo se creó este acceso (para reproducir)

La contraseña de root no estaba disponible, así que se inyectó la llave **offline**: se montaron
los discos `qcow2` (vía WSL + loop), se escribió la pública en `/root/.ssh/authorized_keys` de
cada nodo y se reempaquetaron los `qcow2`. Por eso `start-all.ps1` arranca las VMs ya accesibles
por llave.

## Nota de seguridad

- Es una **llave de laboratorio** para VMs locales (`127.0.0.1`), sin passphrase, para automatizar
  la demo. **No la reutilices** fuera de este ejercicio ni la subas a repositorios públicos.
- Si publicas el repo, **excluye la llave privada** del control de versiones.
- paramiko usa `AutoAddPolicy` (acepta el host key sin verificar): aceptable en localhost de
  laboratorio, no en producción.
