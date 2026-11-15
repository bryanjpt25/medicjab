"""Escenarios: qué hace cada botón del frontend sobre los motores del Proyecto A.

Cada escenario define:
  crisis     -> clave de ECLSSTelemetrySimulator.trigger_crisis (NORMAL, SPE_EVENT, CO2_LEAK, SLOW_DEPRESS)
  ecg_speed  -> factor de velocidad del ECG fuente (1.0 ≈ 72 bpm) para que el DSP mida taquicardia real
  blackout   -> corta el enlace con la Tierra (gateway/FIFO)
  gravity_g  -> gravedad que se le pasa al motor orbital
  psych      -> mini-test mental que se envía al gemelo (None = no se envía)
  profile    -> signos que el Proyecto A NO mide (PA, glucosa, sueño, ánimo, temperatura).
                SON SIMULADOS (vienen del scenarios.js original del Proyecto B).
"""

PROFILE_NORMAL = dict(
    pa=(118, 76), pa_class="", pa_desc="Perfusión sistémica normal",
    glu=92, glu_class="", glu_desc="Control glucémico óptimo",
    temp=36.6, temp_class="", temp_desc="Termorregulación estable",
    sleep=7.2, sleep_color="#22c55e",
    mood="Estable · Óptimo (9/10)", mood_class="", mood_desc="Sin signos de fatiga cognitiva",
    ia_class="", ia_title="NOMINAL", ia_desc="Sin anomalías",
)

SCENARIOS = {
    "normal": dict(
        crisis="NORMAL", ecg_speed=1.0, blackout=False, gravity_g=0.0, psych=None,
        profile=PROFILE_NORMAL,
    ),
    "radiacion": dict(
        crisis="SPE_EVENT", ecg_speed=1.79, blackout=False, gravity_g=0.0, psych=None,
        profile=dict(
            pa=(136, 88), pa_class="warn", pa_desc="Elevación tensional por estrés agudo",
            glu=154, glu_class="warn", glu_desc="Hiperglucemia por estrés oxidativo",
            temp=38.2, temp_class="crit", temp_desc="Febrícula por radiación ionizante",
            sleep=5.0, sleep_color="#f59e0b",
            mood="Fatiga Aguda / Náuseas (4/10)", mood_class="crit",
            mood_desc="Síndrome prodrómico: hidratar y resguardar",
            ia_class="crit", ia_title="RADIACIÓN SPE", ia_desc="Refugio blindado",
        ),
    ),
    "aislamiento": dict(
        crisis="NORMAL", ecg_speed=1.22, blackout=False, gravity_g=0.0,
        psych=dict(phq2_score=4, gad2_score=4, phq9_item9=0,
                   mental_fatigue_vas=7.0, irritability_vas=7.0),
        profile=dict(
            pa=(126, 82), pa_class="", pa_desc="Límite superior normal",
            glu=114, glu_class="warn", glu_desc="Cortisol elevado por déficit de sueño",
            temp=36.5, temp_class="", temp_desc="Normal",
            sleep=3.8, sleep_color="#ef4444",
            mood="Ansioso / Irritable (3/10)", mood_class="crit",
            mood_desc="16 amaneceres/día alteran ciclo de melatonina",
            ia_class="warn", ia_title="FATIGA CIRCADIANA", ia_desc="Ajustar luz 2700K",
        ),
    ),
    "distancia": dict(
        crisis="NORMAL", ecg_speed=1.75, blackout=True, gravity_g=0.0, psych=None,
        profile=dict(
            pa=(90, 56), pa_class="warn", pa_desc="Hipotensión moderada",
            glu=51, glu_class="crit", glu_desc="HIPOGLUCEMIA SEVERA (<60 mg/dL)",
            temp=35.9, temp_class="warn", temp_desc="Descenso térmico periférico",
            sleep=5.8, sleep_color="#f59e0b",
            mood="Confusión / Mareo (3/10)", mood_class="crit",
            mood_desc="Autonomía médica local activa sin Houston",
            ia_class="crit", ia_title="TRIAJE OFFLINE", ia_desc="Dar 15g glucosa",
        ),
    ),
    "gravedad": dict(
        crisis="NORMAL", ecg_speed=1.875, blackout=False, gravity_g=0.38,
        psych=None,
        profile=dict(
            pa=(78, 48), pa_class="crit", pa_desc="INTOLERANCIA ORTOSTÁTICA AGUDA",
            glu=90, glu_class="", glu_desc="Normal",
            temp=36.4, temp_class="", temp_desc="Normal",
            sleep=6.6, sleep_color="#22c55e",
            mood="Aturdimiento / Visión Túnel (5/10)", mood_class="warn",
            mood_desc="Desplazamiento venoso hacia extremidades inferiores",
            ia_class="crit", ia_title="HIPOTENSIÓN 0.38G", ia_desc="Activar traje anti-G",
        ),
    ),
    "entorno": dict(
        crisis="CO2_LEAK", ecg_speed=1.5, blackout=False, gravity_g=0.0, psych=None,
        profile=dict(
            pa=(138, 88), pa_class="warn", pa_desc="Vasodilatación cerebral / PA alta",
            glu=97, glu_class="", glu_desc="Normal",
            temp=37.5, temp_class="warn", temp_desc="Estrés térmico en módulo cerrado",
            sleep=5.4, sleep_color="#f59e0b",
            mood="Cefalea / Letargo (4/10)", mood_class="crit",
            mood_desc="Fusión cabina-salud: ppCO₂ > 6.5 mmHg",
            ia_class="warn", ia_title="ALERTA CO₂ CABINA", ia_desc="Purgar filtros LiOH",
        ),
    ),
}

