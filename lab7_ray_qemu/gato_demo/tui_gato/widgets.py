"""Widgets del dashboard de entrenamiento Ray: WorkerPanel, ClusterFlow,
GlobalProgress, SpeedupCard y LearningCurve. Reutilizados del orquestador QEMU
y adaptados al vocabulario de Ray (tareas/rollouts/generaciones)."""

import time
from collections import deque

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import RichLog, Static

BLUE = "#004E9A"
GREEN = "#7AB830"
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

TRAVEL = 0.9    # segundos que tarda un paquete en cruzar el carril
LANE = 14       # ancho del carril (chars)
SPARK = "▁▂▃▄▅▆▇█"


class WorkerPanel(Vertical):
    """Panel de una tarea Ray: métricas (spinner, rollouts, ocupación, gen actual)
    + salida real del worker."""

    def __init__(self, worker_name: str, **kw):
        super().__init__(**kw)
        self.worker_name = worker_name
        self.chunks = 0
        self.busy_seconds = 0.0
        self.current = "—"
        self.host = ""
        self.state = "esperando"   # esperando | listo | trabajando | caido
        self.spin = 0

    def compose(self):
        yield Static("", id=f"m-{self.worker_name}", classes="metrics")
        yield RichLog(id=f"log-{self.worker_name}", max_lines=200, wrap=False,
                      highlight=False, markup=False)

    def on_mount(self):
        self.border_title = f" {self.worker_name} "
        self.refresh_metrics()

    def refresh_metrics(self):
        active = self.state == "trabajando"
        spin = SPIN[self.spin % len(SPIN)] if active else "•"
        color = GREEN if active else (BLUE if self.state in ("listo",) else "#6e7681")
        bar = "█" * min(self.chunks, 24)
        host = f" [dim]@{self.host}[/]" if self.host else ""
        text = Text.from_markup(
            f"[bold {color}]{spin}[/] estado: [bold]{self.state}[/]{host}\n"
            f"rollouts: [bold {GREEN}]{self.chunks}[/]   ocupado: {self.busy_seconds:.2f}s\n"
            f"[{GREEN}]{bar}[/]\n"
            f"[dim]actual:[/] {self.current}"
        )
        try:
            self.query_one(f"#m-{self.worker_name}", Static).update(text)
        except Exception:
            pass

    def append_line(self, line: str):
        try:
            self.query_one(f"#log-{self.worker_name}", RichLog).write(line)
        except Exception:
            pass

    def set_state(self, state: str):
        self.state = state
        self.remove_class("busy", "down")
        if state == "trabajando":
            self.add_class("busy")
        elif state == "caido":
            self.add_class("down")
        self.refresh_metrics()

    def reset(self):
        self.chunks = 0
        self.busy_seconds = 0.0
        self.current = "—"
        self.set_state("esperando")
        try:
            self.query_one(f"#log-{self.worker_name}", RichLog).clear()
        except Exception:
            pass


class ClusterFlow(Static):
    """Flujo driver<->tareas Ray con PAQUETES que viajan en tiempo real:
    verde = rollout saliente (driver->tarea), azul = parcial entrante (tarea->driver)."""

    def __init__(self, workers, **kw):
        super().__init__("", **kw)
        self._wnames = list(workers)
        self.chunks = {w: 0 for w in self._wnames}
        self.counts = {"task": 0, "result": 0}
        self.active = set()
        self.spin = 0
        self.task_pkts = {w: deque() for w in self._wnames}
        self.result_pkts = {w: deque() for w in self._wnames}
        self._spark = deque(maxlen=24)
        self._last_result = 0
        self._tick_accum = 0

    def on_mount(self):
        self.border_title = " flujo Ray · rollouts en vivo "

    def on_assigned(self, worker):
        if worker in self.chunks:
            self.counts["task"] += 1
            self.active.add(worker)
            self.task_pkts[worker].append(time.time())

    def on_done(self, worker):
        if worker in self.chunks:
            self.counts["result"] += 1
            self.chunks[worker] += 1
            self.active.discard(worker)
            self.result_pkts[worker].append(time.time())

    def drop(self, worker):
        self.active.discard(worker)

    def tick(self):
        self.spin += 1
        now = time.time()
        for w in self._wnames:
            for q in (self.task_pkts[w], self.result_pkts[w]):
                while q and now - q[0] >= TRAVEL:
                    q.popleft()
        self._tick_accum += 1
        if self._tick_accum >= 10:
            self._tick_accum = 0
            self._spark.append(self.counts["result"] - self._last_result)
            self._last_result = self.counts["result"]
        self.refresh()

    def reset(self):
        self.chunks = {w: 0 for w in self._wnames}
        self.counts = {"task": 0, "result": 0}
        self.active = set()
        self.task_pkts = {w: deque() for w in self._wnames}
        self.result_pkts = {w: deque() for w in self._wnames}
        self._spark.clear()
        self._last_result = 0
        self._tick_accum = 0
        self.refresh()

    def _lane(self, pkts, glyph, color, reverse=False):
        now = time.time()
        cells = ["[dim]·[/]"] * LANE
        for ts in pkts:
            age = now - ts
            if 0 <= age < TRAVEL:
                pos = int(age / TRAVEL * (LANE - 1))
                if reverse:
                    pos = LANE - 1 - pos
                cells[pos] = f"[bold {color}]{glyph}[/]"
        return "".join(cells)

    def _sparkline(self):
        if not self._spark:
            return "[dim]" + SPARK[0] * 16 + "[/]"
        mx = max(self._spark) or 1
        return "".join(f"[{GREEN}]{SPARK[int(v / mx * (len(SPARK) - 1))]}[/]"
                       for v in list(self._spark)[-16:])

    def render(self):
        lines = [f"[bold {BLUE}]╔═══════════════════════╗[/]",
                 f"[bold {BLUE}]║ ENTRENADOR (driver Ray)║[/]",
                 f"[bold {BLUE}]╚═══════════════════════╝[/]",
                 ""]
        for w in self._wnames:
            spin = SPIN[self.spin % len(SPIN)] if w in self.active else "[dim]•[/]"
            task_lane = self._lane(self.task_pkts[w], "▸", GREEN)
            res_lane = self._lane(self.result_pkts[w], "◂", "#3fa7ff", reverse=True)
            lines.append(f"  [dim]rollout[/]{task_lane} [bold]{w}[/] {spin}  "
                         f"[{GREEN}]●{self.chunks.get(w, 0)}[/]")
            lines.append(f"  [dim]parcial[/]{res_lane}")
        lines += ["",
                  f"  [dim]msgs[/] rollout=[bold]{self.counts['task']}[/] "
                  f"parcial=[bold]{self.counts['result']}[/]  "
                  f"[dim]activos[/] [bold]{len(self.active)}[/]",
                  f"  [dim]throughput[/] {self._sparkline()} [dim]rollouts/s[/]"]
        return Text.from_markup("\n".join(lines))


