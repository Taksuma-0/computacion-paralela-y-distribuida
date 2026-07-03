"""Ciclo de vida de las VMs QEMU desde el TUI: arrancar, sondear readiness por LLAVE SSH,
y apagar. Funciones puras (sin Textual), testeables aparte. Cada una recibe `emit`
(callable(dict)) para reportar al bus."""

import logging
import os
import socket
import subprocess
import time

import paramiko

from . import events as ev

# paramiko loguea a stderr los intentos fallidos de SSH mientras la VM aun arranca
# (banner errors, conexiones reseteadas). Son benignos (los capturamos), pero
# corromperian la pantalla del TUI: los silenciamos.
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

# Configurable por entorno; defaults del laboratorio.
KEY_PATH = os.environ.get("QEMU_CLUSTER_KEY", r"C:\Users\welin\.ssh\qemu_cluster")
QEMU_PROC = "qemu-system-x86_64w"

# El TUI arranca QEMU con VENTANA VISIBLE (display SDL): las 3 ventanas de QEMU aparecen
# solas cuando parten los nodos (prueba en vivo de que se usa QEMU). Ya NO hay animacion
# pesada ni se tocan/ordenan/mueven las ventanas (eso colgaba la TUI); simplemente aparecen.
# Si en tu equipo las ventanas molestaran, la versión sin ventanas: QEMU_HEADLESS=1.
QEMU_BASE = os.environ.get("QEMU_BASE", r"C:\qemu-cluster-demo")
QEMU_EXE = os.environ.get("QEMU_EXE", os.path.join(QEMU_BASE, "qemu", "qemu-system-x86_64w.exe"))
DISKS_DIR = os.environ.get("QEMU_DISKS", os.path.join(QEMU_BASE, "disks"))
HEADLESS = os.environ.get("QEMU_HEADLESS", "0") == "1"

# Popen por nodo de las VMs que ARRANCO el TUI (para apagado escalonado por-nodo).
_VM_PROCS = {}

# Acelerador QEMU, elegido y cacheado una vez (whpx si hay hardware; si no, tcg).
_ACCEL = None

# nodo -> puerto SSH reenviado en el host
NODES = {"nodo0": 2220, "nodo1": 2221, "nodo2": 2222}
# workers que procesan en modo host (coordinador en el host)
WORKER_NODES = {"nodo1": 2221, "nodo2": 2222}

# nodo -> (disco qcow2, reglas hostfwd). Misma topologia que el start-all.ps1 original.
VM_SPECS = {
    "nodo0": ("nodo0.qcow2", ["tcp:127.0.0.1:2220-:22"]),
    "nodo1": ("nodo1.qcow2", ["tcp:127.0.0.1:2221-:22", "tcp:127.0.0.1:9001-:9000"]),
    "nodo2": ("nodo2.qcow2", ["tcp:127.0.0.1:2222-:22", "tcp:127.0.0.1:9002-:9000"]),
}


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ssh_ready(ssh_port: int, timeout: float = 10.0) -> bool:
    """True si se puede autenticar por llave en root@127.0.0.1:ssh_port."""
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect("127.0.0.1", port=ssh_port, username="root", key_filename=KEY_PATH,
                    timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                    look_for_keys=False, allow_agent=False)
        return True
    except Exception:
        return False
    finally:
        try:
            cli.close()
        except Exception:
            pass


