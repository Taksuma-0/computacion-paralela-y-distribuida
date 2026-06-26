# Prueba 1 — Parte II grupal (INFB8090)

Computación Paralela y Distribuida — Ingeniería Civil en Ciencia de Datos — UTEM
Profesor: Michael Gabriel Miranda Sandoval — Sección 412 — Mayo 2026

## Integrantes

- Welinton Barrera Mondaca
- Joaquin Araya
- Juan Toledo

## Entregables principales

| Archivo / carpeta | Qué es |
|---|---|
| **`reporte.pdf`** | Informe grupal Parte II completo (portada, 3 ejercicios, discusión, conclusiones, registro de entorno, declaración de IA y referencias). **Documento principal a revisar.** |
| **`parte_1_individual/`** | Fotografías de la respuesta individual de Welinton (Joaquin y Juan no tuvieron oportunidad de fotografiar sus pruebas, como se explica en el informe). |
| **`proyecto_integrador/documento_proyecto.pdf`** | Parte III — Proyecto Integrador semestral (3 páginas): detección de anomalías en trayectorias ADS-B de OpenSky con pipeline híbrido Dask + OpenMP. |

## Estructura del repositorio

```
parte_2_grupal/
├── reporte.pdf                    ← informe compilado (entregable principal)
├── README.md                      ← este archivo
│
├── parte_1_individual/            ← Parte I individual (fotografías)
│   └── prueba 1 fotos welinton/   ← respuesta individual de Welinton
│
├── proyecto_integrador/           ← Parte III Proyecto Integrador semestral
│   ├── documento_proyecto.pdf     ← documento de 3 páginas (entregable)
│   ├── documento_proyecto.tex     ← fuente LaTeX
│   └── README.md
│
├── informe_latex/                 ← fuente LaTeX del informe
│   ├── Arxc.tex                   ← fuente principal
│   ├── Arxc.pdf                   ← idéntico a reporte.pdf
│   ├── figuras/                   ← PNG referenciados desde el informe
│   └── logos_utem/                ← logo institucional
│
├── codigo_openmp/                 ← Ejercicio 1 (Normalización masiva con OpenMP)
│   ├── normalizacion.cpp          ← solución C++/OpenMP (50.000.000 × 16 con NaN)
│   ├── Makefile                   ← compila con -O3 -std=c++20 -fopenmp
│   └── README.md                  ← comandos de compilación y ejecución
│
├── codigo_python/                 ← Ejercicios 2 y 3 (Python)
│   ├── generar_logs.py            ← generador reproducible de logs .gz
│   ├── benchmark_logs.py          ← Ej.2: pipeline secuencial/threads/processes/híbrido
│   ├── benchmark_embeddings.py    ← Ej.3: top-k por bloques (20.000 × 128)
│   └── generar_graficos.py        ← regenera los PNG del informe desde los CSV
│
├── datos_generados/               ← muestra local reproducible
│   └── logs_rba_gateway_16mib/    ← 8 archivos .jsonl.gz + manifest
│
└── anexos_benchmark/              ← CSV de resultados + registro de entorno
    ├── openmp_normalizacion_50m.csv       ← Ej.1, OMP_NUM_THREADS=1,2,4,8
    ├── openmp_normalizacion_50m_raw.csv   ← Ej.1, mediciones crudas
    ├── pipeline_logs_16mib.csv            ← Ej.2, 4 estrategias × workers
    ├── embeddings_topk_20000.csv          ← Ej.3, workers=1,2,4
    ├── embeddings_topk_6000.csv           ← Ej.3, escala intermedia
    ├── embeddings_topk_12000.csv          ← Ej.3, escala intermedia
    └── entorno_ejecucion.txt              ← SO, CPU, RAM, compilador, comandos
```

## Cómo reproducir

### Ejercicio 1 — OpenMP

```powershell
cd codigo_openmp
g++ -O3 -std=c++20 -fopenmp normalizacion.cpp -o normalizacion.exe
foreach ($t in 1, 2, 4, 8) {
    $env:OMP_NUM_THREADS = "$t"
    .\normalizacion.exe --rows 50000000 --cols 16 --nan-rate 0.035 --csv
}
```

### Ejercicio 2 — Pipeline de logs

```powershell
cd codigo_python
python generar_logs.py --out-dir ..\datos_generados\logs_rba_gateway_16mib --target-mb 16 --files 8 --seed 4128090
python benchmark_logs.py --input-dir ..\datos_generados\logs_rba_gateway_16mib --out-csv ..\anexos_benchmark\pipeline_logs_16mib.csv --workers 1 2 4 8 --repeats 2 --warmups 1
```

Para reproducir el tamaño completo de 2 GiB que pide el enunciado:

```powershell
python generar_logs.py --out-dir ..\datos_generados\logs_rba_gateway_2gib --target-mb 2048 --files 32 --seed 4128090
```

### Ejercicio 3 — Embeddings

```powershell
cd codigo_python
python benchmark_embeddings.py --n 20000 --dim 128 --block 1024 --topk 10 --workers 1 2 4 --repeats 1 --out-csv ..\anexos_benchmark\embeddings_topk_20000.csv
```

### Regenerar las figuras

```powershell
cd codigo_python
python generar_graficos.py
```

### Recompilar el PDF (opcional)

```powershell
cd informe_latex
latexmk -pdf Arxc.tex
copy Arxc.pdf ..\reporte.pdf
```

## Entorno usado

Windows 11 Home · AMD Ryzen 7 6800H (8 físicos / 16 lógicos) · 15,26 GiB RAM ·
Python 3.13.5 · g++ 13.2.0 (MinGW-W64) con soporte `-fopenmp` · MiKTeX para LaTeX.

Detalle completo en `anexos_benchmark/entorno_ejecucion.txt` y en la sección
"Registro de entorno y ejecución" del `reporte.pdf`.

## Declaración de apoyo

Se usó documentación pública (OpenMP, Python, NumPy, OpenSky, RBA, Azure
Application Gateway, SIFT1M) y asistencia computacional para búsqueda de
referencias, organización del informe y revisión de código. El grupo
revisó, adaptó y ejecutó todos los programas localmente; los comandos y
los resultados quedan en `anexos_benchmark/` y en el `reporte.pdf`.

## Material de referencia OpenMP

Para el ejercicio 1 se usó como base el paquete `OpenMP.rar` entregado por
el profesor: instructivo `Leeme.txt`, configuración portable para
VSCode/w64devkit y los ejemplos `suma_50M.c` y `primos_pesado.c`.
