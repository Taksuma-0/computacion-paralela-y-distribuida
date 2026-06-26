# Guía de ejecución — "El gato que aprende solo" (Ray + QEMU)

Demo de cómputo distribuido: un agente que **aprende a jugar al gato (tic‑tac‑toe)
por refuerzo**, entrenado **en paralelo con Ray** sobre el clúster QEMU/Debian, y
una **interfaz web interactiva** (`gato.html`) para jugar contra la IA, ver la
curva de aprendizaje y un replay de cómo mejora.

> **Convención:** cada bloque indica dónde se ejecuta:
> 🪟 = PowerShell en **Windows** · 🐧 = terminal dentro de **ray0** (por SSH).

---

## 0. Atajo para probar sin clúster (opcional, en Windows)

Solo necesitas Python 3. Sirve para ver el demo funcionando antes de la clase:

```powershell
# 🪟 Windows, dentro de la carpeta gato_demo
python gato_rl_ray.py --backend local 12 500 4
```

Genera `gato.html` en la misma carpeta. Ábrelo con doble clic. Esto **no usa Ray**
(corre secuencial); es solo para validar el programa y la interfaz.

---

## 1. Requisitos y estructura

- Windows con **QEMU** y **WHPX** habilitado (Plataforma del hipervisor de Windows).
- El ZIP `qemu-cluster-demo.zip` **extraído** en `C:\qemu-cluster-demo` con esta forma
  (rama Debian/Ray; la rama Alpine `disks/` no se toca):

```
C:\qemu-cluster-demo
├── qemu\qemu-system-x86_64w.exe
├── debian_disks\  (ray0.qcow2, ray1.qcow2, ray2.qcow2, debian-base.qcow2)
└── ray\start-all-debian-ray-nat.ps1
```

- Dentro de cada VM: usuario `ray` y el entorno `~/ray-env` con Ray instalado.

---

## 2. Levantar las VMs (Windows)

```powershell
# 🪟 Windows
cd C:\qemu-cluster-demo\ray
Set-ExecutionPolicy -Scope Process Bypass     # por si bloquea el script
.\start-all-debian-ray-nat.ps1
```

Debe imprimir los puertos SSH (2320/2321/2322) y el Dashboard (8265 → ray0).
Espera ~30–60 s a que arranque Debian.

| VM   | SSH desde Windows            | Extra                         |
|------|------------------------------|-------------------------------|
| ray0 | `ssh ray@127.0.0.1 -p 2320`  | Dashboard: http://127.0.0.1:8265 |
| ray1 | `ssh ray@127.0.0.1 -p 2321`  | (worker futuro)               |
| ray2 | `ssh ray@127.0.0.1 -p 2322`  | (worker futuro)               |

> Para esta demo basta **ray0** (Ray de un solo nodo). El paso a multinodo está al final.

---

## 3. Iniciar Ray en ray0

```powershell
# 🪟 Windows
ssh ray@127.0.0.1 -p 2320
```

```bash
# 🐧 dentro de ray0
. ~/ray-env/bin/activate
python -c "import ray; print('Ray', ray.__version__)"   # verificación rápida

ray stop || true
ray start --head \
  --node-ip-address=127.0.0.1 \
  --port=6379 \
  --dashboard-host=0.0.0.0 \
  --dashboard-port=8265

ray status        # debe reportar 1 nodo y CPU=2
```

Abre el **Dashboard** en el navegador de Windows: <http://127.0.0.1:8265>

---

## 4. Copiar el programa a ray0

```powershell
# 🪟 Windows, en la carpeta gato_demo (donde está gato_rl_ray.py)
ssh ray@127.0.0.1 -p 2320 "mkdir -p ~/ray-demo"
scp -P 2320 .\gato_rl_ray.py ray@127.0.0.1:~/ray-demo/
```

---

## 5. Ejecutar el entrenamiento distribuido

### Opción A — directo (lo más simple)

```bash
# 🐧 dentro de ray0
cd ~/ray-demo
. ~/ray-env/bin/activate
python gato_rl_ray.py 30 2000 8
#                      │   │    └ tareas Ray en paralelo por generación
#                      │   └ partidas de self-play por tarea
#                      └ generaciones de aprendizaje
```

Verás la tabla por generación (la columna **no‑derrota** debe subir hacia ~99 %),
la curva ASCII, un replay y, al final, la ruta de `gato.html`. La columna **nodos**
muestra qué máquina ejecutó cada lote (en single‑node: `ray0`).

### Opción B — como Ray Job (reproducible, queda en el Dashboard)

