# TUI "El gato que aprende solo" — Ray sobre QEMU

Interfaz de terminal (Textual, **estilo del orquestador QEMU**: tema UTEM, escudo,
paneles por worker en vivo, ClusterFlow, curva y speedup) que:

1. **⏻ Levanta el clúster** Debian/Ray — **1 nodo** (ray0) o **3 nodos reales** (ray0+ray1+ray2) —
   y arranca **Ray** (`ray start --head` + workers, Dashboard 8265).
2. **▶ Entrena** el gato por refuerzo **DENTRO de las VMs con Ray**, mostrándolo en vivo:
   tareas Ray **repartidas entre los nodos**, **curva de aprendizaje subiendo**, progreso por generación.
3. **🎮 Jugar** contra el modelo **entrenado de forma distribuida**, en un tablero en la TUI.
4. **⏼ Apaga** el clúster ordenadamente.

> Hay además un **modo local (ensayo)** que entrena en el host (sin VM ni Ray) para
> probar/ensayar toda la TUI sin levantar nada.

---

## 1. Prerrequisitos (una sola vez)

**a) Extraer el clúster Debian/Ray** (no viene extraído; ~3 GB):
```powershell
cd C:\Users\welin\Desktop\universidad\Paralela\ray_qemu\gato_demo
.\extraer_debian_ray.ps1
```
Deja `C:\qemu-cluster-demo\debian_disks\ray0.qcow2` (+ ray1/ray2) y `ray\`.

**b) Dependencias de la TUI** (las instala el lanzador, o manual):
```powershell
python -m pip install -r requirements-tui.txt   # textual, rich, paramiko
```

**c) Preparar el acceso por LLAVE** (una vez; **no se necesita contraseña**): genera una llave
propia (`ray_cluster`) e inyecta su pública en los discos de las VMs **offline** (Docker + libguestfs,
igual que el clúster Alpine):
```powershell
.\preparar_acceso_ray.ps1
```
Requiere haber hecho (a) primero. No toca la llave `qemu_cluster` del lab Alpine.

---

## 2. Lanzar

```powershell
cd C:\Users\welin\Desktop\universidad\Paralela\ray_qemu\gato_demo
.\run_tui_gato.ps1
```
(equivale a `python -m tui_gato` dentro de `gato_demo`).

---

## 3. Flujo de la demo (modo VM Debian)

En el **launcher**: ajusta *generaciones / partidas-por-tarea / tareas*, **Modo = VM Debian** y
**Nodos = 3** (multinodo) o **1** (single, rápido), y:

1. **⏻ Levantar Ray** → aparecen las **ventanas de QEMU** (1 o 3, prueba de las VMs). Con
   **Nodos=3** la TUI arma una **red interna VM↔VM** (hub Ethernet en el host), inicia
   `ray start --head` en ray0 y une ray1/ray2 con `ray start --address`; muestra el
   **Dashboard `http://127.0.0.1:8265`**. Cuando la línea diga `ray0 ✓  ray1 ✓  ray2 ✓`, listo.
2. **▶ Entrenar** → cambia a la pantalla de entrenamiento: sube `gato_rl_ray.py` por SFTP, lo
   corre **en el clúster** con `--emit-events`, y verás en vivo:
   - **paneles por tarea Ray** (w0, w1, …) con rollouts y el nodo que los ejecutó (`@ray0/@ray1/@ray2`),
   - **ClusterFlow** (rollouts ↔ parciales viajando),
   - **curva de aprendizaje** subiendo de ~60–80 % a ~100 %,
   - **progreso** de generaciones (+ speedup si activas *Benchmark = sí*).
   Al terminar baja `gato_modelo.json` al host. (Pulsa **q** para volver al launcher.)
3. **🎮 Jugar** → juega contra el modelo entrenado (elige X u O; la IA usa la política
   aprendida + una red de seguridad táctica).
4. **⏼ Apagar** → `ray stop` + cierra la VM.

> Abre también el **Dashboard** en el navegador (`http://127.0.0.1:8265`) durante el
> entrenamiento para mostrar las tareas/recursos de Ray.

---

## 4. Modo local (ensayo, sin VM)

