"""Loader for Pune IMD gridded daily rainfall dataset (0.25° resolution, 40 cells).

Columns: date, latitude, longitude, rainfall_mm_per_day
Temporal span: 2015-01-28 to 2025-12-31.
Label: 'IMD gridded (observed-derived)'. (NOT station data).
Explicit in-district cell classification and extreme value flagging (>300 mm/day).
"""
import os
from typing import Optional, List, Dict, Tuple
import numpy as np
import pandas as pd
from src.data.schema import (
    PROVENANCE_PROVIDED, PROVENANCE_ASSUMPTION, FLAG_VALID,
    FLAG_EXTREME_VERIFY, GridCellMeta
)

SOURCE_LABEL = "IMD gridded (observed-derived)"

# Reference taluka headquarters approximate centers in Pune district
# Used only if /data/static/talukas.csv is not provided
DEFAULT_TALUKA_CENTERS = [
    ("Haveli / Pune City", 18.5204, 73.8567),
    ("Maval (Lonavla/Vadgaon)", 18.7500, 73.6800),
    ("Mulshi (Paud/Lavasa)", 18.5300, 73.6100),
    ("Velhe", 18.2900, 73.6300),
    ("Bhor", 18.1500, 73.8500),
    ("Purandar (Saswad)", 18.3400, 74.0300),
    ("Khed (Rajgurunagar)", 18.8500, 73.9000),
    ("Ambegaon (Ghodegaon)", 19.0300, 73.7500),
    ("Junnar", 19.2000, 73.8800),
    ("Shirur", 18.8200, 74.3700),
    ("Daund", 18.4700, 74.5800),
    ("Baramati", 18.1500, 74.5800),
    ("Indapur", 18.1200, 75.0200),
]