```bash
# 🐧 dentro de ray0
cd ~/ray-demo
. ~/ray-env/bin/activate
ray job submit \
  --address http://127.0.0.1:8265 \
  --working-dir . \
  -- python gato_rl_ray.py 30 2000 8
```

> ⚠️ El `--working-dir .` es importante: sin él, el entrypoint puede correr desde
> otro directorio y fallar con *file not found*.

Seguimiento del job:

```bash
ray job status <job_id>
ray job logs <job_id> --follow
```

En el Dashboard (pestañas **Jobs** y **Cluster/Tasks**) se ven las tareas
ejecutándose en paralelo.

---

## 6. Abrir la interfaz interactiva

El programa deja `gato.html` en `~/ray-demo`. Cópialo a Windows y ábrelo:

```powershell
# 🪟 Windows
scp -P 2320 ray@127.0.0.1:~/ray-demo/gato.html .
.\gato.html      # o doble clic
```

En la página puedes:
- **Jugar contra la IA** (elige X u O).
- Ver la **curva de aprendizaje** (botón *Animar aprendizaje*).
- Ver el **replay**: mueve el deslizador de generación para ver cómo mejora el agente.

---

## 7. (Opcional) Medir speedup

```bash
# 🐧 dentro de ray0
python gato_rl_ray.py 40 4000 8 --benchmark
```

Imprime **T1** (1 tarea), **Tp** (8 tareas), **Speedup = T1/Tp**,
**Eficiencia = S/p** y **Overhead = p·Tp − T1**. Para que el speedup se note,
sube `partidas_por_tarea` (tareas con más cómputo amortizan mejor el overhead).

---

## 8. Apagado ordenado

```bash
# 🐧 en ray0
ray stop
sudo poweroff
```

O desde Windows: `ssh ray@127.0.0.1 -p 2320 "sudo poweroff"`.

---

## 9. (Avanzado) Pasar a multinodo real

El código **no cambia**: ya reporta hostnames y reparte tareas. Solo falta red
interna VM↔VM (NAT user‑mode no conecta las VMs entre sí). Con una red interna
(p. ej. ray0=10.10.0.10, ray1=.11, ray2=.12):

```bash
# 🐧 ray0 (head con su IP interna, NO 127.0.0.1)
ray start --head --node-ip-address=10.10.0.10 --port=6379 \
  --dashboard-host=0.0.0.0 --dashboard-port=8265
# 🐧 ray1 y ray2 (workers)
ray start --address=10.10.0.10:6379 --node-ip-address=10.10.0.11   # ray1
ray start --address=10.10.0.10:6379 --node-ip-address=10.10.0.12   # ray2
```

Al volver a ejecutar el demo, la columna **nodos** y los chips del HTML mostrarán
`ray0, ray1, ray2`: las tareas de self‑play se reparten entre las tres máquinas.

---

## 10. Problemas frecuentes

| Síntoma | Causa probable | Acción |
|---|---|---|
| `ssh: connection refused` | la VM aún arranca o puerto equivocado | espera el boot; confirma el puerto (2320 ray0) |
| El Dashboard no abre | Ray no está iniciado o `--dashboard-host` | en ray0: `ray status`; reinicia `ray start --head ...` |
| `ModuleNotFoundError: ray` | no activaste el venv | `. ~/ray-env/bin/activate` antes de ejecutar |
| Job: *file not found* | faltó `--working-dir .` | ejecuta el job desde `~/ray-demo` con `--working-dir .` |
| Speedup ≈ 1 | tareas muy chicas (domina el overhead) | sube `partidas_por_tarea` |
| Caracteres raros en la curva ASCII | consola sin UTF‑8 | el programa fuerza UTF‑8; en Windows usa Windows Terminal |
| El HTML no genera | excepción durante el run | revisa el traceback en la terminal/`ray job logs` |

---

### Resumen exprés

```text
🪟  cd C:\qemu-cluster-demo\ray ; .\start-all-debian-ray-nat.ps1
🪟  scp -P 2320 .\gato_rl_ray.py ray@127.0.0.1:~/ray-demo/
🐧  ssh ray@127.0.0.1 -p 2320  →  . ~/ray-env/bin/activate
🐧  ray stop || true ; ray start --head --node-ip-address=127.0.0.1 --port=6379 --dashboard-host=0.0.0.0 --dashboard-port=8265
🐧  cd ~/ray-demo ; python gato_rl_ray.py 30 2000 8
🪟  scp -P 2320 ray@127.0.0.1:~/ray-demo/gato.html .  →  abrir en el navegador
```
