"""Fast, deterministic contract tests for the React/FastAPI boundary and policy."""
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.responses import FileResponse
import pytest

from src.data.evidence_builder import EvidenceBuilder
from src.policy.policy import ActionThresholds, Policy
from src.replay_engine import ReplayEngine
from src.risk import estimate_cascade_probability
from web_app import app, dashboard, events, health, serve_react


def test_react_frontend_is_served_from_built_assets():
    response = serve_react("")
    assert isinstance(response, FileResponse)
    html = Path(response.path).read_text(encoding="utf-8")
    assert '<div id="root"></div>' in html
    assert "/assets/" in html


def test_http_routes_are_registered_and_health_and_events_are_available():
    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/events" in paths
    assert "/api/dashboard" in paths
    assert "/{path:path}" in paths
    assert health()["ok"] is True
    keys = {event["key"] for event in events()}
    assert {"2016_lavasa", "2019_flood", "2024_sinhagad", "2023_quiet"}.issubset(keys)


def test_api_rejects_conflicting_probability_threshold_order_before_loading_data():
    with pytest.raises(HTTPException) as exc:
        dashboard(p_prepare=0.6, p_alert=0.5, p_escalate=0.7)
    assert exc.value.status_code == 422
    assert "Probability thresholds" in exc.value.detail


def test_threshold_dataclass_rejects_inconsistent_action_ladder():
    with pytest.raises(ValueError, match="Probability thresholds"):
        ActionThresholds(p_prepare=0.60, p_alert=0.50, p_escalate=0.70)
    with pytest.raises(ValueError, match="3-day rainfall thresholds"):
        ActionThresholds(rain_3d_prepare_mm=150, rain_3d_alert_mm=100)


def test_district_summary_propagates_thresholds_to_each_cell():
    builder = EvidenceBuilder.__new__(EvidenceBuilder)
    builder.imd = SimpleNamespace(
        in_district_cells=["cell-a", "cell-b"],
        get_date_slice=lambda date: "date-slice",
    )
    builder.build_susceptibility_priors = lambda: None
    seen = []

    def evaluate_cell(date, cell_id, thresh_3d, thresh_24h, date_slice_df=None):
        seen.append((date, cell_id, thresh_3d, thresh_24h, date_slice_df))
        return {
            "rain_1d_mm": 12.0,
            "rain_3d_mm": 45.0,
            "landslide_trigger_index": 0.2,
        }

    builder.evaluate_cell_evidence = evaluate_cell
    builder.get_source_agreement = lambda date: {"confidence_penalty": 0.0}
    summary = builder.evaluate_district_summary("2024-07-25", thresh_3d=175.0, thresh_24h=95.0)
    assert len(summary["cells"]) == 2
    assert all(row[2:4] == (175.0, 95.0) for row in seen)
    assert all(row[4] == "date-slice" for row in seen)


def test_replay_accepts_and_propagates_custom_rainfall_thresholds():
    class RecordingEvidence:
        def __init__(self):
            self.seen = []

        def evaluate_district_summary(self, date, thresh_3d, thresh_24h):
            self.seen.append((date, thresh_3d, thresh_24h))
            return {
                "district_max_3d_mm": 10.0,
                "district_mean_3d_mm": 5.0,
                "district_max_1d_mm": 4.0,
                "district_mean_1d_mm": 2.0,
                "max_landslide_trigger_index": 0.1,
                "source_agreement": {"confidence_penalty": 0.0},
                "district_max_cell": "CELL_18.50_73.75",
                "cells": [],
            }

    evidence = RecordingEvidence()
    result = ReplayEngine(evidence, Policy(fatigue=False)).run_replay(
        "2024_sinhagad", thresh_3d=175.0, thresh_24h=95.0
    )
    assert len(result["timeline"]) == 11
    assert len(evidence.seen) == 11
    assert all(row[1:] == (175.0, 95.0) for row in evidence.seen)


def test_rainfall_trigger_reason_names_the_actual_trigger():
    decision = Policy().step_decision(p_cas=0.10, rain_3d=0.0, rain_24h=100.0, susceptibility=0.50)
    assert decision["action_name"] == "ALERT"
    assert "24-hour rain 100.0 mm" in decision["plain_reason"]
    assert "P(CASCADE) 0.10 >=" not in decision["plain_reason"]


def test_visible_24_hour_escalation_threshold_changes_the_recommendation():
    decision = Policy().step_decision(p_cas=0.10, rain_3d=0.0, rain_24h=130.0, susceptibility=0.30)
    assert decision["action_name"] == "ESCALATE"
    assert "24-hour rain 130.0 mm" in decision["plain_reason"]


def test_shared_risk_heuristic_is_bounded_and_disagreement_reduces_risk():
    baseline = estimate_cascade_probability(100, 40, 0.5, 0.0)
    discounted = estimate_cascade_probability(100, 40, 0.5, 0.35)
    assert 0.02 <= baseline <= 0.98
    assert discounted < baseline
    with pytest.raises(ValueError, match="finite"):
        estimate_cascade_probability(float("nan"), 40, 0.5, 0.0)
