"""FastAPI entry point for the React CASCADE SENTINEL dashboard.

Run from any directory with: python run.py
The API is read-only except for the explicit operator acknowledgment route. That route
records an audit acknowledgment only; it does not dispatch sirens or public alerts.
"""
from __future__ import annotations

import json
import asyncio
import math
import os
import threading
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.data.evidence_builder import EvidenceBuilder
from src.data.live_adapter import LiveAdapter
from src.data.loader_glc import GLCLoader
from src.data.loader_imd import IMDLoader
from src.data.loader_openmeteo import OpenMeteoLoader
from src.ledger.ledger import Ledger
from src.policy.policy import ACTIONS, ActionThresholds, Policy, run_scripted_scenarios
from src.replay_engine import HISTORICAL_EVENTS, ReplayEngine
from src.risk import estimate_cascade_probability

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
LEDGER_PATH = BASE_DIR / "data" / "operations_ledger.json"


def windows_selector_loop_factory(use_subprocess: bool = False) -> asyncio.AbstractEventLoop:
    """Use the Windows selector loop for local serving; the Proactor pipe can hang in restricted desktops."""
    return asyncio.SelectorEventLoop()


@lru_cache(maxsize=1)
def get_services() -> dict[str, Any]:
    """Load data exactly once; absolute paths make service startup cwd-independent."""
    imd = IMDLoader(filepath=str(BASE_DIR / "data" / "pune_imd_rainfall.csv"))
    imd.load()
    om = OpenMeteoLoader(filepath=str(BASE_DIR / "data" / "open-meteo-18_52N73_87E561m.csv"))
    om.load()
    glc = GLCLoader(
        raw_filepath=str(BASE_DIR / "data" / "Global_Landslide_Catalog_Export_rows__3_.csv"),
        derived_filepath=str(BASE_DIR / "data" / "derived" / "glc_pune_candidates.csv"),
    )
    glc.process_and_export()
    evidence = EvidenceBuilder(imd, om, glc)
    evidence.build_susceptibility_priors()
    return {
        "imd": imd,
        "om": om,
        "glc": glc,
        "evidence": evidence,
        "live": LiveAdapter(cache_dir=str(BASE_DIR / "data" / "cache")),
    }


@lru_cache(maxsize=128)
def _district_summary(date_str: str, trigger_3d: float, trigger_24h: float) -> dict[str, Any]:
    return get_services()["evidence"].evaluate_district_summary(
        date_str, thresh_3d=trigger_3d, thresh_24h=trigger_24h
    )


@lru_cache(maxsize=512)
def _cell_summary(date_str: str, cell_id: str, trigger_3d: float, trigger_24h: float) -> dict[str, Any]:
    return get_services()["evidence"].evaluate_cell_evidence(
        date_str, cell_id, thresh_3d=trigger_3d, thresh_24h=trigger_24h
    )


@lru_cache(maxsize=96)
def _cached_replay(
    event_key: str,
    threshold_signature: tuple[tuple[str, Any], ...],
    trigger_3d: float,
    trigger_24h: float,
    hysteresis: bool,
    k_down: int,
) -> dict[str, Any]:
    thresholds = ActionThresholds(**dict(threshold_signature))
    policy = Policy(thresholds=thresholds, hysteresis=hysteresis, fatigue=False, k_down=k_down)
    return ReplayEngine(get_services()["evidence"], policy).run_replay(
        event_key, thresh_3d=trigger_3d, thresh_24h=trigger_24h
    )


def _native(value: Any) -> Any:
    """Convert pandas/numpy objects to strict JSON values (never NaN/Infinity)."""
    if isinstance(value, dict):
        return {str(k): _native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value) if value is None or np.isscalar(value) else False:
        return None
    return value