# Selector "órbita" de la cabecera -> parámetros del motor orbital
ORBITS = {
    "Órbita baja":      dict(altitude_km=420.0,         gravity_g=None),
    "Tránsito Lunar":   dict(altitude_km=384_400.0,     gravity_g=None),
    "Superficie Marte": dict(altitude_km=225_000_000.0, gravity_g=0.38),
}

ASTRONAUTS = {
    "Cmdr. Rivera": "Comandante",
    "Dra. Vance": "Médico",
    "Ing. Sato": "Ingeniero",
}

# Protocolos automáticos (copiados de app.py del Proyecto A)
PROTOCOLS = {
    "Taquicardia": ["Sentar al astronauta y pedirle que respire lento y profundo",
                    "Verificar electrodos y repetir la lectura de ECG",
                    "Preparar el kit de medicación cardíaca de a bordo",
                    "Notificar al comandante de la misión"],
    "arritmia": ["Pedir al astronauta que se detenga y se siente",
                 "Repetir ECG y comparar con el registro de referencia",
                 "Notificar al comandante y al médico de vuelo (si hay enlace)"],
    "SpO₂": ["Administrar oxígeno suplementario",
             "Verificar sellado del traje / mascarilla",
             "Notificar al comandante de la misión"],
    "CO₂": ["Revisar y reemplazar los filtros de CO₂ (scrubbers)",
            "Aumentar la ventilación de la cabina",
            "Reducir la actividad física de la tripulación"],
    "Despresurización": ["Localizar la fuga (escotillas, sellos, puertos)",
                         "Cerrar las escotillas de los módulos afectados",
                         "Colocar trajes de presión a la tripulación",
                         "Notificar al comandante de la misión"],
    "Radiación": ["Mover a la tripulación al refugio con mayor blindaje",
                  "Suspender actividades extravehiculares",
                  "Registrar la dosis acumulada de cada astronauta",
                  "Notificar al comandante de la misión"],
}

# Texto de la región "extremidades" para el escáner corporal (del scenarios.js original)
LEGS = {
    "normal": "Distribución de fluidos adaptada a microgravedad orbital.",
    "radiacion": "Sin compromiso vascular periférico.",
    "aislamiento": "Tono muscular estable.",
    "distancia": "Debilidad generalizada.",
    "gravedad": "Acumulación súbita de sangre en miembros inferiores tras meses en 0g.",
    "entorno": "Normal.",
}
