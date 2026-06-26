"""Corazón de la TUI Ray: App Textual con 3 pantallas (Launcher + TrainDashboard + Play).

- El EventBus (events.py) recibe eventos de hilos productores (boot de ray0, entrenamiento
  por SSH o local) y la App los drena con un set_interval, actualizando los widgets.
- Modo 'vm': Ray DENTRO de la VM Debian (ray0) por SSH (llave propia). Modo 'local': ensayo,
  entrena en el host como subproceso (mismo flujo visual), sin VM.
- Reusa el diseño del orquestador QEMU (tema, escudo, WorkerPanel, ClusterFlow, SpeedupCard).

Lanzar:  cd ray_qemu/gato_demo ; python -m tui_gato   (o ./run_tui_gato.ps1)
"""

import json
import os
import subprocess
import sys
import threading
import time

from rich.text import Text
from textual.app import App
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Select, Static

from . import events as ev
from . import gato_core as gc
from . import ray_control as rc
from . import ssh_run
from .banner import BLUE, GREEN, banner_markup, header_markup
from .widgets import ClusterFlow, GlobalProgress, LearningCurve, SpeedupCard, WorkerPanel

HERE = os.path.dirname(os.path.abspath(__file__))      # .../gato_demo/tui_gato
DEMO_DIR = os.path.dirname(HERE)                        # .../gato_demo
SCRIPT = os.path.join(DEMO_DIR, "gato_rl_ray.py")
MODEL_PATH = os.path.join(DEMO_DIR, "gato_modelo.json")

AMBER = "#d29922"
RED = "#b3261e"

MODES = {
    "vm": "VM Debian · Ray sobre QEMU",
    "local": "Local · ensayo (sin VM)",
}


# ============================================================
# Pantalla 1: Launcher
# ============================================================

class LauncherScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield Static(Text.from_markup(banner_markup()), id="banner")
        with Vertical(id="menu"):
            with Horizontal(classes="row"):
                yield Label("Generaciones:")
                yield Input(value="15", id="gens")
            with Horizontal(classes="row"):
                yield Label("Partidas/tarea:")
                yield Input(value="1500", id="games")
            with Horizontal(classes="row"):
                yield Label("Tareas Ray:")
                yield Input(value="6", id="tasks")
            with Horizontal(classes="row"):
                yield Label("Modo:")
                yield Select([(MODES["vm"], "vm"), (MODES["local"], "local")],
                             value="vm", allow_blank=False, id="mode")
            with Horizontal(classes="row"):
                yield Label("Nodos:")
                yield Select([("3 (multinodo Ray)", "3"), ("1 (single, rápido)", "1")],
                             value="3", allow_blank=False, id="nodos")
            with Horizontal(classes="row"):
                yield Label("Benchmark:")
                yield Select([("no", "no"), ("sí (mide speedup)", "si")],
                             value="no", allow_blank=False, id="bench")
            with Horizontal(classes="row"):
                yield Button("⏻ Levantar Ray", id="btn-boot", classes="-go")
                yield Button("▶ Entrenar", id="btn-train")
                yield Button("🎮 Jugar", id="btn-play")
                yield Button("⏼ Apagar", id="btn-shutdown", classes="-danger")
                yield Button("Salir", id="btn-quit")
        yield Static("ray0:  (sin sondear)", id="cluster-status")
        yield RichLog(id="launch-log", markup=False, highlight=False, max_lines=400)
        yield Footer()

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "btn-boot":
            self.app.boot_action(self._cfg())
        elif bid == "btn-train":
            self.app.train_action(self._cfg())
        elif bid == "btn-play":
            self.app.play_action()
        elif bid == "btn-shutdown":
            self.app.shutdown_action(self._cfg())
        elif bid == "btn-quit":
            self.app.action_quit()

    def _cfg(self):
        def _int(wid, default):
            try:
                return max(1, int(self.query_one(wid, Input).value))
            except Exception:
                return default
        return {
            "gens": _int("#gens", 15),
            "games": _int("#games", 1500),
            "tasks": _int("#tasks", 4),
            "mode": self.query_one("#mode", Select).value,
            "nodos": int(self.query_one("#nodos", Select).value),
            "bench": self.query_one("#bench", Select).value == "si",
        }


# ============================================================
# Pantalla 2: Train Dashboard
# ============================================================

