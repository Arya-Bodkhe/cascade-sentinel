"""Comprehensive system test suite for CASCADE SENTINEL Pune Real-Data Upgrade."""
import os
import json
import numpy as np
import pandas as pd
import pytest

from src.data.loader_openmeteo import OpenMeteoLoader
from src.data.loader_imd import IMDLoader
from src.data.loader_glc import GLCLoader
from src.data.live_adapter import LiveAdapter
from src.data.evidence_builder import EvidenceBuilder
from src.policy.policy import (
    Policy, ActionThresholds, CostModel,
    ACTION_WATCH, ACTION_PREPARE, ACTION_ALERT, ACTION_ESCALATE,
    run_scripted_scenarios
)
from src.ledger.ledger import Ledger
from src.replay_engine import ReplayEngine, HISTORICAL_EVENTS


# =============================================================================
# 1. DATA LAYER TESTS
# =============================================================================
def test_openmeteo_loader_utc_to_ist_and_missing_handling():
    om = OpenMeteoLoader()
    df = om.load()

    assert len(df) > 90000, "Should have complete hourly time-series"
    assert "time_ist" in df.columns
    assert "quality_flag" in df.columns

    # Verify timezone offset is +05:30
    first_valid = df[df["quality_flag"] == "VALID"].iloc[0]
    assert str(first_valid["time_ist"].tz) == "Asia/Kolkata"

    # Verify Jan-May 2015 is MISSING (NaN), never filled with zero
    jan_slice = df[df["date_ist"] == "2015-01-15"]
    assert len(jan_slice) == 24
    assert (jan_slice["quality_flag"] == "MISSING").all()
    assert jan_slice["rain_mm_h"].isna().all(), "Jan 2015 rain must be NaN, never zero"

    # Verify daily aggregate also preserves NaN
    daily = om.get_daily_aggregates()
    jan_daily = daily[daily["date_ist"] == "2015-01-15"]
    assert pd.isna(jan_daily["rain_mm_day"].values[0]), "Daily rain for missing days must be NaN"


def test_imd_loader_cell_partition_and_extremes():
    imd = IMDLoader()
    df = imd.load()

    assert len(df) == 159640, "40 cells x 3991 days = 159640 records"
    assert len(imd.in_district_cells) == 24, "Must have exactly 24 in-district cells"
    assert len(imd.excluded_cells) == 16, "Must have exactly 16 excluded cells (10 Konkan, 6 Satara/Solapur)"

    # Verify Konkan cells (lon <= 73.25) are excluded
    for cid in imd.excluded_cells:
        meta = imd.cell_metadata[cid]
        assert meta.lat == 18.0 or meta.lon <= 73.25
        assert not meta.in_district
        assert meta.exclusion_reason is not None

    # Verify extreme values (>300 mm/day) are flagged, NOT deleted or clipped
    extremes = imd.get_extreme_records()
    assert len(extremes) == 16, "Must identify all 16 extreme records > 300 mm/day"
    assert (extremes["quality_flag"] == "EXTREME_VERIFY").all()
    assert extremes["rainfall_mm_per_day"].max() > 460.0, "Must preserve the 465.6 mm historic peak without clipping"


def test_glc_loader_candidates_and_priors():
    glc = GLCLoader()
    df = glc.process_and_export()

    assert os.path.exists("data/derived/glc_pune_candidates.csv")
    conf = glc.get_confirmed_in_district()
    assert len(conf) == 3, "Must have exactly 3 confirmed Pune district events"

    # Malin must be marked as predating rainfall baseline
    malin = conf[conf["event_id"] == 6186].iloc[0]
    assert malin["predates_rainfall_baseline"] == True

    # Lavasa 2016-08-03 event
    lavasa = conf[conf["event_id"] == 9415].iloc[0]
    assert lavasa["event_date_ist"] == "2016-08-03"

    # Ambiguous border events
    amb = glc.get_ambiguous()
    assert len(amb) == 9

    # Proximity prior calculation
    d_km, prior = glc.compute_glc_proximity_prior(18.50, 73.50)
    assert 0.0 < prior <= 1.0
    assert d_km < 30.0


def test_live_adapter_offline_resilience():
    la = LiveAdapter(timeout_sec=1)
    df, status, info = la.fetch_cell("CELL_18.50_73.75", 18.50, 73.75)

    assert df is not None
    assert len(df) == 241, "Must generate 7 days past + 3 days forecast = 241 hourly rows"
    assert status in ["LIVE", "CACHED", "OFFLINE-DEMO"]
    assert "rain_mm_h" in df.columns


# =============================================================================
# 2. EVIDENCE & SOURCE AGREEMENT TESTS
# =============================================================================
def test_evidence_builder_and_source_agreement():
    eb = EvidenceBuilder()
    priors = eb.build_susceptibility_priors()

    assert len(priors) == 24
    # Ghats cells must have higher susceptibility prior than eastern rainshadow cells
    ghats_prior = priors["CELL_18.50_73.50"]
    rainshadow_prior = priors["CELL_18.50_74.75"]
    assert ghats_prior > rainshadow_prior, "Ghats cell must have higher susceptibility than rainshadow"

    # Source agreement for Pune flood date 2024-07-25
    agr = eb.get_source_agreement("2024-07-25")
    assert "imd_rain_mm" in agr
    assert "om_rain_mm" in agr
    assert agr["status"] in ["STRONG_AGREEMENT", "MODERATE_DIVERGENCE", "HIGH_CONFLICT"]
    assert 0.0 <= agr["confidence_penalty"] <= 0.40


