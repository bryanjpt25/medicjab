import glob
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dsp_engine import MedicJabDSPEngine
from eclss_engine import ECLSSTelemetrySimulator
from shared import load_bridge

FS = 360                 # Hz (MIT-BIH)
WIN_S = 10               # segundos de ventana mostrada
N = FS * WIN_S
SEG_BEFORE, SEG_AFTER = 90, 126   # 216 muestras alrededor de cada pico R
CREW_ID = "CDR-01"

st.set_page_config(page_title="Astro Health Monitor", layout="wide")
engine = MedicJabDSPEngine(fs=FS)

# ---------------------------------------------------------------------------
# Motor oficial (Monitor Bio-Orbital). Import opcional: si no está, la app
# sigue funcionando con el simulador adaptador en modo "escenario fijo".
# ---------------------------------------------------------------------------
try:
    from monitor_bioorbital import (
        analyze_mission_telemetry,
        fetch_live_space_data,
        ZONES,
    )
    BIOORBITAL_OK = True
except Exception as _e:
    BIOORBITAL_OK = False
    BIOORBITAL_ERR = str(_e)
    ZONES = []

PROTOCOLS = {
    "Taquicardia": [
        "Sentar al astronauta y pedirle que respire lento y profundo",
        "Verificar electrodos y repetir la lectura de ECG",
        "Preparar el kit de medicación cardíaca de a bordo",
        "Notificar al comandante de la misión",
    ],
    "arritmia": [
        "Pedir al astronauta que se detenga y se siente",
        "Repetir ECG y comparar con el registro de referencia",
        "Notificar al comandante y al médico de vuelo (si hay enlace)",
    ],
    "SpO₂": [
        "Administrar oxígeno suplementario",
        "Verificar sellado del traje / mascarilla",
        "Notificar al comandante de la misión",
    ],
    "CO₂": [
        "Revisar y reemplazar los filtros de CO₂ (scrubbers)",
        "Aumentar la ventilación de la cabina",
        "Reducir la actividad física de la tripulación",
    ],
    "Despresurización": [
        "Localizar la fuga (escotillas, sellos, puertos)",
        "Cerrar las escotillas de los módulos afectados",
        "Colocar trajes de presión a la tripulación",
        "Notificar al comandante de la misión",
    ],
    "Radiación": [
        "Mover a la tripulación al refugio con mayor blindaje",
        "Suspender actividades extravehiculares",
        "Registrar la dosis acumulada de cada astronauta",
        "Notificar al comandante de la misión",
    ],
}


def synthetic_ecg(fs=FS, secs=60):
    """ECG sintético de respaldo por si todavía no tienes 100.csv."""
    rng = np.random.default_rng(1)
    base_n = int(0.83 * fs)
    x = np.linspace(0, 1, base_n)
    g = lambda c, w, a: a * np.exp(-((x - c) ** 2) / (2 * w ** 2))
    beat = (g(.20, .025, .15) + g(.37, .008, -.12) + g(.40, .010, 1.0)
            + g(.43, .008, -.25) + g(.65, .050, .30))
    out = []
    while sum(len(b) for b in out) < secs * fs:
        L = int(base_n * rng.uniform(0.88, 1.12))
        out.append(np.interp(np.linspace(0, 1, L), np.linspace(0, 1, base_n), beat))
    s = np.concatenate(out)
    return s + rng.normal(0, 0.01, len(s))


@st.cache_data
def load_signal():
    for p in ("100.csv", os.path.join("data", "100.csv")):
        if os.path.exists(p):
            df = pd.read_csv(p)
            cols = [c for c in df.columns if "MLII" in str(c)]
            col = cols[0] if cols else df.columns[1]
            s = pd.to_numeric(df[col], errors="coerce").dropna().values
            return s.astype(float), True
    return synthetic_ecg(), False


