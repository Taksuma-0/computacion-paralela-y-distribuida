# 🎓 Guion de presentación — Orquestador distribuido sobre clúster QEMU (UTEM)

> Guion para explicar, paso a paso, **qué hace cada parte**, **cómo funciona por dentro**,
> **cómo se distribuye el trabajo**, **qué conexiones usa** y **qué muestra la terminal**.

---

## 0. Resumen en una frase

> Es un **orquestador genérico de tareas distribuidas**: un **coordinador** (en el host) parte un
> problema grande en **trozos (chunks)**, los reparte por **red (TCP)** a varios **agentes de
> trabajo** que corren dentro de **máquinas virtuales QEMU** (Linux Alpine), recoge los resultados,
> los **combina** y mide el **speedup** contra una ejecución secuencial. Todo se maneja desde una
> **TUI** (interfaz de terminal) y deja **evidencia reproducible** en `results/`.

La idea clave: **la plataforma no sabe de ningún dominio**. La "tarea" (contar primos, WordCount,
ETL, grid-search…) se enchufa como un archivo `tasks/task_*.py` que cumple un **contrato** simple.

---

## 1. Las piezas (qué hace cada cosa)

| Pieza | Archivo | Rol |
|---|---|---|
| **Coordinador** | `coordinator_generic.py` | El "cerebro". Parte el trabajo, reparte chunks, reintenta, combina, mide. **No conoce el dominio.** |
| **Agente de trabajo** | `worker_agent.py` | Corre **dentro de cada VM**. Escucha TCP, recibe un chunk, ejecuta `run(chunk)` y devuelve el parcial. **No conoce el dominio.** |
| **Tarea** | `tasks/task_*.py` | La **lógica de negocio**. Define `split / run / merge` (+ `self_test` opcional). Es lo único específico del problema. |
| **Baseline** | `baseline_seq.py` | Ejecuta TODO secuencialmente en un proceso. Es el **denominador honesto** del speedup. |
| **TUI (interfaz)** | `tui/app.py` | App Textual: menú (Launcher) + tablero (Dashboard). Orquesta y muestra todo en vivo. |
| **Ciclo de vida VMs** | `tui/cluster_control.py` | Arranca/apaga las VMs QEMU y sondea que estén listas por SSH. |
| **Tail SSH** | `tui/ssh_tail.py` | Trae por SSH la **salida real** de cada VM (`/tmp/worker_agent.log`) al panel del nodo. |
| **Tareas/payloads** | `tui/payloads.py` | Presets de tareas y sus parámetros por defecto para el menú. |
| **Widgets/estética** | `tui/widgets.py`, `tui/banner.py`, `tui/theme.tcss` | Paneles, barras, flujo de datos, escudo UTEM, colores. |
| **Evidencia** | `results/<job_id>.json` + `.log` | Registro reproducible de cada corrida (chunks, tiempos, speedup, resultado). |

**Topología (modo Clúster):**
- **Coordinador → corre en el HOST** (tu Windows, dentro de la TUI).
- **Workers que procesan → `nodo1` y `nodo2`** (las VMs, según `workers.host.json`).
- **`nodo0`** se enciende como parte del clúster (en el diseño original "todo dentro de QEMU" el
  coordinador vivía en `nodo0`; en esta TUI ese rol lo hace el host).

---

## 2. El contrato de una tarea (lo único de dominio)

Toda tarea en `tasks/` implementa 3 funciones puras (ejemplo real, `task_primes.py`):

```python
def split(payload, workers) -> list[dict]:   # parte el problema en chunks autosuficientes
def run(chunk) -> dict:                       # PROCESA un chunk (puro, idempotente, solo stdlib)
def merge(results) -> dict:                   # combina los parciales en el resultado final
def self_test() -> (chunk, esperado):         # OPCIONAL: health-check funcional
```

Para **"contar primos hasta 300000 en 40 chunks"**:
- `split` → 40 sub-rangos balanceados: `[{start:2,end:7500}, {start:7501,end:15000}, …]`
- `run({start, end})` → `{"prime_count": N}` (cuenta primos en ese rango)
- `merge([...])` → `{"total_primes": suma}`
- `self_test()` → `({start:2,end:10}, {prime_count:4})` (primos 2,3,5,7 = 4)

> Gracias a este contrato, el **mismo** coordinador y el **mismo** agente sirven para primos,
> WordCount, ETL o grid-search **sin cambiar una línea** de la plataforma.

---

## 3. Cómo funciona por dentro (un job de principio a fin)

