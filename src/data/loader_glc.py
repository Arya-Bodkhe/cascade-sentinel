"""Loader and processor for NASA Global Landslide Catalog (GLC).

Filters Indian events to Pune district and Western Maharashtra candidates.
Generates: data/derived/glc_pune_candidates.csv
Classification:
  - in_district: 'yes' (confirmed Pune district)
  - in_district: 'ambiguous' (Ghat crest / Expressway tunnels on Pune/Raigad border)
  - in_district: 'no' (Raigad, Thane, Mumbai, Ratnagiri, Ahmednagar)

NOTE ON MODELING:
Records are sparse. NASA GLC events are used ONLY as:
(a) A historical sanity check against rainfall events.
(b) A weak spatial prior component for landslide susceptibility.
NEVER TRAIN A PREDICTIVE MODEL ON THEM.
Malin (2014-07-30) predates the rainfall record (2015-2025): context only.
"""
import os
import math
from typing import Optional, List, Dict, Tuple
import pandas as pd
import numpy as np
from src.data.schema import PROVENANCE_PROVIDED, PROVENANCE_ASSUMPTION


class GLCLoader:
    def __init__(self, raw_filepath: Optional[str] = None,
                 derived_filepath: str = "data/derived/glc_pune_candidates.csv"):
        if raw_filepath is None:
            for p in ["data/Global_Landslide_Catalog_Export_rows__3_.csv",
                      "data/Global_Landslide_Catalog_Export_rows (3).csv"]:
                if os.path.exists(p):
                    raw_filepath = p
                    break
        self.raw_filepath = raw_filepath
        self.derived_filepath = derived_filepath
        self._df_candidates: Optional[pd.DataFrame] = None

    def process_and_export(self, force_reload: bool = False) -> pd.DataFrame:
        """Parse raw NASA GLC, extract Western Maharashtra candidates, classify, and export."""
        if self._df_candidates is not None and not force_reload:
            return self._df_candidates
        if os.path.exists(self.derived_filepath) and not force_reload:
            self._df_candidates = pd.read_csv(self.derived_filepath)
            return self._df_candidates

        if not self.raw_filepath or not os.path.exists(self.raw_filepath):
            raise FileNotFoundError(f"Raw NASA GLC file not found at {self.raw_filepath}")

        df_raw = pd.read_csv(self.raw_filepath)
        india = df_raw[df_raw["country_name"] == "India"].copy()

        # Bounding box for Western Maharashtra surrounding Pune: Lat 17.5-19.5, Lon 73.0-75.0
        mask_bbox = (
            (india["latitude"] >= 17.5) & (india["latitude"] <= 19.5) &
            (india["longitude"] >= 73.0) & (india["longitude"] <= 75.0)
        )
        candidates = india[mask_bbox].copy()

        # Parse event_date: MM/DD/YYYY HH:MM:SS AM/PM
        candidates["event_datetime_ist"] = pd.to_datetime(
            candidates["event_date"], format="%m/%d/%Y %I:%M:%S %p", errors="coerce"
        )
        candidates["event_date_str"] = candidates["event_datetime_ist"].dt.strftime("%Y-%m-%d")

        # Classification rule based on coordinates and location description
        results = []
        for _, row in candidates.iterrows():
            loc = str(row.get("location_description", "")).lower()
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            eid = int(row["event_id"])

            in_dist = "no"
            reason = "Outside Pune district"

            if eid == 9415 or "lavasa" in loc:
                in_dist = "yes"
                reason = "Confirmed Pune district: Lavasa / Mose valley (Mulshi taluka)"
            elif eid == 6186 or "malin" in loc:
                in_dist = "yes"
                reason = "Confirmed Pune district: Malin village (Ambegaon taluka); 151 fatalities, predates 2015 rainfall data, context only"
            elif eid == 6973 or ("karla" in loc and "ekvira" in loc):
                in_dist = "yes"
                reason = "Confirmed Pune district: Karla / Ekvira Devi (Maval taluka)"
            elif any(k in loc for k in ["khandala", "monkey hill", "adoshi"]):
                in_dist = "ambiguous"
                reason = "Crestline / expressway border zone between Pune (Maval) and Raigad (Khalapur); excluded from calibration, shown for review"
            elif lat == 18.7654 and lon == 73.3640:
                in_dist = "ambiguous"
                reason = "Crestline coordinate near Khandala without specific location description"
            elif any(k in loc for k in ["malshej"]):
                in_dist = "no"
                reason = "Malshej Ghat on Thane / Ahmednagar border (north of Junnar)"
            elif any(k in loc for k in ["raigad", "karjat", "kashedi", "fort"]):
                in_dist = "no"
                reason = "Raigad district (Konkan lowland / west of Ghats)"
            elif any(k in loc for k in ["ratnagiri", "dabhol", "dapoli", "harne"]):
                in_dist = "no"
                reason = "Ratnagiri district (Konkan coast)"
            elif any(k in loc for k in ["mumbai", "thane", "turbhe", "mumbra", "parsik", "diva", "ulhasnagar", "kalwa"]):
                in_dist = "no"
                reason = "Mumbai / Thane / Navi Mumbai metropolitan region"

            predates = str(row["event_date_str"]) < "2015-01-28"

            results.append({
                "event_id": eid,
                "event_date": row["event_date"],
                "event_date_ist": row["event_date_str"],
                "latitude": round(lat, 5),
                "longitude": round(lon, 5),
                "location_description": row["location_description"],
                "location_accuracy": row["location_accuracy"],
                "landslide_trigger": row["landslide_trigger"],
                "landslide_size": row["landslide_size"],
                "fatality_count": row["fatality_count"],
                "injury_count": row["injury_count"],
                "in_district": in_dist,
                "classification_reason": reason,
                "predates_rainfall_baseline": predates,
                "provenance": PROVENANCE_PROVIDED
            })

        df_out = pd.DataFrame(results)
        df_out.sort_values(["in_district", "event_date_ist"], ascending=[False, True], inplace=True)
        os.makedirs(os.path.dirname(self.derived_filepath), exist_ok=True)
        df_out.to_csv(self.derived_filepath, index=False)
        self._df_candidates = df_out
        return self._df_candidates

    def get_confirmed_in_district(self) -> pd.DataFrame:
        df = self.process_and_export()
        return df[df["in_district"] == "yes"].copy()

    def get_ambiguous(self) -> pd.DataFrame:
        df = self.process_and_export()
        return df[df["in_district"] == "ambiguous"].copy()

    def compute_glc_proximity_prior(self, cell_lat: float, cell_lon: float) -> Tuple[float, float]:
        """Compute minimum distance (km) and inverse-distance prior contribution to confirmed events.
        
        Uses Haversine approximation.
        """
        df_conf = self.get_confirmed_in_district()
        if len(df_conf) == 0:
            return 999.0, 0.0

        min_d = 999.0
        for _, r in df_conf.iterrows():
            d_lat = (cell_lat - r["latitude"]) * 111.0
            d_lon = (cell_lon - r["longitude"]) * 111.0 * math.cos(math.radians(cell_lat))
            d = math.sqrt(d_lat**2 + d_lon**2)
            if d < min_d:
                min_d = d

        # Decaying proximity score: 1.0 at 0km, 0.5 at 15km, ~0.1 at 50km
        score = 1.0 / (1.0 + min_d / 15.0)
        return float(min_d), float(score)
