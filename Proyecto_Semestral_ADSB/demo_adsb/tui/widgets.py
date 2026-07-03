"""Widgets custom del dashboard: WorkerPanel, ClusterFlow, GlobalProgress, SpeedupCard."""

import math
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
# estados internos -> etiqueta de control aereo mostrada
STATE_LABEL = {"esperando": "en espera", "listo": "en línea",
               "trabajando": "escaneando", "caido": "fuera de línea"}


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
        self.border_title = f" SECTOR {self.worker_name} "
        self.refresh_metrics()

    def refresh_metrics(self):
        active = self.state == "trabajando"
        spin = SPIN[self.spin % len(SPIN)] if active else "•"
        color = GREEN if active else (BLUE if self.state in ("listo",) else "#6e7681")
        bar = "█" * min(self.chunks, 28)
        lab = STATE_LABEL.get(self.state, self.state)
        text = Text.from_markup(
            f"[bold {color}]{spin}[/] estado: [bold]{lab}[/]\n"
            f"trazas: [bold {GREEN}]{self.chunks}[/]   en antena: {self.busy_seconds:.2f}s\n"
            f"[{GREEN}]{bar}[/]\n"
            f"[dim]traza:[/] {self.current}"
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

    def flash(self):
        """Pulso breve del borde al completar una traza (feedback visual)."""
        self.add_class("flash")
        self.set_timer(0.45, lambda: self.remove_class("flash"))

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
        self.phase = ""

    def on_mount(self):
        self.border_title = " RADAR · torre ⇄ sectores · en vivo "

    def set_phase(self, phase):
        """Ilumina la fase activa del pipeline: split | run | merge."""
        self.phase = phase
        self.refresh()

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
        self.phase = ""
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
                tail = pos + 1 if reverse else pos - 1     # estela: una celda detras
                if 0 <= tail < LANE and cells[tail] == "[dim]·[/]":
                    cells[tail] = f"[{color}]·[/]"
                cells[pos] = f"[bold {color}]{glyph}[/]"
        return "".join(cells)

    def _sparkline(self):
        if not self._spark:
            return "[dim]" + SPARK[0] * 16 + "[/]"
        mx = max(self._spark) or 1
        return "".join(f"[{GREEN}]{SPARK[int(v / mx * (len(SPARK) - 1))]}[/]"
                       for v in list(self._spark)[-16:])

    def _ppi(self):
        """Mini-radar PPI en caracteres: anillos + barrido giratorio + blips por sector."""
        W, H, R = 25, 11, 10.0
        cx, cy = 12.0, 5.0
        theta = (self.spin * 7) % 360
        blips, n = {}, max(1, len(self._wnames))
        for i, w in enumerate(self._wnames):
            ang = math.radians((i + 0.5) / n * 360.0)
            br = round(cy - math.cos(ang) * R * 0.6 / 2.0)
            bc = round(cx + math.sin(ang) * R * 0.6)
            blips[(br, bc)] = w
        rows = []
        for row in range(H):
            out = []
            for col in range(W):
                if (row, col) in blips:
                    w = blips[(row, col)]
                    c = GREEN if w in self.active else "#3fa7ff"
                    out.append(f"[bold {c}]◉[/]")
                    continue
                dx, dy = col - cx, (row - cy) * 2.0
                r = math.hypot(dx, dy)
                if abs(dx) < 0.6 and abs(dy) < 1.1:
                    out.append(f"[{GREEN}]✛[/]")
                elif r > R + 0.4:
                    out.append(" ")
                else:
                    a = math.degrees(math.atan2(dx, -dy)) % 360.0
                    delta = (theta - a) % 360.0
                    if r > 1.0 and delta < 7:
                        out.append("[bold #b6ffcf]•[/]")
                    elif r > 1.0 and delta < 62:
                        out.append(f"[{GREEN}]·[/]")
                    elif abs(r - R) < 0.55 or abs(r - R * 0.62) < 0.5:
                        out.append("[dim]·[/]")
                    else:
                        out.append(" ")
            rows.append("".join(out))
        return rows

    def render(self):
        lines = [f"[bold {BLUE}]╔════════════════════╗[/]",
                 f"[bold {BLUE}]║  TORRE DE CONTROL  ║[/]",
                 f"[bold {BLUE}]╚════════════════════╝[/]",
                 ""]
        segs = []                                    # pipeline: split -> run -> merge
        for k, lab in (("split", "1 SPLIT"), ("run", "2 RUN"), ("merge", "3 MERGE")):
            segs.append(f"[bold {GREEN}]{lab}[/]" if self.phase == k else f"[dim]{lab}[/]")
        lines.append("  " + " [dim]→[/] ".join(segs))
        lines.append("")
        lines += ["   " + r for r in self._ppi()]      # mini-radar PPI (barrido + blips)
        lines.append("")
        for w in self._wnames:
            spin = SPIN[self.spin % len(SPIN)] if w in self.active else "[dim]•[/]"
            task_lane = self._lane(self.task_pkts[w], "▸", GREEN)
            res_lane = self._lane(self.result_pkts[w], "◂", "#3fa7ff", reverse=True)
            lines.append(f"  [dim]traza [/]{task_lane} [bold]{w}[/] {spin}  "
                         f"[{GREEN}]●{self.chunks.get(w, 0)}[/]")
            lines.append(f"  [dim]eco   [/]{res_lane}")
        lines += ["",
                  "  [dim]▸ traza enviada · ◂ eco recibido[/]",
                  f"  [dim]tráfico[/] envíos=[bold]{self.counts['task']}[/] "
                  f"ecos=[bold]{self.counts['result']}[/]  "
                  f"[dim]en antena[/] [bold]{len(self.active)}[/]",
                  f"  [dim]caudal[/] {self._sparkline()} [dim]trazas/s[/]"]
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
        self.border_subtitle = "trazas procesadas / total"
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
        self.border_subtitle = "paralelo vs secuencial"
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


class AlertsCard(Static):
    """Contador en vivo de anomalías detectadas (alertas), y total final tras el merge."""

    def __init__(self, **kw):
        super().__init__("", **kw)
        self.count = 0
        self.final = None

    def on_mount(self):
        self.border_title = " alertas "
        self.border_subtitle = "anomalías detectadas"
        self._redraw()

    def add(self, n):
        if n:
            self.count += n
            self._redraw()

    def set_final(self, detected, total):
        self.final = (detected, total)
        self._redraw()

    def _redraw(self):
        if self.final is not None:
            d, tot = self.final
            self.update(Text.from_markup(f"[bold #ff5247]⚠ {d}[/][dim]/{tot}[/]\n[dim]inyectadas detectadas[/]"))
        elif self.count > 0:
            self.update(Text.from_markup(f"[bold #d29922]⚠ {self.count}[/]\n[dim]en curso…[/]"))
        else:
            self.update(Text.from_markup("[dim]⚠ 0[/]"))

    def reset(self):
        self.count = 0
        self.final = None
        self._redraw()