```
                          HOST (Windows)  ── coordinador (TUI)
                                │
        1) split(payload) ──► N chunks                 (p.ej. 40)
                                │
        2) preparar workers ┌── deploy por SSH/SFTP (sube agente + tarea) [si cluster]
           (por cada VM)    └── health-check FUNCIONAL (envía self_test, valida resultado)
                                │
        3) COLA DINÁMICA (pull): 1 hilo por worker; cada hilo "tira" un chunk de la cola
                                │
        4) por cada chunk:  TCP JSON ──►  worker_agent (en la VM)  ──► run(chunk) ──► parcial
                                │              ▲
        5) reintentos/fallos ───┘   (reintenta tarea fallida; repara/abandona si cae la infra)
                                │
        6) merge(parciales) ──► resultado final
                                │
        7) speedup = baseline_host / tiempo_distribuido     +     results/<job_id>.json
```

### 3.1 Repartir el trabajo: **cola dinámica (pull model)**
- Hay UNA cola con los `chunk_id` pendientes.
- Se lanza **un hilo por worker sano**. Cada hilo, en bucle, **saca** un chunk de la cola, lo
  manda, y al volver saca otro. → **Balanceo automático**: el worker más rápido procesa más chunks
  (no hay reparto fijo). Es el patrón *work-stealing / pull*.

### 3.2 Tolerancia a fallos (lo que lo hace "serio")
- **Fallo de TAREA** (el `run` lanzó excepción): se **reintenta** hasta `max_retries` (2). Si se
  agota, el chunk se marca **abandonado** (pero el job sigue).
- **Fallo de INFRAESTRUCTURA** (se cayó la conexión TCP / la VM): **no** gasta reintentos del chunk.
  El coordinador intenta **reparar** el worker (re-deploy + reiniciar el agente por SSH, hasta 2
  veces); si lo repara, devuelve el chunk a la cola; si no, marca el worker **DOWN** y reparte su
  trabajo entre los que quedan vivos.
- **Health-check funcional**: no basta con que el puerto esté abierto; se envía un `self_test` y se
  exige el **resultado correcto** antes de confiar en un worker.

### 3.3 La medición (speedup honesto)
- `baseline_seq.py` corre el **mismo** `split/run/merge` **secuencial en un proceso** (sin red).
- `speedup = elapsed_baseline / elapsed_distribuido`.
- Es honesto porque ambos resuelven exactamente el mismo problema; lo único que cambia es **dónde**
  y **cómo** se ejecutan los chunks.

---

## 4. Lo distribuido: las conexiones y los puertos

La red entre el host y las VMs usa **QEMU user-mode networking** con **reenvío de puertos**
(`hostfwd`): un puerto del host (127.0.0.1) se mapea al puerto interno de la VM.

| Desde (HOST) | Hacia (VM) | Protocolo | Para qué |
|---|---|---|---|
| `127.0.0.1:2220` | `nodo0:22` | **SSH** | acceso a nodo0 |
| `127.0.0.1:2221` | `nodo1:22` | **SSH** | **deploy** (SFTP) + reiniciar agente + **tail** del log |
| `127.0.0.1:2222` | `nodo2:22` | **SSH** | ídem para nodo2 |
| `127.0.0.1:9001` | `nodo1:9000` | **TCP (JSON)** | enviar **chunks** y recibir parciales |
| `127.0.0.1:9002` | `nodo2:9000` | **TCP (JSON)** | ídem para nodo2 |

### 4.1 Dos canales por worker
1. **SSH (paramiko)** — *plano de control*: copiar el agente y la tarea (SFTP), arrancar/reiniciar
   el agente (`nohup python3 worker_agent.py`), y **leer su log en vivo** (`tail -F`).
2. **TCP JSON** — *plano de datos*: el coordinador abre una conexión, manda **una línea JSON**
   (terminada en `\n`) con el chunk, y el agente responde con **otra línea JSON**. Framing simple y
   robusto a la fragmentación de TCP.

**Mensaje que viaja (host → VM):**
```json
{"job_id":"job-...", "chunk_id":7, "task_name":"task_primes", "chunk":{"start":7501,"end":15000}}
```
**Respuesta (VM → host):**
```json
{"ok":true, "chunk_id":7, "worker":"nodo1", "result":{"prime_count":812}, "seconds":0.83}
```

### 4.2 ¿Por qué TCP? (y no UDP)
Porque los **chunks y los resultados no se pueden perder ni desordenar**. TCP da, **sin que lo programes**:
- **Entrega garantizada** (retransmite si se pierde un paquete),
- **Orden** e **integridad** (checksum) — un parcial cortado o corrupto = **resultado incorrecto**,
- **Conexión petición→respuesta**: abrir → mandar el chunk → leer el parcial → cerrar (un **RPC** minúsculo).

Con **UDP** tendríamos que reimplementar a mano *acks*, retransmisión, orden y reensamblado → **reinventar
TCP**. UDP sirve para tiempo real donde perder un paquete da igual (video, juegos), **no** para datos que
deben llegar bien. Y un **broker** (RabbitMQ) o **gRPC** serían **dependencias innecesarias** para un
orquestador didáctico: **TCP + JSON crudo** *muestra* el paso de mensajes sin esconderlo tras un framework.

