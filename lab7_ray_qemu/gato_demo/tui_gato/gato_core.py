"""Motor del gato (tic-tac-toe) + IA, para la pantalla de juego de la TUI.
Espejo de la lógica de gato_rl_ray.py: la IA usa el modelo aprendido (bestmove)
con una pequeña red de seguridad táctica (ganar/bloquear) para no regalar partidas."""

LINEAS = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
          (0, 3, 6), (1, 4, 7), (2, 5, 8),
          (0, 4, 8), (2, 4, 6)]
VACIO = "." * 9


def turno(b: str) -> str:
    return "X" if b.count("X") == b.count("O") else "O"


def legales(b: str):
    return [i for i, c in enumerate(b) if c == "."]


def aplicar(b: str, i: int, p: str) -> str:
    return b[:i] + p + b[i + 1:]


def ganador(b: str):
    for a, c, d in LINEAS:
        if b[a] != "." and b[a] == b[c] == b[d]:
            return b[a]
    return "draw" if "." not in b else None


def linea_ganadora(b: str):
    for L in LINEAS:
        a, c, d = L
        if b[a] != "." and b[a] == b[c] == b[d]:
            return L
    return None


def jugada_ia(b: str, bestmove: dict) -> int:
    """Jugada de la IA: gana ya / bloquea / política aprendida / heurística."""
    p = turno(b)
    opp = "O" if p == "X" else "X"
    ms = legales(b)
    for m in ms:                                  # gana en una
        if ganador(aplicar(b, m, p)) == p:
            return m
    for m in ms:                                  # bloquea amenaza
        if ganador(aplicar(b, m, opp)) == opp:
            return m
    bm = bestmove.get(b)                           # lo aprendido
    if bm is not None and bm in ms:
        return bm
    for m in (4, 0, 2, 6, 8, 1, 3, 5, 7):         # heurística (centro/esquinas)
        if m in ms:
            return m
    return ms[0]
