"""Corazon del TUI: App Textual con dos pantallas (Launcher + Dashboard).

- El EventBus (events.py) recibe eventos de hilos productores (boot de VMs, job del
  coordinador, tail SSH, stdout de agentes locales) y la App los drena con un
  `set_interval` en el hilo del loop, actualizando los widgets.
- El backend (coordinator_generic.run_job, baseline_seq.run_baseline) es stdlib puro;
  esta capa (Textual/paramiko) es una herramienta del host, aislada del orquestador.
- El arranque del cluster es SIMPLE: una linea de estado + log en el menu (sin pantalla
  animada aparte). Las VMs arrancan headless con WHPX (rapido y sin congelar la TUI).

Lanzar como paquete:  cd orquestador ; python -m tui   (o ./run_tui.ps1)
"""

import json
import os
import subprocess
import sys
import threading
import time

# --- backend (orquestador/) accesible aunque cambie el CWD ---
HERE = os.path.dirname(os.path.abspath(__file__))      # .../orquestador/tui
ORQ_DIR = os.path.dirname(HERE)                         # .../orquestador
if ORQ_DIR not in sys.path:
    sys.path.insert(0, ORQ_DIR)

from rich.text import Text
from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Select, Static

from . import cluster_control as cc
from . import events as ev
from .banner import BLUE, GREEN, banner_markup, header_markup
from .payloads import TASKS
from .ssh_tail import tail_worker
from .widgets import ClusterFlow, GlobalProgress, SpeedupCard, WorkerPanel

import baseline_seq
import coordinator_generic

# clave -> info de tarea
TASK_BY_KEY = {t[0]: {"label": t[1], "file": t[2], "payload": t[3]} for t in TASKS}

# modo -> topologia. "local": agentes en el host (sin QEMU). "cluster": VMs nodo1/nodo2.
MODES = {
    "local": {"label": "Local (host, sin QEMU)", "workers_file": "workers.local.json", "deploy": False},
    "cluster": {"label": "Cluster QEMU (nodo1/nodo2)", "workers_file": "workers.host.json", "deploy": True},
}

AMBER = "#d29922"
RED = "#b3261e"


def _short_chunk(chunk, n=42):
    try:
        s = json.dumps(chunk, ensure_ascii=False, default=str)
    except Exception:
        s = str(chunk)
    return s if len(s) <= n else s[:n - 1] + "~"


# ============================================================
# Agentes locales (modo Local): subprocesos worker_agent.py + captura de su stdout
# ============================================================

class LocalAgents:
    """Lanza/reutiliza worker_agent.py en el host y reenvia su stdout como VM_STDOUT,
    para que los paneles muestren la 'salida real' igual que el tail SSH del cluster."""

    def __init__(self, ports_by_worker, emit, cwd):
        self.ports = ports_by_worker          # {"local1": 9001, ...}
        self.emit = emit
        self.cwd = cwd
        self.procs = {}                       # worker -> Popen (solo los que arrancamos)
        self._stop = False

    def ensure(self):
        for worker, port in self.ports.items():
            if cc.port_open(port):
                self.emit({"kind": ev.LOG, "msg": f"{worker}: agente activo en :{port} (reuso)"})
                continue
            try:
                proc = subprocess.Popen(
                    [sys.executable, "worker_agent.py", "--port", str(port), "--task-dir", "tasks"],
                    cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                )
            except Exception as exc:
                self.emit({"kind": ev.ERROR, "msg": f"{worker}: no pude lanzar agente: {exc}"})
                continue
            self.procs[worker] = proc
            threading.Thread(target=self._pump, args=(worker, proc), daemon=True).start()
            self.emit({"kind": ev.LOG, "msg": f"{worker}: agente local lanzado en :{port}"})
        deadline = time.time() + 8
        while time.time() < deadline and not all(cc.port_open(p) for p in self.ports.values()):
            time.sleep(0.2)

    def _pump(self, worker, proc):
        try:
            for line in proc.stdout:
                if self._stop:
                    break
                line = line.rstrip()
                if line and "escuchando en" not in line:
                    self.emit({"kind": ev.VM_STDOUT, "worker": worker, "line": line})
        except Exception:
            pass

    def stop(self):
        self._stop = True
        for proc in list(self.procs.values()):
            try:
                proc.terminate()
            except Exception:
                pass
        self.procs.clear()


# ============================================================
# Pantalla 1: Launcher
# ============================================================

class LauncherScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield Static(Text.from_markup(banner_markup()), id="banner")
        with Vertical(id="menu"):
            with Horizontal(classes="row"):
                yield Label("Tarea:  ")
                yield Select([(t[1], t[0]) for t in TASKS], value=TASKS[0][0],
                             allow_blank=False, id="task")
            with Horizontal(classes="row"):
                yield Label("Modo:   ")
                yield Select([(MODES["local"]["label"], "local"),
                              (MODES["cluster"]["label"], "cluster")],
                             value="local", allow_blank=False, id="mode")
            with Horizontal(classes="row"):
                yield Label("Payload:")
                yield Input(value=TASKS[0][3], id="payload")
            with Horizontal(classes="row"):
                yield Button("⏻ Despertar clúster QEMU", id="btn-boot", classes="-go")
                yield Button("▶ Ejecutar", id="btn-run")
                yield Button("⏼ Apagar clúster", id="btn-shutdown", classes="-danger")
                yield Button("Salir", id="btn-quit")
        yield Static("clúster:  (sin sondear)", id="cluster-status")
        yield RichLog(id="launch-log", markup=False, highlight=False, max_lines=300)
        yield Footer()

    def on_select_changed(self, event):
        if event.select.id == "task":
            info = TASK_BY_KEY.get(event.value)
            if info:
                try:
                    self.query_one("#payload", Input).value = info["payload"]
                except Exception:
                    pass

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "btn-run":
            self.app.start_run(self._cfg())
        elif bid == "btn-boot":
            self.app.boot_cluster(self._cfg())
        elif bid == "btn-shutdown":
            self.app.shutdown_cluster()
        elif bid == "btn-quit":
            self.app.action_quit()

    def _cfg(self):
        return {
            "mode": self.query_one("#mode", Select).value,
            "task_key": self.query_one("#task", Select).value,
            "payload": self.query_one("#payload", Input).value,
        }


# ============================================================
# Pantalla 2: Dashboard
# ============================================================

class DashboardScreen(Screen):
    # "q" aqui = VOLVER al launcher (no salir de la app); solo el launcher cierra la app.
    BINDINGS = [
        Binding("q", "back", "Volver"),
        Binding("escape", "back", "Volver", show=False),
        Binding("b", "back", "Volver", show=False),
        Binding("a", "apagar", "Apagar clúster"),
    ]

    def __init__(self, workers, mode_label, task_label):
        super().__init__()
        self.worker_names = list(workers)
        self.mode_label = mode_label
        self.task_label = task_label
        self.panels = {}
        self.flow = None
        self.progress = None
        self.speed = None
        self.elog = None

    def compose(self):
        yield Header(show_clock=True)
        yield Static(Text.from_markup(header_markup(f"· {self.mode_label} · {self.task_label}")),
                     id="dash-header")
        with Horizontal(id="dash-body"):
            with Vertical(id="workers-col"):
                for w in self.worker_names:
                    p = WorkerPanel(w, id=f"panel-{w}")
                    self.panels[w] = p
                    yield p
            self.flow = ClusterFlow(self.worker_names)
            yield self.flow
        with Horizontal(id="bottom"):
            self.progress = GlobalProgress()
            yield self.progress
            self.speed = SpeedupCard()
            yield self.speed
        self.elog = RichLog(id="event-log", markup=False, highlight=False, max_lines=500)
        yield self.elog
        yield Footer()

    def action_back(self):
        self.app.leave_dashboard()

    def action_apagar(self):
        self.app.shutdown_cluster()


# ============================================================
# App
# ============================================================