> **Framing:** TCP es un **flujo de bytes**, no mensajes; por eso enmarcamos cada mensaje con un salto de
> línea `\n` (**un JSON por línea**). Así es robusto a que TCP **junte o parta** los paquetes.

### 4.3 ¿Por qué SSH es útil?
TCP mueve los **datos**, pero antes hay que **preparar** las VMs y **vigilarlas**: ese es el **plano de
control**, y lo hace SSH. Aporta:
- **Acceso remoto seguro y autenticado** (por **llave**, sin password) a cada VM.
- **SFTP** (va sobre SSH): **copiar** `worker_agent.py` + la tarea a cada nodo (y solo si cambió el `sha256`).
- **Ejecución remota de comandos**: **arrancar / parar / reiniciar** el agente (`nohup python3
  worker_agent.py …`), comprobar `python3 --version`, **reparar** un nodo caído.
- **Streaming del log**: `tail -F /tmp/worker_agent.log` para traer la **salida real** de la VM al panel.

Todo esto **sin instalar ningún servicio extra** en la VM: SSH ya viene. (Y SSH también corre **sobre TCP**,
puerto 22.)

> En una frase: **SSH = las "manos" para instalar, arrancar y vigilar; TCP = la "tubería" de los datos del
> trabajo.**

### 4.4 Cómo conversan (el diálogo, paso a paso)
**Datos (un chunk), por TCP** — el coordinador es el **cliente**, el agente el **servidor**:
```text
coordinator_generic.send_task              worker_agent.AgentHandler  (en la VM)
        │  TCP connect 127.0.0.1:9001 ──────────►  escuchando en 0.0.0.0:9000
        │  envía  {"job_id","chunk_id":7,"task_name","chunk"}\n  ──►  rfile.readline()
        │                                              load_task(task_name) → run(chunk)
        │                                              imprime línea de estado (la "tailea" el TUI)
        │  ◄──  {"ok":true,"worker","result":{…},"seconds":0.83}\n   ── wfile.write
        │  cierra la conexión  ───────────────────────►  (siguiente chunk)
```
1. El **coordinador** (`send_task`) abre TCP a `task_host:task_port` (p.ej. `127.0.0.1:9001` → `nodo1:9000`
   por el reenvío de QEMU) y manda **una línea JSON** con el chunk.
2. El **agente** (`AgentHandler.handle`) hace `readline()`, importa la tarea, ejecuta `run(chunk)`,
   **imprime** su línea de estado y responde **otra línea JSON** con el parcial.
3. El coordinador **lee hasta el `\n`**, parsea y guarda el parcial → toma el siguiente chunk de la cola.

**Control (preparación y vigilancia), por SSH:**
- **Deploy** → SSH: `mkdir` → SFTP `put` del agente + la tarea (si cambió) → arrancar el agente con `nohup`.
- **Health-check** → en realidad va por **TCP**: manda un `self_test` (con `chunk_id = -1`) y **exige el
  resultado correcto** antes de confiar en el worker (no basta con que el puerto esté abierto).
- **Tail** → SSH: `tail -F /tmp/worker_agent.log` y cada línea aparece en el panel del nodo.

### 4.5 Qué archivo levanta cada conexión
| Conexión | Quién la **inicia / escucha** | Archivo · función |
|---|---|---|
| **Reenvío de puertos host↔VM** (la base de todo) | QEMU al arrancar (`hostfwd`) | `tui/cluster_control.py` → `VM_SPECS` / `boot_cluster()` |
| **TCP de datos — servidor** (escucha `:9000` en la VM) | el **agente**, dentro de la VM | `worker_agent.py` → `ThreadedTCPServer(("0.0.0.0",9000))` + `serve_forever()` |
| **TCP de datos — cliente** (abre la conexión) | el **coordinador**, en el host | `coordinator_generic.py` → `send_task()` (`socket.create_connection`) |
| **SSH deploy / restart / repair** | el **coordinador**, en el host | `coordinator_generic.py` → clase `Deployer` (paramiko + SFTP) |
| **SSH readiness** (¿ya booteó la VM?) | la **TUI**, en el host | `tui/cluster_control.py` → `ssh_ready()` |
| **SSH tail del log** | la **TUI**, en el host | `tui/ssh_tail.py` → `tail_worker()` |

> **Quién arranca a quién:** la TUI (`cluster_control`) **levanta las VMs con el reenvío de puertos** → el
> `Deployer` del coordinador **arranca el agente** por SSH → el agente **abre el servidor TCP** en `:9000` →
> el coordinador **se conecta** a ese puerto para mandar los chunks. Sin el `hostfwd` no existiría ni el SSH
> ni el TCP: es el cimiento de toda la comunicación host↔VM.