class TrainScreen(Screen):
    BINDINGS = [
        Binding("q", "back", "Volver"),
        Binding("escape", "back", "Volver", show=False),
    ]

    def __init__(self, tasks: int, mode_label: str):
        super().__init__()
        self.task_names = [f"w{i}" for i in range(tasks)]
        self.mode_label = mode_label
        self.panels = {}
        self.flow = None
        self.curve = None
        self.progress = None
        self.speed = None
        self.elog = None

    def compose(self):
        yield Header(show_clock=True)
        yield Static(Text.from_markup(header_markup(f"· {self.mode_label}")), id="dash-header")
        with Horizontal(id="dash-body"):
            with Vertical(id="workers-col"):
                for w in self.task_names:
                    p = WorkerPanel(w, id=f"panel-{w}")
                    self.panels[w] = p
                    yield p
            with Vertical(id="right-col"):
                self.flow = ClusterFlow(self.task_names)
                yield self.flow
                self.curve = LearningCurve()
                yield self.curve
        with Horizontal(id="bottom"):
            self.progress = GlobalProgress()
            yield self.progress
            self.speed = SpeedupCard()
            yield self.speed
        self.elog = RichLog(id="event-log", markup=False, highlight=False, max_lines=500)
        yield self.elog
        yield Footer()

    def action_back(self):
        self.app.leave_train()


# ============================================================
# Pantalla 3: Play
# ============================================================

class PlayScreen(Screen):
    BINDINGS = [
        Binding("q", "back", "Volver"),
        Binding("escape", "back", "Volver", show=False),
    ]

    def __init__(self, model: dict):
        super().__init__()
        self.bestmove = model.get("bestmove", {}) if model else {}
        meta = (model or {}).get("meta", {})
        self.subt = (f"{meta.get('estados_aprendidos', '?')} estados · "
                     f"{meta.get('partidas_totales', '?')} partidas · "
                     f"{', '.join(meta.get('hosts', []) or ['?'])}")
        self.board = gc.VACIO
        self.human = "O"
        self.over = False
        self.sc = {"w": 0, "d": 0, "l": 0}

    def compose(self):
        yield Header(show_clock=True)
        yield Static(Text.from_markup(
            f"[bold {GREEN}]🎮 Juega contra el modelo entrenado de forma distribuida[/]\n"
            f"[dim]{self.subt}[/]"), id="play-header")
        yield Static("", id="play-status")
        with Grid(id="board-grid"):
            for i in range(9):
                yield Button(" ", id=f"cell-{i}", classes="cell")
        with Horizontal(id="play-controls"):
            yield Button("Tú: ❌ X (parte)", id="btn-x")
            yield Button("Tú: ⭕ O", id="btn-o")
            yield Button("Reiniciar", id="btn-reset")
            yield Button("Volver", id="btn-back")
        yield Static("", id="score")
        yield Footer()

    def on_mount(self):
        self.new_game()

    def on_button_pressed(self, event):
        bid = event.button.id or ""
        if bid.startswith("cell-"):
            self.play_human(int(bid.split("-")[1]))
        elif bid == "btn-x":
            self.human = "X"
            self.new_game()
        elif bid == "btn-o":
            self.human = "O"
            self.new_game()
        elif bid == "btn-reset":
            self.new_game()
        elif bid == "btn-back":
            self.app.leave_play()

    # --- lógica de juego ---
    def new_game(self):
        self.board = gc.VACIO
        self.over = False
        self.update_board()
        if gc.turno(self.board) != self.human:
            self.set_timer(0.35, self.ai_move)

    def play_human(self, i):
        if self.over or self.board[i] != "." or gc.turno(self.board) != self.human:
            return
        self.board = gc.aplicar(self.board, i, self.human)
        self.update_board()
        if gc.ganador(self.board) is not None:
            self.finish()
        else:
            self.set_timer(0.35, self.ai_move)

    def ai_move(self):
        if self.over or gc.ganador(self.board) is not None:
            return
        m = gc.jugada_ia(self.board, self.bestmove)
        self.board = gc.aplicar(self.board, m, gc.turno(self.board))
        self.update_board()
        if gc.ganador(self.board) is not None:
            self.finish()

    def finish(self):
        self.over = True
        w = gc.ganador(self.board)
        if w == "draw":
            self.sc["d"] += 1
        elif w == self.human:
            self.sc["w"] += 1
        else:
            self.sc["l"] += 1
        self.update_board()

    def update_board(self):
        win = gc.linea_ganadora(self.board) or ()
        for i in range(9):
            try:
                btn = self.query_one(f"#cell-{i}", Button)
            except Exception:
                continue
            c = self.board[i]
            btn.label = "✕" if c == "X" else ("◯" if c == "O" else " ")
            btn.remove_class("x", "o", "win")
            if c == "X":
                btn.add_class("x")
            elif c == "O":
                btn.add_class("o")
            if i in win:
                btn.add_class("win")
            btn.disabled = self.over or c != "."
        # estado
        w = gc.ganador(self.board)
        if w == "draw":
            st = "🤝 Empate"
        elif w:
            st = "🎉 ¡Ganaste!" if w == self.human else "😼 Ganó el gato"
        else:
            st = "Tu turno" if gc.turno(self.board) == self.human else "Pensando…"
        try:
            self.query_one("#play-status", Static).update(Text.from_markup(f"[bold]{st}[/]"))
            self.query_one("#score", Static).update(Text.from_markup(
                f"Tú: [bold {GREEN}]{self.sc['w']}[/]    "
                f"Empates: [bold]{self.sc['d']}[/]    "
                f"Gato 😼: [bold {AMBER}]{self.sc['l']}[/]"))
        except Exception:
            pass

    def action_back(self):
        self.app.leave_play()


