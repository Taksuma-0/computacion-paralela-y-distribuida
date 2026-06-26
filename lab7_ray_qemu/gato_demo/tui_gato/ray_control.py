"""Ciclo de vida de las VMs Debian de Ray desde la TUI: arrancar QEMU, sondear SSH por
LLAVE, iniciar Ray, y apagar. Soporta:

- **Single-node** (ray0): rápido, 1 VM (head = worker).
- **Multinodo** (ray0+ray1+ray2): clúster Ray real. Como la NAT de QEMU aísla las VMs y el
  multicast no funciona en Windows, se conecta una **2ª NIC** de cada VM a un HUB Ethernet en
  el host (netbus.Hub) → LAN interna 10.10.0.0/24. Luego ray0 = head y ray1/ray2 = workers.

Acceso por LLAVE propia (sin contraseña), inyectada en los qcow2 con preparar_acceso_ray.ps1.
La red interna se configura por SSH como root (la llave también está en root)."""

import os
import socket
import subprocess
import time

from . import events as ev
from . import netbus
from . import ssh_run

# --- rutas / QEMU ---
QEMU_BASE = os.environ.get("QEMU_BASE", r"C:\qemu-cluster-demo")
QEMU_EXE = os.environ.get("QEMU_EXE", os.path.join(QEMU_BASE, "qemu", "qemu-system-x86_64w.exe"))
DEBIAN_DISKS = os.environ.get("RAY_DISKS", os.path.join(QEMU_BASE, "debian_disks"))
HEADLESS = os.environ.get("QEMU_HEADLESS", "0") == "1"

# --- topología ---
SSH_HOST = "127.0.0.1"
RAY_USER = os.environ.get("RAY_USER", "ray")
DASH_PORT = int(os.environ.get("RAY_DASH_PORT", "8265"))
DASHBOARD_URL = f"http://127.0.0.1:{DASH_PORT}"
HUB_PORT = int(os.environ.get("RAY_HUB_PORT", "12340"))
RAM_MB = os.environ.get("RAY_VM_MEM", "1280")    # por VM en multinodo
RAM_MB_SINGLE = os.environ.get("RAY_VM_MEM_SINGLE", "2048")

# ray0 es head (single y multi). SSH del host -> :22 de cada VM.
SSH_PORT = {"ray0": 2320, "ray1": 2321, "ray2": 2322}
NAT_MAC = {"ray0": "52:54:00:ca:60:10", "ray1": "52:54:00:ca:60:11", "ray2": "52:54:00:ca:60:12"}
INT_MAC = {"ray0": "52:54:00:ca:70:10", "ray1": "52:54:00:ca:70:11", "ray2": "52:54:00:ca:70:12"}
INT_IP = {"ray0": "10.10.0.10", "ray1": "10.10.0.11", "ray2": "10.10.0.12"}
HEAD_IP = INT_IP["ray0"]

REMOTE_DIR = "/home/ray/ray-demo"
RAY_ENV_ACTIVATE = ". ~/ray-env/bin/activate"

_VM_PROCS = {}      # node -> Popen (las que arrancó la TUI)
_HUB = None         # netbus.Hub (solo en multinodo)
_ACCEL = None


def disk_path(node):
    return os.path.join(DEBIAN_DISKS, f"{node}.qcow2")


