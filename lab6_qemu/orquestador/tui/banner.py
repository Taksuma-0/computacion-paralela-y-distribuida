"""Logo ASCII UTEM (escudo en color + wordmark) y helpers de color para el TUI.

El escudo vive en `_shield_art.py` (generado desde la imagen oficial con Pillow,
medios-bloques ▀ en color). Aqui solo se compone con el wordmark."""

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


def shield_lines():
    """Lineas (markup Rich) del escudo UTEM en color."""
    return list(SHIELD_LINES)


def shield_markup() -> str:
    """Escudo UTEM como bloque de markup."""
    return "\n".join(SHIELD_LINES)


def banner_markup() -> str:
    """Membrete del launcher: escudo a la izquierda + wordmark UTEM a la derecha,
    centrado verticalmente; debajo, el tag y los nodos."""
    right = [f"[bold {BLUE}]{ln}[/]" for ln in UTEM_LINES]
    right += [
        "",
        f"[bold {GREEN}]C L U S T E R   Q E M U[/]",
        "[dim]orquestador distribuido[/]",
        "[dim]Computacion Paralela y Distribuida[/]",
    ]
    start = (len(SHIELD_LINES) - len(right)) // 2
    rows = []
    for i, sline in enumerate(SHIELD_LINES):
        j = i - start
        rblock = right[j] if 0 <= j < len(right) else ""
        rows.append(f"{sline}   {rblock}")
    nodes = f"[{GREEN}]●[/] nodo0    [{GREEN}]●[/] nodo1    [{GREEN}]●[/] nodo2"
    return "\n".join(rows) + f"\n\n{nodes}"


def header_markup(extra: str = "") -> str:
    """Markup compacto para el header del dashboard."""
    return f"[bold {BLUE} on white] UTEM [/] [bold {GREEN}]Cluster QEMU[/]  {extra}"