def _qemu_accel():
    """Elige el acelerador UNA vez (cacheado): WHPX (hardware) si esta disponible -> arranque
    rapido (~10-15s) y SIN el panic 'IO-APIC + timer doesn't work' que da TCG (emulacion
    por software, su IO-APIC es incompleto). Si WHPX no esta, cae a TCG. Override: QEMU_ACCEL."""
    global _ACCEL
    if _ACCEL is not None:
        return _ACCEL
    env = os.environ.get("QEMU_ACCEL")
    if env:
        _ACCEL = env
        return _ACCEL
    _ACCEL = "tcg"
    try:
        # sonda: arranca QEMU con WHPX pausado (-S); si el acelerador inicializa, sigue vivo.
        probe = subprocess.Popen(
            [QEMU_EXE, "-accel", "whpx", "-machine", "pc", "-display", "none", "-m", "64M", "-S"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.0)
        if probe.poll() is None:        # sigue vivo => WHPX inicializo OK
            _ACCEL = "whpx"
        try:
            probe.terminate()
        except Exception:
            pass
    except Exception:
        pass
    return _ACCEL


def boot_cluster(emit, deadline: float = 220.0):
    """Arranca las VMs que falten (display SDL, WHPX si hay) y sondea readiness por SSH.
    Si el cluster YA esta activo, lo reconoce AL INSTANTE (no re-arranca ni re-anima).
    NO toca/ordena las ventanas: aparecen solas (manipularlas colgaba Windows Terminal).
    Emite vm_state por nodo y cluster_ready al terminar."""
    if not os.path.isfile(KEY_PATH):
        emit({"kind": ev.ERROR, "msg": f"No existe la llave SSH: {KEY_PATH}"})
        emit({"kind": ev.CLUSTER_READY, "ready": [], "failed": list(NODES)})
        return

    # FAST PATH: si las 3 ya estan arriba y con SSH, reconocer al instante (sin re-arrancar).
    if all(port_open(p) for p in NODES.values()):
        if all(ssh_ready(p) for p in NODES.values()):
            for n in NODES:
                emit({"kind": ev.VM_STATE, "node": n, "state": "ready"})
            emit({"kind": ev.LOG, "msg": "El clúster ya estaba activo."})
            emit({"kind": ev.CLUSTER_READY, "ready": list(NODES), "failed": []})
            return
        emit({"kind": ev.LOG, "msg": "Las VMs ya estaban arriba; sondeando SSH..."})
    else:
        if not os.path.isfile(QEMU_EXE):
            emit({"kind": ev.ERROR, "msg": f"No existe el ejecutable QEMU: {QEMU_EXE}"})
            emit({"kind": ev.CLUSTER_READY, "ready": [], "failed": list(NODES)})
            return
        accel = _qemu_accel()
        emit({"kind": ev.LOG, "msg": f"Lanzando QEMU [accel={accel}]" +
              (" headless..." if HEADLESS else " (ventanas SDL)...")})
        for node, (disk_name, fwd) in VM_SPECS.items():
            if port_open(NODES[node]):
                continue  # ese nodo ya esta arriba
            disk = os.path.join(DISKS_DIR, disk_name)
            if not os.path.isfile(disk):
                emit({"kind": ev.ERROR, "msg": f"No existe el disco: {disk}"})
                continue
            hostfwd = ",".join("hostfwd=" + rule for rule in fwd)
            # -accel whpx (hardware) si esta: arranque rapido y SIN el panic IO-APIC de TCG;
            # cae a tcg si no hay WHPX. display SDL: ventana propia (sin consola extra).
            args = [QEMU_EXE, "-m", "256M", "-smp", "1", "-name", node,
                    "-accel", accel,
                    "-drive", f"file={disk},format=qcow2,if=virtio",
                    "-netdev", f"user,id=net0,{hostfwd}",
                    "-device", "virtio-net-pci,netdev=net0",
                    "-display", "none" if HEADLESS else "sdl"]
            try:
                _VM_PROCS[node] = subprocess.Popen(
                    args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as exc:
                emit({"kind": ev.ERROR, "msg": f"No pude lanzar {node}: {exc}"})
                continue
            emit({"kind": ev.LOG, "msg": f"{node}: QEMU lanzado"})
            time.sleep(3)   # escalonar: menos contencion en el arranque en frio de varias VMs

    for node in NODES:
        emit({"kind": ev.VM_STATE, "node": node, "state": "booting"})

    end = time.time() + deadline
    pending = dict(NODES)
    while pending and time.time() < end:
        for node, port in list(pending.items()):
            if ssh_ready(port):
                emit({"kind": ev.VM_STATE, "node": node, "state": "ready"})
                emit({"kind": ev.LOG, "msg": f"{node}: SSH listo (llave)"})
                del pending[node]
        if pending:
            time.sleep(2)
    for node in pending:
        emit({"kind": ev.VM_STATE, "node": node, "state": "failed"})
        emit({"kind": ev.ERROR, "msg": f"{node}: no respondió SSH a tiempo"})

    emit({"kind": ev.CLUSTER_READY,
          "ready": [n for n in NODES if n not in pending], "failed": list(pending)})


def shutdown_cluster(emit):
    """Apaga las VMs de forma ESCALONADA (cierra las ventanas una a una) y emite
    cluster_down al terminar."""
    emit({"kind": ev.LOG, "msg": "Apagando VMs..."})
    for node in NODES:
        emit({"kind": ev.VM_STATE, "node": node, "state": "apagando"})
        proc = _VM_PROCS.pop(node, None)
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        time.sleep(0.45)   # escalonado para que se vea cerrar una a una
        emit({"kind": ev.VM_STATE, "node": node, "state": "off"})
        emit({"kind": ev.LOG, "msg": f"{node}: apagado"})
    # fallback: matar cualquier QEMU restante (VMs que ya estaban antes del TUI)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Process {QEMU_PROC} -ErrorAction SilentlyContinue | Stop-Process -Force"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except Exception as exc:
        emit({"kind": ev.ERROR, "msg": f"Error apagando: {exc}"})
    emit({"kind": ev.LOG, "msg": "VMs apagadas."})
    emit({"kind": ev.CLUSTER_DOWN})
