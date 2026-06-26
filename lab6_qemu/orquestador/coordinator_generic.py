#!/usr/bin/env python3
"""coordinator_generic.py - Orquestador GENERICO de tareas distribuidas.

La plataforma (este coordinador + worker_agent.py) NO conoce ningun dominio. La
tarea llega como parametro (--task) y define toda la semantica via split/run/merge.

    python3 coordinator_generic.py --task tasks/task_primes.py \\
        --payload '{"upper":300000,"n_chunks":24}' --workers workers.json --deploy

Modos:
    --local        ejecuta run() de cada chunk en este proceso (sin red). Sirve
                   para validar el contrato de una tarea (V1).
    (red)          reparte los chunks a los worker_agent por TCP usando una COLA
                   DINAMICA (un hilo por worker, pull model) con reintentos y
                   estados por chunk (V4 + V5). Con --deploy, primero copia el
                   agente y la tarea a cada nodo por SSH/SFTP y verifica salud
                   funcional (V3).

Genera evidencia reproducible en results/<job_id>.json y results/<job_id>.log.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import queue
import socket
import sys
import threading
import time
from dataclasses import dataclass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")


# ============================================================
# Carga de tarea y de workers
# ============================================================

def load_task_module(task_path: str):
    if not os.path.isfile(task_path):
        raise FileNotFoundError(f"No existe el archivo de tarea: {task_path}")
    name = os.path.splitext(os.path.basename(task_path))[0]
    spec = importlib.util.spec_from_file_location(name, task_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [fn for fn in ("split", "run", "merge")
               if not hasattr(module, fn) or not callable(getattr(module, fn))]
    if missing:
        raise AttributeError(f"La tarea '{name}' no define: {', '.join(missing)}")
    return module, name


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    task_host: str
    task_port: int
    ssh_host: str
    ssh_port: int


def load_workers(workers_path):
    """Devuelve (config, raw_workers, specs). raw_workers se pasa tal cual a split()."""
    if workers_path is None:
        raw = [{"name": "local"}]
        return {}, raw, []
    with open(workers_path, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    raw = config["workers"]
    specs = [WorkerSpec(w["name"], w["task_host"], int(w["task_port"]),
                        w["ssh_host"], int(w["ssh_port"])) for w in raw]
    return config, raw, specs


# ============================================================
# Logger sencillo (consola + results/<job_id>.log)
# ============================================================

class Logger:
    def __init__(self, path):
        self._fh = open(path, "w", encoding="utf-8")
        self._lock = threading.Lock()

    def __call__(self, message):
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        with self._lock:
            print(line, flush=True)
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self):
        self._fh.close()


# ============================================================
# Protocolo TCP (framing newline-delimited robusto)
# ============================================================

def send_task(spec: WorkerSpec, message: dict, timeout: float) -> dict:
    payload = json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n"
    with socket.create_connection((spec.task_host, spec.task_port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload.encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
    if not buf:
        raise RuntimeError(f"{spec.name} cerro la conexion sin responder")
    return json.loads(buf.decode("utf-8"))


# ============================================================
# Health-check FUNCIONAL (no basta el puerto abierto)
# ============================================================

def _health_probe(task_module, task_name):
    """Devuelve (chunk, expected_or_None). Usa self_test() si existe; si no,
    el primer chunk real (solo se exige ok=True)."""
    if hasattr(task_module, "self_test") and callable(task_module.self_test):
        chunk, expected = task_module.self_test()
        return chunk, expected
    return None, None


def worker_is_healthy(spec, task_module, task_name, payload, raw_workers, timeout):
    chunk, expected = _health_probe(task_module, task_name)
    if chunk is None:
        chunks = task_module.split(payload, raw_workers)
        if not chunks:
            return True, "sin chunks que probar"
        chunk, expected = chunks[0], None
    try:
        resp = send_task(spec, {"job_id": "health", "chunk_id": -1,
                                "task_name": task_name, "chunk": chunk}, timeout)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if not resp.get("ok"):
        return False, f"run remoto fallo: {resp.get('error')}"
    if expected is not None and resp.get("result") != expected:
        return False, f"resultado inesperado: {resp.get('result')} != {expected}"
    return True, "self_test funcional OK"


def wait_for_worker_healthy(spec, task_module, task_name, payload, raw_workers,
                            timeout, deadline_seconds):
    deadline = time.time() + deadline_seconds
    last = "sin intento"
    while time.time() < deadline:
        ok, reason = worker_is_healthy(spec, task_module, task_name, payload, raw_workers, timeout)
        if ok:
            return True, reason
        last = reason
        time.sleep(0.7)
    return False, last


# ============================================================
# Despliegue por SSH/SFTP (V3) - paramiko de carga perezosa
# ============================================================

def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


class Deployer:
    """Copia worker_agent.py + el task elegido a cada nodo y arranca el agente.
    Reusa el patron probar->SSH->matar->subir->iniciar->reprobar del coordinator_aio."""

    def __init__(self, config, task_path, task_name, ssh_password, log, ssh_key=None):
        try:
            import paramiko  # noqa
        except ImportError:
            print("ERROR: falta paramiko en el coordinador.\n"
                  "  Alpine: apk add py3-paramiko   |   pip: pip install paramiko", file=sys.stderr)
            sys.exit(1)
        self.paramiko = paramiko
        self.ssh_user = config.get("ssh_user", "root")
        self.remote_dir = config.get("remote_dir", "/root/orchestrator")
        self.password = ssh_password
        self.ssh_key = ssh_key
        self.task_path = task_path
        self.task_name = task_name
        self.agent_path = os.path.join(SCRIPT_DIR, "worker_agent.py")
        self.log = log
        self.repairs = {}  # spec.name -> nº de reparaciones (cap de seguridad)

    def _connect(self, spec):
        client = self.paramiko.SSHClient()
        client.set_missing_host_key_policy(self.paramiko.AutoAddPolicy())
        kw = dict(hostname=spec.ssh_host, port=spec.ssh_port, username=self.ssh_user,
                  timeout=15, banner_timeout=15, auth_timeout=15, allow_agent=False)
        if self.ssh_key:
            client.connect(key_filename=self.ssh_key, look_for_keys=True, **kw)
        else:
            client.connect(password=self.password, look_for_keys=False, **kw)
        return client

    @staticmethod
    def _exec(client, command, check=True):
        _, stdout, stderr = client.exec_command(command)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        if check and code != 0:
            raise RuntimeError(f"comando remoto fallo ({code}): {command}\n{err}")
        return code, out, err

    def _remote_dir(self):
        return self.remote_dir.rstrip("/")

    def _upload_if_changed(self, client, sftp, local_path, remote_path):
        local_hash = _sha256_file(local_path)
        code, out, _ = self._exec(client, f"sha256sum {remote_path} 2>/dev/null || true", check=False)
        remote_hash = out.split()[0] if out.split() else None
        if remote_hash == local_hash:
            return False
        sftp.put(local_path, remote_path)
        self._exec(client, f"chmod 644 {remote_path}", check=False)
        return True

    def deploy(self, spec):
        """Copia agente + task. Devuelve True si algo cambio (=> conviene reiniciar)."""
        client = self._connect(spec)
        try:
            rdir = self._remote_dir()
            self._exec(client, f"mkdir -p {rdir}/tasks")
            sftp = client.open_sftp()
            try:
                a = self._upload_if_changed(client, sftp, self.agent_path, f"{rdir}/worker_agent.py")
                t = self._upload_if_changed(client, sftp, self.task_path, f"{rdir}/tasks/{self.task_name}.py")
            finally:
                sftp.close()
            self.log(f"[{spec.name}] deploy: agente {'actualizado' if a else 'sin cambios'}, "
                     f"task {'actualizada' if t else 'sin cambios'}")
            return a or t
        finally:
            client.close()

    def _stop(self, client):
        rdir = self._remote_dir()
        self._exec(client, f"[ -f {rdir}/worker_agent.pid ] && kill $(cat {rdir}/worker_agent.pid) "
                           f"2>/dev/null; rm -f {rdir}/worker_agent.pid; sleep 1 || true", check=False)

    def _start(self, client):
        rdir = self._remote_dir()
        cmd = (f"cd {rdir} && nohup python3 worker_agent.py --port 9000 --task-dir {rdir}/tasks "
               f"> /tmp/worker_agent.log 2>&1 & echo $! > {rdir}/worker_agent.pid")
        self._exec(client, cmd, check=True)

    def restart(self, spec):
        client = self._connect(spec)
        try:
            self._exec(client, "python3 --version")
            self._stop(client)
            self._start(client)
        finally:
            client.close()

    def try_repair(self, spec):
        n = self.repairs.get(spec.name, 0)
        if n >= 2:
            self.log(f"[{spec.name}] limite de reparaciones alcanzado")
            return False
        self.repairs[spec.name] = n + 1
        self.log(f"[{spec.name}] reparando (intento {n + 1})...")
        try:
            self.deploy(spec)
            self.restart(spec)
            return True
        except Exception as exc:
            self.log(f"[{spec.name}] reparacion fallo: {exc}")
            return False


# ============================================================
# Modo LOCAL (V1)
# ============================================================

def run_local(task_module, task_name, payload, raw_workers):
    chunks = task_module.split(payload, raw_workers)
    t0 = time.perf_counter()
    partials = [task_module.run(c) for c in chunks]
    elapsed = time.perf_counter() - t0
    final = task_module.merge(partials)
    print(f"[LOCAL] {task_name}: {len(chunks)} chunks en {elapsed:.4f}s")
    print(f"[LOCAL] resultado: {json.dumps(final, ensure_ascii=False, allow_nan=False)}")
    return final


# ============================================================
# Modo DISTRIBUIDO (V4 cola dinamica + V5 reintentos/estados)
# ============================================================

def run_distributed(task_module, task_name, payload, raw_workers, specs, args, log, deployer,
                    on_event=None):
    def emit(kind, **data):
        if on_event is None:
            return
        try:
            on_event({"kind": kind, "t": time.time(), **data})
        except Exception:
            pass  # la telemetria nunca tumba el job

    chunks = task_module.split(payload, raw_workers)
    n = len(chunks)
    chunk_by_id = {i: c for i, c in enumerate(chunks)}
    log(f"job={args.job_id} task={task_name} chunks={n} workers={[s.name for s in specs]}")
    emit("job_start", job_id=args.job_id, task_name=task_name, n_chunks=n,
         workers=[s.name for s in specs], payload=payload)

    # --- Preparar workers: deploy (opcional) + health-check funcional ---
    healthy = []
    for spec in specs:
        if deployer is not None:
            try:
                changed = deployer.deploy(spec)
                if changed:
                    deployer.restart(spec)
            except Exception as exc:
                log(f"[{spec.name}] deploy fallo: {exc}")
        ok, reason = wait_for_worker_healthy(spec, task_module, task_name, payload,
                                             raw_workers, args.timeout, args.health_timeout)
        if not ok and deployer is not None and deployer.try_repair(spec):
            ok, reason = wait_for_worker_healthy(spec, task_module, task_name, payload,
                                                 raw_workers, args.timeout, args.health_timeout)
        if ok:
            healthy.append(spec)
            log(f"[{spec.name}] EN LINEA y funcional: {reason}")
            emit("worker_ready", worker=spec.name, reason=reason)
        else:
            log(f"[{spec.name}] DOWN: {reason} (excluido del job)")
            emit("worker_down", worker=spec.name, reason=reason)

    if not healthy:
        raise RuntimeError("ningun worker quedo sano; no se puede ejecutar el job")
    log(f"Listo para trabajar con {len(healthy)} worker(s): {[s.name for s in healthy]}")

    # --- Estado compartido ---
    pending = queue.Queue()
    for cid in chunk_by_id:
        pending.put((cid, 0))
    results = {}
    states = {cid: "pendiente" for cid in chunk_by_id}
    per_chunk = {cid: {"chunk_id": cid, "state": "pendiente", "attempts": 0} for cid in chunk_by_id}
    per_worker = {s.name: {"chunks": 0, "busy_seconds": 0.0} for s in specs}
    failed = []
    counters = {"retries": 0, "terminal": 0, "live": len(healthy)}
    lock = threading.Lock()

    def worker_loop(spec):
        while True:
            with lock:
                if counters["terminal"] >= n:
                    break
            try:
                cid, attempt = pending.get(timeout=0.2)
            except queue.Empty:
                continue

            with lock:
                states[cid] = "en_ejecucion"
                per_chunk[cid].update(state="en_ejecucion", worker=spec.name, attempts=attempt + 1)
            emit("chunk_assigned", cid=cid, worker=spec.name,
                 chunk=chunk_by_id[cid], attempt=attempt + 1)

            message = {"job_id": args.job_id, "chunk_id": cid,
                       "task_name": task_name, "chunk": chunk_by_id[cid]}
            resp, transport_error = None, None
            try:
                resp = send_task(spec, message, args.timeout)
            except Exception as exc:
                transport_error = f"{type(exc).__name__}: {exc}"

            if resp is not None and resp.get("ok"):
                seconds = resp.get("seconds") or 0.0
                with lock:
                    results[cid] = resp["result"]
                    states[cid] = "completado"
                    per_chunk[cid].update(state="completado", worker=spec.name,
                                          seconds=seconds, attempts=attempt + 1)
                    per_worker[spec.name]["chunks"] += 1
                    per_worker[spec.name]["busy_seconds"] = round(
                        per_worker[spec.name]["busy_seconds"] + seconds, 4)
                    counters["terminal"] += 1
                log(f"[{spec.name}] chunk {cid} OK ({seconds}s)")
                emit("chunk_done", cid=cid, worker=spec.name, seconds=seconds,
                     result_partial=resp["result"])
                continue

            # --- Fallo ---
            if transport_error is not None:
                # Fallo de INFRAESTRUCTURA: no consume reintentos del chunk.
                log(f"[{spec.name}] chunk {cid} fallo de infra: {transport_error}")
                emit("chunk_infra_fail", cid=cid, worker=spec.name, error=transport_error)
                repaired = deployer.try_repair(spec) if deployer is not None else False
                if repaired:
                    emit("worker_repair", worker=spec.name)
                    pending.put((cid, attempt))  # mismo attempt
                    continue
                # No reparable: marcar worker DOWN, devolver el chunk y salir del hilo.
                pending.put((cid, attempt))
                with lock:
                    counters["live"] -= 1
                    per_chunk[cid].update(state="pendiente")
                    states[cid] = "pendiente"
                log(f"[{spec.name}] marcado DOWN; deja de tomar trabajo")
                emit("worker_dropped", worker=spec.name)
                return

            # Fallo determinista de la TAREA (run lanzo excepcion): si consume reintento.
            reason = resp.get("error", "error desconocido")
            log(f"[{spec.name}] chunk {cid} fallo de tarea: {reason}")
            if attempt + 1 <= args.max_retries:
                with lock:
                    counters["retries"] += 1
                    states[cid] = "reintento"
                    per_chunk[cid].update(state="reintento")
                pending.put((cid, attempt + 1))
                emit("chunk_retry", cid=cid, worker=spec.name, reason=reason, attempt=attempt + 1)
            else:
                with lock:
                    states[cid] = "abandonado"
                    per_chunk[cid].update(state="abandonado", error=reason)
                    failed.append({"chunk_id": cid, "error": reason, "attempts": attempt + 1})
                    counters["terminal"] += 1
                log(f"[{spec.name}] chunk {cid} ABANDONADO tras {attempt + 1} intentos")
                emit("chunk_abandoned", cid=cid, worker=spec.name, reason=reason, attempts=attempt + 1)

    threads = [threading.Thread(target=worker_loop, args=(s,), name=s.name) for s in healthy]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    # Si todos los workers murieron antes de terminar, abandonar lo que quede.
    with lock:
        if counters["terminal"] < n:
            for cid in chunk_by_id:
                if states[cid] not in ("completado", "abandonado"):
                    states[cid] = "abandonado"
                    per_chunk[cid].update(state="abandonado", error="todos los workers DOWN")
                    failed.append({"chunk_id": cid, "error": "todos los workers DOWN",
                                   "attempts": per_chunk[cid].get("attempts", 0)})

    completed_ids = sorted(results)
    partials = [results[cid] for cid in completed_ids]
    final = task_module.merge(partials) if partials else None

    record = {
        "job_id": args.job_id,
        "task": os.path.basename(args.task),
        "task_name": task_name,
        "payload": payload,
        "coordinator_location": args.location,
        "workers": [{"name": s.name, "task_host": s.task_host, "task_port": s.task_port} for s in specs],
        "healthy_workers": [s.name for s in healthy],
        "n_chunks": n,
        "completed": len(completed_ids),
        "elapsed": round(elapsed, 4),
        "elapsed_baseline": args.baseline,
        "speedup": round(args.baseline / elapsed, 3) if args.baseline and elapsed > 0 else None,
        "retries": counters["retries"],
        "failed_chunks": failed,
        "per_worker": per_worker,
        "per_chunk": [per_chunk[cid] for cid in sorted(per_chunk)],
        "result": final,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    log(f"FIN: {len(completed_ids)}/{n} chunks OK, {counters['retries']} reintentos, "
        f"{len(failed)} abandonados, {elapsed:.3f}s")
    if args.baseline:
        log(f"speedup = {record['speedup']} (baseline {args.baseline}s / distribuido {elapsed:.3f}s)")
    log(f"resultado: {json.dumps(final, ensure_ascii=False, allow_nan=False)}")
    emit("job_done", record=record)
    return record


class _Args:
    """Namespace tipo-args para reutilizar run_distributed sin argparse (lo usa run_job)."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def run_job(task_path, payload, workers_path, *, deploy=False, ssh_key=None, ssh_password=None,
            max_retries=2, timeout=30.0, health_timeout=25.0, baseline=None, job_id=None,
            location="host", log=None, on_event=None):
    """Entrada programatica (la usa el TUI). Ejecuta un job y escribe results/<job_id>.json.
    `log` puede ser cualquier callable(str); si es None se crea un Logger a archivo."""
    job_id = job_id or f"job-{time.strftime('%Y%m%d-%H%M%S')}"
    task_module, task_name = load_task_module(task_path)
    config, raw_workers, specs = load_workers(workers_path)
    args = _Args(task=task_path, payload=payload, job_id=job_id, max_retries=max_retries,
                 timeout=timeout, health_timeout=health_timeout, baseline=baseline, location=location)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    own_logger = log is None
    if own_logger:
        log = Logger(os.path.join(RESULTS_DIR, job_id + ".log"))
    deployer = None
    if deploy:
        deployer = Deployer(config, task_path, task_name, ssh_password, log=log, ssh_key=ssh_key)
    try:
        record = run_distributed(task_module, task_name, payload, raw_workers, specs, args, log,
                                 deployer, on_event=on_event)
        with open(os.path.join(RESULTS_DIR, job_id + ".json"), "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, allow_nan=False, indent=2)
        return record
    finally:
        if own_logger:
            log.close()


# ============================================================
# main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Orquestador generico de tareas distribuidas.")
    parser.add_argument("--task", required=True, help="Ruta al modulo de tarea (tasks/task_X.py)")
    parser.add_argument("--payload", default="{}", help="Parametros globales del problema en JSON")
    parser.add_argument("--workers", default=None, help="Ruta a workers.json")
    parser.add_argument("--job-id", default=None, help="Identificador del job (por defecto: timestamp)")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout por chunk (s)")
    parser.add_argument("--health-timeout", type=float, default=25.0, help="Espera de salud por worker (s)")
    parser.add_argument("--baseline", type=float, default=None, help="elapsed del baseline secuencial para speedup")
    parser.add_argument("--local", action="store_true", help="Ejecuta run() localmente (sin red)")
    parser.add_argument("--deploy", dest="deploy", action="store_true", help="Despliega agente+task por SSH/SFTP")
    parser.add_argument("--no-deploy", dest="deploy", action="store_false")
    parser.add_argument("--ssh-password", default=None, help="Password SSH (si no, se toma de workers.json o se pregunta)")
    parser.add_argument("--ssh-key", default=None, help="Ruta a llave privada SSH (alternativa al password)")
    parser.add_argument("--location", default="nodo0", help="Etiqueta de donde corre el coordinador (evidencia)")
    parser.set_defaults(deploy=False)
    args = parser.parse_args()

    args.job_id = args.job_id or f"job-{time.strftime('%Y%m%d-%H%M%S')}"
    payload = json.loads(args.payload)
    task_module, task_name = load_task_module(args.task)

    if args.local:
        run_local(task_module, task_name, payload, [{"name": "local"}])
        return

    config, raw_workers, specs = load_workers(args.workers)
    if not specs:
        raise SystemExit("Modo red requiere --workers con al menos un worker.")

    deployer = None
    if args.deploy:
        password = args.ssh_password or config.get("ssh_password")
        if not password and not args.ssh_key:
            import getpass
            password = getpass.getpass(f"Password SSH para {config.get('ssh_user', 'root')}: ")
        os.makedirs(RESULTS_DIR, exist_ok=True)
        deployer = Deployer(config, args.task, task_name, password, log=lambda m: None, ssh_key=args.ssh_key)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    log = Logger(os.path.join(RESULTS_DIR, args.job_id + ".log"))
    if deployer is not None:
        deployer.log = log
    try:
        record = run_distributed(task_module, task_name, payload, raw_workers, specs, args, log, deployer)
        out_path = os.path.join(RESULTS_DIR, args.job_id + ".json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, allow_nan=False, indent=2)
        log(f"evidencia guardada en {out_path}")
    finally:
        log.close()


if __name__ == "__main__":
    main()
