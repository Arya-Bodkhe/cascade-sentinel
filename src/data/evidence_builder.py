"""Evidence builder and susceptibility prior engine for Pune District.

Integrates:
  - IMD daily gridded rainfall across 24 in-district cells.
  - Open-Meteo hourly accumulations & soil moisture for Pune point (18.52N, 73.87E).
  - NASA GLC weak spatial prior (proximity to confirmed in-district events).
  - Source agreement metric between IMD and Open-Meteo at CELL_18.50_73.75.
  - Published Western Ghats empirical landslide rainfall-trigger thresholds.

DATA POLICY ENFORCED:
  - Every value tagged: PROVIDED-DATA, LIVE, CACHED, FORECAST, ASSUMPTION.
  - No synthetic data fabrication.
  - Disagreement between sources lowers belief confidence; never averaged silently.
"""
import os
import math
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from src.data.schema import (
    PROVENANCE_PROVIDED, PROVENANCE_LIVE, PROVENANCE_CACHED,
    PROVENANCE_FORECAST, PROVENANCE_ASSUMPTION, GridCellMeta
)
from src.data.loader_openmeteo import OpenMeteoLoader
from src.data.loader_imd import IMDLoader
from src.data.loader_glc import GLCLoader

# Western Ghats empirical landslide threshold defaults (ASSUMPTION, user-editable)
# Based on Caine / GSI empirical thresholds for Western Ghats basaltic terrain
DEFAULT_THRESH_3D_MM = 150.0      # 3-day cumulative antecedent saturation threshold
DEFAULT_THRESH_24H_MM = 80.0      # 24-hour triggering deluge threshold
DEFAULT_THRESH_HOURLY_MM = 20.0   # 1-hour burst threshold (Pune point only)


