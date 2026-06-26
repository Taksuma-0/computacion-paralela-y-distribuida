"""Tail por SSH de /tmp/worker_agent.log de cada worker -> bus (vm_stdout).
Es la "salida real de la VM" que el TUI muestra en el panel de cada nodo."""

import time

import paramiko

from . import events as ev
from .cluster_control import KEY_PATH


def tail_worker(worker_name: str, ssh_port: int, emit, stop_flag):
    """Bucle de tail -F del log del agente. `stop_flag()` -> True corta limpio.
    Reintenta la conexion si se cae mientras no se pida parar."""
    while not stop_flag():
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            cli.connect("127.0.0.1", port=ssh_port, username="root", key_filename=KEY_PATH,
                        timeout=8, banner_timeout=8, auth_timeout=8,
                        look_for_keys=False, allow_agent=False)
            chan = cli.get_transport().open_session()
            chan.settimeout(0.0)  # no bloqueante
            chan.exec_command("tail -n 25 -F /tmp/worker_agent.log 2>/dev/null")
            buf = b""
            while not stop_flag():
                if chan.recv_ready():
                    data = chan.recv(8192)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        line = raw.decode("utf-8", "replace").rstrip()
                        if line and "escuchando en" not in line:
                            emit({"kind": ev.VM_STDOUT, "worker": worker_name, "line": line})
                elif chan.exit_status_ready() and not chan.recv_ready():
                    break
                else:
                    time.sleep(0.2)
            try:
                chan.close()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            try:
                cli.close()
            except Exception:
                pass
        if not stop_flag():
            time.sleep(2.0)  # reintentar conexion
