"""Captura SVG de las 3 pantallas de la TUI (headless) y arma shots.html para revisarlas.
Ejecutar:  python -m tui_gato._shots"""

import asyncio
import os

from .app import GatoRayTUI

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)


async def main():
    shots = []
    app = GatoRayTUI()
    async with app.run_test(size=(130, 42)) as pilot:
        await pilot.pause(0.4)
        shots.append(("1 · Launcher", app.export_screenshot()))

        cfg = {"gens": 8, "games": 150, "tasks": 4, "mode": "local", "bench": False}
        app.train_action(cfg)
        await pilot.pause(0.3)
        for _ in range(80):
            if app.done_gens >= 3:
                break
            await pilot.pause(0.1)
        await pilot.pause(0.3)
        shots.append(("2 · Entrenamiento (en vivo)", app.export_screenshot()))

        for _ in range(250):
            if not app._train_running:
                break
            await pilot.pause(0.1)
        await pilot.pause(0.3)
        shots.append(("3 · Entrenamiento (fin)", app.export_screenshot()))

        app.leave_train()
        await pilot.pause(0.2)
        app.play_action()
        await pilot.pause(0.7)
        play = app.screen
        # jugar un par de movidas para que se vea acción
        empties = [i for i in range(9) if play.board[i] == "."]
        if empties:
            play.play_human(empties[0])
        await pilot.pause(0.7)
        shots.append(("4 · Jugar contra el modelo", app.export_screenshot()))

    html = ["<!doctype html><meta charset='utf-8'>",
            "<body style='background:#0d1117;margin:0;padding:20px;font-family:sans-serif'>"]
    for name, svg in shots:
        html.append(f"<h2 style='color:#7AB830'>{name}</h2>{svg}<hr style='border-color:#30363d'>")
    html.append("</body>")
    out = os.path.join(DEMO, "shots.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(html))
    print("shots.html escrito:", out, "·", len(shots), "pantallas")


if __name__ == "__main__":
    asyncio.run(main())