def test_landslide_threshold_sensitivity():
    eb = EvidenceBuilder()
    df_sens = eb.calculate_threshold_sensitivity()

    assert len(df_sens) == 3, "Must have Strict, Nominal, and Sensitive rows"
    # All levels must hit 7/7 historical events and have 0 quiet day false alarms
    for _, r in df_sens.iterrows():
        assert r["Historical Event Hits"] == "7/7"
        assert r["Quiet Day False Alerts"] == 0


# =============================================================================
# 3. DECISION POLICY & HYSTERESIS TESTS
# =============================================================================
def test_policy_unified_ladder_and_escalation():
    pol = Policy(k_down=2)

    # Low risk -> WATCH
    r0 = pol.step_decision(p_cas=0.05, rain_3d=5.0)
    assert r0["action_name"] == "WATCH"

    # Moderate risk -> PREPARE
    r1 = pol.step_decision(p_cas=0.35, rain_3d=90.0)
    assert r1["action_name"] == "PREPARE"

    # High risk -> ALERT
    r2 = pol.step_decision(p_cas=0.55, rain_3d=160.0)
    assert r2["action_name"] == "ALERT"

    # Severe hazard -> ESCALATE (requires human confirmation)
    r3 = pol.step_decision(p_cas=0.85, rain_3d=250.0, susceptibility=0.80)
    assert r3["action_name"] == "ESCALATE"
    assert r3["requires_human_confirm"] == True


def test_anti_flapping_hysteresis():
    pol = Policy(k_down=2)
    # Escalate to ALERT
    pol.step_decision(p_cas=0.55, rain_3d=160.0)
    assert pol.level == ACTION_ALERT

    # Single drop below threshold -> MUST HOLD at ALERT (hysteresis)
    r_hold = pol.step_decision(p_cas=0.10, rain_3d=15.0)
    assert pol.level == ACTION_ALERT, "Must hold at ALERT on first drop interval"
    assert "Hysteresis hold" in r_hold["rule_fired"]

    # Second drop below threshold -> Sustained drop satisfied -> step down to WATCH
    r_drop = pol.step_decision(p_cas=0.10, rain_3d=15.0)
    assert pol.level == ACTION_WATCH, "Must de-escalate only after sustained drop (k_down=2)"


def test_cry_wolf_fatigue():
    pol = Policy()
    assert pol.f == 0.0

    # Simulate episode ending with false alarm
    pol.level = ACTION_ALERT
    pol.max_level = ACTION_ALERT
    pol.record_episode_outcome(is_cascade=False)

    assert pol.f > 0.0, "Fatigue must increase after false alarm"


def test_scripted_scenarios_all_pass():
    pol = Policy()
    df_scenarios = run_scripted_scenarios(pol)

    assert len(df_scenarios) == 6
    assert (df_scenarios["Match"] == "[PASS]").all(), "All 6 scripted validation scenarios must pass"


# =============================================================================
# 4. WHY-LEDGER CRYPTOGRAPHIC VERIFICATION TESTS
# =============================================================================
def test_why_ledger_sha256_chain_and_tamper_detection():
    led = Ledger(seed=42)

    # Add entries
    led.add(t=1, p_before=[0.45, 0.20, 0.20, 0.15], p_after=[0.30, 0.20, 0.20, 0.30],
            act_from="WATCH", act_to="PREPARE", contributions={"Rain": 1.2},
            reverses_if="Rain stops", rule_fired="CatchmentSaturation")

    led.add(t=2, p_before=[0.30, 0.20, 0.20, 0.30], p_after=[0.10, 0.10, 0.10, 0.70],
            act_from="PREPARE", act_to="ALERT", contributions={"Rain": 2.5},
            reverses_if="P drops", rule_fired="DelugeThreshold")

    # Add human confirmation
    led.add_human_confirmation(t=3, action="ESCALATE", operator_name="Officer Deshmukh")

    assert len(led.entries) == 3
    assert led.verify() == True, "Ledger hash chain must verify"

    # Tamper with an entry and verify tamper is detected
    led.entries[0]["action_to"] = "WATCH"
    assert led.verify() == False, "Tampered ledger entry must fail verification"


# =============================================================================
# 5. HISTORICAL REPLAY TESTS
# =============================================================================
def test_historical_replay_suite():
    re = ReplayEngine()

    # Replay 2016 Lavasa Landslide
    rep_lavasa = re.run_replay("2016_lavasa")
    assert rep_lavasa["ledger_verified"] == True
    peak_lavasa = [s for s in rep_lavasa["timeline"] if s["is_peak"]][0]
    assert peak_lavasa["action_name"] in ["ALERT", "ESCALATE"], "2016 Lavasa peak must trigger ALERT or ESCALATE"

    # Replay 2023 Quiet Spell (Negative Control)
    rep_quiet = re.run_replay("2023_quiet")
    assert rep_quiet["ledger_verified"] == True
    peak_quiet = [s for s in rep_quiet["timeline"] if s["is_peak"]][0]
    assert peak_quiet["action_name"] == "WATCH", "2023 quiet spell must remain at WATCH (zero false alarms)"
    assert peak_quiet["p_cascade"] < 0.25
