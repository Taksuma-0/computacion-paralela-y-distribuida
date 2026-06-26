"""Smoke test headless de la TUI (sin VM): monta la app, entrena en modo LOCAL
(subproceso real de gato_rl_ray.py), comprueba que los eventos alimentan la curva
y los paneles, baja el modelo, y simula una partida en la pantalla de juego.

Ejecutar:  python -m tui_gato._selftest
"""

import asyncio
import os

from .app import GatoRayTUI, MODEL_PATH


async def main():
    if os.path.isfile(MODEL_PATH):
        try:
            os.remove(MODEL_PATH)
        except Exception:
            pass

    app = GatoRayTUI()
    async with app.run_test() as pilot:
        await pilot.pause(0.3)  # montar launcher (prueba compose)
        assert app.launcher is not None

        cfg = {"gens": 4, "games": 100, "tasks": 3, "mode": "local", "bench": False}
        app.train_action(cfg)
        await pilot.pause(0.3)

        # esperar fin del entrenamiento local (hasta ~25s)
        for _ in range(250):
            if not app._train_running:
                break
            await pilot.pause(0.1)
        assert not app._train_running, "el entrenamiento no terminó"
        assert app.total_gens == 4, f"total_gens={app.total_gens}"

        pts = len(app.train.curve.pts)
        assert pts == 4, f"puntos de curva={pts}"
        rollouts = sum(p.chunks for p in app.train.panels.values())
        assert rollouts == 12, f"rollouts={rollouts} (esperaba 4 gen x 3 tareas)"
        nonloss_final = app.train.curve.pts[-1].get("nonloss", 0)

        app.leave_train()
        await pilot.pause(0.2)
        assert os.path.isfile(MODEL_PATH), "no se generó gato_modelo.json"

        app.play_action()
        await pilot.pause(0.6)  # deja que la IA (X) abra
        play = app.screen
        empties = [i for i in range(9) if play.board[i] == "."]
        assert empties, "tablero sin celdas vacías al inicio"
        before = sum(c != "." for c in play.board)
        play.play_human(empties[0])
        await pilot.pause(0.7)  # deja responder a la IA
        after = sum(c != "." for c in play.board)
        assert after >= before + 1, f"el tablero no avanzó ({before}->{after})"

        print(f"OK · gens={app.total_gens} · curva={pts}pts · rollouts={rollouts} · "
              f"no-derrota_final={nonloss_final*100:.0f}% · board='{play.board}' · "
              f"marcador={play.sc}")


if __name__ == "__main__":
    asyncio.run(main())
