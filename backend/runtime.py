"""SimulationRuntime: orquesta los motores del Proyecto A y produce el estado que consume el frontend.

No modifica ningún archivo de backend/engines/. Cada módulo es opcional: si falta una dependencia
(TensorFlow, Mosquitto, pydantic…) el runtime sigue funcionando y lo informa en state["modules"].
"""
from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ENGINES = Path(__file__).resolve().parent / "engines"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

# Los motores del Proyecto A usan imports planos (from twin import ...): los exponemos en sys.path.
if str(ENGINES) not in sys.path:
    sys.path.insert(0, str(ENGINES))

from dsp_engine import MedicJabDSPEngine          # noqa: E402
from eclss_engine import ECLSSTelemetrySimulator  # noqa: E402

try:
    from scenarios import ASTRONAUTS, LEGS, ORBITS, PROTOCOLS, SCENARIOS
except ImportError:  # ejecutado como paquete: backend.runtime
    from .scenarios import ASTRONAUTS, LEGS, ORBITS, PROTOCOLS, SCENARIOS

FS = 360                    # Hz (MIT-BIH)
WIN_S = 10                  # segundos que analiza el DSP en cada tick
N = FS * WIN_S
SEG_BEFORE, SEG_AFTER = 90, 126   # 216 muestras alrededor de cada pico R (entrada de la CNN)
DISPLAY_DECIM = 3           # 360 Hz -> 120 Hz hacia el navegador
DISPLAY_LAG_S = 2           # solo se emite señal a >2 s del borde de la ventana (sin efectos de borde de filtfilt)
CREW_ID = "CDR-01"
HRV_DESC = {
    "NORMAL_STABLE": ("", "Ritmo sinusal estable"),
    "MODERATE_STRESS": ("warn", "HRV reducida / estrés moderado"),
    "CRITICAL_ALERT": ("crit", "Taquicardia / HRV crítica"),
    "INSUFFICIENT_DATA": ("", "Adquiriendo señal…"),
}


# ----------------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------------
def synthetic_ecg(fs=FS, secs=60, variability=0.22):
    """ECG sintético de respaldo (el de app.py del Proyecto A).

    Cambio respecto a A: la variabilidad RR sube de ±12 % a ±22 %. Con ±12 % el SDNN medido (~36 ms)
    queda justo bajo el umbral de 40 ms del DSP y el estado en reposo parpadeaba entre NOMINAL y ESTRÉS.
    Con ±22 % el SDNN en reposo es 47-88 ms (adulto sano). Con un 100.csv real este valor no se usa.
    """
    rng = np.random.default_rng(1)
    base_n = int(0.83 * fs)
    x = np.linspace(0, 1, base_n)
    g = lambda c, w, a: a * np.exp(-((x - c) ** 2) / (2 * w ** 2))
    beat = (g(.20, .025, .15) + g(.37, .008, -.12) + g(.40, .010, 1.0)
            + g(.43, .008, -.25) + g(.65, .050, .30))
    out = []
    while sum(len(b) for b in out) < secs * fs:
        L = int(base_n * rng.uniform(1 - variability, 1 + variability))
        out.append(np.interp(np.linspace(0, 1, L), np.linspace(0, 1, base_n), beat))
    s = np.concatenate(out)
    return s + rng.normal(0, 0.01, len(s))


def load_signal():
    """Busca 100.csv (MIT-BIH) en data/ o en la raíz; si no existe usa el ECG sintético."""
    for p in (DATA / "100.csv", ROOT / "100.csv"):
        if p.exists():
            df = pd.read_csv(p)
            cols = [c for c in df.columns if "MLII" in str(c)]
            col = cols[0] if cols else df.columns[1]
            s = pd.to_numeric(df[col], errors="coerce").dropna().values
            return s.astype(float), "mit-bih"
    return synthetic_ecg(), "synthetic"


