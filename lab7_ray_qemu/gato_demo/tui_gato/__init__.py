"""TUI (Textual) para el demo 'El gato que aprende solo' con Ray sobre QEMU.

Reutiliza el diseño del orquestador QEMU (tema UTEM, escudo, paneles por worker,
ClusterFlow, SpeedupCard) pero el backend es Ray DENTRO de la VM Debian (ray0):
levanta la VM, entrena el gato por refuerzo mostrándolo en vivo, y deja jugar
contra el modelo entrenado de forma distribuida.

Lanzar:  cd ray_qemu/gato_demo ; python -m tui_gato   (o ./run_tui_gato.ps1)
"""
