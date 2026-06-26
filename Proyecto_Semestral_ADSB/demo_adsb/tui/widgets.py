"""Widgets custom del dashboard: WorkerPanel, ClusterFlow, GlobalProgress, SpeedupCard."""

import time
from collections import deque

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import RichLog, Static

BLUE = "#004E9A"
GREEN = "#7AB830"
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# Animacion de "datos viajando" en ClusterFlow
TRAVEL = 0.9    # segundos que tarda un paquete en cruzar el carril
LANE = 14       # ancho del carril (chars)
SPARK = "▁▂▃▄▅▆▇█"


class WorkerPanel(Vertical):
    """Panel de una VM: metricas (spinner, chunks, ocupacion, chunk actual) + salida real (tail)."""

    def __init__(self, worker_name: str, **kw):
        super().__init__(**kw)
        self.worker_name = worker_name
        self.chunks = 0
        self.busy_seconds = 0.0
        self.current = "—"
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
        bar = "█" * min(self.chunks, 28)
        text = Text.from_markup(
            f"[bold {color}]{spin}[/] estado: [bold]{self.state}[/]\n"
            f"chunks: [bold {GREEN}]{self.chunks}[/]   ocupado: {self.busy_seconds:.2f}s\n"
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
    """Flujo coordinador<->workers con PAQUETES que viajan en tiempo real:
    verde = tarea saliente (COORD->worker), azul = resultado entrante (worker->COORD).
    Pie con sparkline de throughput (chunks/s)."""

    def __init__(self, workers, **kw):
        super().__init__("", **kw)
        self._wnames = list(workers)
        self.chunks = {w: 0 for w in self._wnames}
        self.counts = {"task": 0, "result": 0}
        self.active = set()
        self.spin = 0
        self.task_pkts = {w: deque() for w in self._wnames}    # timestamps de envio
        self.result_pkts = {w: deque() for w in self._wnames}
        self._spark = deque(maxlen=24)
        self._last_result = 0
        self._tick_accum = 0

    def on_mount(self):
        self.border_title = " flujo del cluster · datos en vivo "

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
        for w in self._wnames:                       # podar paquetes que ya llegaron
            for q in (self.task_pkts[w], self.result_pkts[w]):
                while q and now - q[0] >= TRAVEL:
                    q.popleft()
        self._tick_accum += 1
        if self._tick_accum >= 10:                   # ~1 muestra/s de throughput
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
        lines = [f"[bold {BLUE}]╔════════════════════╗[/]",
                 f"[bold {BLUE}]║ COORDINADOR (host) ║[/]",
                 f"[bold {BLUE}]╚════════════════════╝[/]",
                 ""]
        for w in self._wnames:
            spin = SPIN[self.spin % len(SPIN)] if w in self.active else "[dim]•[/]"
            task_lane = self._lane(self.task_pkts[w], "▸", GREEN)
            res_lane = self._lane(self.result_pkts[w], "◂", "#3fa7ff", reverse=True)
            lines.append(f"  [dim]tarea [/]{task_lane} [bold]{w}[/] {spin}  "
                         f"[{GREEN}]●{self.chunks.get(w, 0)}[/]")
            lines.append(f"  [dim]result[/]{res_lane}")
        lines += ["",
                  f"  [dim]msgs[/] task=[bold]{self.counts['task']}[/] "
                  f"result=[bold]{self.counts['result']}[/]  "
                  f"[dim]activos[/] [bold]{len(self.active)}[/]",
                  f"  [dim]throughput[/] {self._sparkline()} [dim]ch/s[/]"]
        return Text.from_markup("\n".join(lines))


class GlobalProgress(Static):
    """Barra de progreso global con shimmer animado (chunks completados / total)."""

    def __init__(self, **kw):
        super().__init__("", **kw)
        self.done = 0
        self.total = 0
        self.frame = 0

    def on_mount(self):
        self.border_title = " progreso "
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