def cabin_alerts(env):
    """Umbrales de cabina (basados en app.py del Proyecto A, recalibrados para que NORMAL sea NOMINAL).

    A usaba CO₂ > 1000 ppm y radiación > 1 / > 10 µSv/h (escala de suelo terrestre). Pero el propio ECLSS
    de A produce 3421 ppm de CO₂ en NORMAL (2.6 mmHg) y ~108 µSv/h al pasar por la Anomalía del Atlántico Sur
    (lat -26, lon -46), así que NORMAL salía en CRÍTICO. Nuevos umbrales (ajústalos con Dick/Bryan):
      CO₂: aviso > 4000 ppm, crítico > 5000 ppm  ·  Radiación: aviso > 150, crítico > 300 µSv/h (SPE = 509)  ·  VOCs: aviso > 600 ppb (NORMAL = 345).
    """
    a = []
    co2 = env["co2_ppm"]
    if co2 > 5000:
        a.append(("error", f"CO₂ de cabina crítico: {co2:.0f} ppm"))
    elif co2 > 4000:
        a.append(("warning", f"CO₂ de cabina elevado: {co2:.0f} ppm"))
    p = env["pressure_kpa"]
    if p < 90:
        a.append(("error", f"Despresurización crítica: {p:.1f} kPa"))
    elif p < 95:
        a.append(("warning", f"Despresurización: presión de cabina {p:.1f} kPa"))
    rad = env["radiation_usv_h"]
    if rad > 300:
        a.append(("error", f"Radiación crítica (SPE): {rad:.1f} µSv/h"))
    elif rad > 150:
        a.append(("warning", f"Radiación elevada: {rad:.2f} µSv/h"))
    if env["vocs_ppb"] > 600:
        a.append(("warning", f"VOCs elevados: {env['vocs_ppb']:.0f} ppb"))
    if not 18 <= env["temperature_c"] <= 27:
        a.append(("warning", f"Temperatura de cabina fuera de rango: {env['temperature_c']:.1f} °C"))
    return a


def protocol_for(msg):
    for key, steps in PROTOCOLS.items():
        if key in msg or (key == "Taquicardia" and "HRV" in msg):
            return key, steps
    return None, []


class LocalGateway:
    """Alternativa sin Mosquitto: JosePipelineEngine (SQLite + búfer FIFO) con la misma interfaz que GatewayEngine."""
    kind = "sqlite-local"

    def __init__(self, db_path):
        from pipeline_engine import JosePipelineEngine
        self.db_path = str(db_path)
        self.engine = JosePipelineEngine(self.db_path)
        self.earth_count = 0
        self.last_error = None

    @property
    def blackout(self):
        return self.engine.blackout_mode

    @blackout.setter
    def blackout(self, value):
        pending = len(self.engine.fifo_buffer)
        self.engine.toggle_blackout(bool(value))        # al restaurar, hace el batch-flush
        if not value:
            self.earth_count += pending

    def publish_packet(self, packet):
        res = self.engine.process_and_store_packet(packet)
        if res["status"] == "SAVED_ONLINE":
            self.earth_count += 1

    def stats(self):
        conn = sqlite3.connect(self.db_path)
        stored = conn.execute("SELECT COUNT(*) FROM telemetry_logs").fetchone()[0]
        conn.close()
        pending = len(self.engine.fifo_buffer)
        return {"total": stored + pending, "pending": pending, "forwarded": stored}

    def recent(self, limit=6):
        out = []
        for d in self.engine.get_recent_history(limit):
            d["_forwarded"] = True
            out.append(d)
        return out