### 4.6 Aceleración por hardware
Las VMs arrancan con **WHPX** (Windows Hypervisor Platform) si está disponible → arranque y CPU
**por hardware** (rápido, ~20 s las 3) y sin el *kernel panic* de la emulación por software (TCG).
Si no hubiera WHPX, cae solo a TCG (más lento).

---

## 5. Qué muestra la terminal (qué "tira" la TUI)

### 5.1 Menú (Launcher)
- Selección de **Tarea**, **Modo** (Local / Clúster) y **Payload** (JSON).
- Botones: **⏻ Despertar clúster**, **▶ Ejecutar**, **⏼ Apagar clúster**, **Salir**.
- **Línea de estado del clúster** (se llena al arrancar):
  `clúster   ✓ nodo0    ✓ nodo1    ⏳ nodo2    (2/3)`
- **Log** con el avance (lanzando QEMU, SSH listo, etc.).

### 5.2 Tablero (Dashboard, durante el job)
- **Un panel por worker** (nodo1, nodo2) con: estado, nº de chunks hechos, tiempo ocupado, chunk
  actual, y la **salida REAL de la VM** (traída por SSH `tail -F` del log del agente). Ej.:
  `[/] nodo1 task_primes chunk#7 in={"start":7501,...} -> {"prime_count":812} (0.83s)`
- **Flujo del clúster**: animación de los **paquetes** (tarea ➜ worker en verde, resultado ◂ en
  azul) + sparkline de throughput (chunks/s).
- **Barra de progreso global** (chunks completados / total).
- **Tarjeta de speedup** (verde si > 1).
- **Event-log** con la traza de eventos del coordinador.

### 5.3 Eventos que emite el coordinador (lo que mueve el tablero)
`job_start → worker_ready → chunk_assigned → chunk_done (× N) → [chunk_retry / chunk_infra_fail /
worker_repair / worker_dropped] → job_done`

### 5.4 Salida final / evidencia
Al terminar, el log dice algo como:
```
FIN: 40/40 chunks OK, 0 reintentos, 0 abandonados, 2.13s
speedup = 1.97 (baseline 4.20s / distribuido 2.13s)
resultado: {"total_primes": 25997}
```
Y se guarda **`results/<job_id>.json`** (chunks, tiempos por worker, speedup, resultado, timestamp)
y **`results/<job_id>.log`** → **prueba reproducible** de la corrida.

---

## 6. 🎬 Guion paso a paso (lo que dices y muestras)

1. **"Esto es un orquestador de tareas distribuidas sobre un clúster de 3 VMs QEMU."**
   Lanzo la TUI:
   ```powershell
   cd C:\Users\welin\Desktop\universidad\Paralela\Paralelismo_con_qemu\orquestador
   powershell -ExecutionPolicy Bypass -File .\run_tui.ps1
   ```

2. **"Primero despierto el clúster."** Click en **⏻ Despertar clúster**.
   → *"Aparecen las 3 ventanas de QEMU (las VMs reales arrancando) y la línea de estado se llena
   `✓ nodo0 ✓ nodo1 ✓ nodo2`. Esto prueba que sí hay máquinas virtuales de verdad."*
   (Por debajo: QEMU arranca con WHPX y el host sondea por SSH hasta que cada VM responde.)

3. **"Elijo una tarea, por ejemplo contar primos hasta 300.000 en 40 chunks, modo Clúster."**
   Explico el **contrato**: `split` parte en 40 trozos, `run` cuenta primos en cada trozo, `merge`
   suma. *"La plataforma no sabe qué es un primo: eso vive solo en `task_primes.py`."*

4. **"Ejecuto."** Click en **▶ Ejecutar**. Mientras corre, explico el tablero:
   - *"Primero mide el **baseline secuencial** en el host (el denominador del speedup)."*
   - *"Luego **despliega** por SSH el agente y la tarea a cada VM y hace un **health-check funcional**."*
   - *"Después reparte los 40 chunks con una **cola dinámica**: cada worker tira trabajo cuando queda
     libre → balanceo automático. Cada panel muestra la **salida real** de su VM."*
   - *"Si una VM se cae, el coordinador la **repara** por SSH o reparte su trabajo; si un chunk falla,
     **reintenta**."*

5. **"Resultado y speedup."** Señalo la tarjeta de speedup y el resultado final
   (`{"total_primes": 25997}`), y menciono que queda **evidencia** en `results/<job_id>.json`.

6. **"Apago el clúster."** Click en **⏼ Apagar clúster** → cierra las VMs ordenadamente.

> **Teclas:** en el menú `q` = Salir; en el tablero `q`/Esc = Volver, `a` = Apagar clúster.

---

## 7. Conceptos de Paralela/Distribuida que demuestra