class IMDLoader:
    def __init__(self, filepath: Optional[str] = None, arrival_lag_days: int = 1):
        if filepath is None:
            for p in ["data/pune_imd_rainfall.csv"]:
                if os.path.exists(p):
                    filepath = p
                    break
        self.filepath = filepath
        self.arrival_lag_days = arrival_lag_days
        self._df: Optional[pd.DataFrame] = None
        self._cell_meta: Optional[Dict[str, GridCellMeta]] = None
        self._percentiles: Optional[Dict[str, Dict[float, float]]] = None
        self._taluka_provided = False

    def _classify_cells(self) -> Dict[Tuple[float, float], Tuple[bool, Optional[str], str]]:
        """Cell-centre classification of all 40 grid cells (5 lats x 8 lons)."""
        mapping = {}
        # Load external talukas if available
        ext_talukas_path = "data/static/talukas.csv"
        taluka_refs = DEFAULT_TALUKA_CENTERS
        if os.path.exists(ext_talukas_path):
            try:
                tdf = pd.read_csv(ext_talukas_path)
                if {"taluka", "lat", "lon"}.issubset(tdf.columns):
                    taluka_refs = [(r["taluka"], float(r["lat"]), float(r["lon"])) for _, r in tdf.iterrows()]
                    self._taluka_provided = True
            except Exception:
                pass

        lats = [18.0, 18.25, 18.5, 18.75, 19.0]
        lons = [73.0, 73.25, 73.5, 73.75, 74.0, 74.25, 74.5, 74.75]

        for lat in lats:
            for lon in lons:
                coord = (lat, lon)
                # Exclusion rule 1: West of Western Ghats crest (Konkan lowland: Raigad/Thane/Ratnagiri)
                if lon <= 73.25:
                    mapping[coord] = (False, "West of Western Ghats divide (Konkan: Raigad/Thane/Ratnagiri)", "Konkan coastal belt")
                    continue

                # Exclusion rule 2: South of Pune district border (Satara/Solapur)
                if lat == 18.0:
                    if lon == 73.50:
                        reason = "South of Pune district (Mahabaleshwar / Satara Ghats border)"
                    elif lon in [73.75, 74.00]:
                        reason = "South of Pune district (Khandala Satara / Phaltan)"
                    else:
                        reason = "South of Pune district (Solapur district: Malshiras/Pandharpur)"
                    mapping[coord] = (False, reason, "Satara/Solapur border")
                    continue

                # In-district cells: Find nearest taluka proxy
                best_taluka = "DATA NOT PROVIDED"
                best_dist = 1e9
                for name, t_lat, t_lon in taluka_refs:
                    d = (lat - t_lat)**2 + (lon - t_lon)**2
                    if d < best_dist:
                        best_dist = d
                        best_taluka = name

                tag_prefix = "" if self._taluka_provided else "DATA NOT PROVIDED: nearest "
                mapping[coord] = (True, None, f"{tag_prefix}{best_taluka}")

        return mapping

    def load(self, force_reload: bool = False) -> pd.DataFrame:
        if self._df is not None and not force_reload:
            return self._df

        if not self.filepath or not os.path.exists(self.filepath):
            raise FileNotFoundError(f"IMD rainfall dataset not found at {self.filepath}")

        df = pd.read_csv(self.filepath)
        df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
        df["latitude"] = df["latitude"].round(2)
        df["longitude"] = df["longitude"].round(2)
        cell_class = self._classify_cells()
        df["cell_id"] = [
            f"CELL_{lat:.2f}_{lon:.2f}"
            for lat, lon in zip(df["latitude"].to_numpy(), df["longitude"].to_numpy())
        ]
        class_by_id = {
            f"CELL_{lat:.2f}_{lon:.2f}": classification
            for (lat, lon), classification in cell_class.items()
        }
        df["in_district"] = df["cell_id"].map({key: value[0] for key, value in class_by_id.items()}).astype(bool)
        df["exclusion_reason"] = df["cell_id"].map({key: value[1] for key, value in class_by_id.items()})
        df["taluka_label"] = df["cell_id"].map({key: value[2] for key, value in class_by_id.items()})

        # Quality flag: Flag extreme values (>300 mm/day) as plausible Western Ghats deluge, verify
        # Never clip or delete!
        df["quality_flag"] = np.where(
            df["rainfall_mm_per_day"] > 300.0,
            FLAG_EXTREME_VERIFY,
            FLAG_VALID
        )
        df["source"] = SOURCE_LABEL
        df["provenance"] = PROVENANCE_PROVIDED
        df["unit"] = "mm/day"

        # Modeled arrival time (IST): event date + arrival_lag_days at 08:30 IST (standard IMD synoptic hour)
        df["event_timestamp_ist"] = df["date"] + " 08:30:00 IST"
        df["arrival_date_ist"] = pd.to_datetime(df["date"]) + pd.Timedelta(days=self.arrival_lag_days)
        df["arrival_timestamp_ist"] = df["arrival_date_ist"].dt.strftime("%Y-%m-%d 08:30:00 IST")

        # Sort chronologically per cell to calculate antecedent rolling sums
        df.sort_values(["cell_id", "date"], inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Antecedent rolling sums per cell
        df["rain_1d"] = df["rainfall_mm_per_day"]
        grouped = df.groupby("cell_id")["rainfall_mm_per_day"]
        df["rain_2d"] = grouped.rolling(2, min_periods=1).sum().reset_index(0, drop=True)
        df["rain_3d"] = grouped.rolling(3, min_periods=1).sum().reset_index(0, drop=True)
        df["rain_7d"] = grouped.rolling(7, min_periods=1).sum().reset_index(0, drop=True)

        self._df = df
        self._compute_climatology_and_percentiles()
        return self._df

    def _compute_climatology_and_percentiles(self):
        """Compute Jun-Sep monsoon climatology mean and baseline percentiles (2015-2025)."""
        df = self._df
        df_dt = pd.to_datetime(df["date"])
        monsoon_mask = df_dt.dt.month.isin([6, 7, 8, 9])
        df_monsoon = df[monsoon_mask]

        # Monsoon mean rainfall per cell
        clim_means = df_monsoon.groupby("cell_id")["rainfall_mm_per_day"].mean().to_dict()

        # Compute percentiles for in-district cells during monsoon
        percentiles = {}
        for cell_id, grp in df_monsoon.groupby("cell_id"):
            vals = grp["rainfall_mm_per_day"].values
            percentiles[cell_id] = {
                50: float(np.percentile(vals, 50)),
                75: float(np.percentile(vals, 75)),
                90: float(np.percentile(vals, 90)),
                95: float(np.percentile(vals, 95)),
                98: float(np.percentile(vals, 98)),
                99: float(np.percentile(vals, 99)),
                "max": float(np.max(vals))
            }
        self._percentiles = percentiles

        # Cell metadata dict
        cell_class = self._classify_cells()
        cell_meta = {}
        for (lat, lon), (in_dist, reason, taluka) in cell_class.items():
            c_id = f"CELL_{lat:.2f}_{lon:.2f}"
            c_mean = clim_means.get(c_id, 0.0)
            cell_meta[c_id] = GridCellMeta(
                cell_id=c_id,
                lat=lat,
                lon=lon,
                in_district=in_dist,
                exclusion_reason=reason,
                nearest_taluka_proxy=taluka,
                monsoon_climatology_mean=c_mean,
                susceptibility_prior=0.5
            )
        self._cell_meta = cell_meta

    @property
    def cell_metadata(self) -> Dict[str, GridCellMeta]:
        if self._cell_meta is None:
            self.load()
        return self._cell_meta

    @property
    def in_district_cells(self) -> List[str]:
        return [cid for cid, m in self.cell_metadata.items() if m.in_district]

    @property
    def excluded_cells(self) -> List[str]:
        return [cid for cid, m in self.cell_metadata.items() if not m.in_district]

    def get_cell_percentiles(self, cell_id: str) -> Dict[float, float]:
        if self._percentiles is None:
            self.load()
        return self._percentiles.get(cell_id, {})

    def get_extreme_records(self) -> pd.DataFrame:
        """Return all records flagged with >300 mm/day."""
        df = self.load()
        return df[df["quality_flag"] == FLAG_EXTREME_VERIFY].copy()

    def get_date_slice(self, date_str: str) -> pd.DataFrame:
        """Return all 40 cells for a single date."""
        df = self.load()
        return df[df["date"] == date_str].copy()
