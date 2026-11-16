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
WIN_S = 10               # seconds of window shown
N = FS * WIN_S
SEG_BEFORE, SEG_AFTER = 90, 126   # 216 samples around each R peak
CREW_ID = "CDR-01"

st.set_page_config(page_title="MEDICJAB", layout="wide")
engine = MedicJabDSPEngine(fs=FS)

# ---------------------------------------------------------------------------
# Official engine (Bio-Orbital Monitor). Optional import: if it is missing, the
# app keeps working with the adapter simulator in "fixed scenario" mode.
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
    "Tachycardia": [
        "Sit the astronaut down and ask them to breathe slowly and deeply",
        "Check the electrodes and repeat the ECG reading",
        "Prepare the onboard cardiac medication kit",
        "Notify the mission commander",
    ],
    "arrhythmia": [
        "Ask the astronaut to stop and sit down",
        "Repeat the ECG and compare it with the baseline recording",
        "Notify the commander and the flight surgeon (if a link is available)",
    ],
    "SpO₂": [
        "Administer supplemental oxygen",
        "Check the suit / mask seal",
        "Notify the mission commander",
    ],
    "CO₂": [
        "Inspect and replace the CO₂ filters (scrubbers)",
        "Increase cabin ventilation",
        "Reduce crew physical activity",
    ],
    "Depressurization": [
        "Locate the leak (hatches, seals, ports)",
        "Close the hatches of the affected modules",
        "Have the crew don pressure suits",
        "Notify the mission commander",
    ],
    "Radiation": [
        "Move the crew to the most heavily shielded shelter",
        "Suspend extravehicular activities",
        "Record each astronaut's accumulated dose",
        "Notify the mission commander",
    ],
}


def synthetic_ecg(fs=FS, secs=60):
    """Fallback synthetic ECG in case 100.csv is not available yet."""
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


@st.cache_resource(show_spinner="Loading AI model (the first time may take a while)...")
def load_ai():
    try:
        from ai_engine import DenisAIEngine
        return DenisAIEngine()
    except Exception as e:
        return str(e)


@st.cache_resource
def load_gateway():
    """Jose's gateway: a single instance (MQTT threads + SQLite + FIFO)."""
    try:
        from gateway_engine import GatewayEngine
        return GatewayEngine()
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def cabin_alerts(env):
    """Cabin thresholds (tune them with Dick)."""
    a = []
    co2 = env["co2_ppm"]
    if co2 > 5000:
        a.append(("error", f"Cabin CO₂ critical: {co2:.0f} ppm"))
    elif co2 > 1000:
        a.append(("warning", f"Cabin CO₂ elevated: {co2:.0f} ppm"))
    p = env["pressure_kpa"]
    if p < 90:
        a.append(("error", f"Depressurization critical: {p:.1f} kPa"))
    elif p < 95:
        a.append(("warning", f"Depressurization: cabin pressure {p:.1f} kPa"))
    rad = env["radiation_usv_h"]
    if rad > 10:
        a.append(("error", f"Radiation critical (SPE): {rad:.1f} µSv/h"))
    elif rad > 1:
        a.append(("warning", f"Radiation elevated: {rad:.2f} µSv/h"))
    if env["vocs_ppb"] > 100:
        a.append(("warning", f"VOCs elevated: {env['vocs_ppb']:.0f} ppb"))
    if not 18 <= env["temperature_c"] <= 27:
        a.append(("warning", f"Cabin temperature out of range: {env['temperature_c']:.1f} °C"))
    return a


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------
sig, is_real = load_signal()
if not is_real:
    st.warning("100.csv not found: using a fallback SYNTHETIC ECG.")

ai = load_ai()
ai_ok = not isinstance(ai, str)
if not ai_ok:
    st.info(f"AI module unavailable (everything else works normally): {ai[:150]}")

gw = load_gateway()
gateway_ok = not isinstance(gw, str)
if not gateway_ok:
    st.info(f"MQTT/SQLite gateway unavailable (is Mosquitto running?): {gw[:200]}")

bridge = load_bridge()
bridge_ok = not isinstance(bridge, str)
if not bridge_ok:
    st.info(f"Bio-digital twin unavailable: {bridge[:200]}")

if not BIOORBITAL_OK:
    st.info(f"Orbital engine (Bio-Orbital Monitor) unavailable: {BIOORBITAL_ERR[:200]}")