@st.cache_resource(show_spinner="Cargando modelo de IA (la primera vez puede tardar)...")
def load_ai():
    try:
        from ai_engine import DenisAIEngine
        return DenisAIEngine()
    except Exception as e:
        return str(e)


@st.cache_resource
def load_gateway():
    """Gateway de Jose: una sola instancia (hilos MQTT + SQLite + FIFO)."""
    try:
        from gateway_engine import GatewayEngine
        return GatewayEngine()
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def cabin_alerts(env):
    """Umbrales de cabina (ajústalos con Dick)."""
    a = []
    co2 = env["co2_ppm"]
    if co2 > 5000:
        a.append(("error", f"CO₂ de cabina crítico: {co2:.0f} ppm"))
    elif co2 > 1000:
        a.append(("warning", f"CO₂ de cabina elevado: {co2:.0f} ppm"))
    p = env["pressure_kpa"]
    if p < 90:
        a.append(("error", f"Despresurización crítica: {p:.1f} kPa"))
    elif p < 95:
        a.append(("warning", f"Despresurización: presión de cabina {p:.1f} kPa"))
    rad = env["radiation_usv_h"]
    if rad > 10:
        a.append(("error", f"Radiación crítica (SPE): {rad:.1f} µSv/h"))
    elif rad > 1:
        a.append(("warning", f"Radiación elevada: {rad:.2f} µSv/h"))
    if env["vocs_ppb"] > 100:
        a.append(("warning", f"VOCs elevados: {env['vocs_ppb']:.0f} ppb"))
    if not 18 <= env["temperature_c"] <= 27:
        a.append(("warning", f"Temperatura de cabina fuera de rango: {env['temperature_c']:.1f} °C"))
    return a


# ---------------------------------------------------------------------------
# Carga de módulos
# ---------------------------------------------------------------------------
sig, is_real = load_signal()
if not is_real:
    st.warning("No encontré 100.csv: usando un ECG SINTÉTICO de respaldo.")

ai = load_ai()
ai_ok = not isinstance(ai, str)
if not ai_ok:
    st.info(f"Módulo de IA no disponible (el resto funciona normal): {ai[:150]}")

gw = load_gateway()
gateway_ok = not isinstance(gw, str)
if not gateway_ok:
    st.info(f"Gateway MQTT/SQLite no disponible (¿está corriendo Mosquitto?): {gw[:200]}")

bridge = load_bridge()
bridge_ok = not isinstance(bridge, str)
if not bridge_ok:
    st.info(f"Gemelo bio-digital no disponible: {bridge[:200]}")

if not BIOORBITAL_OK:
    st.info(f"Motor orbital (Monitor Bio-Orbital) no disponible: {BIOORBITAL_ERR[:200]}")


# ---------------------------------------------------------------------------
# Estado de sesión
# ---------------------------------------------------------------------------
ss = st.session_state
if "mode" not in ss:
    ss.mode = "normal"
    ss.pos = 0.0
    ss.last = time.time()
    ss.blackout_since = None
    ss.last_sync = None
    ss.tw = None
if "sim" not in ss:
    ss.sim = ECLSSTelemetrySimulator(live=False)
    ss.pkt = ss.sim.generate_telemetry_packet()
    ss.last_pkt = time.time()
    ss.hist = []
if "orbit_alt" not in ss:
    ss.orbit_alt = 420.0
if "orbit_lat" not in ss:
    ss.orbit_lat = -26.0
if "orbit_lon" not in ss:
    ss.orbit_lon = -46.0
if "orbit_days" not in ss:
    ss.orbit_days = 45.0


def set_mode(mode):
    ss.mode = mode


def set_crisis(name):
    ss.sim.trigger_crisis(name)


def apply_orbit():
    ss.sim.set_orbital_params(
        altitude_km=ss.orbit_alt,
        latitude_deg=ss.orbit_lat,
        longitude_deg=ss.orbit_lon,
        mission_days=ss.orbit_days,
    )


