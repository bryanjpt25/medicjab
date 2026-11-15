"""salud_espacial.py — Capa adicional «Salud espacial»: peligro espacial → biomarcadores → lógica.

Módulo NUEVO e independiente: no importa ni modifica app.py, twin.py, rules.yaml ni los motores existentes.
Soporte a la decisión de demostración. Los umbrales marcados «demo» son provisionales y NO sustituyen
al médico de vuelo (CMO / flight surgeon). Las fuentes de cada tema están en KB[...]["fuentes"].
"""
from __future__ import annotations

NASA_CAREER_MSV = 600.0   # límite de carrera NASA (NASA-STD-3001 Vol.1, actualización 2022)
ARS_MSV = 750.0           # ≈0,75 Gy: umbral de náuseas/vómito agudos (CDC / REAC-TS)

DIST_S = {                # retardo de ida de la señal (s)
    "ISS · órbita baja": 0.0014, "Luna": 1.28, "Marte · acercamiento": 182.0,
    "Marte · distancia media": 750.0, "Marte · máxima distancia": 1337.0,
}
FASES = {                 # rangos de reposo por fase gravitatoria (umbrales demo)
    "0 g · Microgravedad": dict(g=0.0, pas=(88, 125), pad=(50, 80), fc=(45, 90)),
    "0,16 g · Luna": dict(g=0.16, pas=(92, 128), pad=(54, 82), fc=(48, 92)),
    "0,38 g · Marte": dict(g=0.38, pas=(95, 130), pad=(56, 84), fc=(50, 95)),
    "1 g · Tierra": dict(g=1.0, pas=(100, 130), pad=(60, 85), fc=(50, 100)),
}
INTERVENCIONES = [
    "Luz LED cálida (~2700 K) y de baja intensidad 2 h antes de dormir; luz fría/azulada solo en vigilia.",
    "Bloques de descanso protegidos de 20–30 min, sin tareas críticas tras la noche más corta.",
    "Respiración lenta guiada 5 min (inhalar 4 s, exhalar 6 s) antes de dormir.",
    "Anclar el horario de sueño a un solo huso (GMT/MET) en vez de seguir los ~16 amaneceres diarios.",
    "Cafeína solo por la mañana; ejercicio diario (ARED/cinta).",
    "Avisar al comandante y al psicólogo de operaciones; repetir PHQ-2/GAD-2 (página «Evaluación mental»).",
    "Hipnóticos solo con indicación médica (ver efectos secundarios en la base de conocimiento).",
]


# ------------------------------- 1. Radiación -------------------------------
def evaluar_radiacion(dosis_acum_msv, pico_usv_h, horas_pico, spe, fc, fc_alta_min, glucosa, temp):
    ev = pico_usv_h * horas_pico / 1000.0
    pct = 100.0 * dosis_acum_msv / NASA_CAREER_MSV
    evento = bool(spe) or pico_usv_h > 10.0
    sig = []
    if fc >= 90 and fc_alta_min >= 30:
        sig.append(f"FC en reposo sostenida ({fc:.0f} lpm, {fc_alta_min:.0f} min)")
    if glucosa < 70 or glucosa > 140:
        sig.append(f"glucemia alterada ({glucosa:.0f} mg/dL, estrés oxidativo/metabólico)")
    if temp >= 37.3:
        sig.append(f"febrícula ({temp:.1f} °C)")
    al = []
    if evento and len(sig) >= 2:
        al.append(("error", "Alerta preventiva de posible síndrome de radiación aguda: " + "; ".join(sig)
                   + ". Confirmar con hemograma seriado (linfocitos) y activar refugio."))
    elif evento and sig:
        al.append(("warning", f"Alerta preventiva de posible fatiga celular / estrés oxidativo: {sig[0]}."))
    elif evento:
        al.append(("info", "Pico de radiación sin señales metabólicas: vigilar FC, glucemia y temperatura cada hora."))
    elif sig:
        al.append(("info", "Señales sin pico de radiación; considerar otras causas: " + "; ".join(sig) + "."))
    if ev >= ARS_MSV:
        al.append(("error", f"Dosis del evento ≈ {ev:.0f} mSv: compatible con síndrome de radiación aguda."))
    if pct >= 100:
        al.append(("error", f"Dosis acumulada al {pct:.0f}% del límite de carrera NASA."))
    elif pct >= 75:
        al.append(("warning", f"Dosis acumulada al {pct:.0f}% del límite de carrera NASA."))
    return dict(dosis_evento_msv=ev, limit_pct=pct, evento=evento, senales=sig, alertas=al)


