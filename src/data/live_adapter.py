"""Live API adapter using Open-Meteo free forecast API (no key required).

Fetches past 7 days observed + next 72h forecast per in-district cell centre.
Caches responses to disk in data/cache/.
Status badges:
  - LIVE: API responded successfully.
  - CACHED (<age>): Network unavailable; using last good disk response.
  - OFFLINE-DEMO: Network and cache unavailable; using built-in synthetic/historical template.

SAFETY GUARANTEE: Never throws an unhandled exception or crashes the app on network failure.
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, List
import pandas as pd
import numpy as np

try:
    import urllib.request
    import urllib.error
    HAS_NETWORK_LIB = True
except ImportError:
    HAS_NETWORK_LIB = False

from src.data.schema import (
    PROVENANCE_LIVE, PROVENANCE_CACHED, PROVENANCE_FORECAST,
    FLAG_VALID, EvidencePoint
)

CACHE_DIR = "data/cache"


class LiveAdapter:
    def __init__(self, cache_dir: str = CACHE_DIR, timeout_sec: int = 5):
        self.cache_dir = cache_dir
        self.timeout_sec = timeout_sec
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_path(self, cell_id: str) -> str:
        return os.path.join(self.cache_dir, f"{cell_id}_forecast.json")

    def _format_age(self, mtime: float) -> str:
        elapsed = time.time() - mtime
        if elapsed < 60:
            return "just now"
        if elapsed < 3600:
            return f"{int(elapsed // 60)}m ago"
        if elapsed < 86400:
            return f"{int(elapsed // 3600)}h ago"
        return f"{int(elapsed // 86400)}d ago"

    def fetch_cell(self, cell_id: str, lat: float, lon: float) -> Tuple[Optional[pd.DataFrame], str, str]:
        """Fetch past 7d + 72h forecast for a single grid cell.
        
        Returns:
            (df, status_badge, info_message)
        """
        cache_path = self._get_cache_path(cell_id)
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat:.4f}&longitude={lon:.4f}&"
            f"hourly=rain,precipitation,soil_moisture_0_to_7cm&"
            f"past_days=7&forecast_days=3&timezone=Asia%2FKolkata"
        )

        data = None
        status = "OFFLINE-DEMO"
        info = "No connection or cache available"

        # 1. Attempt Live API Fetch
        if HAS_NETWORK_LIB:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "CascadeSentinel/2.0"})
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    if resp.status == 200:
                        raw_json = resp.read().decode("utf-8")
                        data = json.loads(raw_json)
                        # Save to cache
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump({"timestamp": time.time(), "payload": data}, f)
                        status = "LIVE"
                        info = f"Fetched live data at {datetime.now().strftime('%H:%M:%S IST')}"
            except Exception as e:
                # Fallback to cache
                pass

        # 2. Fallback to Disk Cache if live failed
        if data is None and os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_obj = json.load(f)
                data = cached_obj.get("payload")
                mtime = cached_obj.get("timestamp", os.path.getmtime(cache_path))
                age_str = self._format_age(mtime)
                status = f"CACHED ({age_str})"
                info = f"Loaded cached response from {age_str}"
            except Exception:
                data = None

        # 3. Fallback to Offline Demo if both failed
        if data is None:
            return self._generate_offline_demo(cell_id, lat, lon), "OFFLINE-DEMO", "Operating in offline demo fallback mode"

        # Parse API structure
        try:
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            rain = hourly.get("rain", [0.0] * len(times))
            precip = hourly.get("precipitation", rain)
            soil = hourly.get("soil_moisture_0_to_7cm", [0.25] * len(times))

            df = pd.DataFrame({
                "time_ist": pd.to_datetime(times),
                "rain_mm_h": rain,
                "precip_mm_h": precip,
                "soil_moisture_m3m3": soil,
            })
            df["timestamp_ist"] = df["time_ist"].dt.strftime("%Y-%m-%d %H:%M:%S IST")
            df["date_ist"] = df["time_ist"].dt.date.astype(str)
            df["hour_ist"] = df["time_ist"].dt.hour
            df["cell_id"] = cell_id
            df["lat"] = lat
            df["lon"] = lon

            now_ist = datetime.now()
            df["provenance"] = np.where(df["time_ist"] > now_ist, PROVENANCE_FORECAST,
                                        PROVENANCE_LIVE if status == "LIVE" else PROVENANCE_CACHED)
            df["quality_flag"] = FLAG_VALID
            return df, status, info
        except Exception as e:
            return self._generate_offline_demo(cell_id, lat, lon), "OFFLINE-DEMO", f"Parse error ({str(e)}), used offline demo"

    def _generate_offline_demo(self, cell_id: str, lat: float, lon: float) -> pd.DataFrame:
        """Deterministically generated past 7 days + 72h forecast template for offline mode."""
        base_now = pd.Timestamp.now().floor("h")
        start = base_now - pd.Timedelta(days=7)
        end = base_now + pd.Timedelta(days=3)
        idx = pd.date_range(start=start, end=end, freq="1h")

        # Deterministic wave based on cell lat/lon
        seed = int(lat * 100 + lon * 10) % 1000
        rng = np.random.default_rng(seed)
        n = len(idx)
        # Low background rain with sporadic pulses
        base_rain = np.maximum(0.0, rng.normal(0.5, 1.2, n))
        # Add a pulse in the recent 24h
        pulse_center = 7 * 24 - 12
        pulse = 15.0 * np.exp(-0.5 * ((np.arange(n) - pulse_center) / 6.0)**2)
        rain = np.round(base_rain + pulse, 1)

        df = pd.DataFrame({
            "time_ist": idx,
            "rain_mm_h": rain,
            "precip_mm_h": rain * 1.05,
            "soil_moisture_m3m3": np.clip(0.20 + rain * 0.01, 0.15, 0.45),
        })
        df["timestamp_ist"] = df["time_ist"].dt.strftime("%Y-%m-%d %H:%M:%S IST")
        df["date_ist"] = df["time_ist"].dt.date.astype(str)
        df["hour_ist"] = df["time_ist"].dt.hour
        df["cell_id"] = cell_id
        df["lat"] = lat
        df["lon"] = lon
        df["provenance"] = np.where(df["time_ist"] > base_now, PROVENANCE_FORECAST, PROVENANCE_CACHED)
        df["quality_flag"] = FLAG_VALID
        return df
