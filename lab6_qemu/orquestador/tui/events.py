"""Contrato de eventos entre el coordinador / control de cluster y el TUI,
y un EventBus thread-safe (cola). Los productores (hilos) hacen put(); el App
de Textual drena con drain() desde un set_interval (hilo del loop)."""

import queue

# --- emitidos por el coordinador (run_distributed on_event) ---
JOB_START = "job_start"
WORKER_READY = "worker_ready"
WORKER_DOWN = "worker_down"
WORKER_REPAIR = "worker_repair"
WORKER_DROPPED = "worker_dropped"
CHUNK_ASSIGNED = "chunk_assigned"
CHUNK_DONE = "chunk_done"
CHUNK_RETRY = "chunk_retry"
CHUNK_INFRA_FAIL = "chunk_infra_fail"
CHUNK_ABANDONED = "chunk_abandoned"
JOB_DONE = "job_done"

# --- emitidos por el control de cluster / tail / log ---
VM_STATE = "vm_state"      # {node, state: booting|ready|failed|apagando|off}
VM_STDOUT = "vm_stdout"    # {worker, line}
LOG = "log"                # {msg}
ERROR = "error"            # {msg}
CLUSTER_READY = "cluster_ready"   # {ready: [...], failed: [...]}  fin del arranque
CLUSTER_DOWN = "cluster_down"     # {}                              fin del apagado


class EventBus:
    """Cola thread-safe. put() desde cualquier hilo; drain() en lotes desde el loop."""

    def __init__(self):
        self._q = queue.Queue()

    def put(self, event: dict):
        self._q.put(event)

    def drain(self, max_items: int = 800):
        out = []
        for _ in range(max_items):
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out