# ------------------------- 2. Fatiga y ritmo circadiano ---------------------
def evaluar_fatiga(dias, ref_animo=7.0, ref_fc=62.0, ref_vfc=45.0):
    """dias: lista de dicts {sueno (h), animo (1-10), fc (lpm basal), vfc (RMSSD ms)}."""
    clip = lambda x: min(1.0, max(0.0, x))
    marc, idx = [], []
    for d in dias:
        marc.append(d["sueno"] < 6 and d["animo"] <= ref_animo - 2 and d["fc"] >= ref_fc + 5)
        idx.append(round(100 * (0.35 * clip((8 - d["sueno"]) / 4) + 0.25 * clip((ref_animo - d["animo"]) / 4)
                                + 0.25 * clip((d["fc"] - ref_fc) / 15)
                                + 0.15 * clip((ref_vfc - d["vfc"]) / (ref_vfc * 0.5)))))
    racha = 0
    for m in reversed(marc):
        if not m:
            break
        racha += 1
    al, acc = [], []
    if racha > 3:
        al.append(("error", f"Fatiga conductual / desincronía circadiana: {racha} días seguidos con sueño <6 h, "
                            "ánimo en caída y FC basal elevada. Intervenciones automáticas activadas."))
        acc = INTERVENCIONES
    elif racha >= 2:
        al.append(("warning", f"Tendencia de fatiga en formación ({racha} días); se activan intervenciones al superar 3."))
    return dict(marcados=marc, indice=idx, racha=racha, alertas=al, intervenciones=acc)


# --------------------- 3. Triaje offline y latencia (Edge) ------------------
PROTOCOLOS = {
    "HIPO_INCONSCIENTE": ("Hipoglucemia grave con alteración de conciencia", [
        "Asegurar al tripulante y su vía aérea (de costado; nada por boca).",
        "Glucagón 1 mg IM/SC (o intranasal si el botiquín lo trae).",
        "Pedir ayuda a otro tripulante y registrar la hora; repetir glucemia a los 15 min.",
        "Al recuperar la conciencia: carbohidrato oral y luego uno complejo; vigilar vómito.",
        "Notificar al comandante y enviar el informe a Tierra (respuesta diferida)."]),
    "HIPO": ("Hipoglucemia (con o sin taquicardia)", [
        "Sentar al tripulante; confirmar con glucemia capilar.",
        "Regla de 15: 15–20 g de carbohidrato rápido (tabletas de glucosa o jugo).",
        "Repetir la glucemia a los 15 min; si sigue <70 mg/dL repetir el paso 2.",
        "Cuando se normalice: carbohidrato complejo y reposo; la taquicardia debería ceder.",
        "Si no cede, registrar ECG y escalar a protocolo de taquicardia."]),
    "HIPOXIA": ("Hipoxia (SpO₂ baja)", [
        "Oxígeno suplementario y verificar el sellado de mascarilla/traje.",
        "Revisar fracción de O₂ y presión de cabina (ppO₂).",
        "Reducir actividad; repetir SpO₂ cada 5 min.",
        "Si no mejora en 10 min: evacuar al módulo con aire limpio y avisar al comandante."]),
    "ARS": ("Sospecha de síndrome de radiación aguda", [
        "Llevar a toda la tripulación al refugio de mayor blindaje; suspender EVA.",
        "Anotar hora del primer vómito y la dosis acumulada de cada tripulante.",
        "Antiemético según formulario; hidratación oral/IV.",
        "Hemograma con recuento absoluto de linfocitos cada 4–6 h; aislar para prevenir infecciones.",
        "Notificar al comandante; consulta a Tierra en diferido."]),
    "ORTOSTATICA": ("Hipotensión ortostática / presíncope", [
        "Acostar al tripulante con piernas elevadas (o sujetarlo en supino en baja gravedad).",
        "Líquidos y sal por vía oral; medias/traje de compresión.",
        "Repetir PA/FC supino y de pie a los 10 min.",
        "No permitir EVA ni conducción de rover hasta pasar el test ortostático."]),
    "TAQUI": ("Taquicardia en reposo", [
        "Sentar y respirar lento/profundo; descartar dolor, fiebre, deshidratación.",
        "Verificar electrodos y registrar ECG; comparar con el registro de referencia.",
        "Revisar CO₂ de cabina antes de atribuirla a causa cardíaca.",
        "Si persiste >15 min o hay síntomas (dolor torácico, síncope): kit cardíaco y comandante."]),
    "CO2": ("CO₂ de cabina elevado", [
        "Ventilar el módulo y reemplazar/regenerar los depuradores de CO₂.",
        "Reducir la actividad física de la tripulación.",
        "Reevaluar síntomas (cefalea, disnea, somnolencia) a los 15–30 min.",
        "La pulsioximetría no detecta hipercapnia: confiar en el sensor de CO₂."]),
}