def disks_present(nodes=("ray0",)) -> bool:
    return all(os.path.isfile(disk_path(n)) for n in nodes)


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _qemu_accel():
    global _ACCEL
    if _ACCEL is not None:
        return _ACCEL
    env = os.environ.get("QEMU_ACCEL")
    if env:
        _ACCEL = env
        return _ACCEL
    _ACCEL = "tcg"
    try:
        probe = subprocess.Popen(
            [QEMU_EXE, "-accel", "whpx", "-machine", "pc", "-display", "none", "-m", "64M", "-S"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.0)
        if probe.poll() is None:
            _ACCEL = "whpx"
        try:
            probe.terminate()
        except Exception:
            pass
    except Exception:
        pass
    return _ACCEL


def _launch_vm(node, mem, dash=False, with_internal=False):
    """Lanza QEMU para `node`. NIC1 = NAT (SSH + dashboard en ray0). Si with_internal,
    agrega NIC2 conectada al hub Ethernet del host (LAN interna VM↔VM)."""
    accel = _qemu_accel()
    fwd = f"hostfwd=tcp:127.0.0.1:{SSH_PORT[node]}-:22"
    if dash:
        fwd += f",hostfwd=tcp:127.0.0.1:{DASH_PORT}-:8265"
    args = [QEMU_EXE, "-m", str(mem), "-smp", "2", "-name", node, "-accel", accel,
            "-drive", f"file={disk_path(node)},format=qcow2,if=virtio",
            "-netdev", f"user,id=net0,{fwd}",
            "-device", f"virtio-net-pci,netdev=net0,mac={NAT_MAC[node]}"]
    if with_internal:
        args += ["-netdev", f"socket,id=lan,connect=127.0.0.1:{HUB_PORT}",
                 "-device", f"virtio-net-pci,netdev=lan,mac={INT_MAC[node]}"]
    if HEADLESS:
        args += ["-display", "none"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _VM_PROCS[node] = proc
    return proc


def _wait_ssh(node, deadline) -> bool:
    end = time.time() + deadline
    while time.time() < end:
        if ssh_run.ssh_ready(SSH_HOST, SSH_PORT[node], RAY_USER, timeout=5):
            return True
        time.sleep(2)
    return False


def _config_red_interna(emit, node) -> bool:
    """Configura la 2ª NIC (LAN interna) por SSH como root: detecta la NIC por su MAC y
    le asigna la IP interna fija."""
    mac = INT_MAC[node]
    ip = INT_IP[node]
    cmd = (
        f'mac="{mac}"; '
        'ifc=$(grep -il "$mac" /sys/class/net/*/address | head -1 | sed "s#/sys/class/net/##; s#/address##"); '
        f'ip addr flush dev "$ifc" 2>/dev/null; ip addr add {ip}/24 dev "$ifc"; ip link set "$ifc" up; '
        'echo "$ifc"'
    )
    try:
        code, out, err = ssh_run.run_command(SSH_HOST, SSH_PORT[node], "root", cmd, timeout=30)
        if code == 0:
            emit({"kind": ev.LOG, "msg": f"{node}: red interna {ip} en {out.strip()}"})
            return True
        emit({"kind": ev.ERROR, "msg": f"{node}: no pude configurar red interna: {err.strip()}"})
        return False
    except Exception as exc:
        emit({"kind": ev.ERROR, "msg": f"{node}: SSH root falló para red interna: {exc}"})
        return False


# ============================================================
# SINGLE-NODE (ray0)
# ============================================================

def boot_ray0(emit, deadline: float = 240.0) -> bool:
    if not disks_present(("ray0",)):
        emit({"kind": ev.ERROR, "msg": f"No existe {disk_path('ray0')}."})
        emit({"kind": ev.ERROR, "msg": "Extrae primero: .\\extraer_debian_ray.ps1"})
        emit({"kind": ev.VM_STATE, "node": "ray0", "state": "failed"})
        return False
    if port_open(SSH_PORT["ray0"]) and ssh_run.ssh_ready(SSH_HOST, SSH_PORT["ray0"], RAY_USER):
        emit({"kind": ev.VM_STATE, "node": "ray0", "state": "ready"})
        emit({"kind": ev.LOG, "msg": "ray0 ya estaba activa (autentica por llave)."})
        return True
    if not os.path.isfile(QEMU_EXE):
        emit({"kind": ev.ERROR, "msg": f"No existe QEMU: {QEMU_EXE}"})
        return False
    emit({"kind": ev.LOG, "msg": f"Lanzando QEMU ray0 [{RAM_MB_SINGLE}MB]…"})
    _launch_vm("ray0", RAM_MB_SINGLE, dash=True, with_internal=False)
    emit({"kind": ev.VM_STATE, "node": "ray0", "state": "booting"})
    if _wait_ssh("ray0", deadline):
        emit({"kind": ev.VM_STATE, "node": "ray0", "state": "ready"})
        emit({"kind": ev.LOG, "msg": "ray0: SSH listo (por llave)."})
        return True
    emit({"kind": ev.VM_STATE, "node": "ray0", "state": "failed"})
    emit({"kind": ev.ERROR, "msg": "ray0: no respondió SSH (¿inyectaste la llave?)."})
    return False


def start_ray_head(emit, head_ip="127.0.0.1") -> bool:
    emit({"kind": ev.LOG, "msg": f"Iniciando Ray head en ray0 (ip {head_ip})…"})
    cmd = (f"{RAY_ENV_ACTIVATE} && (ray stop >/dev/null 2>&1 || true) && "
           f"ray start --head --node-ip-address={head_ip} --port=6379 "
           f"--dashboard-host=0.0.0.0 --dashboard-port=8265")
    try:
        code, out, err = ssh_run.run_command(SSH_HOST, SSH_PORT["ray0"], RAY_USER, cmd, timeout=120)
    except Exception as exc:
        emit({"kind": ev.ERROR, "msg": f"No pude iniciar Ray: {exc}"})
        return False
    if code != 0:
        for line in (out + err).splitlines():
            if line.strip():
                emit({"kind": ev.LOG, "msg": "ray0> " + line.strip()})
        emit({"kind": ev.ERROR, "msg": f"`ray start --head` terminó con código {code}."})
        return False
    emit({"kind": ev.LOG, "msg": "ray0: Ray head iniciado."})
    return True


def levantar(emit, deadline: float = 240.0):
    """Botón 'Levantar Ray' en modo single-node."""
    if not boot_ray0(emit, deadline=deadline):
        emit({"kind": ev.CLUSTER_READY, "ready": [], "failed": ["ray0"], "dashboard": None})
        return
    ok = start_ray_head(emit, head_ip="127.0.0.1")
    if ok:
        _ray_status(emit)
        emit({"kind": ev.RAY_HEAD_READY, "dashboard": DASHBOARD_URL})
        emit({"kind": ev.LOG, "msg": f"✓ Ray listo (1 nodo). Dashboard: {DASHBOARD_URL}"})
    emit({"kind": ev.CLUSTER_READY, "ready": ["ray0"] if ok else [],
          "failed": [] if ok else ["ray0"], "dashboard": DASHBOARD_URL if ok else None})


# ============================================================
# MULTINODO (ray0 + ray1 + ray2)
# ============================================================

def _ray_status(emit):
    try:
        _, out, _ = ssh_run.run_command(SSH_HOST, SSH_PORT["ray0"], RAY_USER,
                                        f"{RAY_ENV_ACTIVATE} && ray status", timeout=60)
        for line in out.splitlines():
            if line.strip():
                emit({"kind": ev.LOG, "msg": "ray status> " + line.strip()})
        nodes = out.count(" node_") + out.count("\nnode_") + out.count("1 node_")
        return out
    except Exception:
        return ""


def levantar_multinodo(emit, nodos=("ray0", "ray1", "ray2"), deadline: float = 300.0):
    """Botón 'Levantar Ray' en modo multinodo: hub + boot de N VMs + red interna +
    ray head (ray0) + workers (ray1/ray2)."""
    global _HUB
    nodos = list(nodos)

    if not disks_present(nodos):
        faltan = [n for n in nodos if not os.path.isfile(disk_path(n))]
        emit({"kind": ev.ERROR, "msg": f"Faltan discos: {faltan}. Corre .\\extraer_debian_ray.ps1"})
        emit({"kind": ev.CLUSTER_READY, "ready": [], "failed": nodos, "dashboard": None})
        return

    # 1) hub Ethernet en el host (LAN interna VM↔VM)
    if _HUB is None:
        _HUB = netbus.Hub(port=HUB_PORT).start()
        emit({"kind": ev.LOG, "msg": f"Hub Ethernet del clúster en 127.0.0.1:{HUB_PORT}"})

    # 2) boot de cada VM (2 NICs: NAT + hub)
    emit({"kind": ev.LOG, "msg": f"Lanzando {len(nodos)} VMs [{RAM_MB}MB c/u]…"})
    for n in nodos:
        if port_open(SSH_PORT[n]) and ssh_run.ssh_ready(SSH_HOST, SSH_PORT[n], RAY_USER):
            emit({"kind": ev.LOG, "msg": f"{n}: ya estaba activa."})
        else:
            _launch_vm(n, RAM_MB, dash=(n == "ray0"), with_internal=True)
        emit({"kind": ev.VM_STATE, "node": n, "state": "booting"})

    # 3) esperar SSH en cada una
    listos = []
    for n in nodos:
        if _wait_ssh(n, deadline):
            emit({"kind": ev.VM_STATE, "node": n, "state": "ready"})
            listos.append(n)
        else:
            emit({"kind": ev.VM_STATE, "node": n, "state": "failed"})
            emit({"kind": ev.ERROR, "msg": f"{n}: no respondió SSH a tiempo."})
    if "ray0" not in listos:
        emit({"kind": ev.CLUSTER_READY, "ready": [], "failed": nodos, "dashboard": None})
        return

    # 4) red interna (root SSH) en cada nodo listo
    emit({"kind": ev.LOG, "msg": "Configurando red interna VM↔VM (10.10.0.0/24)…"})
    con_red = [n for n in listos if _config_red_interna(emit, n)]

    # 5) Ray: head en ray0 con IP interna; workers en el resto
    if not start_ray_head(emit, head_ip=HEAD_IP):
        emit({"kind": ev.CLUSTER_READY, "ready": [], "failed": nodos, "dashboard": None})
        return
    workers_ok = ["ray0"]
    for n in con_red:
        if n == "ray0":
            continue
        emit({"kind": ev.LOG, "msg": f"Uniendo {n} al head ({HEAD_IP}:6379)…"})
        cmd = (f"{RAY_ENV_ACTIVATE} && (ray stop >/dev/null 2>&1 || true) && "
               f"ray start --address={HEAD_IP}:6379 --node-ip-address={INT_IP[n]}")
        try:
            code, out, err = ssh_run.run_command(SSH_HOST, SSH_PORT[n], RAY_USER, cmd, timeout=120)
            if code == 0:
                workers_ok.append(n)
                emit({"kind": ev.LOG, "msg": f"{n}: unido al clúster."})
            else:
                emit({"kind": ev.ERROR, "msg": f"{n}: `ray start --address` código {code}: {err.strip()[:200]}"})
        except Exception as exc:
            emit({"kind": ev.ERROR, "msg": f"{n}: error uniendo: {exc}"})

    # 6) estado del clúster
    time.sleep(2)
    _ray_status(emit)
    emit({"kind": ev.RAY_HEAD_READY, "dashboard": DASHBOARD_URL})
    emit({"kind": ev.LOG, "msg": f"✓ Clúster Ray con {len(workers_ok)} nodo(s): {workers_ok}. "
          f"Dashboard: {DASHBOARD_URL}"})
    emit({"kind": ev.CLUSTER_READY, "ready": workers_ok,
          "failed": [n for n in nodos if n not in workers_ok], "dashboard": DASHBOARD_URL})


# ============================================================
# APAGADO (single o multi)
# ============================================================

def shutdown(emit):
    global _HUB
    emit({"kind": ev.LOG, "msg": "Deteniendo Ray y apagando VMs…"})
    # ray stop en cada nodo alcanzable
    for n in list(SSH_PORT):
        if port_open(SSH_PORT[n]):
            try:
                ssh_run.run_command(SSH_HOST, SSH_PORT[n], RAY_USER,
                                    f"{RAY_ENV_ACTIVATE} && ray stop || true", timeout=30)
            except Exception:
                pass
    for n in list(_VM_PROCS):
        emit({"kind": ev.VM_STATE, "node": n, "state": "apagando"})
        proc = _VM_PROCS.pop(n, None)
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        emit({"kind": ev.VM_STATE, "node": n, "state": "off"})
    # matar QEMU restante (VMs no lanzadas por esta TUI)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process qemu-system-x86_64w -ErrorAction SilentlyContinue | Stop-Process -Force"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except Exception:
        pass
    if _HUB is not None:
        try:
            _HUB.stop()
        except Exception:
            pass
        _HUB = None
    emit({"kind": ev.CLUSTER_DOWN})
    emit({"kind": ev.LOG, "msg": "VMs apagadas."})