class EvidenceBuilder:
    def __init__(self,
                 imd_loader: Optional[IMDLoader] = None,
                 om_loader: Optional[OpenMeteoLoader] = None,
                 glc_loader: Optional[GLCLoader] = None,
                 w_clim: float = 0.70,
                 w_glc: float = 0.30):
        self.imd = imd_loader or IMDLoader()
        self.om = om_loader or OpenMeteoLoader()
        self.glc = glc_loader or GLCLoader()
        self.w_clim = w_clim
        self.w_glc = w_glc
        self._susceptibility_priors: Optional[Dict[str, float]] = None

    def build_susceptibility_priors(self, force_reload: bool = False) -> Dict[str, float]:
        """Compute spatial susceptibility prior per in-district cell.
        
        Prior = w_clim * rank_norm(monsoon_climatology) + w_glc * glc_proximity
        Tagged: 'ASSUMPTION: rainfall-climatology proxy, not a geological susceptibility map'
        """
        if self._susceptibility_priors is not None and not force_reload:
            return self._susceptibility_priors

        # Ensure loaders are loaded
        self.imd.load()
        self.glc.process_and_export()

        in_cells = self.imd.in_district_cells
        cell_meta = self.imd.cell_metadata

        # 1. Rank-normalize monsoon climatological rainfall
        clim_vals = [cell_meta[c].monsoon_climatology_mean for c in in_cells]
        ranks = pd.Series(clim_vals).rank(pct=True).values

        # 2. Distance to nearest confirmed GLC event
        priors = {}
        for idx, c_id in enumerate(in_cells):
            meta = cell_meta[c_id]
            min_d, prox_score = self.glc.compute_glc_proximity_prior(meta.lat, meta.lon)
            meta.glc_min_dist_km = min_d
            # Weighted combination
            prior_val = self.w_clim * ranks[idx] + self.w_glc * prox_score
            # Normalize to range [0.05, 0.95]
            prior_val = float(np.clip(prior_val, 0.05, 0.95))
            meta.susceptibility_prior = prior_val
            priors[c_id] = prior_val

        self._susceptibility_priors = priors
        return self._susceptibility_priors

    def get_source_agreement(self, date_str: str) -> Dict[str, Any]:
        """Evaluate agreement between IMD and Open-Meteo for the Pune Cell on a given date.
        
        Returns:
            {
               'imd_rain_mm': float,
               'om_rain_mm': float,
               'abs_delta_mm': float,
               'agreement_ratio': float (0.0 to 1.0, 1.0 = perfect),
               'status': 'AGREEMENT' | 'MODERATE_DIVERGENCE' | 'HIGH_CONFLICT',
               'confidence_penalty': float (0.0 to 0.40)
            }
        """
        om_daily = self.om.get_daily_aggregates()
        om_row = om_daily[om_daily["date_ist"] == date_str]
        om_val = float(om_row["rain_mm_day"].values[0]) if len(om_row) and not pd.isna(om_row["rain_mm_day"].values[0]) else None

        imd_slice = self.imd.get_date_slice(date_str)
        pune_imd = imd_slice[imd_slice["cell_id"] == "CELL_18.50_73.75"]
        imd_val = float(pune_imd["rainfall_mm_per_day"].values[0]) if len(pune_imd) else None

        if om_val is None or imd_val is None:
            return {
                "imd_rain_mm": imd_val,
                "om_rain_mm": om_val,
                "abs_delta_mm": None,
                "agreement_ratio": 1.0,
                "status": "SINGLE_SOURCE_AVAILABLE",
                "confidence_penalty": 0.0,
                "note": "One source missing (e.g. pre-June 2015 or reporting lag)"
            }

        abs_diff = abs(imd_val - om_val)
        denom = max(imd_val, om_val, 10.0)
        rel_diff = abs_diff / denom
        agreement = max(0.0, 1.0 - rel_diff)

        if abs_diff <= 10.0 or agreement >= 0.70:
            status = "STRONG_AGREEMENT"
            penalty = 0.0
        elif abs_diff <= 30.0 or agreement >= 0.40:
            status = "MODERATE_DIVERGENCE"
            penalty = 0.15
        else:
            status = "HIGH_CONFLICT"
            penalty = 0.35  # Lowers confidence in hypothesis filter

        return {
            "imd_rain_mm": round(imd_val, 1),
            "om_rain_mm": round(om_val, 1),
            "abs_delta_mm": round(abs_diff, 1),
            "agreement_ratio": round(agreement, 2),
            "status": status,
            "confidence_penalty": penalty,
            "note": "Disagreement between sources lowers confidence; not averaged silently"
        }

    def evaluate_cell_evidence(self, date_str: str, cell_id: str,
                               thresh_3d: float = DEFAULT_THRESH_3D_MM,
                               thresh_24h: float = DEFAULT_THRESH_24H_MM,
                               date_slice_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """Compile complete evidence vector for a single cell on a given date."""
        self.build_susceptibility_priors()
        meta = self.imd.cell_metadata.get(cell_id)
        if not meta:
            raise ValueError(f"Unknown cell {cell_id}")

        if date_slice_df is not None:
            row = date_slice_df[date_slice_df["cell_id"] == cell_id]
        else:
            cell_slice = self.imd.load()
            row = cell_slice[(cell_slice["cell_id"] == cell_id) & (cell_slice["date"] == date_str)]

        if len(row) == 0:
            return {"error": f"No data for {cell_id} on {date_str}"}

        r = row.iloc[0]
        r_1d = float(r["rain_1d"])
        r_2d = float(r["rain_2d"])
        r_3d = float(r["rain_3d"])
        r_7d = float(r["rain_7d"])

        # Historical percentiles
        pcts = self.imd.get_cell_percentiles(cell_id)
        pct_rank = 0.0
        if pcts:
            for p in [50, 75, 90, 95, 98, 99]:
                if r_1d >= pcts.get(p, 999.0):
                    pct_rank = float(p)

        # Landslide empirical threshold evaluation
        sat_ratio = min(2.0, r_3d / max(thresh_3d, 1.0))
        deluge_ratio = min(2.0, r_1d / max(thresh_24h, 1.0))
        landslide_index = min(1.0, 0.5 * sat_ratio + 0.5 * deluge_ratio)

        # Check Pune point hourly specifics if this is the Pune cell
        hourly_info = None
        if cell_id == "CELL_18.50_73.75":
            om_win = self.om.get_window(date_str, date_str)
            if len(om_win) > 0 and om_win["quality_flag"].iloc[0] != "MISSING":
                hourly_info = {
                    "max_1h_rate_mm_h": float(om_win["rain_acc_1h"].max()),
                    "max_3h_acc_mm": float(om_win["rain_acc_3h"].max()),
                    "mean_soil_moisture": float(om_win["soil_moisture_m3m3"].mean()),
                    "max_soil_moisture": float(om_win["soil_moisture_m3m3"].max()),
                    "label": "Pune point only (Open-Meteo 18.52N, 73.87E)"
                }

        return {
            "cell_id": cell_id,
            "date": date_str,
            "lat": meta.lat,
            "lon": meta.lon,
            "in_district": meta.in_district,
            "taluka_label": meta.nearest_taluka_proxy,
            "susceptibility_prior": meta.susceptibility_prior,
            "monsoon_mean_mm": meta.monsoon_climatology_mean,
            "glc_dist_km": meta.glc_min_dist_km,
            "rain_1d_mm": round(r_1d, 1),
            "rain_2d_mm": round(r_2d, 1),
            "rain_3d_mm": round(r_3d, 1),
            "rain_7d_mm": round(r_7d, 1),
            "percentile_rank": pct_rank,
            "sat_ratio_3d": round(sat_ratio, 2),
            "deluge_ratio_24h": round(deluge_ratio, 2),
            "landslide_trigger_index": round(landslide_index, 3),
            "quality_flag": r["quality_flag"],
            "hourly_pune_point": hourly_info
        }

    def evaluate_district_summary(
        self,
        date_str: str,
        thresh_3d: float = DEFAULT_THRESH_3D_MM,
        thresh_24h: float = DEFAULT_THRESH_24H_MM,
    ) -> Dict[str, Any]:
        """Aggregate evidence across all 24 in-district cells for a single day."""
        self.build_susceptibility_priors()
        in_cells = self.imd.in_district_cells
        date_slice_df = self.imd.get_date_slice(date_str)
        cell_records = [
            self.evaluate_cell_evidence(
                date_str, cid, thresh_3d=thresh_3d, thresh_24h=thresh_24h,
                date_slice_df=date_slice_df,
            )
            for cid in in_cells
        ]

        rain_1d_vals = [c["rain_1d_mm"] for c in cell_records]
        rain_3d_vals = [c["rain_3d_mm"] for c in cell_records]
        ls_indices = [c["landslide_trigger_index"] for c in cell_records]

        max_1d_idx = int(np.argmax(rain_1d_vals))
        max_ls_idx = int(np.argmax(ls_indices))

        agreement = self.get_source_agreement(date_str)

        return {
            "date": date_str,
            "district_mean_1d_mm": round(float(np.mean(rain_1d_vals)), 1),
            "district_max_1d_mm": round(float(np.max(rain_1d_vals)), 1),
            "district_max_cell": in_cells[max_1d_idx],
            "district_mean_3d_mm": round(float(np.mean(rain_3d_vals)), 1),
            "district_max_3d_mm": round(float(np.max(rain_3d_vals)), 1),
            "max_landslide_risk_cell": in_cells[max_ls_idx],
            "max_landslide_trigger_index": round(float(np.max(ls_indices)), 3),
            "source_agreement": agreement,
            "cells": cell_records
        }

    def calculate_threshold_sensitivity(self, events: Optional[List[str]] = None) -> pd.DataFrame:
        """Evaluate trigger sensitivity at Nominal, -20%, and +20% threshold levels across historical events."""
        if events is None:
            events = ["2016-08-03", "2019-08-03", "2019-08-04", "2021-07-22", "2021-07-23", "2024-07-25", "2025-08-20", "2023-08-15"]

        levels = [
            ("Strict (+20%)", DEFAULT_THRESH_3D_MM * 1.20, DEFAULT_THRESH_24H_MM * 1.20),
            ("Nominal (100%)", DEFAULT_THRESH_3D_MM, DEFAULT_THRESH_24H_MM),
            ("Sensitive (-20%)", DEFAULT_THRESH_3D_MM * 0.80, DEFAULT_THRESH_24H_MM * 0.80)
        ]

        rows = []
        for label, t3d, t24h in levels:
            triggered_cells_total = 0
            event_hits = 0
            quiet_alerts = 0
            for ev in events:
                summary = self.evaluate_district_summary(ev)
                # Count cells where landslide_trigger_index >= 0.70 (ALERT or ESCALATE)
                n_trig = sum(1 for c in summary["cells"]
                             if (c["rain_3d_mm"] >= t3d or c["rain_1d_mm"] >= t24h))
                triggered_cells_total += n_trig
                if ev != "2023-08-15" and n_trig > 0:
                    event_hits += 1
                elif ev == "2023-08-15" and n_trig > 0:
                    quiet_alerts += 1

            rows.append({
                "Sensitivity Level": label,
                "3-Day Thresh (mm)": round(t3d, 1),
                "24h Thresh (mm)": round(t24h, 1),
                "Historical Event Hits": f"{event_hits}/{len(events)-1}",
                "Quiet Day False Alerts": quiet_alerts,
                "Total Triggered Cell-Days": triggered_cells_total,
                "Provenace": PROVENANCE_ASSUMPTION
            })

        return pd.DataFrame(rows)