def load_iss_live():
    """Trae datos reales de la ISS y los vuelca al simulador."""
    try:
        live = fetch_live_space_data()
        ss.orbit_alt = float(live["altitude_km"])
        ss.orbit_lat = float(live["latitude_deg"])
        ss.orbit_lon = float(live["longitude_deg"])
        ss.orbit_days = 45.0
        apply_orbit()
        st.toast(f"ISS real: {ss.orbit_alt:.0f} km · Kp {live['geomagnetic_kp']:.1f}")
    except Exception as e:
        st.toast(f"No se pudo leer la ISS: {e}")


def start_blackout():
    ss.blackout_since = time.time()
    ss.last_sync = None
    gw.blackout = True


def end_blackout():
    n = gw.stats()["pending"]
    gw.blackout = False
    ss.blackout_since = None
    ss.last_sync = {"n": n, "t": time.time()}


def reset_all():
    ss.mode = "normal"
    ss.sim.trigger_crisis("NORMAL")
    ss.tw = None
    ss.orbit_alt = 420.0
    ss.orbit_lat = -26.0
    ss.orbit_lon = -46.0
    ss.orbit_days = 45.0
    apply_orbit()
    if bridge_ok:
        bridge.reset()
    if gateway_ok and gw.blackout:
        end_blackout()


def banner(text, color):
    st.markdown(
        f"<div style='background:{color};padding:14px;border-radius:10px;"
        f"text-align:center;font-size:28px;font-weight:700;color:white;'>"
        f"{text}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Panel de control")
    st.selectbox("Astronauta", ["Cmdr. Rivera", "Dra. Chen", "Ing. Okafor"])
    st.selectbox("Misión", ["Órbita baja", "Tránsito a Marte"])
    st.success("Sistema local: ACTIVO (100% offline)")

    st.divider()
    st.subheader("Procesamiento de señal")
    st.checkbox("Inyectar ruido (60 Hz + movimiento)", key="noise")
    st.checkbox("Mostrar señal cruda", key="show_raw", value=True)

    st.divider()
    st.subheader("IA (TFLite)")
    st.checkbox("Usar IA para disparar alertas", key="ai_alerts", value=False,
                disabled=not ai_ok,
                help="Déjalo apagado hasta que el modelo esté entrenado con datos reales.")

    st.divider()
    st.subheader("Órbita (motor oficial)")
    if BIOORBITAL_OK:
        st.slider(
            "Altitud (km)", min_value=0, max_value=400_000,
            value=int(ss.orbit_alt), step=10, key="orbit_alt_slider",
            on_change=lambda: setattr(ss, "orbit_alt", float(ss.orbit_alt_slider)),
        )
        with st.expander("Ajustes finos de órbita", expanded=False):
            st.slider("Latitud (°)", -90.0, 90.0, float(ss.orbit_lat),
                      step=0.5, key="orbit_lat_slider",
                      on_change=lambda: setattr(ss, "orbit_lat", float(ss.orbit_lat_slider)))
            st.slider("Longitud (°)", -180.0, 180.0, float(ss.orbit_lon),
                      step=0.5, key="orbit_lon_slider",
                      on_change=lambda: setattr(ss, "orbit_lon", float(ss.orbit_lon_slider)))
            st.slider("Días de misión", 0, 900, int(ss.orbit_days),
                      step=1, key="orbit_days_slider",
                      on_change=lambda: setattr(ss, "orbit_days", float(ss.orbit_days_slider)))
            st.button("Aplicar órbita", on_click=apply_orbit, width="stretch")
        st.button("📡 Datos reales ISS", on_click=load_iss_live, width="stretch")
    else:
        st.caption("Motor orbital no disponible.")

    st.divider()
    st.subheader("Evaluación mental")
    _pages = sorted(glob.glob(os.path.join("pages", "*.py")))
    if _pages:
        st.page_link(_pages[0].replace("\\", "/"), label="Realizar evaluación mental →")
    else:
        st.caption("No encontré la carpeta pages/.")

    st.divider()
    st.subheader("Contingencias")
    st.caption("Astronauta")
    st.button("Simular Arritmia", on_click=set_mode, args=("arritmia",), width="stretch")
    st.caption("Cabina (ECLSS)")
    st.button("Fuga en depurador de CO₂", on_click=set_crisis, args=("CO2_LEAK",), width="stretch")
    st.button("Evento de partículas solares", on_click=set_crisis, args=("SPE_EVENT",), width="stretch")
    st.button("Despresurización lenta", on_click=set_crisis, args=("SLOW_DEPRESS",), width="stretch")
    st.caption("Comunicaciones")
    st.button("Simular Blackout Espacial", on_click=start_blackout, width="stretch",
              disabled=(not gateway_ok) or gw.blackout)
    st.button("Restaurar enlace con la Tierra", on_click=end_blackout, width="stretch",
              disabled=(not gateway_ok) or (not gw.blackout))
    st.divider()
    st.button("Restablecer todo", on_click=reset_all, type="primary", width="stretch")