- **Descomposición** (split) y **reducción** (merge) — patrón *MapReduce* simplificado.
- **Balanceo de carga dinámico** (cola pull / work-stealing) vs. reparto estático.
- **Comunicación por paso de mensajes** (TCP JSON), no memoria compartida → **sistema distribuido** real.
- **Tolerancia a fallos**: reintentos, health-check funcional, reparación y degradación (worker DOWN).
- **Medición rigurosa**: baseline honesto, speedup, evidencia reproducible.
- **Separación plataforma/dominio**: coordinador y agente genéricos; la tarea es enchufable.

---

## 8. Para correrlo sin la TUI (por si lo preguntan)

```powershell
# Baseline secuencial (denominador del speedup)
python baseline_seq.py --task tasks/task_primes.py --payload '{"upper":300000,"n_chunks":40}'

# Distribuido contra el clúster (coordinador en el host, deploy por SSH a nodo1/nodo2)
python coordinator_generic.py --task tasks/task_primes.py `
  --payload '{"upper":300000,"n_chunks":40}' --workers workers.host.json --deploy `
  --ssh-key C:\Users\welin\.ssh\qemu_cluster --baseline <elapsed_baseline>
```

> La TUI hace exactamente esto por ti (baseline → `run_job(..., deploy=True)`), pero en vivo y con tablero.

---

## 9. Las tareas de paralelización en detalle

La plataforma (coordinador + agente) es **genérica**: lo único de dominio son las tareas en `tasks/`.
Se incluyen **5 tareas** que **no son arbitrarias**: cada una ejercita una **forma de reducción
(`merge`) distinta**, para demostrar que el **mismo** coordinador y el **mismo** agente sirven para
problemas con semánticas muy diferentes **sin cambiar una línea** de la plataforma.

| Tarea | Archivo | Qué computa | `merge` = | Payload por defecto |
|---|---|---|---|---|
| 🔢 **Primos** | `task_primes.py` | cuenta primos hasta `upper` | **suma escalar** | `{"upper":300000,"n_chunks":40}` |
| 📝 **WordCount** | `task_wordcount.py` | frecuencia de palabras (docs sintéticos) | **suma de diccionarios** | `{"seed":2026,"num_docs":8000,"n_chunks":40}` |
| 🗃️ **ETL** | `task_etl.py` | limpia + transforma + agrega registros | **consolidación** | `{"seed":7,"num_rows":200000,"n_chunks":40}` |
| 🎯 **Grid search** | `task_gridsearch.py` | mejor hiperparámetro | **argmax (elegir el mejor)** | `{"grid":{…},"n_chunks":40}` |
| 💥 **Flaky** | `task_flaky.py` | *(prueba)* falla a propósito | suma (demo de reintentos) | `{"n_chunks":12,"fail_chunks":[3,7]}` |

> **El punto pedagógico:** primos, WordCount, ETL y grid-search muestran **cuatro maneras de combinar
> parciales** — *sumar un número*, *sumar diccionarios*, *consolidar/unir* y *elegir el mejor*. Misma
> plataforma, distinta semántica de `merge`. **Eso es lo que prueba que el orquestador es genérico.**

### 9.1 🔢 Primos — *la tarea "patrón oro"*
> **En una frase:** cuenta cuántos números primos hay hasta `upper`, repartiendo el rango `[2, upper]` entre las VMs.

- **`split`**: parte el rango `[2, upper]` en `n_chunks` sub-rangos **balanceados** → `{start, end}`.
- **`run`**: cuenta primos en `[start, end]` (prueba por división hasta √n) → `{prime_count}`.
- **`merge`**: **suma** todos los `prime_count` → `{total_primes}`.
- **`self_test`**: primos entre 2 y 10 = `{2,3,5,7}` → 4.
- **Por qué es la tarea de validación**: su resultado es **verificable contra un valor conocido**
  (π(300.000) = **25.997**). Si el distribuido da ese número, todo el pipeline (split → deploy →
  health-check → cola → reintentos → merge) está **correcto**.
- **Perfil**: casi 100% CPU y **muy pocos datos que mover** → es **la mejor tarea para mostrar
  speedup**, porque el cómputo domina sobre la red.

**Suelta en la terminal** (una línea por chunk → línea final):
```text
[/] nodo1 task_primes chunk#7 in={"start":7501,"end":15000} -> {"prime_count":812} (0.83s)
FIN: 40/40 chunks OK · resultado {"total_primes": 25997} · speedup 1.97
```

### 9.2 📝 WordCount — *el MapReduce clásico*
> **En una frase:** cuenta la frecuencia de cada palabra en miles de documentos generados por semilla (Map = contar, Reduce = sumar).

- **`split`**: reparte `num_docs` documentos en `n_chunks`. **Truco clave**: el chunk **no transporta
  texto**, solo una **semilla** + cuántos documentos generar.
