# Anexo — Declaración de uso de IA generativa y apoyo externo

De acuerdo con las secciones 7 y 12 de la *Pauta de Elaboración y Presentación* del proyecto semestral
(INF8090), se declara de forma explícita el apoyo externo utilizado.

## Herramientas de IA generativa
Se utilizó un **asistente de programación basado en IA generativa** (Claude Code, Anthropic) como apoyo
en:
- redacción y refactorización de código (Python: coordinador, agentes, tareas, TUI; HTML/JS del reporte),
- generación de documentación y de este informe,
- depuración de errores (por ejemplo, el arranque del clúster y el reinicio de agentes),
- diseño de la evaluación experimental y de los gráficos.

## Responsabilidad del grupo
El grupo **comprende, validó y defiende** la totalidad de lo entregado. En concreto:
- El **diseño** de la arquitectura (orquestador coordinador–agentes, `split/run/merge`, cola dinámica,
  tolerancia a fallos) fue decidido y revisado por el equipo.
- La **implementación** se ejecutó y verificó localmente y en el clúster QEMU real.
- Los **resultados** provienen de mediciones reales y trazables (`demo_adsb/results/`), no de valores
  inventados ni editados a mano.
- Cada integrante puede **explicar y defender** el particionamiento, la sincronización, la comunicación
  por TCP, la granularidad y las métricas reportadas.

## Otro apoyo externo
- **Datos**: OpenSky Network — histórico/instantáneas públicas de estados ADS-B (uso académico).
- **Librerías**: Textual, Rich, Paramiko, Requests, NumPy, Pandas, Matplotlib (documentación oficial).
- **Bibliografía**: la indicada en las referencias del informe (Grama et al., Pacheco, Tanenbaum, etc.).

Todo el apoyo externo se usó de forma **crítica y declarada**, como permite la pauta.
