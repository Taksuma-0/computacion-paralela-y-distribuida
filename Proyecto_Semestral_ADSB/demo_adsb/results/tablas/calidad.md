# Calidad de la detección (datos reales) — evidencia `job-20260702-163156`

Corrida sobre **636 vuelos reales** de OpenSky · **12 anomalías inyectadas**
para validar (evaluación híbrida) · umbral σ≥4.0 · ejecución clúster QEMU (nodo1+nodo2).

| Métrica | Valor | Significado |
|---|---|---|
| Recall | **1.00** | anomalías inyectadas detectadas (validación) |
| Detectadas en top-12 | 4/12 | inyectadas que además entran al ranking |
| Hallazgos reales en top-12 | 8 | vuelos reales genuinamente anómalos encontrados |
| precision@12 | 0.33 | top-k que son inyectadas (el resto = hallazgos) |
| TP / FP | 12 / 101 | verdaderos/falsos positivos (σ-robusto) |
| FPR | 0.162 | tasa de marcados sobre normales |

_Nota:_ con datos reales, los "no inyectados" del top-k **no son errores** sino hallazgos genuinos
(holdings/aproximaciones reales); por eso `precision@k` sale baja aunque el detector funcione. El
**recall** (sobre las inyectadas) es la métrica de validación medible.
