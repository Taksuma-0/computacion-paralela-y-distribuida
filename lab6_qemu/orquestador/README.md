# Orquestador genérico de tareas distribuidas (cluster QEMU)

Ejercicio integrador — Unidad 8, INFB8090 Computación Paralela y Distribuida (UTEM).

Transforma la demo de cluster QEMU que solo contaba primos en un **mini-framework de
ejecución distribuida**: la plataforma (coordinador + workers) **no conoce el dominio**;
cada tarea es un *plugin* que cumple el contrato `split / run / merge` y se pasa como
parámetro en tiempo de ejecución.

```
python3 coordinator_generic.py --task tasks/task_primes.py \
    --payload '{"upper":300000,"n_chunks":24}' --workers workers.json --deploy
```

## Arquitectura: frontera plataforma / tarea

```
   coordinator_generic.py            worker_agent.py (en cada nodo)
   ----------------------            -----------------------------
   - carga la tarea (--task)         - servidor TCP genérico (:9000)
   - split()  -> chunks              - importa la tarea por nombre
   - despliega agente+tarea (SSH)    - ejecuta task.run(chunk)
   - cola dinámica + reintentos      - responde JSON {ok, result, seconds}
   - merge() -> resultado final      - NO contiene lógica de dominio
            |                                   ^
            |   mensaje JSON {job_id, chunk_id, |  respuesta JSON
            |   task_name, chunk}  ------------>|
            v                                   |
        tasks/task_*.py  (split / run / merge / self_test)  <- ÚNICO lugar con dominio
```

La plataforma es agnóstica: `grep -i "is_prime\|wordcount\|etl\|gridsearch" worker_agent.py
coordinator_generic.py` no devuelve nada.

## Contrato de tarea

Cada `tasks/task_*.py` expone:

```python
def split(payload: dict, workers: list) -> list[dict]   # divide en chunks autosuficientes
def run(chunk: dict) -> dict                             # ejecuta UN chunk (puro/idempotente, solo stdlib)
def merge(results: list[dict]) -> dict                   # combina los parciales
def self_test() -> tuple[dict, dict]                     # (opcional) (chunk_trivial, resultado_esperado)
```

**Datos por semilla:** los chunks no transportan datasets. Llevan una `seed` + parámetros y
`run()` **regenera** su porción de datos con `random.Random(seed)` (determinista e idéntico
entre máquinas). Resultado: cero transferencia de archivos y evidencia 100 % reproducible.
`split` deriva semillas disjuntas con una mezcla aritmética estable (no usa `hash()`, que
Python aleatoriza por proceso).

**Health-check funcional:** `self_test()` devuelve un chunk trivial y su resultado esperado.
El coordinador lo envía al agente y exige que coincida — así verifica socket + framing +
carga de tarea + cómputo, no solo que el puerto TCP esté abierto.

## Las 4 tareas (tres formas distintas de `merge`)

| Tarea | `split` | `run` | `merge` | Forma de merge |
|---|---|---|---|---|
| `task_primes` | rangos `[start,end]` | cuenta primos | suma `prime_count` | reducción escalar |
| `task_wordcount` | docs sintéticos por semilla | tokeniza y cuenta | **suma diccionarios** | reducción clave-valor |
| `task_etl` | particiones de filas | extrae→limpia→transforma su lote | **consolida** filas + métricas | concatenación / unión |
| `task_gridsearch` | grilla de hiperparámetros | evalúa configs → score | **elige la mejor** | selección (argmax) |

`task_primes` es la tarea de **paridad/validación**: su resultado es verificable
(π(300000)=25997), lo que permite confiar en el pipeline antes de las tareas nuevas.
`task_flaky` es una tarea de **inyección de fallos** para demostrar reintentos (ver Robustez).

## Estructura

```
orquestador/
├─ coordinator_generic.py   # orquestador (corre en nodo0)
├─ worker_agent.py          # agente genérico (se despliega a nodo1/nodo2)
├─ workers.json             # topología del cluster (10.0.2.2 + puertos reenviados)
├─ workers.local.json       # solo dev: 2 agentes locales en 127.0.0.1
├─ baseline_seq.py          # baseline secuencial (denominador del speedup)
├─ tasks/                   # task_primes, task_wordcount, task_etl, task_gridsearch, task_flaky
├─ scripts/deploy_to_nodo0.ps1
└─ results/                 # evidencia: <job_id>.json + <job_id>.log
```

## Protocolo JSON (una línea por conexión TCP, terminada en `\n`)