class GlobalProgress(Static):
    """Barra de progreso de generaciones con shimmer animado."""

    def __init__(self, **kw):
        super().__init__("", **kw)
        self.done = 0
        self.total = 0
        self.frame = 0

    def on_mount(self):
        self.border_title = " generaciones "
        self._redraw()

    def update_progress(self, done, total):
        self.done, self.total = done, total
        self._redraw()

    def tick(self):
        self.frame += 1
        self._redraw()

    def _redraw(self):
        width = 40
        frac = (self.done / self.total) if self.total else 0.0
        filled = int(frac * width)
        shimmer = (self.frame % filled) if filled else -1
        cells = []
        for i in range(width):
            if i < filled:
                cells.append("[bold #c6f78a]█[/]" if i == shimmer else f"[{GREEN}]█[/]")
            else:
                cells.append("[dim]░[/]")
        bar = "".join(cells)
        self.update(Text.from_markup(
            f"{bar}  [bold]{self.done}[/]/[bold]{self.total}[/]  ({frac * 100:4.0f}%)"))

    def reset(self):
        self.done = 0
        self.total = 0
        self.frame = 0
        self._redraw()


class SpeedupCard(Static):
    """Tarjeta de speedup (verde si >1, naranja si <1)."""

    def on_mount(self):
        self.border_title = " speedup "
        self.update_speedup(None, None, None)

    def update_speedup(self, speedup, elapsed, baseline):
        if speedup is None:
            self.update(Text.from_markup("[dim]—[/]"))
            return
        color = GREEN if speedup >= 1 else "#d29922"
        self.update(Text.from_markup(
            f"[bold {color}]{speedup:.2f}x[/]\n[dim]{elapsed:.1f}s vs {baseline:.1f}s[/]"
        ))

    def reset(self):
        self.update_speedup(None, None, None)


class LearningCurve(Static):
    """Curva de aprendizaje (% de no-derrota) que sube generación a generación."""

    ROWS = 6
    MAXW = 48

    def __init__(self, **kw):
        super().__init__("", **kw)
        self.total = 0
        self.pts = []

    def on_mount(self):
        self.border_title = " curva de aprendizaje · % no-derrota "
        self._redraw()

    def set_total(self, total):
        self.total = total
        self._redraw()

    def add(self, pt):
        self.pts.append(pt)
        self._redraw()

    def reset(self, total=0):
        self.total = total
        self.pts = []
        self._redraw()

    def _redraw(self):
        width = min(max(self.total, len(self.pts), 1), self.MAXW)
        vals = [p.get("nonloss", 0.0) or 0.0 for p in self.pts][-width:]
        lines = []
        for r in range(self.ROWS, 0, -1):
            thr = r / self.ROWS
            row = "".join(f"[{GREEN}]█[/]" if v >= thr - 1e-9 else "[dim]·[/]" for v in vals)
            pad = "[dim]·[/]" * (width - len(vals))
            lines.append(f"[dim]{int(thr * 100):3d}%[/] " + row + pad)
        lines.append("[dim]     " + ("─" * width) + "[/]")
        if self.pts:
            last = self.pts[-1]
            lines.append(
                f"     gen [bold]{last.get('gen', '?')}[/]/{max(self.total - 1, 0)}  "
                f"no-derrota [bold {GREEN}]{(last.get('nonloss', 0) or 0) * 100:.0f}%[/]  "
                f"[dim]gana {(last.get('win', 0) or 0) * 100:.0f}% · "
                f"empata {(last.get('draw', 0) or 0) * 100:.0f}% · "
                f"pierde {(last.get('loss', 0) or 0) * 100:.0f}%[/]")
        else:
            lines.append("     [dim]esperando entrenamiento…[/]")
        self.update(Text.from_markup("\n".join(lines)))
