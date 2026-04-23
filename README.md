# INFB8090 - Computacion Paralela y Distribuida

Repositorio de trabajos practicos del ramo **INFB8090 - Computacion Paralela y Distribuida**.

## Datos generales

- Estudiante: Welinton Barrera Mondaca
- Seccion: 412
- Profesor: Dr. Ing. Michael Miranda Sandoval
- Primer semestre 2026

## Estructura

- `lab1/`: Laboratorio 1, diagnostico experimental de paralelismo.
- `lab2/`: Laboratorio 2, modelos de computacion paralela y metricas de desempeno.
- `lab3/`: Laboratorio 3, concurrencia en Python y benchmarking comparativo.

Cada carpeta contiene el notebook principal y su guion de presentacion. Los laboratorios 2 y 3 tambien incluyen modulos Python auxiliares para ejecutar correctamente los casos con `ProcessPoolExecutor` en Windows.

## Ejecucion

1. Crear y activar un entorno Python.
2. Instalar dependencias:

```powershell
pip install -r requirements.txt
```

3. Abrir el notebook desde la carpeta del laboratorio correspondiente.
4. Ejecutar las celdas en orden.

Para los laboratorios 2 y 3, el notebook debe ejecutarse manteniendo en la misma carpeta sus archivos auxiliares `lab2_workers.py` o `lab3_workers.py`.
