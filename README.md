# Astro Health Monitor — arquitectura unificada (MEDICJAB + interfaz modular)

Fusión de dos proyectos para NASA Space Apps 2026:

- **Proyecto A (MEDICJAB, Python):** DSP de ECG, IA TFLite, simulador ECLSS, motor orbital, gemelo bio‑digital S.H.A.R.E., gateway MQTT/SQLite. → `backend/engines/` (sin modificar).
- **Proyecto B (`astro-health-modular`, HTML/CSS/JS):** escáner anatómico, ECG en vivo, botones de los 5 peligros. → `frontend/`.

## Arquitectura

```
 navegador (frontend/)  <── WebSocket /ws (1 estado/s, incluye ECG) ──  FastAPI (backend/server.py)
        │                                                                    │
        └── POST /api/scenario | toggle | orbit | astronaut | reset ─────────┤
                                                                      backend/runtime.py
                                                                             │
        DSP ─ ECLSS ─ motor orbital ─ gemelo S.H.A.R.E. ─ IA TFLite ─ gateway (backend/engines/)
```

El frontend **solo dibuja**; toda la lógica y los números vienen del backend.

## Estructura

```text
astro-health/
├── run.py                    # python run.py  -> http://127.0.0.1:8000
├── requirements.txt
├── backend/
│   ├── server.py             # FastAPI: REST + WebSocket + sirve el frontend
│   ├── runtime.py            # SimulationRuntime: orquesta los motores de A (tick de 1 s)
│   ├── scenarios.py          # qué hace cada botón (crisis ECLSS, velocidad ECG, blackout, gravedad, perfil)
│   └── engines/              # PROYECTO A tal cual: dsp, ai, eclss, twin, gateway, rules.yaml, app.py (Streamlit)…
├── frontend/                 # PROYECTO B
│   ├── index.html
│   ├── css/styles.css
│   ├── js/  main.js · api.js (nuevo) · state.js · scenarios.js (solo presentación) · ui.js · ecg.js
│   └── assets/anatomia_azul.png
├── data/                     # pon aquí 100.csv (MIT-BIH); se crean las bases SQLite
└── models/                   # model_quantized.tflite se genera aquí
```

## Ejecutar

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

- **Mosquitto es opcional.** Si no está en `127.0.0.1:1883`, el gateway usa `pipeline_engine.py` (SQLite + FIFO) con la misma interfaz.
- **TensorFlow es opcional.** Descomenta `tensorflow-cpu` para activar la CNN; se carga la primera vez que enciendes "Usar IA".
- **Consola Streamlit original (opcional):** `cd backend/engines && streamlit run app.py`.
- Si abres `frontend/index.html` con Live Server (otro puerto): `index.html?api=http://127.0.0.1:8000`.

## Qué botón dispara qué

| Botón | ECLSS (A) | ECG | Otros |
|---|---|---|---|
| Nominal | NORMAL | ×1.0 (~72 bpm) | reinicia el gemelo |
| 1 Radiación | SPE_EVENT | ×1.79 | |
| 2 Aislamiento | NORMAL | ×1.22 | envía mini‑test mental PHQ‑2/GAD‑2 al gemelo |
| 3 Distancia | NORMAL | ×1.75 | **blackout** del gateway (FIFO) |
| 4 Gravedad | NORMAL | ×1.875 | gravedad 0.38 g al motor orbital |
| 5 Entorno | CO2_LEAK | ×1.5 | |

El selector de órbita fija altitud (420 km / 384 400 km / 225 000 000 km) y 0.38 g en "Superficie Marte".

## Qué es real y qué es simulado

- **Medido por los motores de A:** FC, SDNN, RMSSD (DSP sobre el ECG), SpO₂ (modelo de A a partir del CO₂), CO₂/presión/VOCs/radiación (ECLSS), dosis y riesgo (motor orbital), nivel/SHARE/contramedidas (gemelo), paquetes (gateway).
- **Simulado (marcado `SIM` en pantalla):** presión arterial, glucosa, temperatura, horas de sueño y estado de ánimo. A no los produce; vienen del `scenarios.js` original de B (ahora en `backend/scenarios.py`).
- La FC en crisis sale de acelerar el ECG fuente, no de una física real.
- "Usar IA" arranca **apagado**: sin entrenar con datos reales la CNN de A es un modelo de prueba.

## Cambios respecto a los proyectos originales

1. **`requirements.txt`:** se añade `statsmodels` (lo importa `twin.py`; faltaba en A) y `pydantic`/`pyyaml`.
2. **Umbrales de cabina recalibrados** (`runtime.py → cabin_alerts`): con los de A, el escenario NORMAL salía CRÍTICO (CO₂ 3421 ppm > 1000; 108 µSv/h por la Anomalía del Atlántico Sur > 10; VOCs 345 > 100). Ahora: CO₂ 4000/5000 ppm, radiación 150/300 µSv/h, VOCs 600 ppb. **Revísalos con quien lidera ECLSS.**
3. **ECG sintético de respaldo** con más variabilidad (±22 % en vez de ±12 %): con ±12 % el SDNN (~36 ms) quedaba bajo el umbral de 40 ms y el reposo parpadeaba entre NOMINAL y ESTRÉS. Con un `100.csv` real no se usa.
4. **Frontend:** `scenarios.js` ya no contiene datos; `ecg.js` dibuja el ECG filtrado real (gris = cruda); se añade el panel de alertas/gemelo/orbital/gateway; la temperatura ya cambia de color en alerta.

## Reparto de trabajo sugerido

| Área | Archivos |
|---|---|
| Interfaz | `frontend/index.html`, `frontend/css/styles.css` |
| Interacción | `frontend/js/ui.js`, `api.js`, `state.js` |
| Señal / ECG | `frontend/js/ecg.js`, `backend/engines/dsp_engine.py` |
| Escenarios | `backend/scenarios.py` |
| Motores | `backend/engines/*` (cada dueño sigue en su módulo) |
| Integración | `backend/runtime.py`, `backend/server.py`, este README |

> Prototipo educativo. Los valores son simulados; no usar como sistema de diagnóstico médico.
