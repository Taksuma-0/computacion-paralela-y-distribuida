"""Logo ASCII UTEM (escudo en color + wordmark) y helpers de color para la TUI Ray.

El escudo vive en `_shield_art.py` (medios-bloques ▀ en color). Aquí se compone con
el wordmark UTEM y el título del demo Ray."""

from ._shield_art import SHIELD_LINES, SHIELD_W

BLUE = "#004E9A"   # azul institucional UTEM
GREEN = "#7AB830"  # verde institucional UTEM

UTEM_LINES = [
    "█    █  ██████  ██████  █    █",
    "█    █    ██    █       ██  ██",
    "█    █    ██    ████    █ ██ █",
    "█    █    ██    █       █    █",
    "██████    ██    ██████  █    █",
]


def shield_markup() -> str:
    return "\n".join(SHIELD_LINES)


def banner_markup() -> str:
    """Membrete del launcher: escudo a la izquierda + wordmark UTEM + título del demo."""
    right = [f"[bold {BLUE}]{ln}[/]" for ln in UTEM_LINES]
    right += [
        "",
        f"[bold {GREEN}]R A Y   ·   Q E M U[/]",
        "[dim]El gato que aprende solo[/]",
        "[dim]RL distribuido · Computacion Paralela[/]",
    ]
    start = (len(SHIELD_LINES) - len(right)) // 2
    rows = []
    for i, sline in enumerate(SHIELD_LINES):
        j = i - start
        rblock = right[j] if 0 <= j < len(right) else ""
        rows.append(f"{sline}   {rblock}")
    pie = f"[{GREEN}]●[/] ray0 [dim](head)[/]    [dim]●[/] ray1    [dim]●[/] ray2    [dim]· Dashboard 8265[/]"
    return "\n".join(rows) + f"\n\n{pie}"


def header_markup(extra: str = "") -> str:
    """Markup compacto para el header del dashboard."""
    return f"[bold {BLUE} on white] UTEM [/] [bold {GREEN}]Ray · El gato[/]  {extra}"