- **`run`**: **reconstruye** esos documentos con `random.Random(semilla)` (Mersenne Twister:
  determinista e idéntico en cualquier máquina) y cuenta palabras de un vocabulario fijo →
  `{counts:{palabra:n}, docs}`.
- **`merge`**: **suma los diccionarios** palabra por palabra y saca el **top-10** →
  `{docs, distinct, total_tokens, top10}`.
- **Idea distribuida**: *"datos por semilla"* evita mover datos por la red — cada nodo **fabrica** su
  porción de forma reproducible. Es el "hola mundo" del cómputo distribuido (Map = contar por
  documento, Reduce = sumar los conteos).

**Suelta en la terminal** (una línea por chunk → línea final):
```text
[/] nodo2 task_wordcount chunk#3 in={"chunk_seed":…,"num_docs":200} -> {"docs":200,"counts":{…}} (0.19s)
FIN: 40/40 chunks OK · resultado {"docs":8000,"distinct":24,"total_tokens":~320000,"top10":[["data",13820],…]}
```

### 9.3 🗃️ ETL distribuido — *el caso realista de datos*
> **En una frase:** fabrica, limpia y transforma registros sucios y los consolida en un resumen global (un ETL repartido).

Patrón **"cada nodo hace lo suyo"**: cada worker **fabrica** su partición de registros crudos (por
semilla), los **limpia** y **transforma**, y devuelve **agregados + una muestra acotada**.
- **`split`**: reparte `num_rows` filas; cada chunk lleva `chunk_seed, num_rows, row_offset` y tasas de
  basura (`null_rate`, `invalid_rate`).
- **`run`** = un **ETL en miniatura** por fila:
  1. **Extract** — genera un registro crudo sintético (con nulos e inválidos a propósito).
  2. **Clean** — descarta nulos, montos negativos y nombres vacíos.
  3. **Transform** — normaliza (redondea el monto, nombre en MAYÚSCULAS sin espacios).
  4. **Aggregate** — cuenta válidos/descartados, suma/min/max y guarda una muestra.
  - → `{n_valid, n_discarded, sum_amount, min_amount, max_amount, sample}`.
- **`merge`** = **consolidación**: suma conteos y montos, min/max **global**, promedio, y **une las
  muestras** ordenadas → resumen + `consolidated_sample`.
- **Decisión de diseño**: `run` devuelve **agregados + muestra pequeña**, no todas las filas → mensajes
  JSON **livianos** (las VMs tienen 256 MB). En un ETL real, las filas transformadas se
  **persistirían por nodo**.

**Suelta en la terminal** (una línea por chunk → línea final):
```text
[/] nodo1 task_etl chunk#5 in={"num_rows":5000,"row_offset":25000} -> {"n_valid":4231,"n_discarded":769,"sum_amount":1057342.55,…} (0.12s)
FIN: 40/40 chunks OK · resultado {"n_valid":~170000,"n_discarded":~30000,"total_amount":…,"avg_amount":…,"consolidated_sample":[…]}
```

### 9.4 🎯 Grid search — *optimización / ML*
> **En una frase:** prueba todas las combinaciones de hiperparámetros y se queda con la mejor.

Búsqueda de hiperparámetros: probar muchas combinaciones y quedarse con la mejor.
- **`split`**: arma el **producto cartesiano** de la grilla (p.ej. `lr × depth × reg` = 48 combos) y lo
  reparte **round-robin** (`combos[i::n]`) entre los chunks → `{configs, seed}`.
- **`run`**: evalúa cada config con una **función objetivo determinista** (superficie suave con máximo
  cerca de `lr=0.1, depth=4, reg=0`) y devuelve su **mejor local** → `{local_best, evaluated}`.
- **`merge`** = **argmax global**: de los mejores locales, elige el de mayor score →
  `{best_config, best_score, configs_evaluated}`.
- **Lo distinto**: aquí `merge` **no reduce ni une — ELIGE**. Tercera semántica de combinación.

**Suelta en la terminal** (una línea por chunk → línea final):
```text
[/] nodo2 task_gridsearch chunk#1 in={"configs":[…2 configs…]} -> {"local_best":{"config":{"lr":0.1,"depth":4,"reg":0.0},"score":-0.0001},"evaluated":2} (0.01s)
FIN: 40/40 chunks OK · resultado {"best_config":{"lr":0.1,"depth":4,"reg":0.0},"best_score":-0.0001,"configs_evaluated":48}
```

### 9.5 💥 Flaky — *demo de tolerancia a fallos* (no entregable)
> **En una frase:** tarea de prueba que **falla a propósito** en ciertos trozos para ver los reintentos en vivo.