# ---------------------------------------------------------------------------
# Session state
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
    """Fetch real ISS data and load it into the simulator."""
    try:
        live = fetch_live_space_data()
        ss.orbit_alt = float(live["altitude_km"])
        ss.orbit_lat = float(live["latitude_deg"])
        ss.orbit_lon = float(live["longitude_deg"])
        ss.orbit_days = 45.0
        apply_orbit()
        st.toast(f"Live ISS: {ss.orbit_alt:.0f} km · Kp {live['geomagnetic_kp']:.1f}")
    except Exception as e:
        st.toast(f"Could not read ISS data: {e}")


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
    st.header("Control panel")
    st.selectbox("Astronaut", ["Cmdr. Rivera", "Dr. Chen", "Eng. Okafor"])
    st.selectbox("Mission", ["Low Earth orbit", "Mars transit"])
    st.success("Local system: ACTIVE")

    st.divider()
    st.subheader("Signal processing")
    st.checkbox("Inject noise (60 Hz + motion)", key="noise")
    st.checkbox("Show raw signal", key="show_raw", value=True)

    st.divider()
    st.subheader("AI (TFLite)")
    st.checkbox("Use AI to trigger alerts", key="ai_alerts", value=False,
                disabled=not ai_ok,
                help="Leave it off until the model is trained on real data.")

    st.divider()
    st.subheader("Orbit (official engine)")
    if BIOORBITAL_OK:
        st.slider(
            "Altitude (km)", min_value=0, max_value=400_000,
            value=int(ss.orbit_alt), step=10, key="orbit_alt_slider",
            on_change=lambda: setattr(ss, "orbit_alt", float(ss.orbit_alt_slider)),
        )
        with st.expander("Fine orbit settings", expanded=False):
            st.slider("Latitude (°)", -90.0, 90.0, float(ss.orbit_lat),
                      step=0.5, key="orbit_lat_slider",
                      on_change=lambda: setattr(ss, "orbit_lat", float(ss.orbit_lat_slider)))
            st.slider("Longitude (°)", -180.0, 180.0, float(ss.orbit_lon),
                      step=0.5, key="orbit_lon_slider",
                      on_change=lambda: setattr(ss, "orbit_lon", float(ss.orbit_lon_slider)))
            st.slider("Mission days", 0, 900, int(ss.orbit_days),
                      step=1, key="orbit_days_slider",
                      on_change=lambda: setattr(ss, "orbit_days", float(ss.orbit_days_slider)))
            st.button("Apply orbit", on_click=apply_orbit, width="stretch")
        st.button("📡 Live ISS data", on_click=load_iss_live, width="stretch")
    else:
        st.caption("Orbital engine unavailable.")

    st.divider()
    st.subheader("Mental assessment")
    _pages = sorted(glob.glob(os.path.join("pages", "*.py")))
    if _pages:
        st.page_link(_pages[0].replace("\\", "/"), label="Take the mental assessment →")
    else:
        st.caption("pages/ folder not found.")

    st.divider()
    st.subheader("Contingencies")
    st.caption("Astronaut")
    st.button("Simulate Arrhythmia", on_click=set_mode, args=("arritmia",), width="stretch")
    st.caption("Cabin (ECLSS)")
    st.button("CO₂ scrubber leak", on_click=set_crisis, args=("CO2_LEAK",), width="stretch")
    st.button("Solar particle event", on_click=set_crisis, args=("SPE_EVENT",), width="stretch")
    st.button("Slow depressurization", on_click=set_crisis, args=("SLOW_DEPRESS",), width="stretch")
    st.caption("Communications")
    st.button("Simulate Space Blackout", on_click=start_blackout, width="stretch",
              disabled=(not gateway_ok) or gw.blackout)
    st.button("Restore link to Earth", on_click=end_blackout, width="stretch",
              disabled=(not gateway_ok) or (not gw.blackout))
    st.divider()
    st.button("Reset all", on_click=reset_all, type="primary", width="stretch")

st.title("MEDICJAB")


