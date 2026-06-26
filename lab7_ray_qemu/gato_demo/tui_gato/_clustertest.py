"""Verificación END-TO-END del clúster Ray MULTINODO (3 nodos) usando los módulos reales:
levanta ray0+ray1+ray2 (hub + red interna), confirma el clúster, corre un entrenamiento y
comprueba que las tareas se reparten entre los 3 nodos (hostnames), descarga el modelo y apaga.

Ejecutar:  python -m tui_gato._clustertest
"""

import json
import os

from . import ray_control as rc
from . import ssh_run

DEMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(DEMO, "gato_rl_ray.py")
MODEL = os.path.join(DEMO, "gato_modelo_cluster.json")

_ready = {"nodes": []}


def emit(e):
    k = e.get("kind")
    if k == "vm_state":
        print(f"  [vm] {e.get('node')} -> {e.get('state')}")
    elif k in ("log", "error"):
        print(f"  [{k}] {e.get('msg')}")
    elif k == "cluster_ready":
        _ready["nodes"] = e.get("ready", [])
        print(f"  [cluster_ready] ready={e.get('ready')} failed={e.get('failed')}")


def main():
    hosts = set()
    evt = {"chunk_done": 0, "gen_done": 0, "train_done": 0}

    def on_line(line):
        if line.startswith("EVT "):
            try:
                d = json.loads(line[4:])
                kk = d.get("kind")
                if kk in evt:
                    evt[kk] += 1
                if kk == "chunk_done":
                    hosts.add(d.get("hostname"))
                    print(f"    rollout w{d.get('worker')} @ {d.get('hostname')}")
                elif kk == "gen_done":
                    print(f"  GEN {d.get('gen')}: no-derrota {d.get('nonloss')} hosts={d.get('hosts')}")
                return
            except Exception:
                pass
        print("  VM>", line[:100])

    try:
        print("=== 1) LEVANTAR CLÚSTER MULTINODO (3 nodos) ===")
        rc.levantar_multinodo(emit, ("ray0", "ray1", "ray2"))
        if len(_ready["nodes"]) < 2:
            print(f"RESULTADO: ⚠️ solo {len(_ready['nodes'])} nodo(s) en el clúster.")
            return 1

        print("=== 2) ENTRENAMIENTO DISTRIBUIDO (tareas repartidas) ===")
        ssh_run.sftp_put(rc.SSH_HOST, rc.SSH_PORT["ray0"], rc.RAY_USER, SCRIPT,
                         rc.REMOTE_DIR + "/gato_rl_ray.py")
        cmd = (f"{rc.RAY_ENV_ACTIVATE} && cd {rc.REMOTE_DIR} && "
               f"python gato_rl_ray.py 3 2000 9 --emit-events --modelo-salida gato_modelo.json")
        code = ssh_run.stream_command(rc.SSH_HOST, rc.SSH_PORT["ray0"], rc.RAY_USER, cmd,
                                      on_line, lambda: False)
        print(f"  train exit={code} · eventos={evt} · hosts_vistos={sorted(hosts)}")

        print("=== 3) descargar modelo ===")
        ssh_run.sftp_get(rc.SSH_HOST, rc.SSH_PORT["ray0"], rc.RAY_USER,
                         rc.REMOTE_DIR + "/gato_modelo.json", MODEL)
        m = json.load(open(MODEL, encoding="utf-8"))
        print(f"  modelo: {len(m.get('bestmove', {}))} estados, hosts(meta)={m.get('meta', {}).get('hosts')}")

        nodos_clu = len(_ready["nodes"])
        multi = len(hosts) >= 2
        ok = code == 0 and nodos_clu >= 3 and multi and evt["train_done"] == 1
        print(f"RESULTADO: clúster={nodos_clu} nodos · tareas repartidas en {sorted(hosts)} · "
              + ("✅ MULTINODO OK" if ok else "⚠️ revisar"))
        return 0 if ok else 1
    finally:
        print("=== 4) apagado ===")
        try:
            rc.shutdown(emit)
        except Exception as exc:
            print("  shutdown error:", exc)


if __name__ == "__main__":
    raise SystemExit(main())
