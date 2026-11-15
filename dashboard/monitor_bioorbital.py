import json
import math
import threading
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

EARTH_RADIUS_KM = 6371.0
SOLAR_CONSTANT_WM2 = 1361.0
C_KMS = 299792.458
MU_EARTH = 398600.4418
NASA_CAREER_LIMIT_MSV = 600.0
MAGNETOPAUSE_ALT_KM = 57000.0
DISTANCE_LOG_SPAN = 8.7

# Catálogos
ZONES = [
    {"min": 0.0, "max": 100.0, "name": "Atmósfera / ascenso", "color": "#f59e0b"},
    {"min": 100.0, "max": 1300.0, "name": "Órbita baja (LEO / ISS)", "color": "#38bdf8"},
    {"min": 1300.0, "max": 9500.0, "name": "Cinturón de Van Allen interno", "color": "#ef4444"},
    {"min": 9500.0, "max": 13000.0, "name": "Ranura entre cinturones", "color": "#84cc16"},
    {"min": 13000.0, "max": 30000.0, "name": "Cinturón de Van Allen externo", "color": "#f97316"},
    {"min": 30000.0, "max": 57000.0, "name": "Órbita alta (MEO/GEO)", "color": "#a78bfa"},
    {"min": 57000.0, "max": 450000.0, "name": "Espacio cislunar (Luna)", "color": "#e2e8f0"},
    {"min": 450000.0, "max": 5.0e6, "name": "Espacio profundo (L1/L2)", "color": "#22d3ee"},
    {"min": 5.0e6, "max": 1.0e12, "name": "Tránsito interplanetario (Marte)", "color": "#f472b6"},
]

LANDMARKS = [
    ["Kármán", 100.0], ["ISS", 420.0], ["GPS", 20200.0], ["GEO", 35786.0],
    ["Luna", 378000.0], ["L2", 1.5e6], ["Marte mín.", 54.6e6], ["Marte prom.", 225.0e6],
]

SHIPS = {
    "ORION-7": {"color": "#e5e7eb", "gcr": 1.00, "trapped": 1.00, "spe": 1.00, "g": 0.0,
                "note": "Estándar: casco de aluminio con blindaje mixto."},
    "AEGIS-X": {"color": "#3b82f6", "gcr": 0.80, "trapped": 0.50, "spe": 0.35, "g": 0.0,
                "note": "Blindaje reforzado con polietileno y pared de agua."},
    "HELIOS-R": {"color": "#ef4444", "gcr": 0.97, "trapped": 0.90, "spe": 0.70, "g": 0.38,
                 "note": "Hábitat rotatorio: gravedad artificial de 0.38 g (ideal para Marte)."},
    "SOLARIS-G": {"color": "#f59e0b", "gcr": 0.95, "trapped": 0.80, "spe": 0.20, "g": 0.0,
                  "note": "Refugio blindado contra tormentas solares."},
    "NOX-D": {"color": "#6b7280", "gcr": 1.10, "trapped": 1.30, "spe": 1.40, "g": 0.0,
              "note": "Casco ligero: menos masa, menos protección."},
}

SUITS = {
    "Clásico": {"kpa": 29.6, "stiff": 0.30, "note": "Traje de 29.6 kPa: ágil, pero exige pre-respirar O₂."},
    "Intermedio": {"kpa": 41.4, "stiff": 0.50, "note": "41.4 kPa: menos pre-respiración, más rigidez."},
    "Alta presión": {"kpa": 57.2, "stiff": 0.75, "note": "57.2 kPa: casi sin riesgo de descompresión, muy rígido."},
}

SEX = {
    "hombre": {"cancer": 1.00, "ortho": 1.00},
    "mujer": {"cancer": 1.35, "ortho": 1.45},
}

CATEGORIES = {
    1: "Fisiología interna y defensas",
    2: "Gravedad, huesos, equilibrio y visión",
    3: "Presión, oxígeno y caminatas espaciales",
    4: "Mente, sueño, equipo y soporte técnico",
}
CAT_SHORT = {1: "Defensas y corazón", 2: "Huesos y visión", 3: "Presión y EVA", 4: "Mente y sueño"}

CONFIG = {
    "zones": ZONES, "landmarks": LANDMARKS, "ships": SHIPS, "suits": SUITS,
    "magnetopause_km": MAGNETOPAUSE_ALT_KM, "categories": CATEGORIES,
}

# Utilidades
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def sat(x: float, k: float) -> float:
    return 100.0 * (1.0 - math.exp(-max(0.0, x) / k))

def smoothstep(x: float) -> float:
    x = clamp(x)
    return x * x * (3.0 - 2.0 * x)

def gauss(x: float, mu: float, sigma: float) -> float:
    return math.exp(-0.5 * ((x - mu) / sigma) ** 2)