# ----------------------------------------------------------------------------------------------
# Runtime
# ----------------------------------------------------------------------------------------------
class SimulationRuntime:
    def __init__(self):
        self.lock = threading.RLock()
        self.dsp = MedicJabDSPEngine(fs=FS)
        self.sim = ECLSSTelemetrySimulator(live=False)

        self.sig, self.ecg_source = load_signal()
        self._med = float(np.median(self.sig))
        self._scale = float(np.percentile(np.abs(self.sig - self._med), 99.5)) or 1.0
        self._std = float(np.std(self.sig))
        self._fast_cache: dict[float, np.ndarray] = {}

        # estado de la simulación
        self.scenario = "normal"
        self.speed = 1.0
        self.astro = "Cmdr. Rivera"
        self.orbit_name = "Órbita baja"
        self.orbit_gravity = 0.0
        self.toggles = {"noise": False, "raw": True, "ai": False}
        self.n = N + DISPLAY_LAG_S * FS          # contador absoluto de muestras
        self.emitted = self.n - (DISPLAY_LAG_S + 1) * FS
        self.last_t = time.time()
        self.t0 = time.time()
        self.blackout_since = None
        self.last_sync = None
        self.tw = None
        self.hist = []
        self.last_state: dict | None = None

        # módulos opcionales
        self.modules = {"orbital": False, "twin": False, "gateway": "none", "ai": "off"}
        self._init_orbital()
        self.bridge = self._init_twin()
        self.gw = self._init_gateway()
        self.ai = None
        self._ai_thread = None

    # ---- carga de módulos -----------------------------------------------------------------
    def _init_orbital(self):
        try:
            import monitor_bioorbital  # noqa: F401
            self.modules["orbital"] = True
        except Exception as e:
            self.modules["orbital_error"] = f"{type(e).__name__}: {e}"

    def _init_twin(self):
        try:
            from twin_adapter import TwinBridge
            bridge = TwinBridge(rules=str(ENGINES / "rules.yaml"))
            self.modules["twin"] = True
            return bridge
        except Exception as e:
            self.modules["twin_error"] = f"{type(e).__name__}: {e}"
            return None

    def _init_gateway(self):
        try:                                           # 1º: gateway MQTT del Proyecto A (requiere Mosquitto)
            import gateway_engine
            gateway_engine.DB_FILE = str(DATA / "local_buffer.db")
            gw = gateway_engine.GatewayEngine()
            gw.kind = "mqtt+sqlite"
            self.modules["gateway"] = gw.kind
            return gw
        except Exception as e:
            self.modules["gateway_note"] = f"MQTT no disponible ({type(e).__name__}); uso SQLite local"
        try:                                           # 2º: pipeline SQLite + FIFO sin broker
            gw = LocalGateway(DATA / "telemetry.db")
            self.modules["gateway"] = gw.kind
            return gw
        except Exception as e:
            self.modules["gateway_error"] = f"{type(e).__name__}: {e}"
            return None

    def _load_ai_async(self):
        """TensorFlow tarda en cargar: se hace en un hilo la primera vez que se activa la IA."""
        if self._ai_thread and self._ai_thread.is_alive():
            return
        self.modules["ai"] = "loading"

        def work():
            try:
                from ai_engine import DenisAIEngine
                self.ai = DenisAIEngine(model_path=str(ROOT / "models" / "model_quantized.tflite"))
                self.modules["ai"] = "ready"
            except Exception as e:
                self.modules["ai"] = "unavailable"
                self.modules["ai_error"] = f"{type(e).__name__}: {str(e)[:150]}"

        self._ai_thread = threading.Thread(target=work, daemon=True)
        self._ai_thread.start()

    # ---- acciones (las llama la API) -------------------------------------------------------
    def _source(self):
        if abs(self.speed - 1.0) < 1e-6:
            return self.sig
        key = round(self.speed, 3)
        if key not in self._fast_cache:
            L = int(len(self.sig) / self.speed)
            self._fast_cache[key] = np.interp(np.linspace(0, len(self.sig) - 1, L),
                                              np.arange(len(self.sig)), self.sig)
        return self._fast_cache[key]

    def _push_gravity(self, g):
        # trigger_crisis() reinicia _base; la gravedad se reaplica después
        self.sim._base["gravity_g"] = float(g)

    def start_blackout(self):
        if self.gw and not self.gw.blackout:
            self.blackout_since = time.time()
            self.last_sync = None
            self.gw.blackout = True

    def end_blackout(self):
        if self.gw and self.gw.blackout:
            n = self.gw.stats()["pending"]
            self.gw.blackout = False
            self.blackout_since = None
            self.last_sync = {"n": n, "t": time.time()}

    def apply_scenario(self, key):
        if key not in SCENARIOS:
            raise KeyError(key)
        with self.lock:
            sc = SCENARIOS[key]
            self.scenario = key
            if key == "normal" and self.bridge:
                self.bridge.reset()                    # limpia dosis acumulada y latches del gemelo
                self.tw = None
            self.sim.trigger_crisis(sc["crisis"])
            self._push_gravity(sc["gravity_g"] or self.orbit_gravity)
            self.speed = sc["ecg_speed"]
            if sc["blackout"]:
                self.start_blackout()
            else:
                self.end_blackout()
            if sc["psych"] and self.bridge:
                self.bridge.submit_psych(sc["psych"])  # mini-test mental -> gemelo (aislamiento)

    def set_toggle(self, name, value):
        if name not in self.toggles:
            raise KeyError(name)
        with self.lock:
            self.toggles[name] = bool(value)
            if name == "ai" and value and self.ai is None:
                self._load_ai_async()

    def set_astronaut(self, name):
        if name in ASTRONAUTS:
            self.astro = name

    def set_orbit(self, name):
        if name not in ORBITS:
            raise KeyError(name)
        with self.lock:
            o = ORBITS[name]
            self.orbit_name = name
            self.orbit_gravity = o["gravity_g"] or 0.0
            self.sim.set_orbital_params(altitude_km=o["altitude_km"])
            self.sim.trigger_crisis(self.sim.active_crisis)   # recopia altitud al escenario activo
            self._push_gravity(SCENARIOS[self.scenario]["gravity_g"] or self.orbit_gravity)

    def reset_all(self):
        with self.lock:
            self.toggles = {"noise": False, "raw": True, "ai": self.toggles["ai"]}
            self.set_orbit("Órbita baja")
            self.apply_scenario("normal")

    # ---- tick: 1 vez por segundo -----------------------------------------------------------
    def tick(self):
        with self.lock:
            now = time.time()
            dt = max(0.0, now - self.last_t)
            self.last_t = now
            self.n += int(dt * FS)

            sc = SCENARIOS[self.scenario]
            prof = sc["profile"]

            # 1) ECG fuente (+ ruido opcional) -> DSP del Proyecto A
            idx = np.arange(self.n - N, self.n)
            src = self._source()
            x = src[idx % len(src)].copy()
            if self.toggles["noise"]:
                t_abs = idx / FS
                x = x + self._std * (0.4 * np.sin(2 * np.pi * 60 * t_abs)
                                     + 1.0 * np.sin(2 * np.pi * 0.25 * t_abs))
            res = self.dsp.process_pipeline(x)
            filt, peaks, m = res["filtered_ecg"], res["r_peaks"], res["metrics"]

            # 2) Trozo de ECG nuevo para el navegador (120 Hz, ya filtrado)
            end_abs = self.n - DISPLAY_LAG_S * FS
            a = np.arange(self.emitted, end_abs)
            a = a[a % DISPLAY_DECIM == 0]
            self.emitted = end_abs
            rel = a - (self.n - N)
            rel = rel[(rel >= 0) & (rel < N)]
            ecg = {
                "fs": FS // DISPLAY_DECIM,
                "raw": np.round((x[rel] - self._med) / self._scale, 4).tolist(),
                "filt": np.round(filt[rel] / self._scale, 4).tolist(),
            }

            # 3) Telemetría de cabina (ECLSS)
            pkt = self.sim.generate_telemetry_packet()
            env = pkt["environment"]
            self.hist.append(env)
            self.hist = self.hist[-90:]
            spo2 = int(max(85, 98 - max(0.0, env["co2_ppm"] - 2000) / 600))

            # 4) IA (TFLite), solo si está cargada
            ai_res = None
            if self.ai is not None and self.toggles["ai"]:
                try:
                    valid = [p for p in peaks if p >= SEG_BEFORE and p + SEG_AFTER <= N]
                    preds = []
                    for p in valid[-5:]:
                        s = filt[p - SEG_BEFORE:p + SEG_AFTER]
                        s = (s - s.mean()) / (s.std() + 1e-8)
                        preds.append(self.ai.predict_ecg_segment(s))
                    if preds:
                        n_arr = sum(r["prediction"] == "ARRHYTHMIA" for r in preds)
                        ai_res = {"label": "ARRHYTHMIA" if n_arr > len(preds) / 2 else "NORMAL",
                                  "n_arr": n_arr, "n": len(preds),
                                  "conf": float(np.mean([r["confidence"] for r in preds]))}
                except Exception as e:
                    self.modules["ai_error"] = f"{type(e).__name__}: {e}"

            # 5) Alertas
            alerts = []
            if m["status"] == "CRITICAL_ALERT":
                alerts.append(("error", f"Taquicardia / HRV crítica: {m['BPM']} bpm, SDNN {m['SDNN']} ms"))
            elif m["status"] == "MODERATE_STRESS":
                alerts.append(("warning", f"Estrés moderado: {m['BPM']} bpm, SDNN {m['SDNN']} ms"))
            if ai_res and ai_res["label"] == "ARRHYTHMIA":
                alerts.append(("error", f"IA: posible arritmia ({ai_res['n_arr']}/{ai_res['n']} latidos)"))
            if spo2 < 92:
                alerts.append(("error", f"SpO₂ crítica: {spo2}%"))
            alerts += cabin_alerts(env)
            # Signos NO medidos por el Proyecto A (perfil simulado del Proyecto B)
            for label, key in (("Presión arterial", "pa"), ("Glucosa", "glu"), ("Temperatura", "temp")):
                cls = prof[f"{key}_class"]
                if cls:
                    alerts.append(("error" if cls == "crit" else "warning",
                                   f"{label} (simulada): {prof[f'{key}_desc']}"))

            # 6) Gemelo bio-digital
            if self.bridge:
                self.tw = self.bridge.step(m["BPM"], spo2, env)
            tw = self.tw
            tw_ok = bool(tw) and "error" not in tw
            if tw_ok:
                alerts += [(lvl, msg) for lvl, msg in tw["alerts"]]

            # 7) Gateway (MQTT o SQLite local)
            blackout = bool(self.gw and self.gw.blackout)
            if self.gw:
                try:
                    self.gw.publish_packet({
                        "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                        "crew_id": CREW_ID,
                        "cabin_status": pkt["cabin_status"],
                        "biometrics": {"heart_rate_bpm": m["BPM"], "sdnn": m["SDNN"], "rmssd": m["RMSSD"],
                                       "hrv_status": m["status"], "spo2_pct": spo2},
                        "environment": env,
                        "ai": {"label": ai_res["label"], "confidence": round(ai_res["conf"], 1)} if ai_res else None,
                        "twin": {k: tw[k] for k in ("level", "share_index", "anomaly")} if tw_ok else None,
                        "alerts": [msg for _, msg in alerts],
                    })
                except Exception as e:
                    self.gw.last_error = f"publish: {e}"
            gstats = self.gw.stats() if self.gw else {"total": 0, "pending": 0, "forwarded": 0}

            # 8) Análisis orbital (Monitor Bio-Orbital)
            full = self.sim.last_full_analysis()
            rad, met = full["radiation"], full["metrics"]

            # 9) Estado para el frontend
            if any(l == "error" for l, _ in alerts):
                bcls, btxt = "critico", "ESTADO: CRÍTICO"
            elif alerts:
                bcls, btxt = "alerta", "ESTADO: ALERTA"
            else:
                bcls, btxt = "", "ESTADO: NOMINAL"

            days = int(self.sim.orbit["mission_days"])
            elapsed_h = days * 24 + int((now - self.t0) // 3600)
            elapsed_m = int(((now - self.t0) % 3600) // 60)
            meta = (f"{self.astro} · {ASTRONAUTS[self.astro]} · {self.orbit_name} · "
                    f"Día {days} · T+{elapsed_h}:{elapsed_m:02d}")

            delay = met["delay_oneway_s"]
            delay_txt = f"{delay:.1f}s" if delay < 60 else f"{delay / 60:.0f} min"
            if blackout:
                secs = int(now - self.blackout_since) if self.blackout_since else 0
                comms_title = f"Enlace con Tierra: BLACKOUT ({secs} s)"
                comms_sub = f"Modo autónomo · {gstats['pending']} paquetes en búfer FIFO"
            elif self.last_sync and gstats["pending"] > 0:
                comms_title = f"Enlace restablecido: retransmitiendo ({gstats['pending']})"
                comms_sub = f"Escenario de cabina: {pkt['cabin_status']}"
            elif self.last_sync and now - self.last_sync["t"] < 15:
                comms_title = f"Enlace restablecido: {self.last_sync['n']} paquetes enviados"
                comms_sub = f"Escenario de cabina: {pkt['cabin_status']}"
            else:
                comms_title = f"Enlace con Tierra: nominal ({delay_txt})"
                comms_sub = f"Escenario de cabina: {pkt['cabin_status']}"

            fc_cls, fc_desc = HRV_DESC.get(m["status"], ("", ""))
            heart_pt = "crit" if (fc_cls == "crit" or spo2 < 92) else ("warn" if (
                fc_cls == "warn" or sc["crisis"] != "NORMAL") else "")
            abd_pt = prof["glu_class"]
            legs_pt = "crit" if prof["pa_class"] == "crit" else ""

            ia_desc = prof["ia_desc"]
            if ai_res:
                ia_desc += f" · CNN: {ai_res['label']} {ai_res['conf']:.0f}%"
            ia_cls = prof["ia_class"]
            if ai_res and ai_res["label"] == "ARRHYTHMIA":
                ia_cls = "crit"

            rad_cls = "crit" if env["radiation_usv_h"] > 300 else ("warn" if env["radiation_usv_h"] > 150 else "")
            pa_txt = f"{prof['pa'][0]}/{prof['pa'][1]}"

            state = {
                "t": now,
                "scenario": self.scenario,
                "selection": {"astro": self.astro, "orbit": self.orbit_name},
                "banner": {"cls": bcls, "text": btxt, "meta": meta},
                "comms": {"title": comms_title, "sub": comms_sub, "blackout": blackout},
                "vitals": {
                    "fc": {"val": int(round(m["BPM"])), "cls": fc_cls, "desc": fc_desc,
                           "sdnn": m["SDNN"], "rmssd": m["RMSSD"]},
                    "spo2": {"val": spo2},
                    "pa": {"val": pa_txt, "cls": prof["pa_class"], "desc": prof["pa_desc"], "simulated": True},
                    "glu": {"val": prof["glu"], "cls": prof["glu_class"], "desc": prof["glu_desc"], "simulated": True},
                    "temp": {"val": f"{prof['temp']:.1f}", "cls": prof["temp_class"], "desc": prof["temp_desc"],
                             "simulated": True},
                    "sueno": {"val": prof["sleep"], "color": prof["sleep_color"], "simulated": True},
                    "animo": {"val": prof["mood"], "cls": prof["mood_class"], "desc": prof["mood_desc"],
                              "simulated": True},
                    "rad": {"val": f"{rad['cum_msv']:.2f}", "cls": rad_cls,
                            "desc": f"Ahora: {rad['total']:.2f} µSv/h · {rad['limit_pct']:.0f}% límite NASA"},
                    "ia": {"title": prof["ia_title"], "desc": ia_desc, "cls": ia_cls},
                },
                "points": {"heart": heart_pt, "abdomen": abd_pt, "legs": legs_pt},
                "organs": {
                    "heart": (f"{fc_desc}: {m['BPM']:.0f} bpm · SDNN {m['SDNN']:.0f} ms · "
                              f"RMSSD {m['RMSSD']:.0f} ms · SpO₂ {spo2}% · PA {pa_txt} mmHg."),
                    "abdomen": f"Glucosa {prof['glu']} mg/dL: {prof['glu_desc']}. Temp. {prof['temp']:.1f} °C.",
                    "legs": LEGS[self.scenario],
                },
                "alerts": [{"level": l, "msg": msg, "protocol": protocol_for(msg)[0],
                            "steps": protocol_for(msg)[1]} for l, msg in alerts],
                "twin": ({"level": tw["level"], "share_index": tw["share_index"], "anomaly": tw["anomaly"],
                          "step": tw["step"], "requires_clinician": tw["requires_clinician"],
                          "options": tw["options"][:4]} if tw_ok else
                         ({"error": tw["error"]} if tw else None)),
                "orbital": {"risk": full["risk_score"], "status": full["status"], "zone": full["zone"]["name"],
                            "cum_msv": rad["cum_msv"], "limit_pct": rad["limit_pct"],
                            "delay_s": delay, "autonomy_pct": met["autonomy_need_pct"],
                            "anomalies": [{"sev": a["severity"], "code": a["code"], "detail": a["detail"]}
                                          for a in full["anomalies"]][:6]},
                "cabin": env,
                "gateway": {"kind": getattr(self.gw, "kind", "none"), **gstats,
                            "earth": getattr(self.gw, "earth_count", 0), "blackout": blackout,
                            "rows": self._gateway_rows(), "error": getattr(self.gw, "last_error", None)},
                "toggles": dict(self.toggles),
                "modules": dict(self.modules, ecg_source=self.ecg_source),
                "ecg": ecg,
            }
            self.last_state = state
            return state

    def _gateway_rows(self):
        rows = []
        if not self.gw:
            return rows
        try:
            for h in self.gw.recent(6):
                ts = datetime.fromisoformat(h["timestamp"]).astimezone()
                rows.append({
                    "t": ts.strftime("%H:%M:%S"),
                    "scenario": h.get("cabin_status"),
                    "hr": (h.get("biometrics") or {}).get("heart_rate_bpm"),
                    "level": (h.get("twin") or {}).get("level"),
                    "forwarded": bool(h.get("_forwarded")),
                })
        except Exception:
            pass
        return rows
