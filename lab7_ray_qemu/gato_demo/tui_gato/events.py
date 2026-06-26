"""Contrato de eventos entre los productores (boot de VM, entrenamiento Ray por
SSH o local) y la TUI, más un EventBus thread-safe (cola). Los hilos productores
hacen put(); la App de Textual drena con drain() desde un set_interval."""

import queue

# --- control de la VM / Ray / log (los emite ray_control y la app) ---
VM_STATE = "vm_state"          # {node, state: booting|ready|failed|apagando|off}
VM_STDOUT = "vm_stdout"        # {worker, line}  (salida cruda en un panel)
LOG = "log"                    # {msg}
ERROR = "error"                # {msg}
CLUSTER_READY = "cluster_ready"  # {ready:[...], failed:[...], dashboard:url}
CLUSTER_DOWN = "cluster_down"    # {}
RAY_HEAD_READY = "ray_head_ready"  # {dashboard:url}

# --- emitidos por el entrenamiento (líneas 'EVT {json}' de gato_rl_ray.py) ---
TRAIN_START = "train_start"    # {generaciones, tareas, partidas_por_tarea}
GEN_START = "gen_start"        # {gen, epsilon}
CHUNK_ASSIGNED = "chunk_assigned"  # {worker, gen}
CHUNK_DONE = "chunk_done"      # {worker, hostname, seconds, partidas}
GEN_DONE = "gen_done"          # {gen, epsilon, nonloss, win, draw, loss, partidas, hosts}
TRAIN_DONE = "train_done"      # {meta, nonloss, win, draw}
BENCHMARK = "benchmark"        # {speedup, eficiencia, overhead, t1, tp, ...}
MODEL_READY = "model_ready"    # {path, estados}


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
