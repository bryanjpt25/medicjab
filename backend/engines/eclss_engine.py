"""
eclss_engine.py — Adaptador ECLSS basado en el motor oficial
'Monitor Bio-Orbital' (analyze_mission_telemetry).
"""

import time
from datetime import datetime, timezone

try:
    from monitor_bioorbital import analyze_mission_telemetry
    BIOORBITAL_OK = True
except ImportError:
    BIOORBITAL_OK = False
    analyze_mission_telemetry = None

BASE_SCENARIOS = {
    "NORMAL": {
        "altitude_km": 420.0, "latitude_deg": -26.0, "longitude_deg": -46.0,
        "velocity_kms": 7.66, "utc_hour": 16.0,
        "solar_flux_f107": 150.0, "geomagnetic_kp": 3.0, "spe_level": 0,
        "cabin_co2_mmhg": 2.6, "cabin_pressure_kpa": 101.3, "cabin_o2_pct": 21.0,
        "prebreathe_min": 0, "eva": 0, "mission_days": 45,
        "gravity_g": 0.0, "exercise_h": 2.0, "sleep_h": 7.0,
        "crew_size": 4, "workload_pct": 50.0, "phase": "orbita",
        "sex": "hombre", "ship": "ORION-7", "suit": "Clásico",
    },
    "CO2_LEAK": {
        "altitude_km": 420.0, "latitude_deg": -26.0, "longitude_deg": -46.0,
        "velocity_kms": 7.66, "utc_hour": 16.0,
        "solar_flux_f107": 150.0, "geomagnetic_kp": 3.0, "spe_level": 0,
        "cabin_co2_mmhg": 4.2, "cabin_pressure_kpa": 99.0, "cabin_o2_pct": 20.5,
        "prebreathe_min": 0, "eva": 0, "mission_days": 45,
        "gravity_g": 0.0, "exercise_h": 2.0, "sleep_h": 6.0,
        "crew_size": 4, "workload_pct": 65.0, "phase": "orbita",
        "sex": "hombre", "ship": "ORION-7", "suit": "Clásico",
    },
    "SPE_EVENT": {
        "altitude_km": 420.0, "latitude_deg": -26.0, "longitude_deg": -46.0,
        "velocity_kms": 7.66, "utc_hour": 16.0,
        "solar_flux_f107": 220.0, "geomagnetic_kp": 7.5, "spe_level": 4,
        "cabin_co2_mmhg": 2.8, "cabin_pressure_kpa": 101.0, "cabin_o2_pct": 21.0,
        "prebreathe_min": 0, "eva": 0, "mission_days": 45,
        "gravity_g": 0.0, "exercise_h": 1.0, "sleep_h": 6.5,
        "crew_size": 4, "workload_pct": 60.0, "phase": "orbita",
        "sex": "hombre", "ship": "ORION-7", "suit": "Clásico",
    },
    "SLOW_DEPRESS": {
        "altitude_km": 420.0, "latitude_deg": -26.0, "longitude_deg": -46.0,
        "velocity_kms": 7.66, "utc_hour": 16.0,
        "solar_flux_f107": 150.0, "geomagnetic_kp": 3.0, "spe_level": 0,
        "cabin_co2_mmhg": 2.8, "cabin_pressure_kpa": 88.5, "cabin_o2_pct": 20.0,
        "prebreathe_min": 0, "eva": 0, "mission_days": 45,
        "gravity_g": 0.0, "exercise_h": 1.5, "sleep_h": 6.5,
        "crew_size": 4, "workload_pct": 55.0, "phase": "orbita",
        "sex": "hombre", "ship": "ORION-7", "suit": "Clásico",
    },
}

class ECLSSTelemetrySimulator:
    def __init__(self, live: bool = False):
        self.live = live
        self.active_crisis = "NORMAL"
        self._base = dict(BASE_SCENARIOS["NORMAL"])
        self.orbit = {
            "altitude_km": self._base["altitude_km"],
            "latitude_deg": self._base["latitude_deg"],
            "longitude_deg": self._base["longitude_deg"],
            "mission_days": self._base["mission_days"],
        }

    def trigger_crisis(self, crisis_type: str):
        if crisis_type in BASE_SCENARIOS:
            self.active_crisis = crisis_type
            self._base = dict(BASE_SCENARIOS[crisis_type])
            self._base["altitude_km"] = self.orbit["altitude_km"]
            self._base["latitude_deg"] = self.orbit["latitude_deg"]
            self._base["longitude_deg"] = self.orbit["longitude_deg"]
            self._base["mission_days"] = self.orbit["mission_days"]

    def set_orbital_params(self, altitude_km=None, latitude_deg=None, longitude_deg=None, mission_days=None):
        if altitude_km is not None: self.orbit["altitude_km"] = float(altitude_km)
        if latitude_deg is not None: self.orbit["latitude_deg"] = float(latitude_deg)
        if longitude_deg is not None: self.orbit["longitude_deg"] = float(longitude_deg)
        if mission_days is not None: self.orbit["mission_days"] = float(mission_days)

    def generate_telemetry_packet(self) -> dict:
        params = dict(self._base)
        params["altitude_km"] = self.orbit["altitude_km"]
        params["latitude_deg"] = self.orbit["latitude_deg"]
        params["longitude_deg"] = self.orbit["longitude_deg"]
        params["mission_days"] = self.orbit["mission_days"]
        params["utc_hour"] = datetime.now(timezone.utc).hour + datetime.now(timezone.utc).minute / 60.0

        if BIOORBITAL_OK and analyze_mission_telemetry:
            result = analyze_mission_telemetry(params)
            rad = result["radiation"]
            radiation_usv_h = rad["total"]
        else:
            # Fallback de emergencia si no está el motor oficial
            radiation_usv_h = 0.12
            if self.active_crisis == "SPE_EVENT": radiation_usv_h = 25.0

        pressure_kpa = params["cabin_pressure_kpa"]
        co2_ppm = params["cabin_co2_mmhg"] * 1_000_000.0 / 760.0
        vocs_ppb = 40.0 + 0.06 * co2_ppm + 2.0 * params["workload_pct"]
        
        over_co2 = max(0.0, co2_ppm - 1000.0) / 1000.0
        temp_c = 22.5 + 0.4 * over_co2 + 0.15 * (101.3 - pressure_kpa)

        return {
            "timestamp": time.time(),
            "cabin_status": self.active_crisis,
            "environment": {
                "co2_ppm": round(co2_ppm, 2),
                "vocs_ppb": round(vocs_ppb, 2),
                "pressure_kpa": round(pressure_kpa, 2),
                "temperature_c": round(temp_c, 2),
                "radiation_usv_h": round(radiation_usv_h, 4),
            },
        }

    def last_full_analysis(self) -> dict:
        params = dict(self._base)
        params.update(self.orbit)
        params["utc_hour"] = datetime.now(timezone.utc).hour
        if BIOORBITAL_OK and analyze_mission_telemetry:
            return analyze_mission_telemetry(params)
        else:
            return {
                "risk_score": 0, "status": "NOMINAL", "zone": {"name": "Desconocida"},
                "radiation": {"cum_msv": 0, "limit_pct": 0, "total": 0, "gcr": 0, "saa": 0},
                "metrics": {"delay_oneway_s": 0, "autonomy_need_pct": 0},
                "anomalies": [], "supplies": {"food_kg": 0, "water_l": 0, "med_kits": 0, "resupply_possible": True, "status": ""}
            }