# Normalizacion masiva con OpenMP

Este directorio contiene la propuesta C++ para el ejercicio grupal 1.

Compilacion usada:

```powershell
g++ -O3 -std=c++20 -fopenmp normalizacion.cpp -o normalizacion.exe
```

Ejecucion de escala completa solicitada para comparar hilos:

```powershell
foreach ($t in 1, 2, 4, 8) {
    $env:OMP_NUM_THREADS = "$t"
    .\normalizacion.exe --rows 50000000 --cols 16 --nan-rate 0.035 --csv
}
```

Ejecucion reducida para pruebas locales:

```powershell
$env:OMP_NUM_THREADS = "4"
.\normalizacion.exe --rows 5000000 --cols 16 --nan-rate 0.035
```

El programa genera una matriz sintetica reproducible en memoria. La estructura numerica esta inspirada en variables de seguimiento aereo: latitud, longitud, velocidad, altura, razon vertical, rumbo y otros indicadores continuos. Los valores faltantes se representan con `NaN` y se ignoran en el calculo de media y desviacion estandar.