# ============================================================
# App
# ============================================================

class GatoRayTUI(App):
    CSS_PATH = "theme.tcss"
    TITLE = "UTEM · Ray · El gato que aprende"
    BINDINGS = [("q", "quit", "Salir")]

    def __init__(self):
        super().__init__()
        self.bus = ev.EventBus()
        self.launcher = LauncherScreen()
        self.train = None
        self._busy = False
        self._train_running = False
        self._stop = False
        self.total_gens = 0
        self.done_gens = 0
        self._train_t0 = None
        self.vm_states = {}
        self.dashboard = None

    def get_default_screen(self):
        return self.launcher

    def on_mount(self):
        self.set_interval(0.1, self._drain)

    # ---------- acciones de la UI ----------

    def boot_action(self, cfg):
        if cfg["mode"] == "local":
            self._log("Modo local (ensayo): no hay VM que levantar. Pulsa ▶ Entrenar.")
            return
        if self._busy:
            self._log("Ya hay una operación de clúster en curso…")
            return
        self._busy = True
        if cfg.get("nodos", 1) >= 2:
            n = cfg["nodos"]
            self._log(f"Levantando clúster Ray MULTINODO ({n} VMs)… aparecen {n} ventanas QEMU.")
            nodos = ("ray0", "ray1", "ray2")[:n]
            threading.Thread(target=rc.levantar_multinodo, args=(self.bus.put, nodos),
                             daemon=True).start()
        else:
            self._log("Levantando Ray en ray0 (single-node)… mira la ventana de QEMU.")
            threading.Thread(target=rc.levantar, args=(self.bus.put,), daemon=True).start()

    def train_action(self, cfg):
        if self._train_running:
            self._log("Ya hay un entrenamiento en curso.")
            return
        self.train = TrainScreen(cfg["tasks"], MODES[cfg["mode"]])
        self.push_screen(self.train)
        self._train_running = True
        self._stop = False
        if cfg["mode"] == "vm":
            threading.Thread(target=self._run_train_vm, args=(cfg,), daemon=True).start()
        else:
            threading.Thread(target=self._run_train_local, args=(cfg,), daemon=True).start()

    def play_action(self):
        if not os.path.isfile(MODEL_PATH):
            self._log("No hay modelo aún. Entrena primero (se baja gato_modelo.json).")
            return
        try:
            with open(MODEL_PATH, encoding="utf-8") as f:
                model = json.load(f)
        except Exception as exc:
            self._log(f"No pude leer el modelo: {exc}")
            return
        self.push_screen(PlayScreen(model))

    def shutdown_action(self, cfg):
        if cfg["mode"] == "local":
            self._log("Modo local: no hay VM que apagar.")
            return
        if self._busy:
            self._log("Ya hay una operación de clúster en curso…")
            return
        self._busy = True
        self._stop = True
        threading.Thread(target=rc.shutdown, args=(self.bus.put,), daemon=True).start()

    def leave_train(self):
        self._stop = True
        if self.train is not None:
            try:
                self.pop_screen()
            except Exception:
                pass
            self.train = None

    def leave_play(self):
        try:
            self.pop_screen()
        except Exception:
            pass

    def action_quit(self):
        self._stop = True
        self.exit()

    # ---------- hilos de entrenamiento (solo bus.put) ----------

    def _on_train_line(self, line):
        if line.startswith("EVT "):
            try:
                self.bus.put(json.loads(line[4:]))
                return
            except Exception:
                pass
        self.bus.put({"kind": ev.LOG, "msg": line})

    def _run_train_vm(self, cfg):
        emit = self.bus.put
        try:
            emit({"kind": ev.LOG, "msg": "Subiendo gato_rl_ray.py a ray0 por SFTP…"})
            ssh_run.sftp_put(rc.SSH_HOST, rc.SSH_PORT["ray0"], rc.RAY_USER,
                             SCRIPT, rc.REMOTE_DIR + "/gato_rl_ray.py")
        except Exception as exc:
            emit({"kind": ev.ERROR, "msg": f"SFTP falló: {exc}"})
            self._train_running = False
            return
        bench = " --benchmark" if cfg["bench"] else ""
        cmd = (f"{rc.RAY_ENV_ACTIVATE} && cd {rc.REMOTE_DIR} && "
               f"python gato_rl_ray.py {cfg['gens']} {cfg['games']} {cfg['tasks']} "
               f"--emit-events --modelo-salida gato_modelo.json{bench}")
        emit({"kind": ev.LOG, "msg": "Ejecutando entrenamiento Ray dentro de ray0…"})
        try:
            ssh_run.stream_command(rc.SSH_HOST, rc.SSH_PORT["ray0"], rc.RAY_USER,
                                   cmd, self._on_train_line, lambda: self._stop)
        except Exception as exc:
            emit({"kind": ev.ERROR, "msg": f"Entrenamiento falló: {exc}"})
            self._train_running = False
            return
        try:
            ssh_run.sftp_get(rc.SSH_HOST, rc.SSH_PORT["ray0"], rc.RAY_USER,
                             rc.REMOTE_DIR + "/gato_modelo.json", MODEL_PATH)
            emit({"kind": ev.LOG, "msg": "Modelo descargado. Pulsa 🎮 Jugar (q para volver)."})
        except Exception as exc:
            emit({"kind": ev.ERROR, "msg": f"No pude bajar el modelo: {exc}"})
        self._train_running = False

    def _run_train_local(self, cfg):
        emit = self.bus.put
        args = [sys.executable, SCRIPT, str(cfg["gens"]), str(cfg["games"]), str(cfg["tasks"]),
                "--emit-events", "--backend", "local",
                "--modelo-salida", MODEL_PATH, "--salida", os.path.join(DEMO_DIR, "gato.html")]
        if cfg["bench"]:
            args.append("--benchmark")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        emit({"kind": ev.LOG, "msg": "Modo local: entrenando en el host (ensayo, sin Ray)…"})
        try:
            proc = subprocess.Popen(args, cwd=DEMO_DIR, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                    errors="replace", bufsize=1, env=env)
        except Exception as exc:
            emit({"kind": ev.ERROR, "msg": f"No pude lanzar el entrenamiento: {exc}"})
            self._train_running = False
            return
        for line in proc.stdout:
            if self._stop:
                try:
                    proc.terminate()
                except Exception:
                    pass
                break
            self._on_train_line(line.rstrip())
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        emit({"kind": ev.LOG, "msg": "Entrenamiento (local) finalizado. Pulsa 🎮 Jugar."})
        self._train_running = False

    # ---------- drenado del bus ----------

    def _drain(self):
        for e in self.bus.drain():
            try:
                self._handle(e)
            except Exception:
                pass
        t = self.train
        if t is not None and t.is_mounted and t.flow is not None:
            try:
                t.flow.tick()
                t.progress.tick()
                for p in t.panels.values():
                    if p.state == "trabajando":
                        p.spin += 1
                        p.refresh_metrics()
                if self._train_t0 is not None:
                    el = time.monotonic() - self._train_t0
                    self._set_header(f"· ⏱ {el:4.1f}s · gen {self.done_gens}/{self.total_gens}")
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
            self._log(e.get("line", ""))
        elif kind == ev.CLUSTER_READY:
            self._busy = False
            self.dashboard = e.get("dashboard")
            if e.get("ready"):
                msg = "✓ Ray listo en ray0."
                if self.dashboard:
                    msg += f" Dashboard: {self.dashboard}"
                self._log(msg + " Ya puedes ▶ Entrenar.")
            else:
                self._log("No se pudo dejar Ray listo. Revisa la llave (preparar_acceso_ray.ps1) y recursos.")
        elif kind == ev.CLUSTER_DOWN:
            self._busy = False
            self._log("ray0 apagada.")
        elif kind == ev.RAY_HEAD_READY:
            self._log(f"Dashboard de Ray: {e.get('dashboard')}")

        elif kind == ev.TRAIN_START:
            self.total_gens = e.get("generaciones", 0)
            self.done_gens = 0
            self._train_t0 = time.monotonic()
            self._reset_train()
            t = self.train
            if t and t.is_mounted:
                t.curve.set_total(self.total_gens)
                t.progress.update_progress(0, self.total_gens)
            self._log(f"Entrenamiento: {self.total_gens} generaciones · "
                      f"{e.get('tareas')} tareas · {e.get('partidas_por_tarea')} partidas/tarea")
        elif kind == ev.GEN_START:
            pass
        elif kind == ev.CHUNK_ASSIGNED:
            w = f"w{e.get('worker')}"
            t = self.train
            if t and t.is_mounted:
                if t.flow:
                    t.flow.on_assigned(w)
                p = t.panels.get(w)
                if p:
                    p.current = f"gen {e.get('gen')}"
                    p.set_state("trabajando")
        elif kind == ev.CHUNK_DONE:
            w = f"w{e.get('worker')}"
            t = self.train
            if t and t.is_mounted:
                if t.flow:
                    t.flow.on_done(w)
                p = t.panels.get(w)
                if p:
                    p.chunks += 1
                    p.busy_seconds += e.get("seconds", 0.0) or 0.0
                    p.host = e.get("hostname", "")
                    p.set_state("listo")
                    p.append_line(f"rollout gen ok · {e.get('partidas')} partidas · "
                                  f"{e.get('seconds')}s @{e.get('hostname')}")
        elif kind == ev.GEN_DONE:
            self.done_gens = (e.get("gen", 0) or 0) + 1
            t = self.train
            if t and t.is_mounted:
                t.curve.add(e)
                t.progress.update_progress(self.done_gens, self.total_gens)
            self._log(f"gen {e.get('gen')}: no-derrota {(e.get('nonloss', 0) or 0) * 100:.1f}% "
                      f"(ε={e.get('epsilon')})")
        elif kind == ev.BENCHMARK:
            t = self.train
            if t and t.is_mounted and t.speed:
                t.speed.update_speedup(e.get("speedup"), e.get("tp"), e.get("t1"))
            self._log(f"Benchmark: speedup {e.get('speedup')}x · "
                      f"eficiencia {(e.get('eficiencia', 0) or 0) * 100:.0f}%")
        elif kind == ev.TRAIN_DONE:
            self._train_t0 = None
            meta = e.get("meta", {})
            t = self.train
            if t and t.is_mounted:
                for p in t.panels.values():
                    if p.state == "trabajando":
                        p.set_state("listo")
            self._log(f"FIN entrenamiento: no-derrota final {(e.get('nonloss', 0) or 0) * 100:.0f}% · "
                      f"{meta.get('partidas_totales')} partidas · {meta.get('segundos')}s")
        elif kind == ev.MODEL_READY:
            self._log(f"Modelo listo: {e.get('estados')} estados aprendidos.")

    # ---------- helpers de UI ----------

    def _reset_train(self):
        t = self.train
        if not (t and t.is_mounted):
            return
        try:
            for p in t.panels.values():
                p.reset()
            t.flow.reset()
            t.curve.reset(self.total_gens)
            t.progress.reset()
            t.speed.reset()
        except Exception:
            pass

    def _set_vm_state(self, node, state):
        if node:
            self.vm_states[node] = state
        icons = {"ready": f"[{GREEN}]✓[/]", "booting": f"[{AMBER}]⏳[/]",
                 "apagando": f"[{AMBER}]⏳[/]", "failed": f"[{RED}]✗[/]", "off": "[dim]○[/]"}
        parts = []
        for n in ("ray0", "ray1", "ray2"):
            if n in self.vm_states:
                ic = icons.get(self.vm_states[n], "[dim]·[/]")
                parts.append(f"{ic} [bold]{n}[/]")
        dash = f"   [dim]· {self.dashboard}[/]" if self.dashboard else ""
        linea = ("clúster   " + "    ".join(parts) + dash) if parts else "ray0:  (sin sondear)"
        try:
            self.launcher.query_one("#cluster-status", Static).update(Text.from_markup(linea))
        except Exception:
            pass

    def _set_header(self, live):
        t = self.train
        if t is not None and t.is_mounted:
            try:
                t.query_one("#dash-header", Static).update(
                    Text.from_markup(header_markup(f"· {t.mode_label} {live}")))
            except Exception:
                pass

    def _log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        target = None
        t = self.train
        if t is not None and t.is_mounted and t.elog is not None:
            target = t.elog
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
    GatoRayTUI().run()


if __name__ == "__main__":
    main()
