# Contexto — Proyecto Semestral ADS-B

> Esta carpeta es una **copia separada** del Proyecto Integrador semestral del ramo
> *Computación Paralela y Distribuida*, extraída para trabajarlo de forma independiente
> del resto de la Prueba 1. El original **no se modificó ni se borró**.

## De dónde salió esta copia

- **Origen:** `Prueba.SegundaMitad/prueba_1_computacion_paralela/parte_2_grupal/proyecto_integrador/`
- **Fecha de la copia:** 2026-06-24
- **Qué se copió:** `documento_proyecto.tex`, `documento_proyecto.pdf`, `README.md`
- **Qué NO se copió:** archivos auxiliares de LaTeX (`.aux`, `.log`, `.fls`, `.fdb_latexmk`, `.out`),
  que se regeneran solos al compilar.

## Qué es el proyecto

**Título:** Detección de anomalías de comportamiento en trayectorias ADS-B de OpenSky
Network a escala anual mediante un pipeline híbrido **Dask + OpenMP**.

Es la **Parte III — Proyecto Integrador semestral**: un documento de diseño/propuesta
(2–4 páginas según pauta) de un sistema que, a partir de los datos **ADS-B** que emiten
las aeronaves (posición, altitud, velocidad, rumbo), detecta y rankea trayectorias
anómalas: maniobras evasivas, *go-arounds*, *holdings* prolongados, descensos anómalos,
vuelos no comerciales (medevac, estatales, *ferry*), etc.

> Nota: en su estado actual el proyecto es una **propuesta de diseño**, no implementación.
> El código real del pipeline aún no existe; lo que hay es el documento que define problema,
> datos, estrategia de paralelización, métricas, riesgos y resultado esperado.

## Datos del entregable

| Campo | Valor |
|---|---|
| Ramo | Computación Paralela y Distribuida (INFB8090) |
| Carrera | Ingeniería Civil en Ciencia de Datos — UTEM |
| Profesor | Michael Gabriel Miranda Sandoval |
| Sección | 412 |
| Fecha | Mayo de 2026 |
| Integrantes | Welinton Barrera Mondaca, Joaquin Araya, Juan Toledo |

## Secciones del documento (cubren la rúbrica de 15 pts)

1. Problema delimitado y pertinencia para ciencia de datos
2. Datos: volumen (~1 TB comprimido/año), tipo, estructura y origen (OpenSky / `state_vectors_data4`)
3. Hipótesis de paralelización y distribución (mapa etapa → tipo de carga → estrategia)
4. Estrategia técnica preliminar (pipeline de 4 etapas; *kernels* C++/OpenMP vía `pybind11`)
5. Herramientas tentativas (Dask Distributed, `pyarrow`, `scikit-learn`, OpenMP, MPI alternativo)
6. Métricas de evaluación y diseño de *benchmarking* (speedup, `precision@k`, costo)
7. Riesgos, límites y supuestos (*data skew*, cobertura oceánica, *ground truth* escaso)
8. Resultado esperado del proyecto final (Sₚ ≥ 8 con 16 *workers*, `precision@50` ≥ 0,3, etc.)

## Cómo recompilar el PDF

```powershell
latexmk -pdf documento_proyecto.tex
```

Requiere MiKTeX (o cualquier distribución LaTeX con `latexmk`).

## PoC distribuida (avance temprano)

Ya existe una **prueba de concepto funcional** de la etapa central del proyecto —el
*scoring embarrassingly-parallel sobre particiones*— implementada como una tarea
enchufable del orquestador distribuido propio:

- **Ubicación:** `Paralelismo_con_qemu/orquestador/tasks/task_adsb.py` (+ reporte
  `adsb_report.py` y registro en la TUI).
- **Qué hace:** genera trayectorias ADS-B sintéticas (vuelos normales + anomalías
  inyectadas con *ground-truth*: rodeo, holding, descenso anómalo, go-around),
  extrae *features* de comportamiento (desvío de ruta vía haversine, curvatura,
  tasa vertical) y las puntúa con un detector no supervisado **z-robusto (MAD)**.
  El `merge` produce un **ranking top-k** de los vuelos más anómalos.
- **Distribución real:** corre sobre el coordinador/agentes del orquestador (cola
  dinámica, tolerancia a fallos, *datos por semilla* → cero transferencia). Medido
  en 2 nodos locales: **speedup ≈ 1.7×**, `recall = 1.0`, `precision@10 = 1.0`,
  FPR ≈ 0.4 % (equivalencia exacta baseline ↔ distribuido).
- **Visualización:** al terminar el job desde la TUI se abre un HTML autocontenido
  (un *scope* de radar de control aéreo con las trayectorias, el ranking y las
  métricas).

**Relación con el proyecto final:** esta PoC valida el patrón de paralelización de la
etapa de *scoring* (la §3–§4 del documento). El proyecto final escalará a datos
reales de OpenSky y evaluará **Dask/Ray** frente a este orquestador propio para esa
etapa; la PoC sirve de baseline conceptual y de evidencia de que el componente
distribuido funciona end-to-end.

**Reproducir** (desde `Paralelismo_con_qemu/orquestador/`): elegir *“ADS-B anomalias
(ranking top-k)”* en la TUI (`./run_tui.ps1`, modo Local), o por CLI:
`python coordinator_generic.py --task tasks/task_adsb.py --workers workers.local.json --no-deploy --payload '{...}'`.