def _thresholds(
    p_prepare: float = 0.25,
    p_alert: float = 0.50,
    p_escalate: float = 0.70,
    rain_3d_prepare: float = 80.0,
    rain_3d_alert: float = 150.0,
    rain_3d_escalate: float = 220.0,
    rain24_alert: float = 80.0,
    rain24_escalate: float = 120.0,
) -> ActionThresholds:
    try:
        return ActionThresholds(
            p_prepare=p_prepare,
            p_alert=p_alert,
            p_escalate=p_escalate,
            rain_3d_prepare_mm=rain_3d_prepare,
            rain_3d_alert_mm=rain_3d_alert,
            rain_3d_escalate_mm=rain_3d_escalate,
            rain_24h_alert_mm=rain24_alert,
            rain_24h_escalate_mm=rain24_escalate,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _event_data(event_key: str) -> Any:
    meta = HISTORICAL_EVENTS.get(event_key)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Unknown event: {event_key}")
    return meta


def _map_cells(services: dict[str, Any], date_str: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the full 40-cell grid, separating excluded border cells from district totals."""
    imd = services["imd"]
    rows = {c["cell_id"]: c for c in summary["cells"]}
    date_slice = imd.get_date_slice(date_str).set_index("cell_id")
    output: list[dict[str, Any]] = []
    for cell_id, meta in imd.cell_metadata.items():
        if cell_id in rows:
            output.append(rows[cell_id])
            continue
        record = date_slice.loc[cell_id] if cell_id in date_slice.index else None
        rain_1d = float(record["rainfall_mm_per_day"]) if record is not None else 0.0
        rain_3d = float(record["rain_3d"]) if record is not None else 0.0
        output.append({
            "cell_id": cell_id,
            "lat": meta.lat,
            "lon": meta.lon,
            "in_district": False,
            "exclusion_reason": meta.exclusion_reason,
            "taluka_label": meta.nearest_taluka_proxy,
            "rain_1d_mm": rain_1d,
            "rain_3d_mm": rain_3d,
            "susceptibility_prior": meta.susceptibility_prior,
            "landslide_trigger_index": 0.0,
            "quality_flag": str(record["quality_flag"]) if record is not None else "MISSING",
        })
    return output


def _historical_dashboard(
    services: dict[str, Any],
    event_key: str,
    date_str: str,
    cell_id: str,
    thresholds: ActionThresholds,
    trigger_3d: float,
    trigger_24h: float,
    hysteresis: bool,
    k_down: int,
) -> dict[str, Any]:
    meta = _event_data(event_key)
    event_dates = pd.date_range(meta.start_date, meta.end_date, freq="D").strftime("%Y-%m-%d").tolist()
    if date_str not in event_dates:
        raise HTTPException(status_code=422, detail="Selected date must be inside the chosen event replay window")
    imd = services["imd"]
    if cell_id not in imd.in_district_cells:
        raise HTTPException(status_code=422, detail="Target cell must be one of the 24 in-district cells")
    summary = _district_summary(date_str, trigger_3d, trigger_24h)
    cell = _cell_summary(date_str, cell_id, trigger_3d, trigger_24h)
    replay = _cached_replay(
        event_key, tuple(asdict(thresholds).items()), trigger_3d, trigger_24h, hysteresis, k_down
    )
    selected = next(step for step in replay["timeline"] if step["date"] == date_str)
    agreement = summary["source_agreement"]
    probability = estimate_cascade_probability(
        summary["district_max_3d_mm"],
        summary["district_max_1d_mm"],
        summary["max_landslide_trigger_index"],
        agreement.get("confidence_penalty", 0.0),
    )
    return {
        "mode": "historical",
        "status": "PROVIDED-DATA (OFFLINE REPLAY)",
        "status_detail": "IMD/Open-Meteo historical data; no network required for this replay.",
        "scope_note": "District calculations include the 24 classified in-district grid cells only.",
        "selected_date": date_str,
        "selected_cell": cell_id,
        "event": asdict(meta),
        "events": [asdict(item) | {"key": key} for key, item in HISTORICAL_EVENTS.items()],
        "event_dates": event_dates,
        "summary": summary,
        "cell_evidence": cell,
        "cells": _map_cells(services, date_str, summary),
        "risk": {
            "p_cascade": probability,
            "source_confidence_penalty": agreement.get("confidence_penalty", 0.0),
            "formula": "0.05 + 0.45*(district max 3-day/200) + 0.35*(district max 24-hour/120) + 0.15*max landslide index; source conflict discount applied; clipped to [0.02, 0.98].",
            "classification": "engineering heuristic; not a calibrated forecast probability",
        },
        "decision": {
            "action_name": selected["action_name"],
            "action_level": selected["action_level"],
            "candidate_name": selected["action_name"],
            "requires_human_confirm": selected["action_name"] == "ESCALATE",
            "rule_fired": selected["rule_fired"],
            "plain_reason": selected["plain_reason"],
            "reverses_if": selected["reverses_if"],
            "p_cascade": selected["p_cascade"],
        },
        "timeline": replay["timeline"],
        "ledger": {"entries": [], "verified": True, "count": 0},
        "thresholds": asdict(thresholds),
        "trigger_thresholds": {"rain_3d_mm": trigger_3d, "rain_24h_mm": trigger_24h},
        "policy_state": {"hysteresis": hysteresis, "k_down": k_down, "scope": "event replay; one step per historical day"},
        "scenarios": run_scripted_scenarios(Policy(thresholds=thresholds)).to_dict(orient="records"),
    }


class ThresholdPayload(BaseModel):
    p_prepare: float = 0.25
    p_alert: float = 0.50
    p_escalate: float = 0.70
    rain_3d_prepare_mm: float = 80.0
    rain_3d_alert_mm: float = 150.0
    rain_3d_escalate_mm: float = 220.0
    rain_24h_alert_mm: float = 80.0
    rain_24h_escalate_mm: float = 120.0


class ConfirmationPayload(BaseModel):
    event_key: str
    date: str
    operator_name: str = Field(min_length=2, max_length=120)
    thresholds: ThresholdPayload = Field(default_factory=ThresholdPayload)
    trigger_3d: float = Field(default=150.0, ge=0, le=1000)
    trigger_24h: float = Field(default=80.0, ge=0, le=1000)
    hysteresis: bool = True
    k_down: int = Field(default=2, ge=1, le=8)


app = FastAPI(title="CASCADE SENTINEL API", version="1.0.0")
_LEDGER_LOCK = threading.Lock()
_LEDGER: Optional[Ledger] = None


def _load_ledger() -> Ledger:
    global _LEDGER
    if _LEDGER is not None:
        return _LEDGER
    ledger = Ledger(seed=42)
    if LEDGER_PATH.exists():
        try:
            entries = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Could not read audit ledger: {exc}") from exc
        if not isinstance(entries, list) or not Ledger.verify_entries(entries):
            raise HTTPException(status_code=503, detail="Audit ledger integrity check failed; writes are disabled")
        ledger.entries = entries
        ledger.prev = entries[-1]["hash"] if entries else "0" * 64
    _LEDGER = ledger
    return ledger


def _save_ledger(ledger: Ledger) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = LEDGER_PATH.with_suffix(".json.tmp")
    temp_path.write_text(ledger.to_json(), encoding="utf-8")
    os.replace(temp_path, LEDGER_PATH)


def _ledger_payload() -> dict[str, Any]:
    with _LEDGER_LOCK:
        ledger = _load_ledger()
        return {"entries": ledger.entries, "verified": ledger.verify(), "count": len(ledger.entries)}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "cascade-sentinel", "frontend_built": (FRONTEND_DIST / "index.html").exists()}


@app.get("/api/events")
def events() -> list[dict[str, Any]]:
    return [asdict(item) | {"key": key} for key, item in HISTORICAL_EVENTS.items()]


@app.get("/api/dashboard")
def dashboard(
    mode: str = "historical",
    event_key: str = "2024_sinhagad",
    date: Optional[str] = None,
    cell_id: str = "CELL_18.50_73.75",
    p_prepare: float = 0.25,
    p_alert: float = 0.50,
    p_escalate: float = 0.70,
    rain_3d_prepare: float = 80.0,
    rain_3d_alert: float = 150.0,
    rain_3d_escalate: float = 220.0,
    rain24_alert: float = 80.0,
    rain24_escalate: float = 120.0,
    trigger_3d: float = 150.0,
    trigger_24h: float = 80.0,
    hysteresis: bool = True,
    k_down: int = 2,
) -> JSONResponse:
    if mode not in {"historical", "live"}:
        raise HTTPException(status_code=422, detail="mode must be 'historical' or 'live'")
    if not (0 <= trigger_3d <= 1000 and 0 <= trigger_24h <= 1000):
        raise HTTPException(status_code=422, detail="Evidence thresholds must be between 0 and 1000 mm")
    thresholds = _thresholds(
        p_prepare, p_alert, p_escalate, rain_3d_prepare, rain_3d_alert,
        rain_3d_escalate, rain24_alert, rain24_escalate,
    )
    if not 1 <= k_down <= 8:
        raise HTTPException(status_code=422, detail="k_down must be between 1 and 8")
    services = get_services()
    if mode == "historical":
        meta = _event_data(event_key)
        selected_date = date or meta.peak_date
        payload = _historical_dashboard(
            services, event_key, selected_date, cell_id, thresholds,
            trigger_3d, trigger_24h, hysteresis, k_down,
        )
        payload["ledger"] = _ledger_payload()
        return JSONResponse(_native(payload))

    # Live mode is strictly a selected-cell advisory. The map remains historical reference
    # because the free provider is queried for one cell at a time, not all 24 cells.
    imd = services["imd"]
    if cell_id not in imd.in_district_cells:
        raise HTTPException(status_code=422, detail="Target cell must be one of the 24 in-district cells")
    meta = imd.cell_metadata[cell_id]
    live_df, live_status, live_info = services["live"].fetch_cell(cell_id, meta.lat, meta.lon)
    if live_df is None or live_df.empty:
        raise HTTPException(status_code=503, detail="No live, cached, or demo telemetry is available")
    now_ist = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).floor("h")
    observed = live_df[live_df["time_ist"] <= now_ist].copy()
    last_24 = observed[observed["time_ist"] > now_ist - pd.Timedelta(hours=24)]
    last_72 = observed[observed["time_ist"] > now_ist - pd.Timedelta(hours=72)]
    valid_24 = last_24[last_24["quality_flag"] == "VALID"]
    valid_72 = last_72[last_72["quality_flag"] == "VALID"]
    if len(valid_24) < 18 or len(valid_72) < 54:
        raise HTTPException(
            status_code=503,
            detail="Insufficient valid observations in the last 24/72 hours; no live recommendation was calculated.",
        )
    rain_24 = float(valid_24["rain_mm_h"].sum(min_count=18))
    rain_72 = float(valid_72["rain_mm_h"].sum(min_count=54))
    if not math.isfinite(rain_24) or not math.isfinite(rain_72):
        raise HTTPException(status_code=503, detail="Recent rainfall observations are incomplete; no live recommendation was calculated.")
    rain_24 = max(0.0, rain_24)
    rain_72 = max(0.0, rain_72)
    prior = float(meta.susceptibility_prior)
    ls_index = min(1.0, 0.5 * min(2.0, rain_72 / max(trigger_3d, 1.0)) + 0.5 * min(2.0, rain_24 / max(trigger_24h, 1.0)))
    penalty = 0.15 if live_status.startswith("CACHED") else 0.0
    p_cascade = estimate_cascade_probability(rain_72, rain_24, ls_index, penalty)
    policy = Policy(thresholds=thresholds, hysteresis=hysteresis, fatigue=False, k_down=k_down)
    decision = policy.step_decision(
        p_cas=p_cascade, rain_3d=rain_72, rain_24h=rain_24,
        susceptibility=prior, pct_rank=0.0,
    )
    reference_date = str(imd.load()["date"].max())
    reference_summary = services["evidence"].evaluate_district_summary(
        reference_date, thresh_3d=trigger_3d, thresh_24h=trigger_24h
    )
    latest_observed = live_df[live_df["time_ist"] <= now_ist]
    live_record = latest_observed.iloc[-1].to_dict()
    live_cell = {
        "cell_id": cell_id, "date": str(now_ist.date()), "lat": meta.lat, "lon": meta.lon,
        "in_district": True, "taluka_label": meta.nearest_taluka_proxy,
        "susceptibility_prior": prior, "rain_1d_mm": round(rain_24, 1),
        "rain_3d_mm": round(rain_72, 1), "rain_2d_mm": None,
        "rain_7d_mm": None, "percentile_rank": None,
        "landslide_trigger_index": round(ls_index, 3),
        "quality_flag": live_record.get("quality_flag", "MISSING"),
        "hourly_pune_point": None,
    }
    valid_hourly = live_df[live_df["quality_flag"] == "VALID"].tail(96)
    hourly = [{
        "time": row["time_ist"].strftime("%Y-%m-%d %H:%M"),
        "rain_mm_h": float(row["rain_mm_h"]),
        "provenance": row["provenance"],
    } for _, row in valid_hourly.iterrows()]
    return JSONResponse(_native({
        "mode": "live", "status": live_status, "status_detail": live_info,
        "scope_note": "LIVE selected-cell advisory only. Grid map and district context are the latest historical IMD reference, not live coverage for all 24 cells.",
        "selected_date": str(now_ist.date()), "selected_cell": cell_id,
        "event": asdict(_event_data(event_key)),
        "events": [asdict(item) | {"key": key} for key, item in HISTORICAL_EVENTS.items()],
        "event_dates": pd.date_range(_event_data(event_key).start_date, _event_data(event_key).end_date, freq="D").strftime("%Y-%m-%d").tolist(),
        "summary": {
            "date": str(now_ist.date()), "district_mean_1d_mm": round(rain_24, 1),
            "district_max_1d_mm": round(rain_24, 1), "district_max_cell": cell_id,
            "district_mean_3d_mm": round(rain_72, 1), "district_max_3d_mm": round(rain_72, 1),
            "max_landslide_risk_cell": cell_id, "max_landslide_trigger_index": round(ls_index, 3),
            "source_agreement": {"status": "SINGLE_SOURCE_LIVE", "confidence_penalty": penalty,
                                 "note": "Only the selected live grid cell is fetched; sources are not silently blended."},
            "cells": reference_summary["cells"],
        },
        "cell_evidence": live_cell,
        "cells": _map_cells(services, reference_date, reference_summary),
        "risk": {"p_cascade": p_cascade, "source_confidence_penalty": penalty,
                 "formula": "The selected-cell 24h/72h observations feed the shared rainfall heuristic.",
                 "classification": "selected-cell advisory; not a district-wide or calibrated forecast"},
        "decision": {
            "action_name": decision["action_name"], "action_level": decision["action_level"],
            "candidate_name": decision["candidate_name"], "requires_human_confirm": decision["requires_human_confirm"],
            "rule_fired": decision["rule_fired"], "plain_reason": decision["plain_reason"],
            "reverses_if": decision["reverses_if"], "p_cascade": p_cascade,
        },
        "timeline": [], "hourly": hourly,
        "ledger": _ledger_payload(), "thresholds": asdict(thresholds),
        "trigger_thresholds": {"rain_3d_mm": trigger_3d, "rain_24h_mm": trigger_24h},
        "policy_state": {"hysteresis": hysteresis, "k_down": k_down, "scope": "single selected-cell snapshot"},
        "scenarios": run_scripted_scenarios(Policy(thresholds=thresholds)).to_dict(orient="records"),
    }))


@app.get("/api/ledger")
def ledger() -> JSONResponse:
    return JSONResponse(_native(_ledger_payload()))


@app.post("/api/ledger/confirm")
def confirm_escalation(payload: ConfirmationPayload) -> JSONResponse:
    """Append a human acknowledgment. This endpoint never performs external dispatch."""
    thresholds = _thresholds(**payload.thresholds.model_dump())
    event = _event_data(payload.event_key)
    imd = get_services()["imd"]
    selected_cell = "CELL_18.50_73.75"
    decision = _historical_dashboard(
        get_services(), payload.event_key, payload.date, selected_cell, thresholds,
        payload.trigger_3d, payload.trigger_24h, payload.hysteresis, payload.k_down,
    )["decision"]
    if decision["action_name"] != "ESCALATE":
        raise HTTPException(status_code=409, detail="Only a current ESCALATE recommendation can be acknowledged")
    note = (
        "Operator acknowledgment recorded by this local application; no siren, dispatch, or public notification was sent. "
        "Identity and authorization are not authenticated by this application."
    )
    with _LEDGER_LOCK:
        log = _load_ledger()
        already = any(
            item.get("action_to") == "CONFIRMED_ESCALATE" and item.get("t") == payload.date
            and item.get("input_hash") == f"{payload.event_key}:{payload.date}"
            for item in log.entries
        )
        if not already:
            entry = log.add_human_confirmation(
                t=payload.date, action="ESCALATE", operator_name=payload.operator_name, notes=note
            )
            entry["input_hash"] = f"{payload.event_key}:{payload.date}"
            # Rebuild this single entry's hash with the discriminator included.
            body = {k: v for k, v in entry.items() if k not in ("prev_hash", "hash")}
            import hashlib
            entry["hash"] = hashlib.sha256((json.dumps(body, sort_keys=True) + entry["prev_hash"]).encode("utf-8")).hexdigest()
            log.prev = entry["hash"]
            _save_ledger(log)
        return JSONResponse(_native({"verified": log.verify(), "count": len(log.entries), "entries": log.entries,
                                     "acknowledgment_only": True, "external_dispatch": False}))


@app.get("/api/sensitivity")
def sensitivity() -> JSONResponse:
    services = get_services()
    return JSONResponse(_native(services["evidence"].calculate_threshold_sensitivity().to_dict(orient="records")))


@app.get("/{path:path}", include_in_schema=False)
def serve_react(path: str = ""):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=503,
            detail="React frontend is not built. Run `npm install` and `npm run build` in the project directory.",
        )
    candidate = (FRONTEND_DIST / path).resolve()
    if path and candidate.is_relative_to(FRONTEND_DIST.resolve()) and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(index_file)