def latencia(ida_s):
    rtt = 2 * ida_s
    if rtt < 5:
        modo = "Soporte en tiempo real posible"
    elif rtt < 300:
        modo = "Soporte diferido: iniciar protocolo local y consultar en paralelo"
    else:
        modo = "MODO AUTÓNOMO: ejecutar el protocolo local; la consulta a Tierra es solo informativa"
    return dict(ida_s=ida_s, ida_vuelta_s=rtt, modo=modo, autonomo=rtt >= 300)


def triaje(glucosa, fc, pas, spo2, consciente=True, vomitos=False, co2_ppm=400.0, evento_rad=False):
    """Árbol de decisión local; devuelve [(prioridad, clave, motivo)] ordenado (1 = más urgente)."""
    h = []
    if glucosa < 54 or (glucosa < 70 and fc > 100):
        motivo = f"glucemia {glucosa:.0f} mg/dL" + (f" + taquicardia {fc:.0f} lpm" if fc > 100 else "")
        h.append((1, "HIPO" if consciente else "HIPO_INCONSCIENTE", motivo))
    if spo2 < 90:
        h.append((1, "HIPOXIA", f"SpO₂ {spo2:.0f}%"))
    if evento_rad and vomitos:
        h.append((2, "ARS", "pico de radiación + vómitos"))
    if pas < 85 and fc > 110:
        h.append((2, "ORTOSTATICA", f"PA sistólica {pas:.0f} mmHg + FC {fc:.0f} lpm"))
    if co2_ppm > 1000:
        h.append((3, "CO2", f"CO₂ {co2_ppm:.0f} ppm"))
    if fc > 120 and not any(k == "HIPO" for _, k, _ in h):
        h.append((3, "TAQUI", f"FC {fc:.0f} lpm"))
    return sorted(h)


# ------------------------ 4. Gravedad y ortostatismo ------------------------
def evaluar_ortostatico(fase, pas, pad, fc, sup=None, dias_0g=0):
    cfg = FASES[fase]
    al = []
    for nombre, v, rg, u in (("PAS", pas, cfg["pas"], "mmHg"), ("PAD", pad, cfg["pad"], "mmHg"),
                             ("FC", fc, cfg["fc"], "lpm")):
        if v < rg[0] or v > rg[1]:
            al.append(("warning", f"{nombre} {v:.0f} {u} fuera del rango de {fase} ({rg[0]}–{rg[1]})."))
    s = 0.0
    d = dict(dPAS=0.0, dPAD=0.0, dFC=0.0)
    if cfg["g"] == 0:
        al.append(("info", "En 0 g no hay estrés ortostático: el riesgo aparece al pasar a una fase con gravedad."))
    elif sup:
        d = dict(dPAS=sup["pas"] - pas, dPAD=sup["pad"] - pad, dFC=fc - sup["fc"])
        s = max(d["dPAS"] / 20, d["dPAD"] / 10, d["dFC"] / 30, 0.0)
        extra = " Riesgo mayor tras >14 días en 0 g." if dias_0g >= 14 else ""
        if s >= 1.5 or pas < 85:
            al.append(("error", "Hipotensión ortostática franca con taquicardia compensatoria." + extra))
        elif s >= 1.0:
            al.append(("warning", "Criterio de intolerancia ortostática (caída PAS ≥20 / PAD ≥10 mmHg o FC ≥+30 lpm)." + extra))
    return dict(rangos=cfg, delta=d, riesgo=min(100, round(50 * s)), alertas=al)