def _num(params: dict, key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return float(default)

def zone_for(alt_km: float):
    for idx, zone in enumerate(ZONES):
        if alt_km < zone["max"]:
            return idx, zone
    return len(ZONES) - 1, ZONES[-1]

def fetch_live_space_data() -> dict:
    result = {
        "source": "LIVE_NASA_ISS_API", "altitude_km": 418.0, "latitude_deg": -24.5,
        "longitude_deg": -48.0, "velocity_kms": 7.66, "geomagnetic_kp": 3.5, "solar_flux_f107": 145.0,
    }
    try:
        req = urllib.request.Request("https://api.wheretheiss.at/v1/satellites/25544", headers={"User-Agent": "NASA-Space-Apps/2.0"})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            iss = json.loads(resp.read().decode("utf-8"))
            result["altitude_km"] = round(float(iss["altitude"]), 2)
            result["latitude_deg"] = round(float(iss["latitude"]), 2)
            result["longitude_deg"] = round(float(iss["longitude"]), 2)
            result["velocity_kms"] = round(float(iss["velocity"]) / 3600.0, 3)
    except Exception:
        result["source"] = "SIMULATED_FALLBACK"
    try:
        req_nasa = urllib.request.Request("https://api.nasa.gov/DONKI/GST?api_key=DEMO_KEY", headers={"User-Agent": "NASA-Space-Apps/2.0"})
        with urllib.request.urlopen(req_nasa, timeout=3.5) as resp:
            storms = json.loads(resp.read().decode("utf-8"))
            if isinstance(storms, list) and storms:
                kp_list = storms[-1].get("allKpIndex", [])
                if kp_list:
                    result["geomagnetic_kp"] = float(kp_list[-1].get("kpIndex", 3.5))
    except Exception:
        pass
    return result

def calculate_atmospheric_density(altitude_km: float) -> float:
    if altitude_km < 0: return 1.225
    elif altitude_km <= 25: rho0, h0, scale_h = 1.225, 0.0, 7.249
    elif altitude_km <= 50: rho0, h0, scale_h = 3.899e-2, 25.0, 6.349
    elif altitude_km <= 100: rho0, h0, scale_h = 1.027e-3, 50.0, 5.582
    elif altitude_km <= 200: rho0, h0, scale_h = 5.297e-7, 100.0, 15.0
    elif altitude_km <= 500: rho0, h0, scale_h = 2.789e-10, 200.0, 45.0
    elif altitude_km <= 1000: rho0, h0, scale_h = 7.248e-13, 500.0, 85.0
    else: return 1e-16
    return rho0 * math.exp(-(altitude_km - h0) / scale_h)

def calculate_solar_geometry(utc_hour: float, lat_deg: float, lon_deg: float, alt_km: float) -> dict:
    now = datetime.now(timezone.utc)
    day_of_year = now.timetuple().tm_yday
    declination_rad = math.radians(23.44) * math.sin(math.radians((360.0 / 365.0) * (day_of_year - 81)))
    subsolar_lat = math.degrees(declination_rad)
    subsolar_lon = -15.0 * (utc_hour - 12.0)
    subsolar_lon = ((subsolar_lon + 180.0) % 360.0) - 180.0
    solar_time = utc_hour + (lon_deg / 15.0)
    hour_angle = math.radians(15.0 * (solar_time - 12.0))
    lat_rad = math.radians(lat_deg)
    sin_elev = clamp(math.sin(lat_rad) * math.sin(declination_rad) + math.cos(lat_rad) * math.cos(declination_rad) * math.cos(hour_angle), -1.0, 1.0)
    solar_elevation_deg = math.degrees(math.asin(sin_elev))
    horizon_dip_deg = math.degrees(math.acos(EARTH_RADIUS_KM / (EARTH_RADIUS_KM + max(0.0, alt_km))))
    in_eclipse = solar_elevation_deg < -horizon_dip_deg
    irradiance = 0.0 if in_eclipse else (SOLAR_CONSTANT_WM2 * math.exp(-0.15 * math.exp(-alt_km / 8.5)) if alt_km < 100 else SOLAR_CONSTANT_WM2)
    return {"solar_elevation_deg": round(solar_elevation_deg, 2), "subsolar_lat_deg": round(subsolar_lat, 2),
            "subsolar_lon_deg": round(subsolar_lon, 2), "in_eclipse": in_eclipse, "solar_irradiance_wm2": round(irradiance, 1)}

def earth_sky_fraction(alt_km: float) -> float:
    x = EARTH_RADIUS_KM / (EARTH_RADIUS_KM + max(0.0, alt_km))
    return (1.0 - math.sqrt(max(0.0, 1.0 - x * x))) / 2.0

def magnetic_transmission(alt_km: float, lat_deg: float, kp: float) -> float:
    if alt_km >= MAGNETOPAUSE_ALT_KM: return 1.0
    r_re = (EARTH_RADIUS_KM + max(0.0, alt_km)) / EARTH_RADIUS_KM
    cos_l = max(0.08, math.cos(math.radians(min(85.0, abs(lat_deg)))))
    shell = r_re / (cos_l ** 2)
    l_lo, l_hi = 3.0 - 0.15 * kp, 8.0 - 0.45 * kp
    t = clamp((shell - l_lo) / (l_hi - l_lo))
    near_mp = smoothstep((alt_km - 20000.0) / (MAGNETOPAUSE_ALT_KM - 20000.0))
    return max(0.03, t, near_mp)

def radiation_components(alt_km, lat_deg, lon_deg, f107, kp, spe_level, ship, eva) -> dict:
    alt_km = max(0.0, alt_km)
    r_re = (EARTH_RADIUS_KM + alt_km) / EARTH_RADIUS_KM
    cos_l = max(0.08, math.cos(math.radians(min(85.0, abs(lat_deg)))))
    shell = r_re / (cos_l ** 2)
    trans = magnetic_transmission(alt_km, lat_deg, kp)
    sky = earth_sky_fraction(alt_km)
    atm = max(0.002, math.exp(-(100.0 - alt_km) / 16.0)) if alt_km < 100 else 1.0
    modulation = 1.25 - 0.5 * clamp((f107 - 65.0) / 235.0)
    gcr = 75.0 * modulation * (1.0 - sky) * (0.35 + 0.65 * trans)
    in_mag = alt_km < MAGNETOPAUSE_ALT_KM
    inner = 6000.0 * gauss(shell, 1.65, 0.30) * smoothstep((r_re - 1.12) / 0.30) if in_mag else 0.0
    outer = (2500.0 * (1.0 + 0.15 * kp) * gauss(shell, 4.7, 0.75) * smoothstep((r_re - 1.4) / 2.0)) if in_mag else 0.0
    belts = inner + outer
    d_lat = (lat_deg + 30.0) / 22.0
    d_lon = ((lon_deg + 45.0 + 180.0) % 360.0 - 180.0) / 35.0
    saa_index = math.exp(-0.5 * (d_lat ** 2 + d_lon ** 2))
    saa = 0.0
    if alt_km > 150.0:
        gain = min(6.0, (alt_km / 420.0) ** 1.5)
        taper = 1.0 if alt_km <= 1500.0 else math.exp(-(alt_km - 1500.0) / 1500.0)
        saa = 90.0 * saa_index * smoothstep((alt_km - 150.0) / 200.0) * gain * taper
    spe_base = [0.0, 150.0, 800.0, 4000.0, 20000.0, 80000.0][int(clamp(spe_level, 0, 5))]
    spe = spe_base * trans * (1.0 - sky)
    gcr_f = ship["gcr"] * (1.05 if eva else 1.0)
    trap_f = ship["trapped"] * (3.0 if eva else 1.0)
    spe_f = ship["spe"] * (4.0 if eva else 1.0)
    comps = {"gcr": gcr * gcr_f * atm, "belts": belts * trap_f * atm, "saa": saa * trap_f * atm, "spe": spe * spe_f * atm}
    comps["total"] = comps["gcr"] + comps["belts"] + comps["saa"] + comps["spe"]
    comps["saa_index"] = saa_index
    comps["shell"] = shell
    comps["trans"] = trans
    return comps

def radiation_profile(lat_deg, lon_deg, f107, kp, spe_level, ship, eva, points: int = 120) -> list:
    out = []
    for i in range(points):
        s = i / (points - 1)
        d = 10 ** (s * DISTANCE_LOG_SPAN) - 1.0
        rate = radiation_components(d, lat_deg, lon_deg, f107, kp, spe_level, ship, eva)["total"]
        out.append([round(d, 1), round(rate, 2)])
    return out

def analyze_mission_telemetry(params: dict) -> dict:
    # Extraer parámetros (con valores por defecto)
    alt_km = clamp(_num(params, "altitude_km", 415.0), 0.0, 5.0e8)
    lat_deg = clamp(_num(params, "latitude_deg", -25.0), -90.0, 90.0)
    lon_deg = clamp(_num(params, "longitude_deg", -48.0), -180.0, 180.0)
    vel_kms = clamp(_num(params, "velocity_kms", 7.66), 0.0, 20.0)
    utc_hour = clamp(_num(params, "utc_hour", 16.0), 0.0, 24.0)
    f107 = clamp(_num(params, "solar_flux_f107", 150.0), 60.0, 350.0)
    kp = clamp(_num(params, "geomagnetic_kp", 3.5), 0.0, 9.0)
    spe_level = int(clamp(_num(params, "spe_level", 0), 0, 5))
    co2 = clamp(_num(params, "cabin_co2_mmhg", 2.8), 0.0, 20.0)
    press = clamp(_num(params, "cabin_pressure_kpa", 101.3), 20.0, 150.0)
    o2_pct = clamp(_num(params, "cabin_o2_pct", 21.0), 10.0, 100.0)
    prebreathe = clamp(_num(params, "prebreathe_min", 0.0), 0.0, 600.0)
    eva = str(params.get("eva", "0")).lower() in ("1", "true", "yes")
    days = int(clamp(_num(params, "mission_days", 45), 0, 2000))
    g_slider = clamp(_num(params, "gravity_g", 0.0), 0.0, 1.0)
    exercise_h = clamp(_num(params, "exercise_h", 2.0), 0.0, 6.0)
    sleep_h = clamp(_num(params, "sleep_h", 7.0), 2.0, 12.0)
    crew = int(clamp(_num(params, "crew_size", 4), 1, 12))
    workload = clamp(_num(params, "workload_pct", 50.0), 0.0, 100.0)

    phase = params.get("phase", "orbita")
    if phase not in ("ascenso", "orbita", "reentrada"): phase = "orbita"
    ship = SHIPS.get(params.get("ship", "ORION-7"), SHIPS["ORION-7"])
    suit = SUITS.get(params.get("suit", "Clásico"), SUITS["Clásico"])
    sex = SEX.get(params.get("sex", "hombre"), SEX["hombre"])

    zone_idx, zone = zone_for(alt_km)
    
    # Distancia, retardo (luz) y vista de la Tierra
    delay_s = (EARTH_RADIUS_KM + alt_km) / C_KMS
    earth_deg = 2.0 * math.degrees(math.asin(EARTH_RADIUS_KM / (EARTH_RADIUS_KM + alt_km)))
    earth_out_of_view = earth_deg < 1.0
    autonomy_need = min(100.0, 100.0 * math.log10(1.0 + delay_s) / math.log10(1251.0))

    # Aerodinámica y Radiación
    rho = calculate_atmospheric_density(alt_km)
    dyn_press_kpa = (0.5 * rho * ((vel_kms * 1000.0) ** 2)) / 1000.0
    solar = calculate_solar_geometry(utc_hour, lat_deg, lon_deg, alt_km)
    rad = radiation_components(alt_km, lat_deg, lon_deg, f107, kp, spe_level, ship, eva)
    
    avg_bg_rate = rad["gcr"] + rad["belts"] + 0.10 * rad["saa"]
    daily_msv = avg_bg_rate * 24.0 / 1000.0
    event_msv = rad["spe"] * 24.0 / 1000.0
    cum_msv = daily_msv * days + event_msv
    limit_pct = cum_msv / NASA_CAREER_LIMIT_MSV * 100.0
    acute_72h_msv = rad["total"] * 72.0 / 1000.0
    cancer_added_pct = cum_msv / 1000.0 * 5.0 * sex["cancer"]

    # Gravedad y Microgravedad
    g_eff = clamp(max(g_slider, ship["g"]))
    in_space = alt_km >= 100.0 or phase == "reentrada"
    mg = max(0.0, 1.0 - g_eff / 0.5) if in_space else 0.0

    # Cabina / EVA
    ppo2 = press * o2_pct / 100.0
    n2_cabin = press * (1.0 - o2_pct / 100.0)
    tissue_n2 = n2_cabin * math.exp(-prebreathe * math.log(2.0) / 360.0)
    dcs_ratio = tissue_n2 / suit["kpa"]
    dcs_prob = clamp((dcs_ratio - 1.3) / (2.7 - 1.3)) * 100.0
    hyp_prob = clamp((19.0 - ppo2) / 7.0) * 100.0
    co2_prob = clamp((co2 - 2.5) / 4.5) * 100.0

    # Factores humanos y psicológicos (A mayor distancia, mayor impacto)
    sleep_debt = max(0.0, 7.5 - sleep_h)
    iso_load = 1.0 - math.exp(-days / 180.0)
    dist_load = min(30.0, 10.0 * math.log10(1.0 + delay_s)) + (15.0 if earth_out_of_view else 0.0)
    crew_f = {1: 1.6, 2: 1.3, 3: 1.15, 4: 1.05}.get(crew, 1.0)
    psych_prob = (iso_load * 40.0 + dist_load + (workload / 100.0) * 15.0 + sleep_debt * 4.0) * crew_f
    circ_penalty = 20.0 if 100.0 <= alt_km < 2000.0 else (10.0 if alt_km >= 2000.0 else 0.0)
    sleep_prob = sleep_debt * 18.0 + max(0.0, workload - 50.0) * 0.35 + circ_penalty
    team_prob = ((crew_f - 0.95) * 40.0 + min(25.0, 9.0 * math.log10(1.0 + delay_s)) + sleep_debt * 5.0 + (workload - 50.0) * 0.25 + iso_load * 20.0)
    ex = min(1.0, exercise_h / 2.5)

    bone_loss_pct = round((days / 30.0) * 1.25 * mg * (1.0 - 0.55 * ex), 2)
    muscle_loss_pct = round(20.0 * (1.0 - math.exp(-days / 60.0)) * mg * (1.0 - 0.7 * ex), 1)
    sans_pct = 100.0 * (1.0 - math.exp(-(days / 110.0) * mg * (1.0 + 0.35 * max(0.0, co2 - 2.0)))) if in_space else 4.0

    # =========================================================================
    # ANOMALÍAS DE INGENIERÍA (ENFOCADAS EN EL ENTORNO Y DISTANCIA)
    # =========================================================================
    anomalies, eng_pts = [], []
    def anom(code, severity, detail, pts):
        anomalies.append({"code": code, "severity": severity, "detail": detail})
        eng_pts.append(pts)

    if alt_km < 80 and dyn_press_kpa > 35.0:
        anom("AERO_MAX_Q_EXCEEDED", "CRÍTICA", f"Presión dinámica ({dyn_press_kpa:.2f} kPa) supera el límite estructural (35 kPa).", 35)
    elif 150.0 <= alt_km <= 600.0 and (0.5 * rho * ((vel_kms * 1000.0) ** 2)) * (f107 / 150.0) > 5e-4:
        anom("ORBITAL_DRAG_SPIKE", "ADVERTENCIA", f"Arrastre atmosférico elevado. La atmósfera se expandió por el flujo solar (F10.7={f107:.0f}).", 20)

    if rad["saa_index"] > 0.50 and 180.0 < alt_km < 3000.0:
        anom("GEOMAG_SAA_TRANSIT", "ALTA", f"Tránsito por la Anomalía del Atlántico Sur (SAA). Índice {rad['saa_index']:.2f} ({rad['saa']:.0f} µSv/h). Riesgo de fallos lógicos en aviónica por partículas (SEU). Apagar equipos no esenciales.", 30)

    if rad["belts"] > 500.0:
        crit = rad["belts"] > 2000.0
        anom("VAN_ALLEN_DWELL", "CRÍTICA" if crit else "ALTA", f"Exposición a Cinturón de Van Allen: {rad['belts']:.0f} µSv/h. Los electrones/protones atrapados dañan la electrónica. Cruzar rápido o usar blindaje pesado.", 60 if crit else 35)

    if kp >= 6.0 and abs(lat_deg) >= 55.0 and alt_km < MAGNETOPAUSE_ALT_KM:
        anom("SOLAR_POLAR_BREACH", "CRÍTICA", f"Tormenta geomagnética (Kp={kp:.1f}) en cúspide polar. El escudo magnético se abre, atenuando enlaces de radio y permitiendo radiación.", 35)

    if spe_level >= 2 and rad["spe"] > 300.0:
        crit = acute_72h_msv >= 250.0
        anom("SOLAR_PARTICLE_EVENT", "CRÍTICA" if crit else "ALTA", f"Tormenta de partículas solares (Nivel {spe_level}): {rad['spe']:.0f} µSv/h adicionales. Apagar sistemas no vitales, refugiarse en el módulo más blindado.", 60 if crit else 25)

    if co2 > 3.5: anom("ECLSS_CO2_HIGH", "ALTA", f"ppCO₂ en {co2:.1f} mmHg excede el máximo (3.0 mmHg). Fallo en los depuradores (scrubbers).", 25)
    if press < 90.0 and ppo2 < 18.5: anom("ECLSS_DEPRESSURIZATION", "CRÍTICA", f"Presión de cabina en {press:.1f} kPa. Fuga activa detectada. Poner máscaras de O₂ y cerrar escotillas.", 35)
    elif press < 90.0: anom("CABIN_LOW_PRESSURE_STAGING", "INFORMATIVA", f"Cabina a {press:.1f} kPa. Baja presión controlada para preparar EVA.", 0)
    if eva and dcs_prob >= 45.0: anom("EVA_NO_GO_DCS", "CRÍTICA", f"EVA no recomendada: riesgo de descompresión {dcs_prob:.0f}% por falta de pre-respiración.", 30)

    if delay_s >= 3.0:
        high = delay_s >= 60.0
        anom("COMMS_LATENCY", "ALTA" if high else "ADVERTENCIA", f"Retardo de comunicación de {delay_s:.1f} s. La tripulación opera en completa autonomía; la Tierra no puede ayudar en emergencias inmediatas.", 20 if high else 10)

    if alt_km >= MAGNETOPAUSE_ALT_KM:
        anom("MAGNETOSPHERE_EXIT", "INFORMATIVA", "Nave fuera de la magnetosfera terrestre. Sin escudo natural contra rayos cósmicos (GCR). Dependencia total del blindaje de la nave.", 0)

    eng_score = min(100, sum(eng_pts))

    # =========================================================================
    # ENFERMEDADES Y PROTOCOLOS MÉDICOS (VÍNCULADOS A DISTANCIA/TIEMPO)
    # =========================================================================
    conditions = []
    cat_probs = {1: [], 2: [], 3: [], 4: []}
    def cond(cat, name, prob, why, action, min_show=10.0):
        prob = round(clamp(prob, 0.0, 100.0), 1)
        cat_probs[cat].append(prob)
        if prob < min_show: return
        sev = ("CRÍTICA" if prob >= 70 else "ALTA" if prob >= 45 else "MODERADA" if prob >= 25 else "BAJA")
        conditions.append({"category": cat, "name": name, "probability": prob, "severity": sev, "why": why, "action": action})

    # 1. Fisiología interna y defensas
    stress = clamp(0.5 * workload / 100.0 + 0.3 * sleep_debt / 3.5 + 0.2 * psych_prob / 100.0)
    cond(1, "Inmunodepresión (Herpes, EBV latente)", sat(days, 70.0) * (0.35 + 0.4 * mg) * (0.6 + 0.8 * stress),
         f"El estrés ({stress * 100:.0f}%), la ingravidez y el aislamiento debilitan las defensas tras {days} días.",
         "Monitoreo inmunológico semanal, control estricto del sueño, suplementos de Vitamina D y antivirales profilácticos si hay brotes.")
    
    cond(1, "Alteración del microbioma (Disbiosis)", sat(days, 90.0) * (0.45 + 0.35 * mg),
         "El confinamiento extremo y la dieta de tubo alteran la flora intestinal y cutánea.",
         "Dieta rica en fibra prebiótica, probióticos liofilizados, limpieza con toallitas antimicrobianas (sin alcohol).")

    cond(1, "Corazón esférico, arritmias y trombosis", sat(days, 170.0) * mg * (0.9 + 0.5 * min(1.0, cum_msv / NASA_CAREER_LIMIT_MSV)),
         f"Sin gravedad (g={g_eff:.2f}), el músculo cardíaco se atrofia y la sangre se acumula. Riesgo alto de coágulos.",
         "Ejercicio aeróbico intenso (cinta con arnés) 1h/día, medias de compresión neumática, ecografías Doppler mensuales.")

    if phase == "reentrada":
        cond(1, "Hipotensión ortostática (Desmayo al aterrizar)", sat(days, 12.0) * mg * sex["ortho"],
             "El cuerpo olvidó cómo bombear sangre contra la gravedad. Al ponerse de pie, la presión cae en picada.",
             "Traje anti-G (pantalones de compresión), ingesta masiva de sal y agua (1.5L) 2 horas antes del aterrizaje, salida en camilla.")

    cond(1, "Cáncer por radiación acumulada", limit_pct * sex["cancer"],
         f"Dosis acumulada ≈ {cum_msv:.0f} mSv ({limit_pct:.0f}% del límite NASA). Riesgo adicional de cáncer ≈ {cancer_added_pct:.1f}%.",
         "Uso de refugio blindado (tormentas), limitar EVA en órbita alta, y rotación de tripulación si el límite se acerca al 100%.")

    cond(1, "Síndrome de Irradiación Aguda (ARS)", acute_72h_msv / 700.0 * 100.0,
         f"Dosis a 72h sería ≈ {acute_72h_msv:.0f} mSv (síntomas a partir de 700 mSv). Náuseas, vómito y caída de glóbulos blancos.",
         "Refugio inmediato, antieméticos (Zofran), monitoreo de hemograma cada 6h, aislamiento para evitar infecciones.")

    # 2. Gravedad, huesos, equilibrio y visión
    cond(2, "SANS (Síndrome Neuro-ocular)", sans_pct,
         f"Fluidos hacia la cabeza + CO₂ ({co2:.1f} mmHg) causan edema en el nervio óptico y aplanamiento del globo ocular.",
         "Traje de presión negativa en piernas (LBNP) 2h/día, medir presión intraocular, usar lentes de contacto ajustables, bajar CO₂.")

    sms = mg * 100.0 * 0.7 * math.exp(-days / 4.0)
    readapt = 100.0 * mg * 0.85 * (1.0 - math.exp(-days / 10.0)) if phase == "reentrada" else 0.0
    vest_why = "Vértigo intenso al intentar caminar o pilotar tras el aterrizaje." if readapt >= sms else "Náuseas, sudoración fría y desorientación en los primeros días de vuelo."
    cond(2, "Mareo espacial y pérdida de coordinación", max(sms, readapt), vest_why,
         "Movimientos lentos de cabeza, antieméticos (Prometazina), entrenamiento en silla giratoria, prohibir pilotar en las primeras 24h post-aterrizaje.")

    cond(2, "Osteopenia (Huesos frágiles)", bone_loss_pct * 14.0,
         f"Pérdida de {bone_loss_pct:.1f}% de masa ósea en cadera/pelvis. Riesgo altísimo de fractura en impactos.",
         "Dispositivo de ejercicio resistivo (ARED) 2h/día obligatorio, suplementos de Calcio + Vitamina D, escaneo DEXA al retornar.")

    cond(2, "Atrofia muscular", muscle_loss_pct * 4.5,
         f"Pérdida de {muscle_loss_pct:.1f}% de masa muscular. Fatiga rápida y pérdida de fuerza para EVA.",
         "Ejercicio anaeróbico, dieta hiperproteica (1.5g/kg), uso de exoesqueletos suaves si la gravedad artificial es nula.")

    # 3. Presión, oxígeno y caminatas espaciales
    if eva:
        cond(3, "Enfermedad por Descompresión (DCS)", dcs_prob,
             f"N₂ en tejido/presión del traje = {dcs_ratio:.2f} (umbral 1.65). Pre-respiración de {prebreathe:.0f} min es insuficiente.",
             "Abortar EVA. Pre-respirar O₂ al 100% por 4 horas (o usar ejercicio para acelerar purga de N₂). Oxígeno hiperbárico si hay dolor articular.", min_show=0.0)

    cond(3, "Hipoxia (Falta de O₂ tisular)", hyp_prob,
         f"ppO₂ en cabina = {ppo2:.1f} kPa (normal 21). Afecta la cognición y visión.",
         "Subir fracción de O₂, usar mascarillas suplementarias, revisar generadores de O₂ (OGS).", min_show=5.0)

    cond(3, "Hipercapnia (Intoxicación por CO₂)", co2_prob,
         f"ppCO₂ de {co2:.1f} mmHg. Provoca dolores de cabeza punzantes y letargo extremo.",
         "Reemplazar cartuchos de hidróxido de litio (LiOH), ventilar módulos, reducir actividad física a mínimo.", min_show=8.0)

    if eva:
        eva_prob = 100.0 * clamp(0.35 * workload / 100.0 + 0.20 * suit["stiff"] + 0.20 * hyp_prob / 100.0 + 0.15 * co2_prob / 100.0 + 0.10 * sleep_debt / 3.5)
        cond(3, "Fatiga cognitiva en EVA", eva_prob,
             f"Rigidez del traje ({suit['stiff']*100:.0f}%), carga de trabajo {workload:.0f}%. El traje consume mucha energía física.",
             "Tareas cortas con descansos de 10 min por hora. Checklists verbales por radio. Compañero de seguridad (buddy system) observando fatiga.", min_show=0.0)

    if alt_km < 100.0 and phase in ("ascenso", "reentrada"):
        cond(3, "Sobrecarga G e intolerancia ortostática", clamp(dyn_press_kpa / 35.0) * 85.0,
             f"Presión dinámica de {dyn_press_kpa:.1f} kPa. Fuerzas G extremas comprimen el tórax.",
             "Respiración AGS (Anti-G Straining Maneuver), asiento reclinado, traje anti-G presurizado.", min_show=10.0)

    # 4. Mente, sueño, equipo y soporte técnico (CRÍTICO EN MARTE)
    cond(4, "Depresión y estrés por aislamiento", psych_prob,
         f"{days} días confinados, tripulación de {crew}. Distancia retardo mental por los {delay_s:.1f} s de latencia con la Tierra.",
         "Sesiones psicológicas semanales (con retardo), contacto familiar privado, mantener rutinas diarias estrictas y celebraciones a bordo.")

    if earth_out_of_view:
        cond(4, "Desapego (Earth-out-of-view)", min(95.0, 25.0 + 22.0 * math.log10(1.0 + delay_s)),
             f"La Tierra mide solo {earth_deg:.3g}° en el cielo. Es un punto. Los astronautas reportan una soledad profunda y existencial.",
             "Usar Realidad Virtual inmersiva con paisajes terrestres, ventanas virtuales, escribir diarios, mantener contacto con la familia programado.")

    cond(4, "Tensión interpersonal y fallos de equipo", team_prob,
         f"Tripulación de {crew}, retardo de {delay_s:.1f} s y déficit de sueño de {sleep_debt:.1f} h. Conflictos por espacios reducidos.",
         "Entrenamiento en resolución de conflictos, rotación de tareas domésticas, tener un 'mediador' designado, dar espacio personal (hipocresía de ruido).")

    cond(4, "Pérdida crónica de sueño y fatiga", sleep_prob,
         f"Duermen {sleep_h:.1f} h/día. " + ("En LEO ven 16 amaneceres/día, desajustando el ritmo circadiano." if 100.0 <= alt_km < 2000.0 else "Sin ciclo día/noche natural, el cerebro pierde la noción del tiempo."),
         "Iluminación circadiana (azul 480nm de día, ámbar de noche), melatonina, horarios fijos, tapones para oídos y antifaces.")

    cond(4, "Dependencia autónoma de soporte vital", autonomy_need,
         f"Con {delay_s:.1f} s de retardo, la Tierra no puede guiar. Si hay una fuga o fallo médico, la tripulación está sola.",
         "Protocolos de emergencia a bordo, manuales de reparación, asistente de IA a bordo, repuestos redundantes (impresión 3D).", min_show=15.0)

    conditions.sort(key=lambda c: (c["category"], -c["probability"]))

    # =========================================================================
    # VÍVERES, SUMINISTROS Y AUTONOMÍA
    # =========================================================================
    # Cálculo simple de víveres: 2.5 kg comida + 3 kg agua por persona por día
    food_needed = days * crew * 2.5
    water_needed = days * crew * 3.0
    resupply_possible = delay_s < 60.0 # Si el retardo es mayor a 1 min, reabastecer es logísticamente casi imposible
    
    supplies = {
        "food_kg": round(food_needed, 1),
        "water_l": round(water_needed, 1),
        "med_kits": math.ceil(days / 30.0), # 1 botiquín por mes
        "resupply_possible": resupply_possible,
        "status": "CRÍTICO: Misión sin retorno" if not resupply_possible else "Nominal: Posible reabastecimiento"
    }

    domains = []
    for cid, cname in CATEGORIES.items():
        ps = sorted(cat_probs[cid], reverse=True) + [0.0, 0.0]
        domains.append({"id": cid, "name": cname, "short": CAT_SHORT[cid], "score": round(0.7 * ps[0] + 0.3 * ps[1])})
    scores = [d["score"] for d in domains]
    med_score = round(0.6 * max(scores) + 0.4 * (sum(scores) / len(scores)))
    risk_score = int(min(100, round(0.7 * max(eng_score, med_score) + 0.3 * min(eng_score, med_score))))
    if any(a["severity"] == "CRÍTICA" for a in anomalies) or not resupply_possible:
        risk_score = max(risk_score, 60)
    status = "CRÍTICO" if risk_score >= 60 else ("PRECAUCIÓN" if risk_score >= 25 else "NOMINAL")

    return {
        "status": status, "risk_score": risk_score, "engineering_score": eng_score, "medical_score": med_score,
        "zone": {"index": zone_idx, "name": zone["name"], "color": zone["color"]},
        "metrics": {
            "air_density_kgm3": f"{rho:.3e}", "dynamic_pressure_kpa": round(dyn_press_kpa, 4),
            "delay_oneway_s": delay_s, "delay_round_s": 2.0 * delay_s, "earth_angular_deg": earth_deg,
            "earth_out_of_view": earth_out_of_view, "l_shell": round(rad["shell"], 2),
            "magnetic_transmission": round(rad["trans"], 3), "saa_index": round(rad["saa_index"], 3),
            "g_effective": round(g_eff, 2), "ppo2_kpa": round(ppo2, 1), "dcs_ratio": round(dcs_ratio, 2),
            "sleep_debt_h": round(sleep_debt, 1), "autonomy_need_pct": round(autonomy_need, 1),
            "sans_risk_pct": round(sans_pct, 1), "bone_loss_pct": bone_loss_pct, "muscle_loss_pct": muscle_loss_pct,
            **solar,
        },
        "radiation": {
            "gcr": round(rad["gcr"], 2), "belts": round(rad["belts"], 2),
            "saa": round(rad["saa"], 2), "spe": round(rad["spe"], 2), "total": round(rad["total"], 2),
            "daily_msv": round(daily_msv, 3), "event_msv": round(event_msv, 2),
            "cum_msv": round(cum_msv, 1), "limit_pct": round(limit_pct, 1),
            "acute_24h_msv": round(rad["total"] * 24.0 / 1000.0, 1), "acute_72h_msv": round(acute_72h_msv, 1), "cancer_added_pct": round(cancer_added_pct, 2),
        },
        "supplies": supplies, # NUEVO: Víveres
        "domains": domains, "anomalies": anomalies, "conditions": conditions,
        "profile": {
            "current": radiation_profile(lat_deg, lon_deg, f107, kp, spe_level, ship, eva),
            "equator": radiation_profile(0.0, -45.0, f107, kp, spe_level, ship, eva),
        },
    }

def fmt_time(seconds: float) -> str:
    if seconds < 1: return f"{seconds * 1000:.0f} ms"
    if seconds < 120: return f"{seconds:.1f} s"
    if seconds < 7200: return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"

# ==============================================================================
# INTERFAZ WEB
# ==============================================================================
HTML_DASHBOARD = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>NASA Space Apps · Monitor Bio-Orbital (Distancia y Salud)</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #050912; --panel: #0a1628; --line: #14466b; --accent: #22d3ee; --ice: #7dd3fc;
    --text: #e6f1ff; --muted: #8aa4c2; --ok: #10b981; --warn: #f59e0b; --crit: #ef4444;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px; color: var(--text); min-height: 100vh;
    font-family: 'Rajdhani', 'Segoe UI', sans-serif; font-weight: 500; line-height: 1.35;
    background: radial-gradient(ellipse at 15% -10%, #0c2f55 0%, transparent 52%), radial-gradient(ellipse at 95% 105%, #0e2748 0%, transparent 48%), var(--bg);
  }
  header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; padding-bottom: 12px; margin-bottom: 14px; border-bottom: 1px solid var(--line); }
  h1 { margin: 0; font-size: 1.55rem; font-weight: 700; color: var(--accent); }
  header small { color: var(--muted); font-size: .98rem; }
  #src { display: inline-block; margin-left: 8px; color: var(--ice); font-size: .85rem; }
  
  .presets { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; max-width: 760px; }
  .presets button, .zone-btns button { background: #0b1b30; color: var(--text); border: 1px solid #1d4f78; padding: 6px 11px; border-radius: 4px; cursor: pointer; font-size: .92rem; font-weight: 600; transition: background .15s, border-color .15s; font-family: inherit; }
  .presets button:hover, .zone-btns button:hover { background: #0a4a6e; border-color: var(--accent); }

  .kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 14px; }
  .kpi { position: relative; background: linear-gradient(180deg, rgba(14,30,54,.9), rgba(8,17,32,.92)); border: 1px solid #12395a; border-left: 3px solid var(--accent); border-radius: 4px; padding: 9px 12px; }
  .kpi .label { font-size: .85rem; color: var(--muted); }
  .kpi .val { font-size: 1.5rem; font-weight: 700; line-height: 1.15; margin-top: 2px; }
  .kpi .sub { font-size: .85rem; color: var(--ice); margin-top: 2px; }
  .kpi.s-crit { border-left-color: var(--crit); } .kpi.s-warn { border-left-color: var(--warn); } .kpi.s-ok { border-left-color: var(--ok); }

  .main-grid { display: grid; grid-template-columns: 330px minmax(0, 1.5fr) minmax(0, 1.05fr); gap: 14px; align-items: start; }
  .panel { position: relative; background: linear-gradient(180deg, rgba(14,30,54,.88), rgba(8,17,32,.92)); border: 1px solid #14466b; border-radius: 4px; padding: 14px; margin-bottom: 14px; box-shadow: 0 0 22px rgba(14,116,144,.16); }
  .panel h2 { margin: 0 0 10px; font-size: 1.05rem; font-weight: 700; color: var(--ice); border-bottom: 1px solid #12395a; padding-bottom: 7px; }
  .side, .health { position: sticky; top: 10px; max-height: calc(100vh - 24px); overflow-y: auto; scrollbar-width: thin; scrollbar-color: #1d4f78 transparent; }

  .lbl { font-size: .9rem; color: var(--muted); margin: 10px 0 5px; }
  .seg { display: flex; flex-wrap: wrap; gap: 6px; }
  .seg button { flex: 1 1 auto; background: #0b1b30; border: 1px solid #1d4f78; color: var(--text); padding: 7px 9px; border-radius: 4px; cursor: pointer; font-size: .92rem; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 6px; font-family: inherit; }
  .seg button:hover { border-color: var(--ice); }
  .seg button.on { border-color: var(--accent); background: #0e2c4a; box-shadow: 0 0 10px rgba(34,211,238,.4); }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; border: 1px solid rgba(255,255,255,.4); }
  .note { font-size: .88rem; color: var(--muted); margin-top: 5px; min-height: 1.2em; }
  .switch { display: flex; gap: 8px; align-items: center; margin: 12px 0 4px; font-size: .98rem; cursor: pointer; }
  .switch input, .chk input { accent-color: var(--accent); width: 16px; height: 16px; }

  details { border-top: 1px solid #12395a; margin-top: 10px; padding-top: 8px; }
  summary { cursor: pointer; font-weight: 700; color: var(--ice); font-size: 1rem; margin-bottom: 6px; }
  .control { margin-bottom: 9px; transition: opacity .2s; }
  .control label { display: flex; justify-content: space-between; font-size: .92rem; margin-bottom: 2px; }
  .control label b { color: var(--accent); font-weight: 700; }
  input[type=range] { width: 100%; accent-color: var(--accent); }

  canvas { width: 100%; height: auto; display: block; background: #03060d; border: 1px solid #12304d; border-radius: 4px; }
  #ruler { cursor: pointer; }
  .dist-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin: 8px 0; }
  .dist-row input[type=number] { width: 170px; background: #07111f; color: var(--text); border: 1px solid #1d4f78; border-radius: 4px; padding: 6px 8px; font: inherit; font-weight: 700; font-size: 1.05rem; }
  .equiv { color: var(--ice); font-size: .95rem; }
  .zone-btns { display: flex; flex-wrap: wrap; gap: 6px; }
  .zone-name { font-weight: 700; }

  .stack { display: flex; height: 12px; border-radius: 3px; overflow: hidden; background: #0b1b30; margin-top: 10px; }
  .stack i { display: block; height: 100%; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: .88rem; color: var(--muted); margin-top: 7px; }
  .legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }

  .tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  .tile { background: #07111f; border: 1px solid #12395a; border-radius: 4px; padding: 7px 9px; }
  .tile span { display: block; font-size: .8rem; color: var(--muted); }
  .tile b { font-size: 1.1rem; }

  .alert-box { padding: 9px 11px; border-radius: 4px; margin-bottom: 8px; font-size: .95rem; border-left: 4px solid; }
  .crit { background: rgba(220,38,38,.16); border-color: #ef4444; }
  .warn { background: rgba(245,158,11,.16); border-color: #f59e0b; }
  .info { background: rgba(56,189,248,.12); border-color: #38bdf8; }
  .ok { background: rgba(16,185,129,.16); border-color: #10b981; }

  .doms { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; margin-bottom: 4px; }
  .dom-top { display: flex; justify-content: space-between; font-size: .92rem; }
  .bar { height: 7px; background: #0b1b30; border-radius: 4px; overflow: hidden; margin-top: 3px; }
  .bar i { display: block; height: 100%; border-radius: 4px; transition: width .25s; }
  .bar.g i { background: var(--ok); } .bar.y i { background: var(--warn); } .bar.r i { background: var(--crit); }

  .cat-head { display: flex; justify-content: space-between; margin: 14px 0 6px; font-weight: 700; color: var(--ice); border-bottom: 1px solid #12395a; padding-bottom: 4px; font-size: .98rem; }
  .cond { padding: 9px 11px; border-radius: 4px; margin-bottom: 8px; border-left: 4px solid; background: rgba(10,26,46,.8); }
  .cond.CRITICA { border-color: #ef4444; background: rgba(220,38,38,.15); }
  .cond.ALTA { border-color: #f97316; background: rgba(249,115,22,.13); }
  .cond.MODERADA { border-color: #f59e0b; background: rgba(245,158,11,.11); }
  .cond.BAJA { border-color: #38bdf8; }
  .cond-top { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
  .cond-top strong { font-size: 1rem; line-height: 1.2; }
  .cond-top .prob { font-weight: 700; color: var(--text); white-space: nowrap; }
  .cond p { margin: 5px 0 0; font-size: .9rem; color: #c3d4ea; }
  .cond p b { color: var(--ice); }

  @media (max-width: 1250px) { .main-grid { grid-template-columns: 1fr; } .side, .health { position: static; max-height: none; } .kpis { grid-template-columns: repeat(3, 1fr); } }
</style>
</head>
<body>
  <header>
    <div>
      <h1>🚀 NASA SPACE APPS · DISTANCIA Y SALUD ORBITAL</h1>
      <small>Mueve la distancia para simular el impacto en suministros, radiación y protocolos médicos.<span id="src"></span></small>
    </div>
    <div class="presets" id="presets"></div>
  </header>

  <div class="kpis" id="kpis"></div>

  <div class="main-grid">
    <aside class="panel side">
      <h2>TRIPULACIÓN Y ENTORNO</h2>
      <div class="lbl">Tripulante</div><div class="seg" id="seg_sex"></div>
      <div class="lbl">Modelo de nave</div><div class="seg" id="seg_ship"></div><div class="note" id="ship_note"></div>
      <div class="lbl">Estilo del traje</div><div class="seg" id="seg_suit"></div><div class="note" id="suit_note"></div>
      <label class="switch"><input type="checkbox" id="eva"> Caminata espacial (EVA) en curso</label>
      <div id="sliders"></div>
    </aside>

    <main>
      <section class="panel">
        <h2>DISTANCIA A LA TIERRA (SIMULADOR)</h2>
        <canvas id="ruler" width="720" height="112"></canvas>
        <input id="dist_slider" type="range" min="0" max="1000" step="1" style="margin-top: 10px;">
        <div class="dist-row">
          <label>Distancia manual <input id="dist_num" type="number" min="0" max="500000000" step="any"> km</label>
          <div class="equiv" id="dist_equiv"></div>
        </div>
        <div class="zone-btns" id="zone_btns" style="margin-top: 10px;"></div>
      </section>

      <section class="panel">
        <h2>VÍVERES, RECURSOS Y AUTONOMÍA</h2>
        <div id="supplies_panel"></div>
      </section>

      <section class="panel">
        <h2>ANOMALÍAS DE INGENIERÍA Y ENTORNO</h2>
        <div id="anomalies_list"></div>
      </section>

      <section class="panel">
        <h2>RADIACIÓN SEGÚN LA DISTANCIA</h2>
        <canvas id="prof" width="720" height="250"></canvas>
        <div id="rad_break"></div>
      </section>
    </main>

    <aside class="panel health">
      <h2>ENFERMEDADES Y PROTOCOLOS DE ACCIÓN</h2>
      <div class="doms" id="domains"></div>
      <div id="medical_list"></div>
    </aside>
  </div>

<script>
  const CFG = __CONFIG__;
  const $ = id => document.getElementById(id);
  const R_E = 6371.0, C_KMS = 299792.458, AU_KM = 149597870.7, MU = 398600.4418, DLOG = 8.7, DMAX = 5e8, RULER_PAD = 18;
  const clampJS = (x, a, b) => Math.max(a, Math.min(b, x));
  const s2d = s => s <= 0 ? 0 : Math.pow(10, s / 1000 * DLOG) - 1;
  const d2s = d => d <= 0 ? 0 : Math.log10(d + 1) / DLOG * 1000;
  const roundSig = (x, n) => { if (x === 0) return 0; const p = Math.pow(10, n - Math.ceil(Math.log10(Math.abs(x)))); return Math.round(x * p) / p; };

  function fmtKm(d) {
    if (d >= 1e6) return (d / 1e6).toLocaleString('es', { maximumFractionDigits: d < 1e7 ? 2 : 1 }) + ' M km';
    if (d >= 100) return Math.round(d).toLocaleString('es') + ' km';
    return d.toLocaleString('es', { maximumFractionDigits: 1 }) + ' km';
  }
  function fmtTime(s) {
    if (s < 1) return (s * 1000).toFixed(0) + ' ms';
    if (s < 120) return s.toFixed(1) + ' s';
    if (s < 7200) return (s / 60).toFixed(1) + ' min';
    return (s / 3600).toFixed(1) + ' h';
  }
  const fmtDeg = a => a >= 10 ? a.toFixed(0) + '°' : a >= 0.1 ? a.toFixed(1) + '°' : a.toPrecision(2) + '°';
  const zoneOf = d => CFG.zones.find(z => d >= z.min && d < z.max) || CFG.zones[CFG.zones.length - 1];

  const DEFAULTS = { dist: 415, lat: -26, lon: -46, vel: 7.66, autoVel: true, utc: 16, f107: 165, kp: 4, spe: 0, press: 101.3, o2: 21, co2: 4.1, prebreathe: 0, eva: false, days: 65, g: 0, ex: 2, sleep: 6.5, crew: 4, work: 60, phase: 'orbita' };
  const S = Object.assign({ sex: 'hombre', ship: 'ORION-7', suit: 'Clásico' }, DEFAULTS);

  const SPE_LABELS = ['0 · sin evento', '1 · menor', '2 · moderado', '3 · fuerte', '4 · severo', '5 · extremo'];
  const SLIDERS = [
    { group: 'Posición y órbita', items: [
      { id: 'lat', label: 'Latitud', min: -90, max: 90, step: 0.5, fmt: v => v.toFixed(1) + '°' },
      { id: 'lon', label: 'Longitud', min: -180, max: 180, step: 0.5, fmt: v => v.toFixed(1) + '°' },
      { id: 'vel', label: 'Velocidad', min: 0, max: 11.2, step: 0.05, fmt: v => v.toFixed(2) + ' km/s', extra: '<label class="chk"><input type="checkbox" id="autoVel"> Velocidad orbital automática</label>' },
      { id: 'utc', label: 'Hora UTC', min: 0, max: 23, step: 1, fmt: v => v + ' h' } ] },
    { group: 'Clima espacial', items: [
      { id: 'f107', label: 'Flujo solar F10.7', min: 65, max: 300, step: 5, fmt: v => v },
      { id: 'kp', label: 'Índice geomagnético Kp', min: 0, max: 9, step: 0.5, fmt: v => v.toFixed(1) },
      { id: 'spe', label: 'Tormenta de partículas solares', min: 0, max: 5, step: 1, fmt: v => SPE_LABELS[v] } ] },
    { group: 'Cabina y EVA', items: [
      { id: 'press', label: 'Presión de cabina', min: 60, max: 105, step: 0.5, fmt: v => v.toFixed(1) + ' kPa' },
      { id: 'o2', label: 'Oxígeno en cabina', min: 18, max: 35, step: 0.5, fmt: v => v.toFixed(1) + ' %' },
      { id: 'co2', label: 'CO₂ de cabina', min: 0.5, max: 8, step: 0.1, fmt: v => v.toFixed(1) + ' mmHg' },
      { id: 'prebreathe', label: 'Pre-respiración de O₂', min: 0, max: 300, step: 5, fmt: v => v + ' min' } ] },
    { group: 'Factores Humanos', items: [
      { id: 'days', label: 'Días en misión', min: 0, max: 900, step: 1, fmt: v => v + ' d' },
      { id: 'g', label: 'Gravedad local', min: 0, max: 1, step: 0.01, fmt: v => v.toFixed(2) + ' g' },
      { id: 'ex', label: 'Ejercicio diario', min: 0, max: 4, step: 0.1, fmt: v => v.toFixed(1) + ' h' },
      { id: 'sleep', label: 'Sueño por noche', min: 3, max: 9, step: 0.1, fmt: v => v.toFixed(1) + ' h' },
      { id: 'crew', label: 'Tamaño de la tripulación', min: 1, max: 8, step: 1, fmt: v => v },
      { id: 'work', label: 'Carga de trabajo', min: 0, max: 100, step: 5, fmt: v => v + ' %' } ] },
  ];

  const SCEN = {
    iss: { label: '🛰️ LEO (ISS 420km)', v: { dist: 420, lat: -26, lon: -46, days: 45, crew: 4, sleep: 7, work: 50 } },
    van_allen: { label: '☢️ Van Allen', v: { dist: 3800, lat: 0, lon: -45, co2: 2.6, days: 3, ex: 1, work: 60 } },
    moon: { label: '🌙 Luna', v: { dist: 378000, f107: 100, kp: 2, co2: 2.6, days: 12, ex: 2, sleep: 7, work: 55 } },
    mars_transit: { label: '🔴 Tránsito a Marte', v: { dist: 225000000, f107: 110, kp: 1.5, spe: 2, co2: 3.0, days: 200, ex: 2.5, sleep: 6.5, crew: 6, work: 55, ship: 'HELIOS-R' } },
    mars_surface: { label: '🔴 Superficie Marciana', v: { dist: 225000000, f107: 110, kp: 1.5, co2: 2.8, days: 500, ex: 2, sleep: 7, crew: 4, work: 40, g: 0.38 } }
  };
  const ZONE_BTNS = [['ISS · 420 km', 420], ['Van Allen · 3.800 km', 3800], ['Luna · 378.000 km', 378000], ['Marte · 225 M km', 225e6]];

  function setScenario(v) { Object.assign(S, DEFAULTS, v); update(); }
  async function loadLiveNASA() {
    try {
      const d = await (await fetch('/api/live')).json();
      $('src').textContent = ' · Fuente: ' + d.source;
      setScenario({ dist: d.altitude_km, lat: d.latitude_deg, lon: d.longitude_deg, vel: d.velocity_kms, autoVel: false, utc: new Date().getUTCHours(), f107: d.solar_flux_f107, kp: d.geomagnetic_kp, co2: 2.7, days: 45 });
    } catch (e) { $('src').textContent = ' · No se pudo leer /api/live'; }
  }

  function buildControls() {
    $('sliders').innerHTML = SLIDERS.map(g => `<details open><summary>${g.group}</summary>${g.items.map(it => `
      <div class="control" id="c_${it.id}"><label for="${it.id}"><span>${it.label}</span><b id="v_${it.id}"></b></label>
      <input id="${it.id}" type="range" min="${it.min}" max="${it.max}" step="${it.step}"></div>${it.extra || ''}`).join('')}</details>`).join('');
    SLIDERS.forEach(g => g.items.forEach(it => {
      $(it.id).addEventListener('input', e => { S[it.id] = parseFloat(e.target.value); if (it.id === 'vel') S.autoVel = false; update(); });
    }));
    $('autoVel').addEventListener('change', e => { S.autoVel = e.target.checked; update(); });
    $('eva').addEventListener('change', e => { S.eva = e.target.checked; update(); });
  }
  function buildSegs() {
    const defs = { sex: [['hombre', '👨‍🚀 Hombre'], ['mujer', '👩‍🚀 Mujer']], ship: Object.keys(CFG.ships).map(k => [k, k]), suit: Object.keys(CFG.suits).map(k => [k, k]) };
    Object.entries(defs).forEach(([key, arr]) => {
      const host = $('seg_' + key);
      host.innerHTML = arr.map(([v, l]) => `<button type="button" data-val="${v}">${key === 'ship' ? '<span class="dot" style="background:' + CFG.ships[v].color + '"></span>' : ''}${l}</button>`).join('');
      host.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { S[key] = b.dataset.val; update(); }));
    });
  }
  function buildPresets() {
    $('presets').innerHTML = '<button type="button" data-k="live">📡 Datos reales ISS</button>' + Object.entries(SCEN).map(([k, s]) => `<button type="button" data-k="${k}">${s.label}</button>`).join('');
    $('presets').querySelectorAll('button').forEach(b => b.addEventListener('click', () => { b.dataset.k === 'live' ? loadLiveNASA() : setScenario(SCEN[b.dataset.k].v); }));
    $('zone_btns').innerHTML = ZONE_BTNS.map(([l, d]) => `<button type="button" data-d="${d}">${l}</button>`).join('');
    $('zone_btns').querySelectorAll('button').forEach(b => b.addEventListener('click', () => { S.dist = parseFloat(b.dataset.d); update(); }));
    $('dist_slider').addEventListener('input', e => { S.dist = roundSig(s2d(parseFloat(e.target.value)), 3); update(); });
    $('dist_num').addEventListener('change', e => { S.dist = clampJS(parseFloat(e.target.value) || 0, 0, DMAX); update(); });
    $('ruler').addEventListener('click', e => {
      const r = e.target.getBoundingClientRect(), W = e.target.width;
      const x = (e.clientX - r.left) / r.width * W;
      S.dist = roundSig(s2d(clampJS((x - RULER_PAD) / (W - 2 * RULER_PAD), 0, 1) * 1000), 3); update();
    });
  }

  function syncUI() {
    SLIDERS.forEach(g => g.items.forEach(it => { $(it.id).value = S[it.id]; $('v_' + it.id).textContent = it.fmt(S[it.id]); }));
    $('autoVel').checked = S.autoVel; $('eva').checked = S.eva;
    $('dist_slider').value = d2s(S.dist);
    if (document.activeElement !== $('dist_num')) $('dist_num').value = S.dist;
    const rr = (R_E + S.dist) / R_E, z = zoneOf(S.dist);
    $('dist_equiv').innerHTML = `<span class="zone-name" style="color:${z.color}">${z.name}</span> · ${rr.toFixed(2)} radios terrestres · retardo de luz: ${fmtTime((R_E + S.dist) / C_KMS)}` + (S.dist > 1e6 ? ` · ${(S.dist / AU_KM).toFixed(3)} UA` : '');
    ['sex', 'ship', 'suit'].forEach(k => document.querySelectorAll('#seg_' + k + ' button').forEach(b => b.classList.toggle('on', b.dataset.val === S[k])));
    $('ship_note').textContent = CFG.ships[S.ship].note; $('suit_note').textContent = CFG.suits[S.suit].note;
    ['lat', 'lon'].forEach(id => $('c_' + id).classList.toggle('dim', S.dist >= CFG.magnetopause_km));
    drawRuler();
  }

  function drawRuler() {
    const c = $('ruler'), ctx = c.getContext('2d'), W = c.width, H = c.height, P = RULER_PAD;
    const X = d => P + d2s(d) / 1000 * (W - 2 * P);
    ctx.clearRect(0, 0, W, H);
    CFG.zones.forEach(z => { const a = X(z.min), b = X(Math.min(z.max, DMAX)); ctx.fillStyle = z.color + '55'; ctx.fillRect(a, 48, b - a, 20); });
    ctx.strokeStyle = '#2d5a85'; ctx.lineWidth = 1; ctx.strokeRect(P, 48, W - 2 * P, 20);
    ctx.font = '600 11px Rajdhani, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    CFG.landmarks.forEach(([name, d], i) => {
      const x = X(d), up = i % 2 === 0;
      ctx.strokeStyle = '#8aa4c2'; ctx.beginPath(); ctx.moveTo(x, up ? 40 : 68); ctx.lineTo(x, up ? 48 : 76); ctx.stroke();
      ctx.fillStyle = '#c3d4ea'; ctx.fillText(name, x, up ? 33 : 86);
    });
    const mx = X(S.dist);
    ctx.strokeStyle = '#22d3ee'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(mx, 14); ctx.lineTo(mx, 72); ctx.stroke();
    ctx.fillStyle = '#22d3ee'; ctx.beginPath(); ctx.moveTo(mx - 6, 6); ctx.lineTo(mx + 6, 6); ctx.lineTo(mx, 16); ctx.closePath(); ctx.fill();
    ctx.textAlign = mx > W * 0.75 ? 'right' : 'left'; ctx.font = '700 12px Rajdhani, sans-serif';
    ctx.fillText(fmtKm(S.dist), mx + (mx > W * 0.75 ? -10 : 10), 12);
  }

  function drawProfile(d) {
    const c = $('prof'), ctx = c.getContext('2d'), W = c.width, H = c.height;
    const x0 = 56, x1 = W - 14, y0 = 14, y1 = H - 40;
    const X = dist => x0 + d2s(dist) / 1000 * (x1 - x0);
    const Y = v => y0 + (1 - clampJS(Math.log10(Math.max(v, 1)) / 5.4, 0, 1)) * (y1 - y0);
    ctx.clearRect(0, 0, W, H);
    CFG.zones.forEach(z => { const a = X(z.min), b = X(Math.min(z.max, DMAX)); ctx.fillStyle = z.color + '22'; ctx.fillRect(a, y0, b - a, y1 - y0); });
    ctx.font = '600 11px Rajdhani, sans-serif'; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ['1', '10', '100', '1 k', '10 k', '100 k'].forEach((t, e) => {
      const y = Y(Math.pow(10, e)); ctx.strokeStyle = '#14304d'; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
      ctx.fillStyle = '#8aa4c2'; ctx.fillText(t, x0 - 6, y);
    });
    ctx.save(); ctx.translate(12, (y0 + y1) / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillStyle = '#8aa4c2'; ctx.fillText('µSv/h', 0, 0); ctx.restore();
    ctx.textAlign = 'center';
    CFG.landmarks.forEach(([name, dist], i) => { ctx.fillStyle = '#8aa4c2'; ctx.fillText(name, X(dist), y1 + 12 + (i % 2) * 13); });
    const line = (pts, color, dash, w) => {
      ctx.beginPath(); ctx.setLineDash(dash); ctx.strokeStyle = color; ctx.lineWidth = w;
      pts.forEach((p, i) => { const x = X(p[0]), y = Y(p[1]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); ctx.setLineDash([]);
    };
    line(d.profile.equator, '#7c8da3', [5, 4], 1.5);
    line(d.profile.current, '#22d3ee', [], 2.4);
    const mx = X(S.dist), my = Y(d.radiation.total);
    ctx.strokeStyle = 'rgba(250,204,21,.7)'; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(mx, y0); ctx.lineTo(mx, y1); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#facc15'; ctx.beginPath(); ctx.arc(mx, my, 5, 0, 2 * Math.PI); ctx.fill();
    ctx.font = '700 12px Rajdhani, sans-serif'; ctx.textAlign = mx > W * 0.7 ? 'right' : 'left';
    ctx.fillText(d.radiation.total.toFixed(d.radiation.total < 100 ? 1 : 0) + ' µSv/h', mx + (mx > W * 0.7 ? -9 : 9), Math.max(y0 + 8, my - 10));
    ctx.font = '600 11px Rajdhani, sans-serif'; ctx.textAlign = 'left';
    ctx.fillStyle = '#22d3ee'; ctx.fillText('— a la latitud actual', x0 + 8, y0 + 10);
    ctx.fillStyle = '#7c8da3'; ctx.fillText('- - sobre el ecuador', x0 + 8, y0 + 24);

    const r = d.radiation, tot = Math.max(r.total, 1e-9);
    const parts = [['Rayos cósmicos', '#38bdf8', r.gcr], ['Cinturones', '#f97316', r.belts], ['SAA', '#ef4444', r.saa], ['Tormenta solar', '#facc15', r.spe]];
    $('rad_break').innerHTML = `<div class="stack">${parts.map(p => `<i style="width:${(p[2] / tot * 100).toFixed(1)}%;background:${p[1]}"></i>`).join('')}</div>
      <div class="legend">${parts.map(p => `<span><i class="sw" style="background:${p[1]}"></i>${p[0]} ${p[2].toFixed(1)} µSv/h</span>`).join('')}</div>`;
  }

  const lvl = p => p >= 60 ? 'r' : p >= 30 ? 'y' : 'g';
  const sevClass = s => s === 'CRÍTICA' ? 'CRITICA' : s;
  function kpi(label, val, sub, cls) { return `<div class="kpi ${cls || ''}"><div class="label">${label}</div><div class="val">${val}</div><div class="sub">${sub || ''}</div></div>`; }

  function render(d) {
    const m = d.metrics, r = d.radiation, z = d.zone, sup = d.supplies;
    const stCls = d.status === 'CRÍTICO' ? 's-crit' : d.status === 'PRECAUCIÓN' ? 's-warn' : 's-ok';
    
    $('kpis').innerHTML =
      kpi('Riesgo global', `${d.risk_score}/100`, `${d.status}`, stCls) +
      kpi('Distancia', fmtKm(S.dist), `<span style="color:${z.color}">${z.name}</span>`) +
      kpi('Retardo ida/vuelta', fmtTime(m.delay_oneway_s), `Autonomía: ${m.autonomy_need_pct}%`, m.delay_oneway_s >= 60 ? 's-crit' : 's-ok') +
      kpi('Radiación', `${r.total.toFixed(r.total < 100 ? 1 : 0)} µSv/h`, `Límite acumulado: ${r.limit_pct.toFixed(0)}%`, r.limit_pct >= 100 ? 's-crit' : 's-ok') +
      kpi('Tierra se ve de', fmtDeg(m.earth_angular_deg), m.earth_out_of_view ? 'Solo un punto lejano' : 'Disco visible') +
      kpi('Gravedad', `${m.g_effective} g`, m.g_effective < 0.1 ? 'Microgravedad' : 'Gravedad parcial');

    // Render de suministros
    let supHtml = `<div class="tiles" style="grid-template-columns: repeat(3, 1fr);">`;
    supHtml += `<div class="tile"><span>Comida requerida</span><b>${sup.food_kg} kg</b></div>`;
    supHtml += `<div class="tile"><span>Agua requerida</span><b>${sup.water_l} L</b></div>`;
    supHtml += `<div class="tile"><span>Botiquines médicos</span><b>${sup.med_kits} u.</b></div>`;
    supHtml += `</div>`;
    
    if (sup.resupply_possible) {
        supHtml += `<div class="alert-box ok" style="margin-top:10px;">✅ <b>Logística viable:</b> La Tierra puede enviar naves de reabastecimiento (retardo asumible).</div>`;
    } else {
        supHtml += `<div class="alert-box crit" style="margin-top:10px;">⚠️ <b>ALERTA DE AUTONOMÍA:</b> Retardo de comunicación extremo. Es IMPOSIBLE esperar reabastecimiento. Todo debe estar a bordo o reciclarse (ECLSS).</div>`;
    }
    $('supplies_panel').innerHTML = supHtml;

    drawProfile(d);

    $('anomalies_list').innerHTML = d.anomalies.length === 0
      ? '<div class="alert-box ok">✅ Subsistemas nominales.</div>'
      : d.anomalies.map(a => `<div class="alert-box ${a.severity === 'CRÍTICA' || a.severity === 'ALTA' ? 'crit' : a.severity === 'ADVERTENCIA' ? 'warn' : 'info'}"><strong>[${a.severity}] ${a.code}:</strong> ${a.detail}</div>`).join('');

    $('domains').innerHTML = d.domains.map(x => `<div><div class="dom-top"><span>${x.short}</span><b>${x.score}%</b></div><div class="bar ${lvl(x.score)}"><i style="width:${x.score}%"></i></div></div>`).join('');

    let html = '';
    d.domains.forEach(dom => {
      const list = d.conditions.filter(c => c.category === dom.id);
      html += `<div class="cat-head"><span>${dom.name}</span><span>${dom.score}%</span></div>`;
      html += list.length === 0 ? '<div class="alert-box ok">✅ Sin riesgos clínicos.</div>'
        : list.map(c => `<div class="cond ${sevClass(c.severity)}"><div class="cond-top"><strong>${c.name}</strong><span class="prob">${c.probability}% · ${c.severity}</span></div>
          <div class="bar ${lvl(c.probability)}"><i style="width:${c.probability}%"></i></div>
          <p><b>Causa:</b> ${c.why}</p><p><b>Protocolo de acción:</b> ${c.action}</p></div>`).join('');
    });
    $('medical_list').innerHTML = html;
  }

  let reqSeq = 0;
  async function update() {
    if (S.autoVel && S.dist >= 150) S.vel = clampJS(Math.sqrt(MU / (R_E + S.dist)), 0, 11.2);
    syncUI();
    const my = ++reqSeq;
    const q = new URLSearchParams({
      altitude_km: S.dist, latitude_deg: S.lat, longitude_deg: S.lon, velocity_kms: S.vel, utc_hour: S.utc,
      solar_flux_f107: S.f107, geomagnetic_kp: S.kp, spe_level: S.spe, cabin_co2_mmhg: S.co2, cabin_pressure_kpa: S.press,
      cabin_o2_pct: S.o2, prebreathe_min: S.prebreathe, eva: S.eva ? 1 : 0, mission_days: S.days, gravity_g: S.g,
      exercise_h: S.ex, sleep_h: S.sleep, crew_size: S.crew, workload_pct: S.work, phase: S.phase, sex: S.sex, ship: S.ship, suit: S.suit,
    });
    try {
      const res = await fetch('/api/analyze?' + q.toString());
      const data = await res.json();
      if (my === reqSeq) render(data);
    } catch (e) {}
  }

  window.onload = () => { buildControls(); buildSegs(); buildPresets(); update(); };
</script>
</body>
</html>
"""

class MissionControlHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def _send(self, body: bytes, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
    def _send_json(self, payload: dict):
        self._send(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = HTML_DASHBOARD.replace("__CONFIG__", json.dumps(CONFIG, ensure_ascii=False))
            self._send(html.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/api/analyze":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            self._send_json(analyze_mission_telemetry(params))
        elif parsed.path == "/api/live":
            self._send_json(fetch_live_space_data())
        else:
            self.send_error(404)

def start_mission_control():
    print("=== INICIANDO SISTEMA BIO-ORBITAL (ENFOQUE DISTANCIA Y SALUD) ===")
    server = None
    port = 8050
    for candidate_port in range(8050, 8065):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate_port), MissionControlHandler)
            port = candidate_port
            break
        except OSError: continue
    if server is None:
        print("No se pudo abrir un puerto local disponible.")
        return
    url = f"http://127.0.0.1:{port}"
    print(f"\nPanel visual activo en: {url}")
    print("Presiona Ctrl + C en esta terminal para detener el servidor.")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido correctamente.")
        server.server_close()

if __name__ == "__main__":
    start_mission_control()