class ClusterTUI(App):
    CSS_PATH = "theme.tcss"
    TITLE = "UTEM · Cluster QEMU"
    BINDINGS = [("q", "quit", "Salir")]

    def __init__(self):
        super().__init__()
        self.bus = ev.EventBus()
        self.launcher = LauncherScreen()
        self.dash = None
        self._job_workers = []
        self._worker_ports = {}
        self._worker_ssh = {}
        self.total_chunks = 0
        self.done_chunks = 0
        self._job_t0 = None
        self.vm_states = {}
        self._cluster_busy = False      # hay un arranque/apagado de cluster en curso
        self.local_agents = None
        self._tail_stop = False
        self._tail_threads = []
        self._job_running = False

    def get_default_screen(self):
        return self.launcher

    def on_mount(self):
        self.set_interval(0.1, self._drain)

    # ---------- acciones disparadas por la UI ----------

    def start_run(self, cfg):
        if self._job_running:
            self._log("Ya hay un job en ejecucion; espera a que termine.")
            return
        mode = cfg["mode"]
        mc = MODES[mode]
        wf = os.path.join(ORQ_DIR, mc["workers_file"])
        try:
            wlist = json.load(open(wf, encoding="utf-8"))["workers"]
        except Exception as exc:
            self._log(f"No pude leer {mc['workers_file']}: {exc}")
            return
        self._job_workers = [w["name"] for w in wlist]
        self._worker_ports = {w["name"]: w["task_port"] for w in wlist}
        self._worker_ssh = {w["name"]: w.get("ssh_port") for w in wlist}
        info = TASK_BY_KEY[cfg["task_key"]]
        self.dash = DashboardScreen(self._job_workers, mc["label"], info["label"])
        self.push_screen(self.dash)
        self._job_running = True
        threading.Thread(target=self._run_job, args=(mode, info["file"], cfg["payload"]),
                         daemon=True).start()

    def boot_cluster(self, cfg=None):
        """Arranca el cluster SIN pantalla animada: solo log + linea de estado (liviano)."""
        if self._cluster_busy:
            self._log("Ya hay un arranque/apagado en curso…")
            return
        self._cluster_busy = True
        self._log("Despertando clúster QEMU (headless, WHPX)… mira la línea de estado.")
        threading.Thread(target=cc.boot_cluster, args=(self.bus.put,),
                         kwargs={"deadline": 150}, daemon=True).start()

    def shutdown_cluster(self):
        if self._cluster_busy:
            self._log("Ya hay un arranque/apagado en curso…")
            return
        self._cluster_busy = True
        self._tail_stop = True
        if self.local_agents:
            self.local_agents.stop()
            self.local_agents = None
        self._log("Apagando clúster QEMU…")
        threading.Thread(target=cc.shutdown_cluster, args=(self.bus.put,), daemon=True).start()

    def leave_dashboard(self):
        """Volver del dashboard al launcher, parando tails/agentes (no cierra la app)."""
        self._tail_stop = True
        if self.local_agents:
            self.local_agents.stop()
            self.local_agents = None
        if self.dash is not None:
            try:
                self.pop_screen()
            except Exception:
                pass
            self.dash = None

    def action_quit(self):
        self._tail_stop = True
        if self.local_agents:
            self.local_agents.stop()
        self.exit()

    # ---------- hilos de trabajo (solo hacen bus.put) ----------

    def _run_job(self, mode, task_file_rel, payload_str):
        emit = self.bus.put
        mc = MODES[mode]
        task_path = os.path.join(ORQ_DIR, task_file_rel)
        try:
            payload = json.loads(payload_str)
        except Exception as exc:
            emit({"kind": ev.ERROR, "msg": f"Payload JSON invalido: {exc}"})
            self._job_running = False
            return

        if mode == "local":
            if self.local_agents is None:
                self.local_agents = LocalAgents(self._worker_ports, emit, ORQ_DIR)
            self.local_agents.ensure()
        else:
            self._start_tails()

        emit({"kind": ev.LOG, "msg": "Midiendo baseline secuencial (host)..."})
        baseline_elapsed = None
        try:
            base = baseline_seq.run_baseline(task_path, payload)
            baseline_elapsed = base["elapsed"]
            emit({"kind": ev.LOG, "msg": f"Baseline host: {baseline_elapsed:.3f}s"})
        except Exception as exc:
            emit({"kind": ev.ERROR, "msg": f"Baseline fallo: {exc}"})

        wf = os.path.join(ORQ_DIR, mc["workers_file"])
        try:
            coordinator_generic.run_job(
                task_path, payload, wf,
                deploy=mc["deploy"],
                ssh_key=(cc.KEY_PATH if mc["deploy"] else None),
                baseline=baseline_elapsed,
                on_event=emit,
                log=lambda m: emit({"kind": ev.LOG, "msg": m}),
                location="host",
            )
        except Exception as exc:
            emit({"kind": ev.ERROR, "msg": f"Job fallo: {exc}"})
        finally:
            self._job_running = False

    def _start_tails(self):
        self._tail_stop = False
        for w in self._job_workers:
            port = self._worker_ssh.get(w)
            if not port:
                continue
            t = threading.Thread(target=tail_worker,
                                 args=(w, port, self.bus.put, lambda: self._tail_stop),
                                 daemon=True)
            t.start()
            self._tail_threads.append(t)

    # ---------- drenado del bus y despacho a widgets (hilo del loop) ----------

    def _drain(self):
        for e in self.bus.drain():
            try:
                self._handle(e)
            except Exception:
                pass
        d = self.dash
        if d is not None and d.is_mounted and d.flow is not None:
            try:
                d.flow.tick()
                d.progress.tick()
                for p in d.panels.values():
                    if p.state == "trabajando":
                        p.spin += 1
                        p.refresh_metrics()
                if self._job_t0 is not None:
                    el = time.monotonic() - self._job_t0
                    rate = self.done_chunks / el if el > 0 else 0.0
                    self._set_header(f"· ⏱ {el:4.1f}s · {rate:4.1f} ch/s")
            except Exception:
                pass

    def _handle(self, e):
        kind = e.get("kind")

        if kind == ev.LOG:
            self._log(e.get("msg", ""))
        elif kind == ev.ERROR:
            self._log("[ERROR] " + e.get("msg", ""))
        elif kind == ev.VM_STATE:
            self._set_vm_state(e.get("node"), e.get("state"))
        elif kind == ev.VM_STDOUT:
            p = self._panel(e.get("worker"))
            if p:
                p.append_line(e.get("line", ""))
        elif kind == ev.CLUSTER_READY:
            self._cluster_busy = False
            ready = e.get("ready", [])
            failed = e.get("failed", [])
            if failed:
                self._log(f"Clúster PARCIAL: listos {ready} · sin SSH {failed}")
            else:
                self._log(f"✓ Clúster listo ({len(ready)}/3). Ya puedes Ejecutar.")
        elif kind == ev.CLUSTER_DOWN:
            self._cluster_busy = False
            self._log("Clúster apagado.")

        elif kind == "job_start":
            self.total_chunks = e.get("n_chunks", 0)
            self.done_chunks = 0
            self._job_t0 = time.monotonic()
            self._reset_dashboard()
            self._progress(0, self.total_chunks)
            self._log(f"JOB {e.get('job_id')} | {e.get('task_name')} | "
                      f"{self.total_chunks} chunks | workers {e.get('workers')}")
        elif kind == "worker_ready":
            p = self._panel(e.get("worker"))
            if p:
                p.set_state("listo")
            self._log(f"{e.get('worker')} EN LINEA")
        elif kind in ("worker_down", "worker_dropped"):
            w = e.get("worker")
            p = self._panel(w)
            if p:
                p.set_state("caido")
            if self.dash and self.dash.flow:
                self.dash.flow.drop(w)
            self._log(f"{w} {'DOWN' if kind == 'worker_down' else 'cayo a mitad'}: {e.get('reason', '')}")
        elif kind == "worker_repair":
            self._log(f"{e.get('worker')} reparado por SSH")
        elif kind == "chunk_assigned":
            w = e.get("worker")
            if self.dash and self.dash.flow:
                self.dash.flow.on_assigned(w)
            p = self._panel(w)
            if p:
                p.current = _short_chunk(e.get("chunk"))
                p.set_state("trabajando")
        elif kind == "chunk_done":
            w = e.get("worker")
            secs = e.get("seconds") or 0.0
            if self.dash and self.dash.flow:
                self.dash.flow.on_done(w)
            p = self._panel(w)
            if p:
                p.chunks += 1
                p.busy_seconds += secs
                p.refresh_metrics()
            self.done_chunks += 1
            self._progress(self.done_chunks, self.total_chunks)
        elif kind == "chunk_retry":
            self._log(f"reintento chunk {e.get('cid')} en {e.get('worker')}: {e.get('reason', '')}")
        elif kind == "chunk_infra_fail":
            self._log(f"infra-fail chunk {e.get('cid')} en {e.get('worker')}: {e.get('error', '')}")
        elif kind == "chunk_abandoned":
            self.done_chunks += 1
            self._progress(self.done_chunks, self.total_chunks)
            self._log(f"chunk {e.get('cid')} ABANDONADO tras {e.get('attempts')} intentos")
        elif kind == "job_done":
            rec = e.get("record", {})
            sp, el, bl = rec.get("speedup"), rec.get("elapsed"), rec.get("elapsed_baseline")
            if self.dash and self.dash.speed and sp is not None and el is not None and bl:
                self.dash.speed.update_speedup(sp, el, bl)
            if self.dash:
                for p in self.dash.panels.values():
                    if p.state == "trabajando":
                        p.set_state("listo")
            self._job_t0 = None
            _fin_el = rec.get("elapsed") or 0.0
            _fin_rate = (rec.get("completed", self.done_chunks) / _fin_el) if _fin_el else 0.0
            self._set_header(f"· ✓ {_fin_el:.1f}s · {_fin_rate:.1f} ch/s")
            self._log(f"FIN: {rec.get('completed')}/{rec.get('n_chunks')} OK, "
                      f"{rec.get('retries')} reintentos, {len(rec.get('failed_chunks', []))} abandonados, "
                      f"{rec.get('elapsed')}s" + (f", speedup {sp}x" if sp else ""))
            if rec.get("task_name") == "task_adsb":
                self._adsb_report(rec)

    # ---------- helpers de UI ----------

    def _panel(self, worker):
        d = self.dash
        if d is not None and d.is_mounted:
            return d.panels.get(worker)
        return None

    def _progress(self, done, total):
        d = self.dash
        if d is not None and d.is_mounted and d.progress is not None:
            try:
                d.progress.update_progress(done, total)
            except Exception:
                pass

    def _reset_dashboard(self):
        d = self.dash
        if not (d is not None and d.is_mounted):
            return
        try:
            for p in d.panels.values():
                p.reset()
            d.flow.reset()
            d.progress.reset()
            d.speed.reset()
        except Exception:
            pass

    def _set_vm_state(self, node, state):
        """Actualiza la LINEA de estado del cluster en el launcher (liviano, sin animacion)."""
        if node:
            self.vm_states[node] = state
        icons = {"ready": f"[{GREEN}]✓[/]", "booting": f"[{AMBER}]⏳[/]",
                 "apagando": f"[{AMBER}]⏳[/]", "failed": f"[{RED}]✗[/]", "off": "[dim]○[/]"}
        parts = []
        for n in ("nodo0", "nodo1", "nodo2"):
            st = self.vm_states.get(n, "-")
            parts.append(f"{icons.get(st, '[dim]·[/]')} [bold]{n}[/]")
        ready = sum(1 for n in ("nodo0", "nodo1", "nodo2") if self.vm_states.get(n) == "ready")
        try:
            self.launcher.query_one("#cluster-status", Static).update(
                Text.from_markup("clúster   " + "     ".join(parts) + f"      [dim]({ready}/3)[/]"))
        except Exception:
            pass
        p = self._panel(node)
        if p:
            mapping = {"booting": "esperando", "ready": "listo", "failed": "caido", "off": "esperando"}
            p.set_state(mapping.get(state, "esperando"))

    def _set_header(self, live):
        d = self.dash
        if d is not None and d.is_mounted:
            base = f"· {d.mode_label} · {d.task_label} "
            try:
                d.query_one("#dash-header", Static).update(
                    Text.from_markup(header_markup(base + live)))
            except Exception:
                pass

    def _adsb_report(self, record):
        """Genera y abre el HTML del reporte ADS-B (hilo daemon: no congela la TUI).
        Usa el `record` EN MEMORIA (el .json se escribe despues, evita la carrera)."""
        def work():
            try:
                import adsb_report  # perezoso: ORQ_DIR ya esta en sys.path
                out = os.path.join(ORQ_DIR, "results", f"{record.get('job_id')}.html")
                adsb_report.build_html(record, out)
                self.bus.put({"kind": ev.LOG, "msg": f"HTML ADS-B generado: {out}"})
                try:
                    os.startfile(out)  # Windows: abre en el navegador por defecto
                except Exception:
                    import webbrowser
                    webbrowser.open("file://" + out)
            except Exception as exc:
                self.bus.put({"kind": ev.ERROR, "msg": f"No pude generar/abrir HTML ADS-B: {exc}"})
        threading.Thread(target=work, daemon=True).start()

    def _log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        target = None
        d = self.dash
        if d is not None and d.is_mounted and d.elog is not None:
            target = d.elog
        else:
            try:
                target = self.launcher.query_one("#launch-log", RichLog)
            except Exception:
                target = None
        if target is not None:
            try:
                target.write(line)
            except Exception:
                pass


def main():
    ClusterTUI().run()


if __name__ == "__main__":
    main()