```jsonc
// coordinador -> agente
{"job_id":"job-...", "chunk_id":7, "task_name":"task_primes", "chunk":{...}}
// agente -> coordinador
{"ok":true,  "chunk_id":7, "result":{...}, "seconds":0.83}
{"ok":false, "chunk_id":7, "error":"ValueError: ...", "trace":"..."}
```

## Ejecución

### A) Validación local en el host (sin VMs)

Permite probar V1–V5 sin QEMU usando dos agentes locales (simulan nodo1/nodo2).

```powershell
# 1) Contrato en local (sin red):
python coordinator_generic.py --task tasks/task_primes.py --payload '{"upper":300000,"n_chunks":24}' --local

# 2) Levantar dos agentes (dos terminales, o en segundo plano):
#    Puertos 9101/9102 (los de workers.local.json) para no chocar con los reenvios QEMU 9001/9002.
python worker_agent.py --port 9101 --task-dir tasks
python worker_agent.py --port 9102 --task-dir tasks

# 3) Job distribuido contra los agentes locales (sin despliegue SSH):
python coordinator_generic.py --task tasks/task_wordcount.py `
    --payload '{"seed":2026,"num_docs":8000,"n_chunks":24}' `
    --workers workers.local.json --no-deploy
```

### B) Cluster QEMU (coordinador en nodo0)

```powershell
# 1) Extraer el paquete y lanzar las 3 VMs (una sola vez):
& "C:\Program Files\WinRAR\UnRAR.exe" x ".\qemu-cluster-demo.rar" "C:\qemu-cluster-demo\"
powershell -ExecutionPolicy Bypass -File C:\qemu-cluster-demo\scripts\start-all.ps1

# 2) Desplegar el proyecto a nodo0 e instalar paramiko:
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_to_nodo0.ps1
```
```bash
# 3) Entrar a nodo0 y ejecutar (el coordinador despliega agente+tarea a nodo1/nodo2):
ssh -p 2220 root@127.0.0.1
cd /root/orchestrator
python3 coordinator_generic.py --task tasks/task_primes.py     --payload '{"upper":300000,"n_chunks":24}'  --workers workers.json --deploy
python3 coordinator_generic.py --task tasks/task_wordcount.py  --payload '{"seed":2026,"num_docs":8000,"n_chunks":24}' --workers workers.json
python3 coordinator_generic.py --task tasks/task_etl.py        --payload '{"seed":7,"num_rows":200000,"n_chunks":24}'  --workers workers.json
python3 coordinator_generic.py --task tasks/task_gridsearch.py --payload '{"seed":2026,"grid":{"lr":[0.01,0.05,0.1,0.5],"depth":[2,4,8,16],"reg":[0.0,0.1,0.3]},"n_chunks":24}' --workers workers.json
```

> El `--deploy` solo hace falta la primera vez (o cuando cambia el código): copia
> `worker_agent.py` + la tarea por SFTP comparando `sha256`, mata el agente viejo y arranca
> el nuevo. Luego puedes omitirlo.

### Opciones del coordinador

| Flag | Default | Uso |
|---|---|---|
| `--task` | — | módulo de tarea |
| `--payload` | `{}` | parámetros globales (JSON) |
| `--workers` | — | `workers.json` |
| `--deploy` / `--no-deploy` | no-deploy | desplegar agente+tarea por SSH/SFTP |
| `--ssh-key` | — | llave privada SSH para el despliegue (recomendado; alternativa al password) |
| `--ssh-password` | — | password SSH (si no hay llave; o se toma de workers.json / se pregunta) |
| `--max-retries` | 2 | reintentos por chunk antes de abandonar |
| `--timeout` | 30 | timeout por chunk (s) |
| `--baseline` | — | `elapsed` del baseline para registrar speedup |
| `--local` | off | ejecuta `run()` en este proceso (sin red) |

## Evidencia y métricas

Cada job escribe `results/<job_id>.json` (parámetros, workers, `per_chunk`, `per_worker`,
`retries`, `failed_chunks`, `result`, `elapsed`, `speedup`) y `results/<job_id>.log`.

Para el **speedup**, medir primero el baseline secuencial y pasarlo con `--baseline`:

```bash
python3 baseline_seq.py --task tasks/task_wordcount.py --payload '{"seed":2026,"num_docs":8000,"n_chunks":24}'
# -> usar el 'elapsed' impreso como --baseline en el coordinator
```

## Robustez (cómo reproducir)