- Tarea de **prueba** que **falla de forma determinista** en los chunks de `fail_chunks`.
- Sirve para **mostrar en vivo** los reintentos y los estados (`chunk_retry`, chunk abandonado) **sin
  tener que romper una VM** de verdad.
- Con `{"n_chunks":12,"fail_chunks":[3,7]}`: los chunks 3 y 7 se **reintentan** y, si siguen fallando,
  se marcan **abandonados** mientras **el resto del job termina bien**.

**Suelta en la terminal** (los chunks 3 y 7 fallan y se reintentan):
```text
[x] nodo1 task_flaky chunk#3 -> ERROR "fallo deterministico forzado" → reintento 1/2 … 2/2 → ABANDONADO
[✓] nodo2 task_flaky chunk#5 -> {"i":5,"ok":1} (0.00s)
FIN: 10/12 OK, 2 abandonados (chunks 3 y 7) · resultado {"sum":10,"ids":[0,1,2,4,5,6,8,9,10,11]}
```

### 9.6 ⚖️ El baseline secuencial (`baseline_seq.py`) — el denominador honesto
**Qué es**: ejecuta exactamente el **mismo** `split → run(todos los chunks) → merge`, pero en **un solo
proceso del host**, **sin red ni SSH**.

```python
chunks   = task.split(payload, [{"name": "baseline-local"}])
t0       = perf_counter()
partials = [task.run(chunk) for chunk in chunks]   # ← lo ÚNICO cronometrado: el cómputo
elapsed  = perf_counter() - t0
final    = task.merge(partials)
```

- **Qué mide**: solo el **bucle de cómputo** (`run` de todos los chunks) — el trabajo "puro", el mismo
  que en distribuido se reparte entre las VMs.
- **El speedup**: `speedup = elapsed_baseline / elapsed_distribuido`.
- **Por qué es honesto**:
  1. Resuelve **el mismo problema** con el **mismo código de dominio** (mismo `split/run/merge`).
  2. El **resultado debe coincidir** con el del distribuido → verifica **correctitud**, no solo velocidad.
  3. Lo único que cambia es **dónde y cómo** corren los chunks: 1 proceso vs. N workers por red.
- **Matiz importante (no se infla el número)**: el baseline corre en el **host** (potente) y las VMs son
  **256 MB / 1 vCPU**. Por eso el speedup **no está garantizado > 1**: refleja si el **paralelismo real**
  (varias VMs a la vez) supera el **handicap por núcleo + el overhead de red**. Para **primos** (mucho
  CPU, poca red) normalmente gana; en tareas con poco cómputo por chunk la red puede comerse la ventaja
  — y **ese también es un resultado válido y honesto que mostrar**.

---

## 10. 🎬 Guion cronometrado de ~10 minutos (presentación)

> Versión **cerrada y cronometrada** para exponer. (La de la §6 es la versión rápida de referencia.)
> **Antes de empezar:** ten el clúster despierto (Despertar es **idempotente**) y **una corrida previa
> de primos en `results/`** por si la red falla en vivo.

| Min | Bloque | Qué muestro |
|---|---|---|
| **0:00–1:00** | Apertura: qué es y por qué importa | la frase del §0 / portada |
| **1:00–2:30** | Arquitectura y piezas | diagrama del §3 |
| **2:30–4:00** | Contrato + las tareas (4 merges) | tabla del §9 / `task_primes.py` |
| **4:00–5:00** | Despertar clúster (EN VIVO) | ventanas QEMU + línea de estado |
| **5:00–7:00** | Ejecutar **Primos** (el corazón) | tablero: baseline → cola → speedup |
| **7:00–8:00** | Tolerancia a fallos (**Flaky** EN VIVO) | reintentos en el event-log |
| **8:00–9:00** | Lo distribuido: conexiones/puertos | tabla del §4 + JSON |
| **9:00–10:00** | Cierre: evidencia + conceptos + apagar | `results/` + apagar clúster |

### ⏱️ 0:00–1:00 — Apertura
- **Muestro:** la portada o la frase del §0.
- **Digo:** *"Construí un **orquestador genérico de tareas distribuidas**. Un coordinador parte un
  problema grande en trozos, los reparte por red a varias máquinas virtuales que los procesan en
  paralelo, junta los resultados y mide cuánto más rápido fue que hacerlo secuencial. Lo clave: **la
  plataforma no sabe de qué va el problema** — la tarea se enchufa."*
- **Tip:** una frase, sin entrar en código todavía.

### ⏱️ 1:00–2:30 — Arquitectura y piezas
- **Muestro:** el diagrama del §3.
- **Digo:** *"Tres piezas. El **coordinador** en el host: el cerebro, reparte y mide. El **agente**
  dentro de cada VM: recibe un trozo, lo ejecuta, devuelve el parcial. Y la **tarea**, lo único
  específico del dominio. Coordinador y agente son **genéricos** — los mismos para todos los problemas.
  Más un **baseline** secuencial como patrón de comparación."*