st.title("Astro Health Monitor")


# ---------------------------------------------------------------------------
# Panel en vivo
# ---------------------------------------------------------------------------
@st.fragment(run_every=0.5)
def live_panel():
    mode = ss.mode
    now = time.time()
    blackout = gateway_ok and gw.blackout

    # --- Telemetría de cabina: un paquete por segundo ---
    new_packet = False
    if now - ss.last_pkt >= 1.0:
        ss.pkt = ss.sim.generate_telemetry_packet()
        ss.last_pkt = now
        ss.hist.append(ss.pkt["environment"])
        ss.hist = ss.hist[-90:]
        new_packet = True
    pkt = ss.pkt
    env = pkt["environment"]

    # --- Avanzar ECG ---
    speed = 1.7 if mode == "arritmia" else 1.0
    ss.pos += (now - ss.last) * FS * speed
    ss.last = now
    start, need = int(ss.pos), int(N * speed)
    seg = np.take(sig, np.arange(start, start + need), mode="wrap")
    x = np.interp(np.linspace(0, need - 1, N), np.arange(need), seg) if speed != 1 else seg

    if ss.get("noise"):
        t_abs = (start + np.arange(N)) / FS
        x = x + np.std(x) * (0.4 * np.sin(2 * np.pi * 60 * t_abs)
                             + 1.0 * np.sin(2 * np.pi * 0.25 * t_abs))

    # --- DSP ---
    res = engine.process_pipeline(x)
    filt, peaks = res["filtered_ecg"], res["r_peaks"]
    m = res["metrics"]

    # --- IA ---
    ai_res = None
    if ai_ok:
        valid = [p for p in peaks if p >= SEG_BEFORE and p + SEG_AFTER <= N]
        preds = []
        for p in valid[-5:]:
            s = filt[p - SEG_BEFORE:p + SEG_AFTER]
            s = (s - s.mean()) / (s.std() + 1e-8)
            preds.append(ai.predict_ecg_segment(s))
        if preds:
            n_arr = sum(r["prediction"] == "ARRHYTHMIA" for r in preds)
            ai_res = {
                "label": "ARRHYTHMIA" if n_arr > len(preds) / 2 else "NORMAL",
                "n_arr": n_arr, "n": len(preds),
                "conf": float(np.mean([r["confidence"] for r in preds])),
            }

    # --- SpO₂ simulado ---
    spo2 = int(max(85, 98 - max(0.0, env["co2_ppm"] - 2000) / 600))
    body_temp = 36.6

    # --- Alertas ---
    alerts = []
    if m["status"] == "CRITICAL_ALERT":
        alerts.append(("error", f"Taquicardia / HRV crítica: {m['BPM']} bpm, SDNN {m['SDNN']} ms"))
    elif m["status"] == "MODERATE_STRESS":
        alerts.append(("warning", f"Estrés moderado: {m['BPM']} bpm, SDNN {m['SDNN']} ms"))
    if ai_res and ss.get("ai_alerts") and ai_res["label"] == "ARRHYTHMIA":
        alerts.append(("error", f"IA: posible arritmia ({ai_res['n_arr']}/{ai_res['n']} latidos)"))
    if spo2 < 92:
        alerts.append(("error", f"SpO₂ crítica: {spo2}%"))
    alerts += cabin_alerts(env)

    # --- Gemelo bio-digital ---
    if bridge_ok and new_packet:
        ss.tw = bridge.step(m["BPM"], spo2, env)
    tw = ss.get("tw")
    tw_ok = bool(tw) and "error" not in tw
    if tw_ok:
        alerts += tw["alerts"]

    # --- Gateway MQTT ---
    if gateway_ok and new_packet:
        gw.publish_packet({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "crew_id": CREW_ID,
            "cabin_status": pkt["cabin_status"],
            "biometrics": {
                "heart_rate_bpm": m["BPM"], "sdnn": m["SDNN"], "rmssd": m["RMSSD"],
                "hrv_status": m["status"], "spo2_pct": spo2,
            },
            "environment": env,
            "ai": {"label": ai_res["label"], "confidence": round(ai_res["conf"], 1)}
                  if ai_res else None,
            "twin": {k: tw[k] for k in ("level", "share_index", "anomaly")}
                    if tw_ok else None,
            "alerts": [msg for _, msg in alerts],
        })

    gstats = gw.stats() if gateway_ok else {"total": 0, "pending": 0, "forwarded": 0}

    # --- Banner y enlace ---
    c_state, c_link = st.columns([3, 2])
    with c_state:
        if any(l == "error" for l, _ in alerts):
            banner("ESTADO: CRÍTICO", "#dc2626")
        elif alerts:
            banner("ESTADO: ALERTA", "#d97706")
        else:
            banner("ESTADO: NOMINAL", "#16a34a")
    with c_link:
        if blackout:
            secs = int(now - ss.blackout_since) if ss.blackout_since else 0
            st.error(f"Enlace con Tierra: PERDIDO ({secs} s)")
            st.caption(f"Modo autónomo · {gstats['pending']} paquetes retenidos en el búfer FIFO (SQLite)")
        else:
            sync = ss.last_sync
            if sync and gstats["pending"] > 0:
                st.warning(f"Enlace restablecido: retransmitiendo... {gstats['pending']} pendientes")
            elif sync and now - sync["t"] < 15:
                st.success(f"Enlace restablecido: {sync['n']} paquetes retransmitidos a la Tierra")
            else:
                st.info("Enlace con Tierra: ACTIVO (sincronizado)")
        st.caption(f"Escenario de cabina: {pkt['cabin_status']}")

    # --- Métricas del astronauta ---
    st.caption("ASTRONAUTA")
    c = st.columns(6)
    c[0].metric("Frecuencia cardíaca", f"{m['BPM']:.0f} bpm")
    c[1].metric("SDNN", f"{m['SDNN']:.0f} ms")
    c[2].metric("RMSSD", f"{m['RMSSD']:.0f} ms")
    c[3].metric("SpO₂", f"{spo2} %")
    c[4].metric("Temp. corporal", f"{body_temp} °C")
    if ai_res:
        c[5].metric("IA (TFLite)", ai_res["label"],
                    f"{ai_res['conf']:.0f}% confianza", delta_color="off")
    else:
        c[5].metric("IA (TFLite)", "N/D")

    # --- Métricas de cabina ---
    st.caption("CABINA (ECLSS)")
    k = st.columns(5)
    k[0].metric("CO₂", f"{env['co2_ppm']:.0f} ppm")
    k[1].metric("VOCs", f"{env['vocs_ppb']:.0f} ppb")
    k[2].metric("Presión", f"{env['pressure_kpa']:.1f} kPa")
    k[3].metric("Temp. cabina", f"{env['temperature_c']:.1f} °C")
    k[4].metric("Radiación", f"{env['radiation_usv_h']:.2f} µSv/h")

    # --- ANÁLISIS ORBITAL (motor oficial) ---
    if BIOORBITAL_OK:
        st.caption("ANÁLISIS ORBITAL · MONITOR BIO-ORBITAL")
        full = ss.sim.last_full_analysis()
        r = full["radiation"]
        met = full["metrics"]
        o = st.columns(5)
        o[0].metric("Riesgo global", f"{full['risk_score']}/100", full["status"],
                    delta_color="off")
        o[1].metric("Zona", full["zone"]["name"])
        o[2].metric("Dosis acumulada", f"{r['cum_msv']:.0f} mSv",
                    f"{r['limit_pct']:.0f}% límite NASA")
        o[3].metric("Retardo ida", f"{met['delay_oneway_s']:.1f} s",
                    f"Autonomía {met['autonomy_need_pct']:.0f}%")
        o[4].metric("Radiación total", f"{r['total']:.1f} µSv/h",
                    f"GCR {r['gcr']:.1f} · SAA {r['saa']:.1f}")

        if full["anomalies"]:
            with st.expander(f"⚠️ Anomalías de ingeniería ({len(full['anomalies'])})", expanded=True):
                for a in full["anomalies"]:
                    sev = a["severity"]
                    fn = st.error if sev == "CRÍTICA" else (st.warning if sev in ("ALTA", "ADVERTENCIA") else st.info)
                    fn(f"**[{sev}] {a['code']}:** {a['detail']}")
        else:
            st.success("✅ Subsistemas orbitales nominales.")

        # Víveres
        sup = full["supplies"]
        with st.expander("Víveres y autonomía", expanded=False):
            sv = st.columns(4)
            sv[0].metric("Comida", f"{sup['food_kg']:.0f} kg")
            sv[1].metric("Agua", f"{sup['water_l']:.0f} L")
            sv[2].metric("Botiquines", f"{sup['med_kits']}")
            sv[3].metric("Reabastecimiento", "Posible" if sup["resupply_possible"] else "IMPOSIBLE")
            st.caption(sup["status"])

    # --- Gemelo bio-digital ---
    if tw and "error" in tw:
        st.error(f"Gemelo bio-digital: {tw['error']}")
    elif tw_ok:
        st.caption("GEMELO BIO-DIGITAL · MOTOR CLÍNICO S.H.A.R.E.")
        g = st.columns(4)
        g[0].metric("Nivel global", tw["level"])
        g[1].metric("SHARE index", f"{tw['share_index']:.2f}")
        g[2].metric("Anomalía", f"{tw['anomaly']:.2f}")
        g[3].metric("Paso S.H.A.R.E.", tw["step"] or "—")
        st.progress(min(int(tw["share_index"] * 100), 100))
        if tw["requires_clinician"]:
            st.warning("El gemelo indica que se requiere confirmación clínica (CMO / flight surgeon).")
        if tw["options"]:
            st.markdown("**Contramedidas propuestas por el gemelo:**")
            for opt in tw["options"][:4]:
                extra = " · requiere médico" if opt["clinician"] else ""
                st.markdown(f"- **{opt['label']}**{extra}: {opt['benefits']}")

    # --- Gráfica ECG ---
    tt = np.arange(N) / FS
    color = "#ff4444" if any(l == "error" for l, _ in alerts) else "#00ff88"
    fig = go.Figure()
    if ss.get("show_raw", True):
        fig.add_trace(go.Scattergl(x=tt, y=x, mode="lines", name="Cruda",
                                   line=dict(color="#888888", width=1), opacity=0.6))
    fig.add_trace(go.Scattergl(x=tt, y=filt, mode="lines", name="Filtrada",
                               line=dict(color=color, width=2)))
    fig.add_trace(go.Scatter(x=tt[peaks], y=filt[peaks], mode="markers", name="Pico R",
                             marker=dict(color="#ffd400", size=9, symbol="triangle-down")))
    fig.update_layout(uirevision="ecg", height=340, template="plotly_dark",
                      margin=dict(l=10, r=10, t=30, b=10),
                      title="ECG: cruda vs. filtrada + detección QRS",
                      xaxis=dict(title="segundos", range=[0.5, WIN_S]),
                      legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")

    # --- Tendencias de cabina ---
    if len(ss.hist) > 2:
        dfh = pd.DataFrame(ss.hist)
        t1, t2, t3 = st.columns(3)
        t1.caption("CO₂ (ppm), últimos 90 s")
        t1.line_chart(dfh["co2_ppm"], height=150)
        t2.caption("Presión (kPa), últimos 90 s")
        t2.line_chart(dfh["pressure_kpa"], height=150)
        t3.caption("Radiación (µSv/h), últimos 90 s")
        t3.line_chart(dfh["radiation_usv_h"], height=150)

    # --- Gateway ---
    with st.expander("Gateway local: MQTT + SQLite + búfer FIFO", expanded=True):
        if not gateway_ok:
            st.warning("Gateway no disponible. Revisa que Mosquitto esté activo (puerto 1883).")
        else:
            p1c, p2c, p3c, p4c = st.columns(4)
            p1c.metric("Guardados en SQLite", gstats["total"])
            p2c.metric("Pendientes en FIFO", gstats["pending"])
            p3c.metric("Recibidos por la Tierra", gw.earth_count)
            p4c.metric("Estado del enlace", "BLACKOUT" if blackout else "ACTIVO")

            rows = []
            for h in gw.recent(6):
                ts = datetime.fromisoformat(h["timestamp"]).astimezone()
                rows.append({
                    "hora": ts.strftime("%H:%M:%S"),
                    "escenario": h.get("cabin_status"),
                    "CO₂ (ppm)": (h.get("environment") or {}).get("co2_ppm"),
                    "FC (bpm)": (h.get("biometrics") or {}).get("heart_rate_bpm"),
                    "nivel gemelo": (h.get("twin") or {}).get("level"),
                    "enviado a Tierra": "✅" if h["_forwarded"] else "⏳ en FIFO",
                })
            if rows:
                st.caption("Últimos paquetes guardados en local_buffer.db")
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            if gw.last_error:
                st.caption(f"Último aviso del gateway: {gw.last_error}")

    # --- Alertas y protocolos ---
    st.subheader("Alertas")
    if not alerts:
        st.success("Todos los signos vitales y la cabina dentro de rango normal")
    shown = set()
    for level, msg in alerts:
        (st.error if level == "error" else st.warning)(msg)
        for key, steps in PROTOCOLS.items():
            if key in shown:
                continue
            if key in msg or (key == "Taquicardia" and "HRV" in msg):
                shown.add(key)
                st.markdown(f"**Protocolo automático ({key}):**")
                for i, s in enumerate(steps, 1):
                    st.markdown(f"{i}. {s}")
                break

    with st.expander("Datos compartidos entre módulos (DSP, IA, ECLSS, gemelo y gateway)"):
        payload = {
            "dsp_ai_features": res["ai_features"],
            "ia_resultado": ai_res,
            "telemetria_cabina": pkt,
            "gemelo": {k2: v for k2, v in (tw or {}).items() if k2 != "options"},
            "gateway": gstats,
        }
        if BIOORBITAL_OK:
            payload["analisis_orbital"] = {
                "risk_score": ss.sim.last_full_analysis()["risk_score"],
                "zone": ss.sim.last_full_analysis()["zone"],
                "radiation": ss.sim.last_full_analysis()["radiation"],
            }
        st.json(payload)


live_panel()