Para **probar la TUI sin levantar la VM** (ideal para ensayar la presentación):
pon **Modo = Local** y pulsa **▶ Entrenar**. Entrena en el host como subproceso
(`gato_rl_ray.py --backend local`), con el mismo flujo visual (paneles, curva, progreso),
genera `gato_modelo.json` y `gato.html`, y luego **🎮 Jugar** funciona igual.
No necesita contraseña, ni Ray, ni QEMU.

---

## 5. Cómo demuestra el uso de Ray

- **Se levanta lo necesario:** la VM Debian (QEMU) + `ray start --head` (Dashboard).
- **Distribución real:** el driver hace `ray.put` de la política y lanza **K tareas
  `@ray.remote`** por generación (`ray.get` recolecta) — visible en los paneles y el flujo.
- **Aprendizaje:** la curva sube generación a generación (medido vs un rival aleatorio).
- **Resultado usable:** juegas contra el modelo entrenado distribuido.

> **Multinodo real (Nodos=3):** como la NAT de QEMU aísla las VMs y el multicast no funciona en
> Windows, la TUI conecta una **2ª NIC** de cada VM a un **hub Ethernet en el host** (`netbus.py`)
> → LAN interna `10.10.0.0/24` (ray0=.10, ray1=.11, ray2=.12, vía SSH root). Así ray1/ray2 se unen
> al head con `ray start --address=10.10.0.10:6379` y las tareas se reparten **de verdad** entre los
> 3 nodos (lo ves en los hostnames y en el Dashboard con **3 nodos / 6 CPU**). Es la "fase siguiente"
> del deck (slides 15/20), ya funcionando.
>
> **RAM:** cada VM usa ~1.3 GB (3 ≈ 3.8 GB); configurable con `RAY_VM_MEM`. Con poca RAM usa **Nodos=1**.

---

## 6. Problemas frecuentes

| Síntoma | Causa probable | Acción |
|---|---|---|
| `No existe ...\debian_disks\ray0.qcow2` | falta extraer | corre `.\extraer_debian_ray.ps1` |
| `ray0: no respondió SSH a tiempo` | la VM aún arranca o falta inyectar la llave | espera el boot; corre `.\preparar_acceso_ray.ps1` |
| `ray status` muestra 1 nodo (esperabas 3) | la red interna no se formó | confirma que la llave se inyectó también en **root**; revisa el `event-log` |
| Multinodo lento / se traba | poca RAM (3×~1.3 GB) | baja `RAY_VM_MEM` o usa **Nodos = 1** |
| `ModuleNotFoundError: textual` | faltan deps | `python -m pip install -r requirements-tui.txt` |
| La curva no sube / no hay paneles | no llegan eventos | revisa el `event-log` abajo; confirma que `ray-env` tiene Ray en la VM |
| `pip`/Ray lento en la VM | recursos | usa menos *partidas-por-tarea*; el modo local sirve para ensayar |
| No abre la ventana de QEMU | headless activado | desactiva `QEMU_HEADLESS`; usa WHPX |

---

## 7. Estructura

```
gato_demo/
├── gato_rl_ray.py        # núcleo RL + Ray (--emit-events, --modelo-salida)
├── tui_gato/             # la TUI (Textual)
│   ├── app.py            # 3 pantallas + EventBus + modos vm/local
│   ├── ray_control.py    # boot 1 o 3 VMs + red interna + ray start head/workers + apagar
│   ├── ssh_run.py        # SSH por LLAVE (ray_cluster): stream + sftp
│   ├── netbus.py         # hub Ethernet en el host (LAN interna VM↔VM para multinodo)
│   ├── widgets.py        # WorkerPanel, ClusterFlow, GlobalProgress, SpeedupCard, LearningCurve
│   ├── gato_core.py      # motor del gato + IA (para jugar)
│   ├── banner.py, _shield_art.py, theme.tcss, events.py
│   └── __main__.py
├── run_tui_gato.ps1            # lanzador (instala deps + python -m tui_gato)
├── extraer_debian_ray.ps1      # extrae debian_disks/ + ray/ del ZIP (one-time)
├── preparar_acceso_ray.ps1     # genera la llave propia e inyecta su pública (one-time)
├── preparar_acceso_ray.Dockerfile  # imagen libguestfs para la inyección
└── requirements-tui.txt        # textual, rich, paramiko
```
