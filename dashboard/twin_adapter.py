"""Puente entre el dashboard y el BioDigitalTwin de Mariano."""
from datetime import datetime, timedelta, timezone

from twin import BioDigitalTwin, CrewSample

CREW_ID = "CDR-01"
SIM_STEP_MIN = 20        # minutos simulados por cada tick (1 s real)
CO2_DEMO_FACTOR = 1.3    # escala de demo para que la fuga llegue a CRITICAL
DOSE_BOOST = 3000.0      # acelera la dosis acumulada para verla en segundos
BACKGROUND_USV_H = 0.2   # radiación de fondo: no se acumula
DOSE_30D_BASE = 16.0     # mGy
DOSE_1Y_BASE = 6.0
LEVEL_MAP = {"CAUTION": "warning", "WARNING": "warning", "CRITICAL": "error"}


class TwinBridge:
    def __init__(self, rules="rules.yaml"):
        self.twin = BioDigitalTwin(rules)
        self.reset()

    def reset(self):
        self.twin.state.crews.clear()
        self.t = datetime(2027, 3, 1, 8, tzinfo=timezone.utc)
        self.dose = 0.0

    def _options(self):
        """Contramedidas de la sesión S.H.A.R.E. activa."""
        cs = self.twin.state.crews.get(CREW_ID)
        if not cs or not cs.session:
            return []
        try:
            return self.twin._options_for(cs.session)
        except Exception:
            return []

    def submit_psych(self, psych):
        """Envía el resultado del mini-test mental. Se ingesta dos veces con
        24 h simuladas de separación porque las reglas mentales exigen
        2 confirmaciones."""
        try:
            rep = None
            for _ in range(2):
                self.t += timedelta(hours=24)
                sample = CrewSample.model_validate({
                    "crew_id": CREW_ID, "timestamp": self.t, "psych": psych})
                rep = self.twin.ingest(sample)
            return {"level": rep.state.overall_level,
                    "mental_index": rep.state.mental_index}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def step(self, bpm, spo2, env):
        try:
            self.t += timedelta(minutes=SIM_STEP_MIN)
            excess = max(0.0, env["radiation_usv_h"] - BACKGROUND_USV_H)
            self.dose += excess * (SIM_STEP_MIN / 60) / 1000 * DOSE_BOOST
            ppco2 = env["co2_ppm"] * 1e-6 * env["pressure_kpa"] * 7.50062 * CO2_DEMO_FACTOR

            vitals = {"spo2_pct": min(100.0, max(50.0, float(spo2))),
                      "core_temp_c": 36.8, "sleep_hours": 7.0}
            if bpm and bpm >= 20:
                vitals["hr_rest_bpm"] = min(float(bpm), 250.0)

            sample = CrewSample.model_validate({
                "crew_id": CREW_ID,
                "timestamp": self.t,
                "vitals": vitals,
                "environment": {
                    "ppco2_mmhg": min(76.0, max(0.0, ppco2)),
                    "cns_dose_30d_mgy": DOSE_30D_BASE + self.dose,
                    "cns_dose_1y_mgy": DOSE_1Y_BASE + self.dose,
                    "noise_sleep_nc": 34.0,
                },
            })
            rep = self.twin.ingest(sample)
            return {
                "level": rep.state.overall_level,
                "share_index": rep.state.share_index,
                "anomaly": rep.state.anomaly_score,
                "alerts": [(LEVEL_MAP.get(a.level, "warning"),
                            f"Gemelo: {a.message}") for a in rep.alerts],
                "citations": {a.rule_id: a.citation for a in rep.alerts},
                "step": rep.share.step,
                "requires_clinician": rep.share.requires_clinician,
                "options": [{"label": o["label"], "benefits": o["benefits"],
                             "limits": o["harms_limits"],
                             "clinician": o["requires_clinician"]}
                            for o in self._options()],
            }
        except Exception as e:   # no debe tumbar el dashboard
            return {"error": f"{type(e).__name__}: {e}"}