- **Health-check funcional** antes de repartir: un worker que abre el puerto pero responde
  mal queda excluido (o se repara por SSH si `--deploy`).
- **Cola dinámica:** un hilo por worker que pide trabajo al terminar → balanceo automático.
- **Reintentos con límite + estados** (`pendiente→en_ejecucion→completado|fallido→reintento→abandonado`):
  ```bash
  # Falla determinista en 2 chunks -> reintenta y luego los ABANDONA (sin invalidar el job):
  python3 coordinator_generic.py --task tasks/task_flaky.py --payload '{"n_chunks":6,"fail_chunks":[2,4]}' --workers workers.json --max-retries 2
  ```
- **Tolerancia a caída de worker:** si un worker muere a mitad del job, sus chunks se
  re-encolan y otro worker los completa (verificado: matando un agente, el job termina 60/60).

## Validación en el cluster QEMU real (medido)

Ejecutado con el **coordinador en nodo0** desplegando a nodo1/nodo2 por SSH/SFTP.
Entorno: Alpine Linux 3.23, kernel 6.18, Python 3.12.13, cada VM 256 MB / 1 vCPU.

Acceso: como la contraseña de root de las VMs no estaba disponible, se configuró
**autenticación por llave SSH** (la práctica que recomienda la teoría): se inyectó una
llave pública en `/root/.ssh/authorized_keys` de cada nodo y el coordinador despliega con
`--ssh-key`. La plataforma soporta llave o password indistintamente.

Speedup (baseline secuencial en 1 nodo vs distribuido en nodo1+nodo2):

| Tarea | baseline | distribuido | speedup | resultado |
|---|---|---|---|---|
| primes | 11.37 s | 7.72 s | **1.47** | 25 997 primos |
| wordcount | 5.41 s | 4.10 s | **1.32** | 319 564 tokens, 24 distintos |
| etl | 11.06 s | 9.01 s | **1.23** | 155 403 válidas / 44 597 descartadas |
| gridsearch | 0.03 s | 0.61 s | 0.05 | mejor `{lr:0.1,depth:4,reg:0.0}` |

- **Determinismo entre máquinas:** los resultados del cluster coinciden exactamente con los
  del baseline y con las corridas locales (p.ej. gridsearch da el mismo `best_score 0.00538`),
  gracias a la generación de datos por semilla.
- **gridsearch** tiene speedup < 1 porque su cómputo es trivial frente al overhead de red:
  sirve para demostrar **generalidad** (merge = argmax), no aceleración. Las tareas con cómputo
  real (primes, wordcount, etl) sí escalan en dos nodos.
- **Robustez en cluster:** reintentos verificados con `task_flaky` (chunks 2 y 4 → 3 intentos →
  abandonados, job no invalidado). Tolerancia a caída de worker verificada matando el agente de
  nodo1 a mitad de un job, en sus dos modos: con `--deploy` el coordinador lo **auto-repara** por
  SSH y lo reincorpora (40/40 completados); sin `--deploy` lo marca **DOWN** y nodo2 asume el resto.
  En ambos casos el job converge sin perder ni duplicar chunks.

La evidencia está en `results/cluster-*.json` (+ `.log`).

## Supuestos y limitaciones

- VMs **Alpine** minimal (256 MB, 1 vCPU): tareas y agente en **stdlib puro**; `paramiko`
  solo en el coordinador (`apk add py3-paramiko`).
- SSH a las VMs como `root`; la contraseña se toma de `--ssh-password`, de `workers.json`
  (`"ssh_password"`) o se pregunta interactivamente.
- Con cómputo liviano y red localhost/QEMU-NAT, el **overhead** puede dominar y dar
  speedup < 1; subir `num_docs`/`num_rows`/grilla para que `run` pese más que la
  comunicación. El informe discute esta curva.
- `task_etl` consolida agregados + una muestra acotada (en un ETL real las filas
  transformadas se persistirían por nodo); mantiene los mensajes JSON livianos.

## Troubleshooting

| Síntoma | Causa / solución |
|---|---|
| `falta paramiko` | en nodo0: `apk add py3-paramiko` |
| worker queda `DOWN` | revisar `start-all.ps1`, puertos reenviados y que el agente arrancó (`/tmp/worker_agent.log` en el nodo) |
| `Address already in use` | el agente usa `allow_reuse_address`; el coordinador mata el PID viejo antes de arrancar |
| resultado distinto entre corridas | no debería: la semilla es determinista; revisar que no se editó una tarea a mitad |
