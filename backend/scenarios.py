"""Scenarios: maps UI interactions to core telemetry and simulation parameters for MEDICJAB.

Each scenario defines:
  crisis     -> key for ECLSSTelemetrySimulator.trigger_crisis (NORMAL, SPE_EVENT, CO2_LEAK, SLOW_DEPRESS)
  ecg_speed  -> ECG sampling frequency multiplier (1.0 ≈ 72 bpm) for real-time DSP triage
  blackout   -> toggles Earth communications link (gateway/FIFO)
  gravity_g  -> gravity level passed to the orbital engine
  psych      -> baseline psychological survey data passed to Bio-Twin (None if unused)
  profile    -> secondary physiological vitals simulated for crew monitoring (BP, glucose, sleep, mood, temp).
"""

PROFILE_NORMAL = dict(
    pa=(118, 76), pa_class="", pa_desc="Normal systemic perfusion",
    glu=92, glu_class="", glu_desc="Optimal glycemic control",
    temp=36.6, temp_class="", temp_desc="Stable thermoregulation",
    sleep=7.2, sleep_color="#22c55e",
    mood="Stable · Optimal (9/10)", mood_class="", mood_desc="No signs of cognitive fatigue",
    ia_class="", ia_title="NOMINAL", ia_desc="No anomalies detected",
)

SCENARIOS = {
    "normal": dict(
        crisis="NORMAL", ecg_speed=1.0, blackout=False, gravity_g=0.0, psych=None,
        profile=PROFILE_NORMAL,
    ),
    "radiacion": dict(
        crisis="SPE_EVENT", ecg_speed=1.79, blackout=False, gravity_g=0.0, psych=None,
        profile=dict(
            pa=(136, 88), pa_class="warn", pa_desc="Blood pressure elevation due to acute stress",
            glu=154, glu_class="warn", glu_desc="Hyperglycemia due to oxidative stress",
            temp=38.2, temp_class="crit", temp_desc="Low-grade fever from ionizing radiation",
            sleep=5.0, sleep_color="#f59e0b",
            mood="Acute Fatigue / Nausea (4/10)", mood_class="crit",
            mood_desc="Prodromal syndrome: hydrate and shelter",
            ia_class="crit", ia_title="SPE RADIATION", ia_desc="Shielded shelter",
        ),
    ),
    "aislamiento": dict(
        crisis="NORMAL", ecg_speed=1.22, blackout=False, gravity_g=0.0,
        psych=dict(phq2_score=4, gad2_score=4, phq9_item9=0,
                   mental_fatigue_vas=7.0, irritability_vas=7.0),
        profile=dict(
            pa=(126, 82), pa_class="", pa_desc="Upper normal limit",
            glu=114, glu_class="warn", glu_desc="Elevated cortisol due to sleep deficit",
            temp=36.5, temp_class="", temp_desc="Normal",
            sleep=3.8, sleep_color="#ef4444",
            mood="Anxious / Irritable (3/10)", mood_class="crit",
            mood_desc="16 sunrises/day disrupt melatonin cycle",
            ia_class="warn", ia_title="CIRCADIAN FATIGUE", ia_desc="Adjust lighting to 2700K",
        ),
    ),
    "distancia": dict(
        crisis="NORMAL", ecg_speed=1.75, blackout=True, gravity_g=0.0, psych=None,
        profile=dict(
            pa=(90, 56), pa_class="warn", pa_desc="Moderate hypotension",
            glu=51, glu_class="crit", glu_desc="SEVERE HYPOGLYCEMIA (<60 mg/dL)",
            temp=35.9, temp_class="warn", temp_desc="Peripheral thermal drop",
            sleep=5.8, sleep_color="#f59e0b",
            mood="Confusion / Dizziness (3/10)", mood_class="crit",
            mood_desc="Local medical autonomy active without Earth ground control",
            ia_class="crit", ia_title="OFFLINE TRIAGE", ia_desc="Administer 15g glucose",
        ),
    ),
    "gravedad": dict(
        crisis="NORMAL", ecg_speed=1.875, blackout=False, gravity_g=0.38,
        psych=None,
        profile=dict(
            pa=(78, 48), pa_class="crit", pa_desc="ACUTE ORTHOSTATIC INTOLERANCE",
            glu=90, glu_class="", glu_desc="Normal",
            temp=36.4, temp_class="", temp_desc="Normal",
            sleep=6.6, sleep_color="#22c55e",
            mood="Lightheadedness / Tunnel Vision (5/10)", mood_class="warn",
            mood_desc="Venous pooling in lower extremities",
            ia_class="crit", ia_title="0.38G HYPOTENSION", ia_desc="Activate anti-G suit",
        ),
    ),
    "entorno": dict(
        crisis="CO2_LEAK", ecg_speed=1.5, blackout=False, gravity_g=0.0, psych=None,
        profile=dict(
            pa=(138, 88), pa_class="warn", pa_desc="Cerebral vasodilation / High BP",
            glu=97, glu_class="", glu_desc="Normal",
            temp=37.5, temp_class="warn", temp_desc="Thermal stress in enclosed module",
            sleep=5.4, sleep_color="#f59e0b",
            mood="Headache / Lethargy (4/10)", mood_class="crit",
            mood_desc="Cabin-health fusion: ppCO₂ > 6.5 mmHg",
            ia_class="warn", ia_title="CABIN CO₂ ALERT", ia_desc="Purge LiOH scrubbers",
        ),
    ),
}

