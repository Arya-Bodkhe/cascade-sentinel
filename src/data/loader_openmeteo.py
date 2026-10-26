"""Loader for Open-Meteo Pune single-point hourly reanalysis dataset.

Source coordinates: 18.523726°N, 73.86876°E, 561 m ASL.
Timezone: UTC stored in file -> converted to IST (+05:30) on load.
Missing handling: Jan-May 2015 is missing, marked as NaN, NEVER zero-filled.
Label: 'gridded estimate (Open-Meteo)'.
"""
import os
from typing import Optional, Tuple
import numpy as np
import pandas as pd
from src.data.schema import (
    PROVENANCE_PROVIDED, FLAG_VALID, FLAG_MISSING, EvidencePoint
)

PUNE_POINT_LAT = 18.523726
PUNE_POINT_LON = 73.86876
PUNE_POINT_ELEVATION_M = 561.0
SOURCE_LABEL = "gridded estimate (Open-Meteo)"


class OpenMeteoLoader:
    def __init__(self, filepath: Optional[str] = None):
        if filepath is None:
            for p in ["data/open-meteo-18_52N73_87E561m.csv",
                      "data/open-meteo-18.52N73.87E561m.csv"]:
                if os.path.exists(p):
                    filepath = p
                    break
        self.filepath = filepath
        self._df: Optional[pd.DataFrame] = None
        self._df_daily: Optional[pd.DataFrame] = None

    def load(self, force_reload: bool = False) -> pd.DataFrame:
        if self._df is not None and not force_reload:
            return self._df

        if not self.filepath or not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Open-Meteo dataset not found at {self.filepath}")

        # Header block of 3 metadata lines before the table (skiprows=3)
        df_raw = pd.read_csv(self.filepath, skiprows=3)

        # Standardize column names
        col_map = {}
        for col in df_raw.columns:
            c_low = col.lower().strip()
            if "time" in c_low:
                col_map[col] = "time_utc"
            elif c_low.startswith("rain"):
                col_map[col] = "rain_mm_h"
            elif c_low.startswith("precip"):
                col_map[col] = "precip_mm_h"
            elif "soil_moisture" in c_low:
                col_map[col] = "soil_moisture_m3m3"
        df = df_raw.rename(columns=col_map).copy()

        # Parse UTC time and convert to IST (+05:30)
        df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
        df["time_ist"] = df["time_utc"].dt.tz_convert("Asia/Kolkata")

        # Build complete hourly UTC grid starting 2015-01-01 00:00:00 UTC
        # This explicitly marks Jan-May 2015 as MISSING (NaN), never filled with zero
        start_utc = pd.Timestamp("2015-01-01 00:00:00", tz="UTC")
        end_utc = df["time_utc"].max()
        full_utc_idx = pd.date_range(start=start_utc, end=end_utc, freq="1h", name="time_utc")

        df_full = df.set_index("time_utc").reindex(full_utc_idx).reset_index()
        df_full["time_ist"] = df_full["time_utc"].dt.tz_convert("Asia/Kolkata")
        df_full["timestamp_ist"] = df_full["time_ist"].dt.strftime("%Y-%m-%d %H:%M:%S IST")
        df_full["date_ist"] = df_full["time_ist"].dt.date.astype(str)
        df_full["hour_ist"] = df_full["time_ist"].dt.hour

        # Mark quality flag: Missing for Jan-May 2015 or nulls, never filled with zero
        df_full["quality_flag"] = np.where(df_full["rain_mm_h"].isna(), FLAG_MISSING, FLAG_VALID)
        df_full["provenance"] = PROVENANCE_PROVIDED
        df_full["source"] = SOURCE_LABEL
        df_full["lat"] = PUNE_POINT_LAT
        df_full["lon"] = PUNE_POINT_LON
        df_full["cell_id"] = "CELL_18.50_73.75"

        # Sort chronologically
        df_full.sort_values("time_ist", inplace=True)
        df_full.reset_index(drop=True, inplace=True)

        # Derived rolling accumulations (Pune point only):
        df_full["rain_acc_1h"] = df_full["rain_mm_h"]
        df_full["rain_acc_3h"] = df_full["rain_mm_h"].rolling(window=3, min_periods=1).sum()
        df_full["rain_acc_24h"] = df_full["rain_mm_h"].rolling(window=24, min_periods=12).sum()
        df_full["rain_acc_72h"] = df_full["rain_mm_h"].rolling(window=72, min_periods=36).sum()

        self._df = df_full
        return self._df

    def get_daily_aggregates(self) -> pd.DataFrame:
        """Aggregate hourly Pune point to calendar day IST for comparison with IMD."""
        if self._df_daily is not None:
            return self._df_daily

        df = self.load()
        # Group by IST date
        daily = df.groupby("date_ist").agg(
            rain_mm_day=("rain_mm_h", "sum"),
            precip_mm_day=("precip_mm_h", "sum"),
            soil_moisture_mean=("soil_moisture_m3m3", "mean"),
            soil_moisture_max=("soil_moisture_m3m3", "max"),
            max_1h_rate=("rain_mm_h", "max"),
        ).reset_index()
        valid_hours = df["quality_flag"].eq(FLAG_VALID).groupby(df["date_ist"]).sum()
        daily["valid_hours"] = daily["date_ist"].map(valid_hours)

        # If day has fewer than 20 valid hours, mark daily rain as NaN (missing, never zero)
        mask_incomplete = daily["valid_hours"] < 20
        daily.loc[mask_incomplete, ["rain_mm_day", "precip_mm_day", "soil_moisture_mean", "max_1h_rate"]] = np.nan
        daily["source"] = SOURCE_LABEL
        daily["cell_id"] = "CELL_18.50_73.75"
        self._df_daily = daily
        return self._df_daily

    def get_window(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Extract slice by IST dates (inclusive)."""
        df = self.load()
        mask = (df["date_ist"] >= start_date) & (df["date_ist"] <= end_date)
        return df.loc[mask].copy()
