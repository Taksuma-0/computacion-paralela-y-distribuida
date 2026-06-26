#!/usr/bin/env python3
"""worker_agent.py - Agente de trabajo GENERICO (parte de la plataforma).

No conoce ningun dominio ni contiene logica de negocio. Escucha en TCP, recibe un
mensaje JSON con el nombre de una tarea y un chunk, importa esa tarea dinamicamente
y ejecuta su funcion run(chunk). La logica de dominio vive 100% en los modulos
tasks/task_*.py, que se despliegan junto a este agente.

Solo stdlib (las VMs son Alpine minimal). Si aparece cualquier simbolo de negocio
en este archivo, el diseno esta acoplado y es un error.

Protocolo (una linea JSON por conexion TCP, terminada en '\\n'):
    recibe : {"job_id": "...", "chunk_id": 7, "task_name": "task_xxxx", "chunk": {...}}
    OK     : {"ok": true,  "chunk_id": 7, "result": {...}, "seconds": 0.83}
    error  : {"ok": false, "chunk_id": 7, "error": "Tipo: mensaje", "trace": "..."}

Uso:
    python3 worker_agent.py --port 9000 --task-dir /root/orchestrator/tasks
"""

import argparse
import importlib.util
import json
import os
import socket
import socketserver
import sys
import time
import traceback

DEFAULT_TASK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks")

# Estado global del agente (configurado en main()).
TASK_DIR = DEFAULT_TASK_DIR
_TASK_CACHE = {}

# --- Linea de estado por chunk (visible en la consola QEMU y tailable por el TUI) ---
_SPIN = "|/-\\"


def _short(obj, n=46):
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= n else s[:n - 1] + "~"


def _print_chunk_line(task_name, chunk_id, chunk, result, elapsed):
    sp = _SPIN[(chunk_id or 0) % len(_SPIN)]
    print(f"[{sp}] {socket.gethostname()} {task_name} chunk#{chunk_id} "
          f"in={_short(chunk)} -> {_short(result)} ({elapsed:.3f}s)", flush=True)


def load_task(task_name: str):
    """Importa tasks/<task_name>.py dinamicamente (con cache por proceso)."""
    name = task_name[:-3] if task_name.endswith(".py") else task_name
    if name in _TASK_CACHE:
        return _TASK_CACHE[name]

    path = os.path.join(TASK_DIR, name + ".py")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"tarea '{name}' no encontrada en {TASK_DIR}")

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run") or not callable(module.run):
        raise AttributeError(f"tarea '{name}' no define run()")

    _TASK_CACHE[name] = module
    return module


class AgentHandler(socketserver.StreamRequestHandler):
    """rfile es un lector BUFFERIZADO sobre el socket: readline() arma el mensaje
    aunque TCP lo fragmente. Toda excepcion se captura y se responde como JSON."""

    def handle(self):
        chunk_id = None
        try:
            raw = self.rfile.readline()
            if not raw:
                return
            request = json.loads(raw.decode("utf-8").strip())
            chunk_id = request.get("chunk_id")

            # Ping de salud opcional: no toca ninguna tarea.
            if request.get("task_name") == "__ping__":
                self._send({"ok": True, "chunk_id": chunk_id, "result": {"agent": "alive"}})
                return

            task = load_task(request["task_name"])
            t0 = time.perf_counter()
            result = task.run(request["chunk"])
            elapsed = time.perf_counter() - t0

            if chunk_id != -1:
                _print_chunk_line(request.get("task_name"), chunk_id, request.get("chunk"), result, elapsed)

            self._send({
                "ok": True,
                "chunk_id": chunk_id,
                "worker": socket.gethostname(),
                "result": result,
                "seconds": round(elapsed, 4),
            })
        except Exception as exc:
            self._send({
                "ok": False,
                "chunk_id": chunk_id,
                "worker": socket.gethostname(),
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc()[-800:],
            })
            traceback.print_exc(file=sys.stderr)

    def _send(self, obj):
        try:
            data = json.dumps(obj, ensure_ascii=False, allow_nan=False) + "\n"
            self.wfile.write(data.encode("utf-8"))
            self.wfile.flush()
        except Exception:
            # Si ni siquiera se pudo serializar/responder, no hay nada mas que hacer.
            traceback.print_exc(file=sys.stderr)


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True   # evita "Address already in use" tras un reinicio
    daemon_threads = True        # los handlers no bloquean el apagado


def main():
    global TASK_DIR
    parser = argparse.ArgumentParser(description="Agente de trabajo generico del orquestador.")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--task-dir", default=DEFAULT_TASK_DIR)
    args = parser.parse_args()

    TASK_DIR = os.path.abspath(args.task_dir)
    server = ThreadedTCPServer(("0.0.0.0", args.port), AgentHandler)
    print(f"worker_agent escuchando en 0.0.0.0:{args.port} | task_dir={TASK_DIR}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("worker_agent detenido.", flush=True)


if __name__ == "__main__":
    main()
