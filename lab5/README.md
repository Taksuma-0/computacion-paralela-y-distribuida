# Suma de Vectores con OpenCL
## Introducción a la Computación Paralela

---

## ¿Qué hace este programa?

Suma dos vectores de **1 048 576 elementos** (1M de floats) en **paralelo** usando OpenCL:

```
C[i] = A[i] + B[i]   para todo i ∈ [0, N)
```

En lugar de hacer 1 millón de sumas una tras otra (serial), OpenCL lanza **1 millón de hilos simultáneos** — uno por elemento.

---

## Conceptos de Computación Paralela

### El modelo de paralelismo

```
CPU Serial:                    OpenCL Paralelo:
─────────────────              ──────────────────────────────────────
Paso 1: C[0] = A[0]+B[0]       Work-item 0:  C[0] = A[0]+B[0]  ┐
Paso 2: C[1] = A[1]+B[1]       Work-item 1:  C[1] = A[1]+B[1]  │
Paso 3: C[2] = A[2]+B[2]       Work-item 2:  C[2] = A[2]+B[2]  │ simultáneo
  ...                          Work-item 3:  C[3] = A[3]+B[3]  │
Paso N: C[N] = A[N]+B[N]         ...                            │
                               Work-item N:  C[N] = A[N]+B[N]  ┘
Total: N pasos                 Total: ~1 paso lógico
```

### ¿Por qué es paralelizable?

La suma de vectores tiene **independencia de datos**: el cálculo de `C[i]` no depende de `C[j]` para ningún `j ≠ i`. Esto lo hace ideal para paralelismo masivo.

### NDRange y Work-items

| Concepto | Descripción |
|---|---|
| **Work-item** | Un hilo de ejecución, procesa un elemento |
| **Work-group** | Grupo de work-items que comparten memoria local |
| **NDRange** | Espacio de índices total (1D, 2D o 3D) |
| **Global size** | Total de work-items lanzados (= N = 1M) |
| **Local size** | Work-items por grupo (= 64) |

---

## Arquitectura del Programa

```
HOST (CPU/RAM)                      DISPOSITIVO (GPU o CPU OpenCL)
─────────────────────               ──────────────────────────────────
1. Crear plataforma/dispositivo
2. Crear contexto + queue
3. Inicializar h_A[], h_B[]
4. Crear buffers d_A, d_B, d_C ──→  Memoria del dispositivo reservada
5. Copiar h_A → d_A             ──→  d_A = [0, 1, 2, ...]
   Copiar h_B → d_B             ──→  d_B = [N, N-1, N-2, ...]
6. Compilar kernel
7. Configurar args (d_A,d_B,d_C,N)
8. Lanzar NDRange (1M work-items) ──→  ████████████████ (paralelo)
9. Leer d_C → h_C               ←──  h_C = [N, N, N, ...]
10. Verificar resultado
```

---

## El Kernel (código del dispositivo)

```c
__kernel void suma_vectores(
    __global const float* A,
    __global const float* B,
    __global       float* C,
    const unsigned int    N
) {
    unsigned int i = get_global_id(0);  // índice único por hilo
    if (i < N) {
        C[i] = A[i] + B[i];            // 1 suma por work-item
    }
}
```

`get_global_id(0)` devuelve un valor distinto para cada work-item (0, 1, 2, ..., N-1), lo que permite que cada uno opere sobre su propio elemento sin interferir con los demás.

---

## Flujo de Memoria

```
RAM del Sistema (Host)          Memoria del Dispositivo
┌─────────────────────┐         ┌─────────────────────┐
│  h_A[1M floats] 4MB │──Write─▶│  d_A[1M floats] 4MB │
│  h_B[1M floats] 4MB │──Write─▶│  d_B[1M floats] 4MB │
│  h_C[1M floats] 4MB │◀─Read──│  d_C[1M floats] 4MB │
└─────────────────────┘         └─────────────────────┘
                                         ▲
                                    Kernel ejecuta
                                  C[i] = A[i] + B[i]
```

---

## Compilar y Ejecutar

### Requisitos

```bash
# Ubuntu/Debian
sudo apt install opencl-headers ocl-icd-opencl-dev pocl-opencl-icd
```

### Compilación

```bash
make
# o manualmente:
gcc -Wall -O2 -std=c99 -DCL_TARGET_OPENCL_VERSION=120 \
    -o suma_vectores suma_vectores.c -lOpenCL -lm
```

### Ejecución

```bash
make run
# o:
./suma_vectores
```

---

## Salida Esperada

```
============================================================
  SUMA DE VECTORES CON OPENCL - COMPUTACIÓN PARALELA
============================================================
  Tamaño del vector : 1048576 elementos
  Memoria por vector: 4.00 MB

[PASO 1] Descubriendo plataforma y dispositivo OpenCL...
  Plataforma: Portable Computing Language
  Nombre        : Intel(R) Xeon(R) Processor @ 2.80GHz
  Unidades calc.: 8 (núcleos de cómputo)

[PASO 8] Lanzando kernel paralelo...
  → Global size : 1048576 work-items
  → Work-groups : 16384 grupos en paralelo

[PASO 10] Verificando resultado...
  ✓ Verificación exitosa: todos los 1048576 elementos son correctos.

  RESUMEN DE RENDIMIENTO
  Resultado : CORRECTO ✓
============================================================
```

---

## Pasos de OpenCL

| Paso | Función | Propósito |
|------|---------|-----------|
| 1 | `clGetPlatformIDs` / `clGetDeviceIDs` | Descubrir hardware |
| 2 | `clCreateContext` / `clCreateCommandQueue` | Entorno de ejecución |
| 3 | — | Inicializar datos en CPU |
| 4 | `clCreateBuffer` | Reservar memoria en dispositivo |
| 5 | `clEnqueueWriteBuffer` | Enviar datos CPU → dispositivo |
| 6 | `clCreateProgramWithSource` / `clBuildProgram` | Compilar kernel |
| 7 | `clSetKernelArg` | Pasar argumentos al kernel |
| 8 | `clEnqueueNDRangeKernel` | **Ejecutar en paralelo** |
| 9 | `clEnqueueReadBuffer` | Recibir resultado dispositivo → CPU |
| 10 | — | Verificar y limpiar recursos |

---

## Extensiones sugeridas

1. **Suma en 2D**: Procesar una matriz M×N con NDRange de 2 dimensiones.
2. **Reducción paralela**: Sumar todos los elementos de un vector (más complejo, usa memoria local).
3. **Medir transferencias**: Cronometrar por separado el tiempo de upload/download vs kernel.
4. **Variar el local_size**: Experimentar con 32, 128, 256 para ver el impacto en rendimiento.

---

*Estándar: OpenCL 1.2 — Compatible con POCL (CPU), AMD GPU, NVIDIA GPU, Intel GPU*
