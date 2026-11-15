# MEDICJAB (Aegis-Crew) — Autonomous Astronaut Health & Life Support Engine

> **NASA International Space Apps Challenge 2026**  
> **Challenge:** Create Health Monitoring Software for Astronauts on Space Missions  
> **Domain:** Deep-Space Medicine | Edge AI | Embedded Systems | S.H.A.R.E. Hazards Mitigation  

## 🚀 Overview
**MEDICJAB** is an offline-first, flight-ready medical triaging and environmental monitoring system engineered for non-medical crew members on long-duration space missions.

## 🛡️ S.H.A.R.E. Space Hazards Coverage
1. **Space Radiation:** Tracks cumulative SPE radiation dosage and metabolic stress.
2. **Isolation & Confinement:** Monitors sleep deficit, PVT reaction time, and LED circadian shift protocols.
3. **Earth Distance:** Zero-cloud local edge gateway with SQLite FIFO blackout queue.
4. **Altered Gravity:** Dynamically adjusts blood pressure thresholds across 0g, 0.16g (Moon), and 0.38g (Mars).
5. **Hostile Environments (ECLSS):** Executes differential diagnosis cross-referencing cabin CO2 spikes against crew vital signs.

## 👥 Engineering Squad (UNMSM)
- **Denis Uscamayta:** Lead Systems & Edge AI / tinyML Architect
- **Bryan Pereda:** Biometric Signal Processing & DSP Lead
- **Dick Cordova:** ECLSS & Environmental Telemetry Simulator Lead
- **Jose Huachohuilca:** Embedded Protocols, MQTT & SQLite Resiliency Specialist
- **Mariano Rodriguez:** Bio-Digital Twin & Clinical Engine Specialist
- **Carlos Quincho:** Full-Stack Edge Dashboard & Pitch Lead

## ⚙️ Quickstart & Local Installation

```bash
# Clone the repository
git clone https://github.com/bryanjpt25/medicjab.git
cd medicjab

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

## ⚙️ Execution
```bash
pip install -r requirements.txt
streamlit run app.py