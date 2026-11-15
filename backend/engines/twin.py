#!/usr/bin/env python3
"""
AEGIS-CREW · twin.py · Gemelo Bio-Digital + motor clínico S.H.A.R.E.

Offline-first / edge: sin red, determinista, estado persistible en JSON.
Dependencias: pandas, numpy, pydantic>=2, pyyaml, scipy, statsmodels (+ stdlib).

Uso:
  python twin.py --demo
  python twin.py --sample muestra.json --state estado.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from scipy import stats

ENGINE_VERSION = "1.2.0"
SCHEMA_VERSION = "aegis-crew/1.0"
STEPS = ["SEEK", "HELP", "ASSESS", "REACH", "EVALUATE"]
WATCHFUL = {
    "id": "CM-WATCHFUL", "label": "Observación activa sin intervención",
    "benefits": "Sin carga adicional de agenda; permite ver si el cuadro se resuelve solo.",
    "harms_limits": "Si progresa se pierde tiempo; no admisible por sí sola en eventos de seguridad.",
    "requires_clinician": False, "effort": "ninguna", "evidence": "AHRQ SHARE (incluir siempre la opción de no tratar)",
}


class Level(IntEnum):
    NOMINAL = 0
    CAUTION = 1
    WARNING = 2
    CRITICAL = 3


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def _r(v: float, n: int = 4) -> float:
    return round(float(v), n)


# =============================================================================
# 1. MODELOS DE REGLAS
# =============================================================================
class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Thresholds(Strict):
    caution: float
    warning: float
    critical: float


class Rule(Strict):
    id: str
    domain: Literal["vital", "environment", "mental"]
    variable: str
    direction: Literal["high", "low"]
    unit: str
    nominal_ref: float
    thresholds: Thresholds
    weight: float = Field(1.0, gt=0, le=1.0)
    tau_hours: Optional[float] = None
    confirm_up: Optional[int] = Field(None, ge=1)
    confirm_down: Optional[int] = Field(None, ge=1)
    bypass_confirm: Optional[int] = Field(None, ge=1)
    latch_until_ack: bool = False
    safety_override: bool = False
    evidence_level: Literal["standard_numeric", "standard_qualitative",
                            "clinical_framework", "engineering_placeholder"]
    citation: str
    rationale: str
    countermeasure_tags: list[str] = Field(default_factory=list)

    @property
    def sign(self) -> int:
        return 1 if self.direction == "high" else -1

    @model_validator(mode="after")
    def _monotonic(self) -> "Rule":
        t, s = self.thresholds, self.sign
        xs = [s * v for v in (self.nominal_ref, t.caution, t.warning, t.critical)]
        if not all(a < b for a, b in zip(xs, xs[1:])):
            raise ValueError(f"{self.id}: umbrales no monótonos para direction={self.direction}")
        return self


class DomainDefaults(Strict):
    tau_hours: float
    confirm_up: int
    confirm_down: int
    stale_after_hours: float


class EngineCfg(Strict):
    domain_weights: dict[str, float]
    severity_anchors: list[float]
    blend_weighted_mean: float
    blend_worst_case: float
    hysteresis_margin_fraction: float
    baseline_min_samples: int
    baseline_max_samples: int
    trend_window_days: float
    trend_min_points: int
    trend_p_value: float
    trend_max_bump: float
    domain_defaults: dict[str, DomainDefaults]


class Countermeasure(Strict):
    id: str
    label: str
    tags: list[str]
    benefits: str
    harms_limits: str
    effort: str
    requires_clinician: bool
    evidence: str


class ShareCfg(Strict):
    follow_up_hours: dict[str, float]
    min_improvement: float
    prompts: dict[str, list[str]]
    assess_questions: list[str]


class RuleBook(Strict):
    meta: dict[str, Any]
    engine: EngineCfg
    rules: list[Rule]
    countermeasures: list[Countermeasure]
    share: ShareCfg

    @model_validator(mode="after")
    def _consistency(self) -> "RuleBook":
        ids = [r.id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs de regla duplicados")
        for r in self.rules:
            if r.domain not in self.engine.domain_weights or r.domain not in self.engine.domain_defaults:
                raise ValueError(f"{r.id}: dominio sin pesos/defaults")
        if len(self.engine.severity_anchors) != 3:
            raise ValueError("severity_anchors debe tener 3 valores")
        return self


# =============================================================================
# 2. MODELOS DE ENTRADA
# =============================================================================
class VitalSigns(Strict):
    spo2_pct: Optional[float] = Field(None, ge=50, le=100)
    hr_rest_bpm: Optional[float] = Field(None, ge=20, le=250)
    core_temp_c: Optional[float] = Field(None, ge=30, le=43)
    sleep_hours: Optional[float] = Field(None, ge=0, le=24)


class Environment(Strict):
    ppco2_mmhg: Optional[float] = Field(None, ge=0, le=76)
    cns_dose_30d_mgy: Optional[float] = Field(None, ge=0)
    cns_dose_1y_mgy: Optional[float] = Field(None, ge=0)
    noise_sleep_nc: Optional[float] = Field(None, ge=0, le=120)


class PsychMiniTest(Strict):
    """Mini-test diario (~2 min): VAS + PHQ-2 + GAD-2 + ítem 9 + carga + cognición + proceso."""
    stress_vas_0_10: Optional[float] = Field(None, ge=0, le=10)
    mental_fatigue_vas: Optional[float] = Field(None, ge=0, le=10)
    phq2_score: Optional[int] = Field(None, ge=0, le=6)
    gad2_score: Optional[int] = Field(None, ge=0, le=6)
    phq9_item9: Optional[int] = Field(None, ge=0, le=3)
    tlx_weighted_0_100: Optional[float] = Field(None, ge=0, le=100)
    bedford_workload_1_10: Optional[int] = Field(None, ge=1, le=10)
    cognitive_z: Optional[float] = Field(None, ge=-8, le=8)
    days_since_ppc: Optional[float] = Field(None, ge=0)
    # NUEVAS variables mentales
    social_contact_days: Optional[float] = Field(None, ge=0)
    irritability_vas: Optional[float] = Field(None, ge=0, le=10)
    motivation_vas: Optional[float] = Field(None, ge=0, le=10)
    appetite_vas: Optional[float] = Field(None, ge=0, le=10)


class CrewSample(Strict):
    crew_id: str
    timestamp: datetime
    vitals: VitalSigns = Field(default_factory=VitalSigns)
    environment: Environment = Field(default_factory=Environment)
    psych: PsychMiniTest = Field(default_factory=PsychMiniTest)

    @field_validator("timestamp")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _utc(v)

    def flat(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for blk in (self.vitals, self.environment, self.psych):
            out.update({k: float(v) for k, v in blk.model_dump().items() if v is not None})
        return out


# =============================================================================
# 3. ESTADO PERSISTENTE
# =============================================================================
class RuleState(BaseModel):
    smoothed: Optional[float] = None
    last_raw: Optional[float] = None
    last_ts: Optional[datetime] = None
    level: int = 0
    since: Optional[datetime] = None
    up: int = 0
    down: int = 0
    bypass: int = 0
    acked: bool = False
    baseline: list[float] = Field(default_factory=list)


class HistPoint(BaseModel):
    ts: datetime
    mental_index: float


class ShareSession(BaseModel):
    session_id: str
    crew_id: str
    opened_at: datetime
    trigger_level: int
    trigger_rule_ids: list[str]
    baseline_share_index: float
    requires_clinician: bool = False
    step: Literal["SEEK", "HELP", "ASSESS", "REACH", "EVALUATE"] = "SEEK"
    status: Literal["OPEN", "PENDING_CLINICIAN", "CLOSED"] = "OPEN"
    problem_summary: list[str] = Field(default_factory=list)
    responses: dict[str, dict] = Field(default_factory=dict)
    decision: Optional[dict] = None
    excluded_options: list[str] = Field(default_factory=list)
    follow_up_due: Optional[datetime] = None
    cycles: int = 0
    log: list[dict] = Field(default_factory=list)


class CrewState(BaseModel):
    rules: dict[str, RuleState] = Field(default_factory=dict)
    history: list[HistPoint] = Field(default_factory=list)
    session: Optional[ShareSession] = None
    closed_sessions: list[ShareSession] = Field(default_factory=list)


class EngineState(BaseModel):
    crews: dict[str, CrewState] = Field(default_factory=dict)


# =============================================================================
# 4. MODELOS DE SALIDA (contrato AEGIS-CREW v1.0)
# =============================================================================
class AlertOut(BaseModel):
    alert_id: str
    rule_id: str
    domain: str
    variable: str
    level: str
    direction: str
    observed_value: float
    smoothed_value: float
    unit: str
    threshold_crossed: float
    severity: float
    anomaly_z: Optional[float]
    since: datetime
    safety_override: bool
    evidence_level: str
    citation: str
    rationale: str
    message: str


class StateOut(BaseModel):
    overall_level: str
    share_index: float
    anomaly_score: float
    mental_index: Optional[float]
    physical_index: Optional[float]
    domain_severity: dict[str, float]
    trend: dict[str, Any]


class ExplainOut(BaseModel):
    share_index_formula: str
    top_contributors: list[dict[str, Any]]
    anomaly_top: list[dict[str, Any]]


class DataQuality(BaseModel):
    updated_rules: list[str]
    missing_rules: list[str]
    stale_rules: list[str]
    baseline_ready_fraction: float
    warnings: list[str]


class Traceability(BaseModel):
    rules_version: str
    rules_sha256: str
    engine_version: str
    input_sha256: str


class ShareOut(BaseModel):
    active: bool
    session_id: Optional[str] = None
    step: Optional[str] = None
    status: Optional[str] = None
    requires_clinician: bool = False
    trigger_level: Optional[str] = None
    trigger_rules: list[str] = Field(default_factory=list)
    follow_up_due: Optional[datetime] = None
    cycles: int = 0
    prompt: dict[str, Any] = Field(default_factory=dict)
    options: list[dict[str, Any]] = Field(default_factory=list)


class AegisReport(BaseModel):
    schema_version: str
    message_id: str
    generated_at: datetime
    source_module: str
    crew_id: str
    timestamp: datetime
    state: StateOut
    alerts: list[AlertOut]
    explain: ExplainOut
    share: ShareOut
    data_quality: DataQuality
    traceability: Traceability


# =============================================================================
# 5. MOTOR
# =============================================================================
class BioDigitalTwin:
    def __init__(self, rules_path: str | Path = "rules.yaml") -> None:
        raw = Path(rules_path).read_bytes()
        self.rules_sha256 = hashlib.sha256(raw).hexdigest()
        self.rb = RuleBook.model_validate(yaml.safe_load(raw))
        self._rules = {r.id: r for r in self.rb.rules}
        self._cms = {c.id: c for c in self.rb.countermeasures}
        self.state = EngineState()

    def save_state(self, path: str | Path) -> None:
        p = Path(path)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(self.state.model_dump_json(), encoding="utf-8")
        tmp.replace(p)

    def load_state(self, path: str | Path) -> None:
        self.state = EngineState.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def _dd(self, rule: Rule) -> DomainDefaults:
        return self.rb.engine.domain_defaults[rule.domain]

    @staticmethod
    def _level(rule: Rule, value: float, worsen: float = 0.0) -> Level:
        s, t = rule.sign, rule.thresholds
        x = s * value + worsen
        if x >= s * t.critical:
            return Level.CRITICAL
        if x >= s * t.warning:
            return Level.WARNING
        if x >= s * t.caution:
            return Level.CAUTION
        return Level.NOMINAL

    def _margin(self, rule: Rule) -> float:
        return self.rb.engine.hysteresis_margin_fraction * abs(rule.thresholds.caution - rule.nominal_ref)

    def _severity(self, rule: Rule, value: float) -> float:
        s, t = rule.sign, rule.thresholds
        xs = [s * rule.nominal_ref, s * t.caution, s * t.warning, s * t.critical]
        ys = [0.0, *self.rb.engine.severity_anchors]
        x = s * value
        if x <= xs[0]:
            return 0.0
        if x >= xs[-1]:
            span = xs[-1] - xs[-2]
            return float(min(1.0, ys[-1] + (1.0 - ys[-1]) * min(1.0, (x - xs[-1]) / span)))
        return float(np.interp(x, xs, ys))

    def _band(self, level: Level) -> tuple[float, float]:
        a = self.rb.engine.severity_anchors
        lo = [0.0, *a]
        hi = [*a, 1.0]
        return lo[int(level)], hi[int(level)]

    @staticmethod
    def _set_level(st: RuleState, lvl: Level, ts: datetime) -> None:
        if int(lvl) != st.level:
            st.level, st.since = int(lvl), ts
            if lvl == Level.NOMINAL:
                st.acked = False
        st.up = st.down = 0

    def _update_rule(self, rule: Rule, st: RuleState, value: float, ts: datetime) -> bool:
        if st.last_ts is not None and ts < st.last_ts:
            return False
        d = self._dd(rule)
        tau = d.tau_hours if rule.tau_hours is None else rule.tau_hours
        c_up = d.confirm_up if rule.confirm_up is None else rule.confirm_up
        c_dn = d.confirm_down if rule.confirm_down is None else rule.confirm_down

        if st.smoothed is None or tau <= 0:
            alpha = 1.0
        else:
            dt_h = (ts - st.last_ts).total_seconds() / 3600.0
            alpha = 1.0 - math.exp(-dt_h / tau)
        prev = value if st.smoothed is None else st.smoothed
        st.smoothed = alpha * value + (1.0 - alpha) * prev
        st.last_raw, st.last_ts = value, ts

        cur = Level(st.level)
        cand = self._level(rule, st.smoothed)
        raw_lvl = self._level(rule, value)

        st.bypass = st.bypass + 1 if (rule.bypass_confirm and raw_lvl == Level.CRITICAL) else 0
        if rule.bypass_confirm and st.bypass >= rule.bypass_confirm and cur < Level.CRITICAL:
            self._set_level(st, Level.CRITICAL, ts)
            cur = Level.CRITICAL

        latched = rule.latch_until_ack and cur >= Level.WARNING and not st.acked

        if cand > cur:
            st.up, st.down = st.up + 1, 0
            if st.up >= c_up:
                self._set_level(st, cand, ts)
        elif cand < cur:
            st.up = 0
            relaxed = self._level(rule, st.smoothed, worsen=self._margin(rule))
            if relaxed < cur and st.bypass == 0 and not latched:
                st.down += 1
                if st.down >= c_dn:
                    self._set_level(st, relaxed, ts)
            else:
                st.down = 0
        else:
            st.up = st.down = 0

        if st.level == Level.NOMINAL:
            st.baseline.append(value)
            del st.baseline[:-self.rb.engine.baseline_max_samples]
        return True

    def acknowledge_latch(self, crew_id: str, rule_id: str, clinician_id: str,
                          ts: Optional[datetime] = None) -> None:
        cs = self.state.crews[crew_id]
        cs.rules[rule_id].acked = True
        if cs.session:
            self._log(cs.session, _utc(ts or datetime.now(timezone.utc)), "LATCH_ACK",
                      rule_id=rule_id, clinician_id=clinician_id)

    def _anomaly_row(self, rule: Rule, st: RuleState) -> tuple[Optional[float], float]:
        if st.smoothed is None or len(st.baseline) < self.rb.engine.baseline_min_samples:
            return None, 0.0
        arr = np.asarray(st.baseline, dtype=float)
        med = float(np.median(arr))
        mad = float(stats.median_abs_deviation(arr, scale="normal"))
        scale = max(mad, 0.25 * abs(rule.thresholds.caution - rule.nominal_ref), 1e-9)
        z = rule.sign * (st.smoothed - med) / scale
        a = float(2.0 * stats.norm.cdf(z) - 1.0) if z > 0 else 0.0
        return float(z), a

    def _trend(self, cs: CrewState) -> dict[str, Any]:
        cfg = self.rb.engine
        out = {"available": False, "slope_per_day": None, "p_value": None, "n": 0, "worsening": False}
        if len(cs.history) < cfg.trend_min_points:
            return out
        df = pd.DataFrame([(h.ts, h.mental_index) for h in cs.history], columns=["ts", "y"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df[df["ts"] >= df["ts"].max() - pd.Timedelta(days=cfg.trend_window_days)]
        out["n"] = int(len(df))
        if len(df) < cfg.trend_min_points or df["y"].nunique() < 2 or df["ts"].nunique() < 2:
            return out
        x = (df["ts"] - df["ts"].min()).dt.total_seconds().to_numpy() / 86400.0
        res = sm.OLS(df["y"].to_numpy(), sm.add_constant(x)).fit()
        slope, p = float(res.params[1]), float(res.pvalues[1])
        if math.isnan(p):
            return out
        out.update(available=True, slope_per_day=_r(slope), p_value=_r(p),
                   worsening=bool(slope > 0 and p < cfg.trend_p_value))
        return out

    # ------------------------------ INGESTA ----------------------------------
    def ingest(self, sample: CrewSample) -> AegisReport:
        cfg, ts = self.rb.engine, sample.timestamp
        cs = self.state.crews.setdefault(sample.crew_id, CrewState())
        flat = sample.flat()
        updated, missing, stale, warns = [], [], [], []

        # === FIX de Claude: bloque limpio, sin truco ternario enrevesado ===
        for rule in self.rb.rules:
            st = cs.rules.setdefault(rule.id, RuleState())
            if rule.variable in flat:
                if self._update_rule(rule, st, flat[rule.variable], ts):
                    updated.append(rule.id)
                else:
                    warns.append(f"OUT_OF_ORDER:{rule.id}")
            else:
                missing.append(rule.id)
                if st.last_ts is not None and (ts - st.last_ts).total_seconds() / 3600 > self._dd(rule).stale_after_hours:
                    stale.append(rule.id)

        rows = []
        for rule in self.rb.rules:
            st = cs.rules.get(rule.id)
            if st is None or st.smoothed is None:
                continue
            lvl = Level(st.level)
            sev = self._severity(rule, st.smoothed)
            lo, hi = self._band(lvl)
            eff = float(np.clip(sev, lo, hi))
            z, a = self._anomaly_row(rule, st)
            rows.append({"rule": rule, "st": st, "lvl": lvl, "sev": sev, "eff": eff, "z": z, "a": a})

        overall = max((r["lvl"] for r in rows), default=Level.NOMINAL)

        num: dict[str, float] = {}
        den: dict[str, float] = {}
        for r in rows:
            d = r["rule"].domain
            num[d] = num.get(d, 0.0) + r["rule"].weight * r["eff"]
            den[d] = den.get(d, 0.0) + r["rule"].weight
        dom_sev = {d: num[d] / den[d] for d in num}
        wsum = sum(cfg.domain_weights[d] for d in dom_sev) or 1.0
        weighted = sum(cfg.domain_weights[d] * dom_sev[d] for d in dom_sev) / wsum
        worst = max((r["eff"] for r in rows), default=0.0)
        blend = cfg.blend_weighted_mean * weighted + cfg.blend_worst_case * worst
        share_index = float(np.clip(max(blend, self._band(overall)[0]), 0.0, 1.0))

        mental_idx = dom_sev.get("mental")
        phys_vals = [(r["rule"].weight, r["eff"]) for r in rows if r["rule"].domain != "mental"]
        physical_idx = (sum(w * e for w, e in phys_vals) / sum(w for w, _ in phys_vals)) if phys_vals else None

        if mental_idx is not None and any(self._rules[u].domain == "mental" for u in updated):
            cs.history.append(HistPoint(ts=ts, mental_index=float(mental_idx)))
            del cs.history[:-400]
        trend = self._trend(cs)

        ready = [r for r in rows if r["z"] is not None]
        if ready:
            ws = np.array([r["rule"].weight * cfg.domain_weights[r["rule"].domain] for r in ready])
            av = np.array([r["a"] for r in ready])
            anomaly = 0.5 * float((ws * av).sum() / ws.sum()) + 0.5 * float(av.max())
        else:
            anomaly = 0.0
        if trend["worsening"]:
            anomaly += min(cfg.trend_max_bump, trend["slope_per_day"] * 10.0)
        anomaly = float(np.clip(anomaly, 0.0, 1.0))

        alerts: list[AlertOut] = []
        for r in sorted(rows, key=lambda x: (-int(x["lvl"]), -x["eff"])):
            if r["lvl"] < Level.CAUTION:
                continue
            rule, st = r["rule"], r["st"]
            thr = getattr(rule.thresholds, r["lvl"].name.lower())
            since = st.since or ts
            alerts.append(AlertOut(
                alert_id=f"{sample.crew_id}:{rule.id}:{r['lvl'].name}:{since.strftime('%Y%m%dT%H%M%SZ')}",
                rule_id=rule.id, domain=rule.domain, variable=rule.variable, level=r["lvl"].name,
                direction=rule.direction, observed_value=_r(st.last_raw), smoothed_value=_r(st.smoothed),
                unit=rule.unit, threshold_crossed=thr, severity=_r(r["eff"]),
                anomaly_z=None if r["z"] is None else _r(r["z"]), since=since,
                safety_override=rule.safety_override, evidence_level=rule.evidence_level,
                citation=rule.citation, rationale=rule.rationale,
                message=f"[{r['lvl'].name}] {rule.id}: {rule.variable}={st.smoothed:.2f} {rule.unit} "
                        f"({'>=' if rule.direction == 'high' else '<='} {thr:g})"))

        tot = sum(r["rule"].weight * r["eff"] for r in rows) or 1.0
        top = sorted(rows, key=lambda r: -r["rule"].weight * r["eff"])[:5]
        explain = ExplainOut(
            share_index_formula=(f"max({cfg.blend_weighted_mean}*media_ponderada_dominios + "
                                 f"{cfg.blend_worst_case}*peor_regla, piso_del_nivel)"),
            top_contributors=[{"rule_id": r["rule"].id, "severity": _r(r["eff"]), "level": r["lvl"].name,
                               "share_of_load": _r(r["rule"].weight * r["eff"] / tot)} for r in top if r["eff"] > 0],
            anomaly_top=[{"rule_id": r["rule"].id, "z": _r(r["z"]), "a": _r(r["a"])}
                         for r in sorted(ready, key=lambda r: -r["a"])[:3] if r["a"] > 0])

        self._sync_share(cs, sample.crew_id, ts, overall, alerts, share_index)

        input_hash = hashlib.sha256(json.dumps(sample.model_dump(mode="json", exclude_none=True),
                                               sort_keys=True).encode()).hexdigest()
        return AegisReport(
            schema_version=SCHEMA_VERSION,
            message_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{sample.crew_id}|{ts.isoformat()}|{input_hash}")),
            generated_at=datetime.now(timezone.utc), source_module="bio_digital_twin",
            crew_id=sample.crew_id, timestamp=ts,
            state=StateOut(overall_level=overall.name, share_index=_r(share_index), anomaly_score=_r(anomaly),
                           mental_index=None if mental_idx is None else _r(mental_idx),
                           physical_index=None if physical_idx is None else _r(physical_idx),
                           domain_severity={k: _r(v) for k, v in dom_sev.items()}, trend=trend),
            alerts=alerts, explain=explain, share=self._share_out(cs),
            data_quality=DataQuality(updated_rules=updated, missing_rules=missing, stale_rules=stale,
                                     baseline_ready_fraction=_r(len(ready) / max(len(rows), 1)), warnings=warns),
            traceability=Traceability(rules_version=str(self.rb.meta.get("rules_version", "?")),
                                      rules_sha256=self.rules_sha256, engine_version=ENGINE_VERSION,
                                      input_sha256=input_hash))

    # ============================ SHARE ======================================
    @staticmethod
    def _log(sess: ShareSession, ts: datetime, event: str, **data: Any) -> None:
        sess.log.append({"ts": ts.isoformat(), "event": event, **data})

    def _options_for(self, sess: ShareSession) -> list[dict[str, Any]]:
        tags: set[str] = set()
        for rid in sess.trigger_rule_ids:
            if rid in self._rules:  # protección ante IDs huérfanos
                tags |= set(self._rules[rid].countermeasure_tags)
        scored = []
        for cm in self.rb.countermeasures:
            hit = len(tags & set(cm.tags))
            if hit and cm.id not in sess.excluded_options:
                scored.append((cm.requires_clinician, -hit, cm))
        scored.sort(key=lambda x: (x[0], x[1]))
        chosen = [cm for *_, cm in scored][:6]
        if sess.requires_clinician and "CM-PMC-CMO" not in {c.id for c in chosen} and "CM-PMC-CMO" in self._cms:
            chosen.append(self._cms["CM-PMC-CMO"])
        opts = [c.model_dump() for c in chosen]
        if "CM-WATCHFUL" not in sess.excluded_options:
            opts.append(dict(WATCHFUL))
        return opts

    def _sync_share(self, cs: CrewState, crew_id: str, ts: datetime, overall: Level,
                    alerts: list[AlertOut], share_index: float) -> None:
        needs_clin = overall == Level.CRITICAL or any(a.safety_override for a in alerts)
        rule_ids = [a.rule_id for a in alerts]
        summary = [a.message for a in alerts[:5]]
        sess = cs.session
        if sess is None:
            if overall >= Level.CAUTION:
                sess = ShareSession(session_id=f"SHR-{crew_id}-{ts.strftime('%Y%m%dT%H%M%S')}", crew_id=crew_id,
                                    opened_at=ts, trigger_level=int(overall), trigger_rule_ids=rule_ids,
                                    baseline_share_index=share_index, requires_clinician=needs_clin,
                                    problem_summary=summary)
                self._log(sess, ts, "OPENED", level=overall.name, rules=rule_ids)
                cs.session = sess
            return
        sess.problem_summary = summary
        for rid in rule_ids:
            if rid not in sess.trigger_rule_ids:
                sess.trigger_rule_ids.append(rid)
        if int(overall) > sess.trigger_level:
            sess.trigger_level = int(overall)
            self._log(sess, ts, "ESCALATED", level=overall.name)
        if needs_clin and not sess.requires_clinician:
            sess.requires_clinician = True
            self._log(sess, ts, "CLINICIAN_REQUIRED")
        if overall == Level.NOMINAL and sess.step in ("SEEK", "HELP", "ASSESS"):
            self._close(cs, sess, ts, "RESOLVED_BEFORE_DECISION")
        elif sess.step == "EVALUATE" and sess.follow_up_due and ts >= sess.follow_up_due:
            self._evaluate(cs, sess, ts, overall, share_index)

    def _close(self, cs: CrewState, sess: ShareSession, ts: datetime, outcome: str) -> None:
        sess.status = "CLOSED"
        self._log(sess, ts, "CLOSED", outcome=outcome)
        cs.closed_sessions.append(sess.model_copy(deep=True))
        del cs.closed_sessions[:-20]
        cs.session = None

    def _evaluate(self, cs: CrewState, sess: ShareSession, ts: datetime, overall: Level, share_index: float) -> None:
        cfg = self.rb.share
        delta = sess.baseline_share_index - share_index
        sess.cycles += 1
        if overall == Level.NOMINAL:
            self._log(sess, ts, "EVALUATED", outcome="RESOLVED", delta=_r(delta))
            self._close(cs, sess, ts, "RESOLVED")
        elif overall < Level(sess.trigger_level) or delta >= cfg.min_improvement:
            sess.follow_up_due = ts + timedelta(hours=cfg.follow_up_hours[overall.name])
            sess.baseline_share_index = share_index
            self._log(sess, ts, "EVALUATED", outcome="IMPROVING_CONTINUE_PLAN", delta=_r(delta))
        else:
            chosen = (sess.decision or {}).get("chosen_option_id")
            if chosen:
                sess.excluded_options.append(chosen)
            if overall >= Level.WARNING:
                sess.requires_clinician = True
            sess.step, sess.status, sess.decision, sess.follow_up_due = "HELP", "OPEN", None, None
            sess.baseline_share_index, sess.trigger_level = share_index, int(overall)
            self._log(sess, ts, "EVALUATED", outcome="NO_IMPROVEMENT_REOPEN_HELP", delta=_r(delta))

    def _share_out(self, cs: CrewState) -> ShareOut:
        s = cs.session
        if s is None:
            return ShareOut(active=False)
        cfg = self.rb.share
        prompt: dict[str, Any] = {"instructions": cfg.prompts[s.step.lower()]}
        if s.step == "SEEK":
            prompt.update(problem_summary=s.problem_summary, may_decline=True, invite_crew_or_family=True)
        elif s.step == "ASSESS":
            prompt["questions"] = cfg.assess_questions
        elif s.step == "REACH":
            prompt.update(requires_clinician_confirmation=s.requires_clinician, may_delegate=True,
                          follow_up_hours=cfg.follow_up_hours[Level(s.trigger_level).name])
        elif s.step == "EVALUATE":
            prompt["follow_up_due"] = s.follow_up_due.isoformat() if s.follow_up_due else None
        return ShareOut(active=True, session_id=s.session_id, step=s.step, status=s.status,
                        requires_clinician=s.requires_clinician, trigger_level=Level(s.trigger_level).name,
                        trigger_rules=s.trigger_rule_ids, follow_up_due=s.follow_up_due, cycles=s.cycles,
                        prompt=prompt, options=self._options_for(s) if s.step in ("HELP", "REACH") else [])

    def record_share_response(self, crew_id: str, step: str, response: dict[str, Any],
                              ts: Optional[datetime] = None) -> ShareOut:
        ts = _utc(ts or datetime.now(timezone.utc))
        cs = self.state.crews[crew_id]
        s = cs.session
        if s is None or s.status == "CLOSED":
            raise ValueError("No hay sesión SHARE abierta")
        if step != s.step:
            raise ValueError(f"Paso esperado: {s.step}")

        if step == "SEEK":
            if response.get("participation") not in ("yes", "delegate", "decline"):
                raise ValueError("participation ∈ {yes, delegate, decline}")
            s.responses["SEEK"] = response
            s.step = "HELP"
        elif step == "HELP":
            if not response.get("teach_back_ok"):
                self._log(s, ts, "TEACH_BACK_FAILED")
                return self._share_out(cs)
            s.responses["HELP"] = response
            s.step = "ASSESS"
        elif step == "ASSESS":
            if not response.get("priorities"):
                raise ValueError("priorities requerido (lista no vacía)")
            s.responses["ASSESS"] = response
            s.step = "REACH"
        elif step == "REACH":
            opt_ids = {o["id"] for o in self._options_for(s)}
            chosen = response.get("chosen_option_id")
            if chosen not in opt_ids:
                raise ValueError(f"chosen_option_id debe ser uno de {sorted(opt_ids)}")
            if s.requires_clinician and not response.get("clinician_confirmed"):
                s.status = "PENDING_CLINICIAN"
                self._log(s, ts, "PENDING_CLINICIAN", chosen=chosen)
                return self._share_out(cs)
            s.responses["REACH"] = response
            s.decision = {"chosen_option_id": chosen, "delegated_to": response.get("delegated_to"),
                          "clinician_confirmed": bool(response.get("clinician_confirmed")), "decided_at": ts.isoformat()}
            hours = self.rb.share.follow_up_hours[Level(s.trigger_level).name]
            s.follow_up_due, s.status, s.step = ts + timedelta(hours=hours), "OPEN", "EVALUATE"
        else:
            s.responses["EVALUATE"] = response
        self._log(s, ts, f"STEP_{step}_DONE")
        return self._share_out(cs)


# =============================================================================
# 6. DEMO y CLI
# =============================================================================
def _demo(rules: str) -> None:
    rng = np.random.default_rng(7)
    twin = BioDigitalTwin(rules)
    t0 = datetime(2027, 3, 1, 8, tzinfo=timezone.utc)
    last: Optional[AegisReport] = None

    for day in range(45):
        ts = t0 + timedelta(days=day)
        drift = max(0.0, day - 18) / 22.0
        n = lambda m, s: float(rng.normal(m, s))
        s = CrewSample(
            crew_id="CDR-01", timestamp=ts,
            vitals=VitalSigns(
                spo2_pct=float(np.clip(n(97.5, 0.5), 90, 100)),
                hr_rest_bpm=n(64 + 12 * drift, 2),
                core_temp_c=n(36.8, 0.12),
                sleep_hours=float(np.clip(n(6.9 - 2.4 * drift, 0.4), 2, 10))),
            environment=Environment(
                ppco2_mmhg=float(np.clip(n(2.6 + 1.0 * drift, 0.12), 0, 76)),
                cns_dose_30d_mgy=n(16, 1.0),
                cns_dose_1y_mgy=0.55 * day,
                noise_sleep_nc=n(34 + 4 * drift, 0.8)),
            psych=PsychMiniTest(
                stress_vas_0_10=float(np.clip(n(2 + 6 * drift, 0.5), 0, 10)),
                mental_fatigue_vas=float(np.clip(n(2 + 5.5 * drift, 0.5), 0, 10)),
                phq2_score=int(np.clip(round(n(0.4 + 3.2 * drift, 0.4)), 0, 6)),
                gad2_score=int(np.clip(round(n(0.4 + 3.0 * drift, 0.4)), 0, 6)),
                phq9_item9=0,
                tlx_weighted_0_100=float(np.clip(n(35 + 30 * drift, 3), 0, 100)),
                bedford_workload_1_10=int(np.clip(round(n(3 + 3 * drift, 0.4)), 1, 10)),
                cognitive_z=n(-0.2 - 1.6 * drift, 0.2),
                days_since_ppc=float(day % 14),
                social_contact_days=float(np.clip(n(1 + 4 * drift, 0.5), 0, 30)),
                irritability_vas=float(np.clip(n(1 + 5 * drift, 0.5), 0, 10)),
                motivation_vas=float(np.clip(n(8 - 5 * drift, 0.5), 0, 10)),
                appetite_vas=float(np.clip(n(7 - 4 * drift, 0.5), 0, 10))))

        rep = twin.ingest(s)
        sh = rep.share

        # === FIX: auto-piloto con if/elif real (no dict+[sh.step]) ===
        guard = 0
        while sh.active and sh.status == "OPEN" and sh.step in ("SEEK", "HELP", "ASSESS", "REACH") and guard < 6:
            guard += 1
            step = sh.step
            if step == "SEEK":
                resp = {"participation": "yes"}
            elif step == "HELP":
                resp = {"teach_back_ok": True}
            elif step == "ASSESS":
                resp = {"priorities": ["sueño", "contacto con familia"]}
            elif step == "REACH":
                chosen = sh.options[0]["id"] if sh.options else "CM-WATCHFUL"
                resp = {"chosen_option_id": chosen, "clinician_confirmed": sh.requires_clinician}
            else:
                break
            sh = twin.record_share_response("CDR-01", step, resp, ts)

        print(f"día {day:02d} | {rep.state.overall_level:8s} | share={rep.state.share_index:.2f} "
              f"anom={rep.state.anomaly_score:.2f} | SHARE: {sh.step or '-':9s} {sh.status or ''}")
        last = rep

    print("\n--- Último informe (contrato AEGIS-CREW) ---")
    print(last.model_dump_json(indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="AEGIS-CREW Bio-Digital Twin")
    ap.add_argument("--rules", default="rules.yaml")
    ap.add_argument("--sample", help="JSON con una CrewSample")
    ap.add_argument("--state", help="archivo de estado persistente (JSON)")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        return _demo(a.rules)
    twin = BioDigitalTwin(a.rules)
    if a.state and Path(a.state).exists():
        twin.load_state(a.state)
    if a.sample:
        rep = twin.ingest(CrewSample.model_validate_json(Path(a.sample).read_text(encoding="utf-8")))
        print(rep.model_dump_json(indent=2))
        if a.state:
            twin.save_state(a.state)


if __name__ == "__main__":
    main()