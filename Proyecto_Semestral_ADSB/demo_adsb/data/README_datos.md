# Datos — Trayectorias ADS-B

## Origen

Vuelos reales obtenidos de **OpenSky Network** (API pública, endpoint `/states/all`, acceso anónimo),
capturados sobre un *bounding box* de Europa central (alto tráfico) con `../ingesta_adsb.py`.

## Contenido

- `trayectorias_reales.json`: **636 vuelos reales** (~732 KB).
- Cada vuelo se agrupa por `icao24`, se filtra (mínimo 8 puntos) y se **resamplea a 40 puntos**
  `[lat, lon, alt]`.
- Campos por vuelo: `icao24` (identificador de aeronave), `callsign` (indicativo) y la trayectoria
  de 40 puntos.

## Regeneración / muestra equivalente

```powershell
cd demo_adsb
python ingesta_adsb.py --source opensky --bbox 47,5,55,15 --snapshots 24 --interval 10
```

El volumen exacto varía según el tráfico al momento de la captura (los datos son un *snapshot* en vivo),
por lo que una nueva ingesta produce una **muestra equivalente**, no idéntica.

## Carga sintética (estudio de escalabilidad)

El benchmark de escalabilidad **no** usa este archivo, sino datos generados por **semilla**
(`tasks/task_adsb.py`): cada partición transporta `seed=7` y el agente regenera sus trayectorias con
`random.Random(seed)`, logrando **transferencia ≈ 0** y reproducibilidad total.

## Restricciones y trazabilidad

- El volumen real es pequeño (un *snapshot*), por lo que la variante sobre datos reales es *I/O-bound*.
- **Semilla fija `seed=7`** en toda generación sintética e inyección de anomalías.
- Cada corrida deja evidencia trazable en `../results/<job-id>.json` (+ reporte `.html`).
