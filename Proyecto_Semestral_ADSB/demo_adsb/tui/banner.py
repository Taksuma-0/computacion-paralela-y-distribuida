"""Logo de la TUI ADS-B: avion + escudo UTEM + wordmark, y helpers de color.

El escudo vive en `_shield_art.py` y el avion en `_plane_art.py`. Aqui se componen
lado a lado (avion a la izquierda, escudo a la derecha) para el membrete del launcher."""

from ._shield_art import SHIELD_LINES, SHIELD_W
from ._plane_art import PLANE_LINES, PLANE_W

BLUE = "#004E9A"   # azul institucional UTEM
GREEN = "#7AB830"  # verde institucional UTEM


def shield_lines():
    """Lineas (markup Rich) del escudo UTEM en color."""
    return list(SHIELD_LINES)


def shield_markup() -> str:
    """Escudo UTEM como bloque de markup."""
    return "\n".join(SHIELD_LINES)


def banner_markup() -> str:
    """Membrete del launcher: avion (izq) + escudo UTEM (der), centrados
    verticalmente; debajo, el wordmark ADS-B."""
    pad = (len(SHIELD_LINES) - len(PLANE_LINES)) // 2
    blank = " " * PLANE_W
    rows = []
    for i, sline in enumerate(SHIELD_LINES):
        j = i - pad
        pline = PLANE_LINES[j] if 0 <= j < len(PLANE_LINES) else blank
        rows.append(f"{pline}   {sline}")
    word = [
        "",
        f"[bold {GREEN}]A D S - B   A N O M A L Y   S C O P E[/]",
        f"[{BLUE}]deteccion distribuida de anomalias de vuelo[/]",
        "[dim]Computacion Paralela y Distribuida · UTEM[/]",
    ]
    return "\n".join(rows) + "\n" + "\n".join(word)


def header_markup(extra: str = "") -> str:
    """Markup compacto para el header del dashboard."""
    return f"[bold {BLUE} on white] UTEM [/] [bold {GREEN}]✈ ADS-B Anomaly Scope[/]  {extra}"