- **Tip:** recalca la **separación plataforma/dominio** — es tu mejor argumento de diseño.

### ⏱️ 2:30–4:00 — El contrato y las tareas
- **Muestro:** la tabla de las **4 formas de merge** (§9) y, si quieres, `task_primes.py`.
- **Digo:** *"Toda tarea implementa tres funciones: `split` parte, `run` procesa un trozo, `merge`
  combina. Lo elegante: incluí **cuatro problemas con cuatro maneras distintas de combinar** — primos
  **suma un número**, WordCount **suma diccionarios**, ETL **consolida datos**, grid-search **elige el
  mejor**. La plataforma no cambió ni una línea."*
- **Tip:** no expliques las 5 a fondo; nombra las **4 semánticas de merge** y profundiza solo en primos.

### ⏱️ 4:00–5:00 — Despertar el clúster (EN VIVO)
- **Muestro:** click en **⏻ Despertar clúster** → aparecen las 3 ventanas QEMU + la línea
  `✓ nodo0  ✓ nodo1  ✓ nodo2`.
- **Digo:** *"Despierto el clúster. Estas tres ventanas son **máquinas virtuales QEMU reales**
  arrancando Linux. Usan aceleración por hardware (**WHPX**) y el host espera a que cada una responda
  por **SSH**."*
- **Tip:** si ya estaban despiertas, lo reconoce **al instante** (idempotente) — dilo como una virtud.

### ⏱️ 5:00–7:00 — Ejecutar Primos (EL CORAZÓN)
- **Muestro:** elegir **Primos / Clúster**, click **▶ Ejecutar**, y narrar el tablero mientras corre.
- **Digo:** *"Cuento primos hasta 300.000 en 40 trozos. Miren el orden: **(1)** primero mide el
  **baseline secuencial** en el host — el denominador. **(2)** **Despliega** por SSH el agente y la
  tarea a cada VM y hace un **health-check funcional** (le manda un mini-problema y exige el resultado
  correcto). **(3)** Reparte los 40 trozos con una **cola dinámica**: cada VM **tira** trabajo cuando
  queda libre, así la más rápida hace más — balanceo automático. Cada panel muestra la **salida real**
  de su VM. **(4)** Al final: **speedup** y el resultado, `total_primes = 25.997`, que es el valor
  correcto — así demuestro que **además de rápido, es correcto**."*
- **Tip:** este es **el** bloque; déjalo correr y narra encima.

### ⏱️ 7:00–8:00 — Tolerancia a fallos (Flaky EN VIVO)
- **Muestro:** tarea **Flaky** con `fail_chunks:[3,7]` → en el event-log aparecen los `chunk_retry`.
- **Digo:** *"Para mostrar robustez tengo una tarea que **falla a propósito** en dos trozos. El
  coordinador los **reintenta**; y si fuera la **VM** la que se cae, en vez de gastar reintentos **la
  repara por SSH** o reparte su trabajo entre las vivas. El job termina igual."*
- **Tip:** si vas justo de tiempo, este es el primer bloque que puedes **recortar** y solo explicar.

### ⏱️ 8:00–9:00 — Lo distribuido: conexiones y puertos
- **Muestro:** la tabla del §4 + el mensaje JSON de ida y vuelta.
- **Digo:** *"Cada worker usa **dos canales**: **SSH** para el control (subir el agente, reiniciarlo,
  leer su log) y **TCP con JSON** para los datos — el coordinador manda una línea JSON con el trozo y
  recibe otra con el parcial. No hay memoria compartida: es **paso de mensajes**, un sistema distribuido
  de verdad."*
- **Tip:** mostrar el JSON concreto vende mucho.

### ⏱️ 9:00–10:00 — Cierre
- **Muestro:** `results/<job_id>.json` y luego **⏼ Apagar clúster**.
- **Digo:** *"Cada corrida deja **evidencia reproducible** en `results/`: trozos, tiempos por worker,
  speedup y resultado. En resumen, esto demuestra **descomposición y reducción, balanceo dinámico, paso
  de mensajes, tolerancia a fallos y medición honesta**. Apago el clúster y cierro el ciclo."*
- **Tip:** terminar **apagando** demuestra el ciclo de vida completo.

### ✅ Checklist antes de presentar
- [ ] Clúster despierto (o despertarlo en el bloque 4:00; es idempotente).
- [ ] Una corrida previa de **primos** en `results/` por si la red falla en vivo.
- [ ] Payloads por defecto cargados (primos `300000/40`; flaky `12/[3,7]`).
- [ ] Tener a mano el número correcto: **π(300.000) = 25.997**.
- [ ] **Plan B:** si una VM no levanta, el job sigue con las demás → dilo como **feature**, no como falla.
