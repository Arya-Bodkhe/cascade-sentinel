"""Standard schema and records for Pune hydro-meteorological evidence."""
from dataclasses import dataclass
from typing import Optional, List, Dict
import pandas as pd

# Standard provenance tags enforced across the whole system
PROVENANCE_PROVIDED = "PROVIDED-DATA"
PROVENANCE_LIVE = "LIVE"
PROVENANCE_CACHED = "CACHED"
PROVENANCE_FORECAST = "FORECAST"
PROVENANCE_ASSUMPTION = "ASSUMPTION"

# Quality flags
FLAG_VALID = "VALID"
FLAG_EXTREME_VERIFY = "EXTREME_VERIFY"
FLAG_MISSING = "MISSING"
FLAG_INTERPOLATED_PROHIBITED = "UNFILLED_GAP"

@dataclass
class EvidencePoint:
    timestamp_ist: str
    cell_id: str
    lat: float
    lon: float
    variable: str          # 'rainfall', 'precipitation', 'soil_moisture'
    value: Optional[float]
    unit: str              # 'mm/h', 'mm/day', 'm3/m3'
    source: str            # 'IMD gridded (observed-derived)', 'gridded estimate (Open-Meteo)', 'Open-Meteo API'
    quality_flag: str
    provenance: str

@dataclass
class GridCellMeta:
    cell_id: str
    lat: float
    lon: float
    in_district: bool
    exclusion_reason: Optional[str]
    nearest_taluka_proxy: str
    monsoon_climatology_mean: float = 0.0
    glc_min_dist_km: float = 999.0
    susceptibility_prior: float = 0.5
