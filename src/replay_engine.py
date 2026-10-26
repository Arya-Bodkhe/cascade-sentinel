"""Historical event replay engine for Pune District.

Provides deterministic, offline replay for top historical flood and landslide events:
  - 2016-08-03: Lavasa/Mulshi landslide match (GLC #9415)
  - 2019-08-04: Historic Pune flood (Khadakwasla discharge)
  - 2021-07-23: Historic Western Ghats deluge (465.6 mm peak)
  - 2024-07-25: Sinhagad Road urban flash flood
  - 2025-08-20: Active monsoon pulse
  - 2023-08-15: Quiet monsoon break (negative control)

Each replay window runs 7 days before peak to 3 days after.
Deterministic, offline, fixed seed.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from src.data.evidence_builder import EvidenceBuilder, DEFAULT_THRESH_3D_MM, DEFAULT_THRESH_24H_MM
from src.policy.policy import Policy, ACTION_WATCH, ACTION_PREPARE, ACTION_ALERT, ACTION_ESCALATE
from src.ledger.ledger import Ledger


@dataclass
class ReplayEventMeta:
    event_id: str
    title: str
    peak_date: str
    start_date: str
    end_date: str
    description: str
    hazard_type: str
    confirmed_glc_match: Optional[str] = None
    expected_peak_action: str = "ALERT"


HISTORICAL_EVENTS: Dict[str, ReplayEventMeta] = {
    "2016_lavasa": ReplayEventMeta(
        event_id="2016_lavasa",
        title="2016-08-03: Lavasa / Mulshi Landslide & Ghats Rain",
        peak_date="2016-08-03",
        start_date="2016-07-27",
        end_date="2016-08-06",
        description="Heavy monsoon catchment deluge matching confirmed NASA GLC Event #9415 at Lavasa/Davse (Mulshi taluka).",
        hazard_type="Landslide & Catchment Flood",
        confirmed_glc_match="NASA GLC #9415 (2016-08-03 09:00 IST, Lavasa)",
        expected_peak_action="ESCALATE"
    ),
    "2019_flood": ReplayEventMeta(
        event_id="2019_flood",
        title="2019-08-04: Historic Pune Flood & Dam Discharge",
        peak_date="2019-08-04",
        start_date="2019-07-28",
        end_date="2019-08-07",
        description="Severe district-wide downpour (>94 mm mean); Khadakwasla dam discharged >45,000 cusecs into Mutha river, flooding Pune urban core.",
        hazard_type="Urban Riverine Flood & Waterlogging",
        confirmed_glc_match=None,
        expected_peak_action="ESCALATE"
    ),
    "2021_deluge": ReplayEventMeta(
        event_id="2021_deluge",
        title="2021-07-23: Western Ghats Deluge (Peak 465.6 mm/day)",
        peak_date="2021-07-23",
        start_date="2021-07-16",
        end_date="2021-07-26",
        description="Historic Western Ghats orographic deluge; 465.6 mm/day recorded at ghat crest border (18.0N 73.5E) and widespread catchment saturation.",
        hazard_type="Extreme Orographic Downpour & Landslide Risk",
        confirmed_glc_match=None,
        expected_peak_action="ESCALATE"
    ),
    "2024_sinhagad": ReplayEventMeta(
        event_id="2024_sinhagad",
        title="2024-07-25: Sinhagad Road Urban Flash Flood",
        peak_date="2024-07-25",
        start_date="2024-07-18",
        end_date="2024-07-28",
        description="Extreme urban rainfall (113.9 mm at Pune City cell, 202.8 mm in catchment); Sinhagad Road, Ekta Nagar inundated, NDRF deployed.",
        hazard_type="Urban Waterlogging & Catchment Flood",
        confirmed_glc_match=None,
        expected_peak_action="ALERT"
    ),
    "2025_pulse": ReplayEventMeta(
        event_id="2025_pulse",
        title="2025-08-20: Late Monsoon Active Pulse",
        peak_date="2025-08-20",
        start_date="2025-08-13",
        end_date="2025-08-23",
        description="Late-season intense pulse across northern and western talukas (max 367.7 mm, district mean 86.6 mm).",
        hazard_type="Catchment Rain Pulse",
        confirmed_glc_match=None,
        expected_peak_action="ALERT"
    ),
    "2023_quiet": ReplayEventMeta(
        event_id="2023_quiet",
        title="2023-08-15: Quiet Monsoon Break (Negative Control)",
        peak_date="2023-08-15",
        start_date="2023-08-08",
        end_date="2023-08-18",
        description="Quiet break monsoon spell (district mean 1.4 mm, max 11.1 mm); negative control demonstrating system does not over-alert.",
        hazard_type="Quiet Spell / No Hazard",
        confirmed_glc_match=None,
        expected_peak_action="WATCH"
    )
}


class ReplayEngine:
    def __init__(self, evidence_builder: Optional[EvidenceBuilder] = None, policy: Optional[Policy] = None):
        self.eb = evidence_builder or EvidenceBuilder()
        self.policy = policy or Policy()

    def run_replay(
        self,
        event_key: str,
        seed: int = 42,
        thresh_3d: float = DEFAULT_THRESH_3D_MM,
        thresh_24h: float = DEFAULT_THRESH_24H_MM,
    ) -> Dict[str, Any]:
        """Execute complete replay for a historical event window and generate timeline steps."""
        meta = HISTORICAL_EVENTS.get(event_key)
        if not meta:
            raise ValueError(f"Unknown historical event key: {event_key}")

        dates = pd.date_range(start=meta.start_date, end=meta.end_date, freq="D").strftime("%Y-%m-%d").tolist()

        pol = Policy(cost=self.policy.cost, thresholds=self.policy.thresholds,
                     hysteresis=self.policy.hysteresis, fatigue=self.policy.use_fatigue,
                     k_down=self.policy.k_down)
        pol.reset()
        ledger = Ledger(seed=seed)

        timeline = []
        p_prev = [0.45, 0.20, 0.20, 0.15]
        act_prev = "WATCH"

        for step_idx, d_str in enumerate(dates):
            summary = self.eb.evaluate_district_summary(
                d_str, thresh_3d=thresh_3d, thresh_24h=thresh_24h
            )

            # Compute district-level aggregate risk
            max_3d = summary["district_max_3d_mm"]
            mean_3d = summary["district_mean_3d_mm"]
            max_1d = summary["district_max_1d_mm"]
            mean_1d = summary["district_mean_1d_mm"]
            max_ls = summary["max_landslide_trigger_index"]
            agr = summary["source_agreement"]

            # Ground truth calibration of P(CASCADE) from multi-timescale hydro evidence
            # Baseline prior
            p_cas_raw = 0.05 + 0.45 * (max_3d / 200.0) + 0.35 * (max_1d / 120.0) + 0.15 * max_ls
            # Apply confidence discount if sources diverge
            p_cas_calib = float(np.clip(p_cas_raw * (1.0 - agr["confidence_penalty"]), 0.02, 0.98))

            p_curr = [
                float(max(0.01, 0.50 * (1.0 - p_cas_calib))),
                float(max(0.01, 0.20 * (1.0 - p_cas_calib))),
                float(max(0.01, 0.30 * (1.0 - p_cas_calib))),
                p_cas_calib
            ]
            p_sum = sum(p_curr)
            p_curr = [p / p_sum for p in p_curr]

            dec = pol.step_decision(
                p_cas=p_curr[3],
                rain_3d=max_3d,
                rain_24h=max_1d,
                susceptibility=0.75,
                pct_rank=95.0 if max_1d > 80.0 else 50.0
            )

            # Write ledger entry if action changed or peak date
            if dec["action_changed"] or d_str == meta.peak_date or step_idx == 0:
                ledger.add(
                    t=step_idx,
                    timestamp_ist=f"{d_str} 08:30:00 IST",
                    p_before=p_prev,
                    p_after=p_curr,
                    act_from=act_prev,
                    act_to=dec["action_name"],
                    contributions=dec["contributions"],
                    reverses_if=dec["reverses_if"],
                    rule_fired=dec["rule_fired"],
                    input_hash=f"imd-{d_str}"
                )

            act_prev = dec["action_name"]
            p_prev = p_curr

            timeline.append({
                "step_idx": step_idx,
                "date": d_str,
                "is_peak": (d_str == meta.peak_date),
                "district_mean_1d_mm": mean_1d,
                "district_max_1d_mm": max_1d,
                "district_mean_3d_mm": mean_3d,
                "district_max_3d_mm": max_3d,
                "max_cell": summary["district_max_cell"],
                "max_landslide_trigger_index": max_ls,
                "p_cascade": p_curr[3],
                "p_all": p_curr,
                "action_name": dec["action_name"],
                "action_level": dec["action_level"],
                "rule_fired": dec["rule_fired"],
                "plain_reason": dec["plain_reason"],
                "reverses_if": dec["reverses_if"],
                "source_agreement": agr,
                "cells": summary["cells"]
            })

        return {
            "meta": meta,
            "dates": dates,
            "timeline": timeline,
            "ledger_entries": ledger.entries,
            "ledger_json": ledger.to_json(),
            "ledger_csv": ledger.to_csv(),
            "ledger_verified": ledger.verify()
        }