# --------------------- 5. Fusión ambiental-biométrica -----------------------
def fusion_ambiental(fc, animo, temp_corp, co2_ppm, temp_cab, ruido_db):
    patron = fc >= 95 and animo <= 4 and 36.0 <= temp_corp <= 37.2
    co2_alto = co2_ppm > 1000
    pasos = [("CO₂ del módulo", f"{co2_ppm:.0f} ppm", "revisar" if co2_alto else "ok"),
             ("Temperatura de cabina", f"{temp_cab:.1f} °C", "ok" if 18 <= temp_cab <= 27 else "revisar"),
             ("Ruido (demo >60 dB)", f"{ruido_db:.0f} dB", "ok" if ruido_db <= 60 else "revisar"),
             ("Causa cardíaca", f"FC {fc:.0f} lpm", "pendiente" if patron else "ok")]
    al = []
    if patron and co2_alto:
        lvl = "error" if co2_ppm > 5000 else "warning"
        al.append((lvl, "Patrón FC↑ + ánimo↓ con temperatura corporal normal y CO₂ elevado: tratar primero "
                        "la acumulación de CO₂ (ventilar/depuradores) y reevaluar antes de diagnosticar un problema cardíaco."))
    elif patron:
        al.append(("warning", "Patrón FC↑ + ánimo↓ con CO₂ normal: CO₂ descartado, continuar con evaluación "
                              "cardíaca (ECG) y revisar ruido/temperatura."))
    return dict(patron=patron, pasos=pasos, alertas=al)


