# Parte III — Proyecto Integrador semestral

**Entregable:** `documento_proyecto.pdf` (3 páginas, dentro del rango 2–4 que pide la pauta).

**Tema:** Detección de anomalías de comportamiento en trayectorias ADS-B de OpenSky Network a escala anual mediante un pipeline híbrido Dask + OpenMP.

## Cobertura de la rúbrica (cuadro 4 de la pauta, 15 pts)

| Criterio | Sección del documento |
|---|---|
| Delimitación del problema y pertinencia DS (3 pts) | §1 |
| Justificación real del paralelismo/distribución (3 pts) | §3 + §4 |
| Coherencia datos $\leftrightarrow$ arquitectura $\leftrightarrow$ estrategia (3 pts) | §2 + §4 + §5 |
| Diseño preliminar de métricas y benchmarking (3 pts) | §6 |
| Identificación honesta de riesgos, límites y supuestos (3 pts) | §7 |

## Cómo regenerar el PDF

```powershell
latexmk -pdf documento_proyecto.tex
```

Requiere MiKTeX o cualquier distribución LaTeX con `latexmk`.