# ---------------------------------------------------------------------------
# Live panel
# ---------------------------------------------------------------------------
@st.fragment(run_every=0.5)
def live_panel():
    mode = ss.mode
    now = time.time()
    blackout = gateway_ok and gw.blackout

    # --- Cabin telemetry: one packet per second ---
    new_packet = False
    if now - ss.last_pkt >= 1.0:
        ss.pkt = ss.sim.generate_telemetry_packet()
        ss.last_pkt = now
        ss.hist.append(ss.pkt["environment"])
        ss.hist = ss.hist[-90:]
        new_packet = True
    pkt = ss.pkt
    env = pkt["environment"]

    # --- Advance ECG ---
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

    # --- AI ---
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

    # --- Simulated SpO₂ ---
    spo2 = int(max(85, 98 - max(0.0, env["co2_ppm"] - 2000) / 600))
    body_temp = 36.6

    # --- Alerts ---
    alerts = []
    if m["status"] == "CRITICAL_ALERT":
        alerts.append(("error", f"Tachycardia / HRV critical: {m['BPM']} bpm, SDNN {m['SDNN']} ms"))
    elif m["status"] == "MODERATE_STRESS":
        alerts.append(("warning", f"Moderate stress: {m['BPM']} bpm, SDNN {m['SDNN']} ms"))
    if ai_res and ss.get("ai_alerts") and ai_res["label"] == "ARRHYTHMIA":
        alerts.append(("error", f"AI: possible arrhythmia ({ai_res['n_arr']}/{ai_res['n']} latidos)"))
    if spo2 < 92:
        alerts.append(("error", f"SpO₂ critical: {spo2}%"))
    alerts += cabin_alerts(env)

    # --- Bio-digital twin ---
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

    # --- Banner and link ---
    c_state, c_link = st.columns([3, 2])
    with c_state:
        if any(l == "error" for l, _ in alerts):
            banner("STATUS: CRITICAL", "#dc2626")
        elif alerts:
            banner("STATUS: ALERT", "#d97706")
        else:
            banner("STATUS: NOMINAL", "#16a34a")
    with c_link:
        if blackout:
            secs = int(now - ss.blackout_since) if ss.blackout_since else 0
            st.error(f"Earth link: LOST ({secs} s)")
            st.caption(f"Autonomous mode · {gstats['pending']} packets held in the FIFO buffer (SQLite)")
        else:
            sync = ss.last_sync
            if sync and gstats["pending"] > 0:
                st.warning(f"Link restored: retransmitting... {gstats['pending']} pending")
            elif sync and now - sync["t"] < 15:
                st.success(f"Link restored: {sync['n']} packets retransmitted to Earth")
            else:
                st.info("Earth link: ACTIVE (synchronized)")
        st.caption(f"Cabin scenario: {pkt['cabin_status']}")

    # --- Astronaut metrics ---
    st.caption("ASTRONAUT")
    c = st.columns(6)
    c[0].metric("Heart rate", f"{m['BPM']:.0f} bpm")
    c[1].metric("SDNN", f"{m['SDNN']:.0f} ms")
    c[2].metric("RMSSD", f"{m['RMSSD']:.0f} ms")
    c[3].metric("SpO₂", f"{spo2} %")
    c[4].metric("Body temp.", f"{body_temp} °C")
    if ai_res:
        c[5].metric("AI (TFLite)", ai_res["label"],
                    f"{ai_res['conf']:.0f}% confidence", delta_color="off")
    else:
        c[5].metric("AI (TFLite)", "N/A")

    # --- Cabin metrics ---
    st.caption("CABIN (ECLSS)")
    k = st.columns(5)
    k[0].metric("CO₂", f"{env['co2_ppm']:.0f} ppm")
    k[1].metric("VOCs", f"{env['vocs_ppb']:.0f} ppb")
    k[2].metric("Pressure", f"{env['pressure_kpa']:.1f} kPa")
    k[3].metric("Cabin temp.", f"{env['temperature_c']:.1f} °C")
    k[4].metric("Radiation", f"{env['radiation_usv_h']:.2f} µSv/h")

    # --- ORBITAL ANALYSIS (official engine) ---
    if BIOORBITAL_OK:
        st.caption("ORBITAL ANALYSIS · BIO-ORBITAL MONITOR")
        full = ss.sim.last_full_analysis()
        r = full["radiation"]
        met = full["metrics"]
        o = st.columns(5)
        o[0].metric("Overall risk", f"{full['risk_score']}/100", full["status"],
                    delta_color="off")
        o[1].metric("Zone", full["zone"]["name"])
        o[2].metric("Accumulated dose", f"{r['cum_msv']:.0f} mSv",
                    f"{r['limit_pct']:.0f}% NASA limit")
        o[3].metric("One-way delay", f"{met['delay_oneway_s']:.1f} s",
                    f"Autonomy {met['autonomy_need_pct']:.0f}%")
        o[4].metric("Total radiation", f"{r['total']:.1f} µSv/h",
                    f"GCR {r['gcr']:.1f} · SAA {r['saa']:.1f}")

        if full["anomalies"]:
            with st.expander(f"⚠️ Engineering anomalies ({len(full['anomalies'])})", expanded=True):
                for a in full["anomalies"]:
                    sev = a["severity"]
                    fn = st.error if sev == "CRÍTICA" else (st.warning if sev in ("ALTA", "ADVERTENCIA") else st.info)
                    fn(f"**[{sev}] {a['code']}:** {a['detail']}")
        else:
            st.success("✅ Orbital subsystems nominal.")

        # Supplies
        sup = full["supplies"]
        with st.expander("Supplies and autonomy", expanded=False):
            sv = st.columns(4)
            sv[0].metric("Food", f"{sup['food_kg']:.0f} kg")
            sv[1].metric("Water", f"{sup['water_l']:.0f} L")
            sv[2].metric("Med kits", f"{sup['med_kits']}")
            sv[3].metric("Resupply", "Possible" if sup["resupply_possible"] else "IMPOSSIBLE")
            st.caption(sup["status"])

    # --- Bio-digital twin ---
    if tw and "error" in tw:
        st.error(f"Bio-digital twin: {tw['error']}")
    elif tw_ok:
        st.caption("BIO-DIGITAL TWIN · S.H.A.R.E. CLINICAL ENGINE")
        g = st.columns(4)
        g[0].metric("Overall level", tw["level"])
        g[1].metric("SHARE index", f"{tw['share_index']:.2f}")
        g[2].metric("Anomaly", f"{tw['anomaly']:.2f}")
        g[3].metric("S.H.A.R.E. step", tw["step"] or "—")
        st.progress(min(int(tw["share_index"] * 100), 100))
        if tw["requires_clinician"]:
            st.warning("The twin indicates clinical confirmation is required (CMO / flight surgeon).")
        if tw["options"]:
            st.markdown("**Countermeasures proposed by the twin:**")
            for opt in tw["options"][:4]:
                extra = " · requires physician" if opt["clinician"] else ""
                st.markdown(f"- **{opt['label']}**{extra}: {opt['benefits']}")

    # --- ECG chart ---
    tt = np.arange(N) / FS
    color = "#ff4444" if any(l == "error" for l, _ in alerts) else "#00ff88"
    fig = go.Figure()
    if ss.get("show_raw", True):
        fig.add_trace(go.Scattergl(x=tt, y=x, mode="lines", name="Raw",
                                   line=dict(color="#888888", width=1), opacity=0.6))
    fig.add_trace(go.Scattergl(x=tt, y=filt, mode="lines", name="Filtered",
                               line=dict(color=color, width=2)))
    fig.add_trace(go.Scatter(x=tt[peaks], y=filt[peaks], mode="markers", name="R peak",
                             marker=dict(color="#ffd400", size=9, symbol="triangle-down")))
    fig.update_layout(uirevision="ecg", height=340, template="plotly_dark",
                      margin=dict(l=10, r=10, t=30, b=10),
                      title="ECG: raw vs. filtered + QRS detection",
                      xaxis=dict(title="seconds", range=[0.5, WIN_S]),
                      legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")

    # --- Cabin trends ---
    if len(ss.hist) > 2:
        dfh = pd.DataFrame(ss.hist)
        t1, t2, t3 = st.columns(3)
        t1.caption("CO₂ (ppm), last 90 s")
        t1.line_chart(dfh["co2_ppm"], height=150)
        t2.caption("Pressure (kPa), last 90 s")
        t2.line_chart(dfh["pressure_kpa"], height=150)
        t3.caption("Radiation (µSv/h), last 90 s")
        t3.line_chart(dfh["radiation_usv_h"], height=150)

    # --- Gateway ---
    with st.expander("Local gateway: MQTT + SQLite + FIFO buffer", expanded=True):
        if not gateway_ok:
            st.warning("Gateway unavailable. Check that Mosquitto is running (port 1883).")
        else:
            p1c, p2c, p3c, p4c = st.columns(4)
            p1c.metric("Saved in SQLite", gstats["total"])
            p2c.metric("Pending in FIFO", gstats["pending"])
            p3c.metric("Received by Earth", gw.earth_count)
            p4c.metric("Link status", "BLACKOUT" if blackout else "ACTIVE")

            rows = []
            for h in gw.recent(6):
                ts = datetime.fromisoformat(h["timestamp"]).astimezone()
                rows.append({
                    "time": ts.strftime("%H:%M:%S"),
                    "scenario": h.get("cabin_status"),
                    "CO₂ (ppm)": (h.get("environment") or {}).get("co2_ppm"),
                    "FC (bpm)": (h.get("biometrics") or {}).get("heart_rate_bpm"),
                    "twin level": (h.get("twin") or {}).get("level"),
                    "sent to Earth": "✅" if h["_forwarded"] else "⏳ in FIFO",
                })
            if rows:
                st.caption("Latest packets saved in local_buffer.db")
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            if gw.last_error:
                st.caption(f"Last gateway notice: {gw.last_error}")

    # --- Alerts and protocols ---
    st.subheader("Alerts")
    if not alerts:
        st.success("All vital signs and the cabin are within normal range")
    shown = set()
    for level, msg in alerts:
        (st.error if level == "error" else st.warning)(msg)
        for key, steps in PROTOCOLS.items():
            if key in shown:
                continue
            if key in msg or (key == "Tachycardia" and "HRV" in msg):
                shown.add(key)
                st.markdown(f"**Automatic protocol ({key}):**")
                for i, s in enumerate(steps, 1):
                    st.markdown(f"{i}. {s}")
                break

    with st.expander("Data shared between modules (DSP, AI, ECLSS, twin and gateway)"):
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