# ------------------------- Base de conocimiento -----------------------------
KB = {
    "radiacion": dict(
        titulo="☢️ Radiación espacial",
        patologias=["Síndrome de radiación aguda (tras un evento SPE intenso)", "Cáncer por dosis acumulada",
                    "Cataratas", "Daño al sistema nervioso central (en estudio)", "Riesgo cardiovascular a largo plazo"],
        sintomas=["Prodrómicos (minutos a días): náuseas, vómito, anorexia, fatiga, cefalea, fiebre",
                  "Latencia aparente de bienestar y luego fase manifiesta: infecciones, sangrado, caída del cabello",
                  "Con dosis altas: diarrea, dolor abdominal, desorientación"],
        diagnostico=["Dosimetría personal y registro de la hora del primer vómito",
                     "Hemograma seriado con recuento absoluto de linfocitos (cada 2–6 h al inicio)",
                     "Linfocitos <1500/mm³ a las 48 h indican exposición relevante; <500 pronóstico malo"],
        tratamiento=["Refugio blindado y suspender EVA", "Antieméticos e hidratación", "Cuidados de soporte y aislamiento",
                     "Factores de crecimiento (G-CSF ≈5 µg/kg/día SC) si hay neutropenia; antimicrobianos y transfusiones según el caso"],
        efectos=["G-CSF: dolor óseo (frecuente), esplenomegalia (rara)", "Ondansetrón: prolongación del QT, cefalea, estreñimiento",
                 "Antibióticos: alergias y disbiosis"],
        fuentes=["CDC: Acute Radiation Syndrome, fact sheet for physicians", "López & Martín, PMC3863169",
                 "NASA-STD-3001 Vol.1 (límites de exposición)"]),
    "aislamiento": dict(
        titulo="😴 Aislamiento y confinamiento",
        patologias=["Insomnio y desincronía circadiana (~16 amaneceres/día en órbita)", "Depresión y ansiedad adaptativas",
                    "Fatiga conductual y cognitiva", "Deterioro del rendimiento y errores operativos"],
        sintomas=["Sueño <6 h (en ISS el promedio fue ≈6,1 h frente a 8,5 h programadas)", "Irritabilidad, ánimo bajo, somnolencia diurna",
                  "Falta de concentración y errores"],
        diagnostico=["Actigrafía o diario de sueño", "PHQ-2 / GAD-2 (página «Evaluación mental»)", "Variabilidad de la FC y tendencia de FC basal",
                     "Prueba de vigilancia psicomotora (PVT)"],
        tratamiento=["Iluminación tunable (más azul de día, cálida/roja de noche)", "Horario de sueño fijo y bloques de descanso",
                     "Respiración lenta, ejercicio y apoyo psicológico", "Melatonina o hipnóticos solo con indicación médica"],
        efectos=["Zolpidem/zaleplon: somnolencia residual, coordinación alterada, amnesia y conductas complejas durante el sueño",
                 "Benzodiacepinas: sedación residual y amnesia anterógrada", "Melatonina: somnolencia leve, cefalea"],
        fuentes=["Barger et al., Lancet Neurology 2014 (sueño y fármacos en astronautas)", "NASA OCHMO: sleep accommodations technical brief",
                 "ESA: ritmo circadiano del astronauta"]),
    "distancia": dict(
        titulo="🛰️ Distancia desde la Tierra",
        patologias=["Hipoglucemia grave", "Taquiarritmias", "Hipoxia", "Cualquier emergencia sin apoyo en tiempo real (retardo hasta ~22 min de ida a Marte)"],
        sintomas=["Hipoglucemia: temblor, sudoración, palpitaciones/taquicardia, hambre, confusión, convulsión o pérdida de conciencia",
                  "Taquicardia: palpitaciones, mareo, dolor torácico, síncope"],
        diagnostico=["Glucemia capilar: <70 mg/dL hipoglucemia, <54 clínicamente significativa; grave si requiere ayuda de otra persona",
                     "ECG y comparación con el registro de referencia", "SpO₂ y signos vitales seriados"],
        tratamiento=["Hipoglucemia consciente: regla de 15 (15–20 g de carbohidrato rápido, repetir a los 15 min)",
                     "Inconsciente: glucagón 1 mg IM/SC, posición de seguridad, nada por boca",
                     "Taquicardia: tratar la causa, maniobras vagales si es estable, fármacos según formulario de a bordo"],
        efectos=["Glucagón: náuseas y vómito (riesgo de aspiración), hiperglucemia de rebote", "Exceso de carbohidratos: hiperglucemia",
                 "Adenosina (si se usa): rubor, disnea breve y pausa cardíaca transitoria"],
        fuentes=["ADA: Standards of Care, hipoglucemia", "NASA-STD-3001 Vol.1 (capacidad médica autónoma)"]),
    "gravedad": dict(
        titulo="🧍 Campos gravitatorios",
        patologias=["Intolerancia ortostática post-vuelo", "Desplazamiento cefálico de fluidos (cara hinchada)",
                    "SANS (síndrome neuro-ocular asociado a vuelos espaciales)", "Pérdida ósea y atrofia muscular", "Cinetosis espacial (mareo)"],
        sintomas=["Mareo al ponerse de pie, visión borrosa, palpitaciones, presíncope o síncope", "Cara hinchada, congestión nasal y cefalea en 0 g",
                  "SANS: cambios de visión, edema del disco óptico, aplanamiento del globo ocular"],
        diagnostico=["Test ortostático: caída de PAS ≥20 o PAD ≥10 mmHg, o FC ≥+30 lpm al pasar de supino a de pie",
                     "Test de inclinación (tilt)", "Fondo de ojo, OCT, ecografía ocular y presión intraocular"],
        tratamiento=["Carga de líquidos y sal antes del descenso", "Prendas de compresión graduada, ejercicio (ARED)",
                     "Presión negativa en piernas (LBNP) en vuelo", "Fludrocortisona 0,1–0,2 mg/día o midodrina 2,5–10 mg cada 8 h (referencial)"],
        efectos=["Midodrina: hipertensión en supino, piel de gallina, retención urinaria; interacción con antieméticos y prolonga QTc",
                 "Fludrocortisona: hipopotasemia, retención de líquidos, hipertensión", "Compresión: molestia local"],
        fuentes=["NASA HRP Evidence Report: Orthostatic Intolerance During Re-exposure to Gravity", "NASA Cardiovascular and Vision Laboratory",
                 "Platts et al., midodrina tras el Space Shuttle (NTRS)"]),
    "ambiente": dict(
        titulo="🫁 Entornos hostiles / cerrados",
        patologias=["Hipercapnia (acumulación de CO₂)", "Hipoxia", "Exposición a contaminantes (VOCs)", "Estrés térmico", "Ruido y alteración del sueño"],
        sintomas=["Hipercapnia: cefalea, disnea, somnolencia, mareo, taquicardia, malestar y confusión",
                  "Hipoxia: fatiga, deterioro cognitivo y visual"],
        diagnostico=["Sensor de CO₂ del módulo antes de atribuir los síntomas a causa cardíaca",
                     "La pulsioximetría NO detecta hipercapnia", "Gasometría si hay equipo; revisión de temperatura, humedad y ruido"],
        tratamiento=["Ventilar y regenerar/reemplazar depuradores de CO₂", "Reducir la actividad física", "Oxígeno suplementario si hay hipoxia",
                     "Analgesia simple para cefalea"],
        efectos=["Oxígeno elevado y prolongado: irritación pulmonar y riesgo de incendio", "Paracetamol en exceso: toxicidad hepática"],
        fuentes=["NASA-STD-3001 Vol.2 (hábitat y salud ambiental)", "Umbrales de CO₂ de cabina del proyecto (app.py)"]),
}
