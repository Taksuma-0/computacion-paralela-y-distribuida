"""Logo ASCII de avion (vista de planta, estilo blip de radar) para la TUI ADS-B.

Un color por linea y ancho visual fijo (PLANE_W) para poder alinearlo junto al
escudo UTEM en banner.py. La nariz va en ambar; el resto en verde fosforo."""

GREEN = "#7AB830"   # verde institucional UTEM (fuselaje)
AMBER = "#d29922"   # ambar (nariz / acento radar)

PLANE_W = 21

# Cada linea tiene EXACTAMENTE 21 caracteres visibles (centrado) -> alinea con el escudo.
_RAW = [
    "          █          ",
    "         ███         ",
    "         ███         ",
    "        █████        ",
    "        █████        ",
    "      █████████      ",
    "    █████████████    ",
    " ███████████████████ ",
    "        █████        ",
    "        █████        ",
    "     ███████████     ",
    "        █████        ",
    "         ███         ",
]

PLANE_LINES = [f"[{AMBER}]{_RAW[0]}[/]"] + [f"[{GREEN}]{ln}[/]" for ln in _RAW[1:]]