# Header Orbit selector mapping
ORBITS = {
    "Órbita baja":      dict(altitude_km=420.0,         gravity_g=None),
    "Tránsito Lunar":   dict(altitude_km=384_400.0,     gravity_g=None),
    "Superficie Marte": dict(altitude_km=225_000_000.0, gravity_g=0.38),
}

ASTRONAUTS = {
    "Cmdr. Rivera": "Commander",
    "Dra. Vance": "Medical Officer",
    "Ing. Sato": "Flight Engineer",
}

# Automated response protocols
PROTOCOLS = {
    "Tachycardia": ["Seat the astronaut and request slow, deep breathing",
                    "Verify electrode contact and re-acquire ECG trace",
                    "Prepare onboard cardiac emergency kit",
                    "Notify mission commander"],
    "Taquicardia": ["Seat the astronaut and request slow, deep breathing",
                    "Verify electrode contact and re-acquire ECG trace",
                    "Prepare onboard cardiac emergency kit",
                    "Notify mission commander"],
    "arrhythmia": ["Instruct astronaut to cease physical activity and rest",
                 "Re-examine ECG trace against baseline profile",
                 "Notify mission commander and flight surgeon (if link active)"],
    "SpO₂": ["Administer supplemental oxygen",
             "Verify suit / mask pressure seal",
             "Notify mission commander"],
    "CO₂": ["Inspect and replace cabin CO₂ scrubber cartridges",
            "Increase cabin atmospheric recirculation rate",
            "Reduce non-essential physical exertion"],
    "Depressurization": ["Isolate leak source (hatch seals, pressure valves)",
                         "Seal bulkheads of affected flight module",
                         "Don emergency pressure suits",
                         "Notify mission commander"],
    "Radiation": ["Relocate crew to storm-sheltered core module",
                  "Suspend extravehicular activities (EVA)",
                  "Record cumulative dosimeter exposure per astronaut",
                  "Notify mission commander"],
}

# Anatomical leg scanner descriptions
LEGS = {
    "normal": "Fluid distribution adapted to orbital microgravity.",
    "radiacion": "No peripheral vascular compromise.",
    "aislamiento": "Stable muscle tone.",
    "distancia": "Generalized physical weakness.",
    "gravedad": "Sudden blood pooling in lower limbs after months in 0g.",
    "entorno": "Normal.",
}