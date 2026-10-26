# CASCADE SENTINEL: Data Sources & Quality Registry

This document records the data provenance, licensing, spatial-temporal resolution, units, and known limitations for all datasets ingested by CASCADE SENTINEL for Pune district, Maharashtra.

---

## 1. Primary Ingested Datasets

### A. Pune IMD Gridded Rainfall
- **Filename:** `data/pune_imd_rainfall.csv`
- **Source:** India Meteorological Department (IMD) Gridded Rainfall Data
- **Download Date:** TO BE FILLED BY USER
- **License / Terms:** TO BE FILLED BY USER (Standard IMD Academic/Research License)
- **Spatial Coverage:** Pune District & surrounding Western Ghats grid bounding box ($18.0^\circ-19.0^\circ\text{N}$, $73.0^\circ-74.75^\circ\text{E}$)
- **Spatial Resolution:** $0.25^\circ \times 0.25^\circ$ (~27 km grid cells; 5 latitudes $\times$ 8 longitudes = 40 cells)
- **Temporal Resolution:** Daily ($08:30\text{ IST}$ observation window)
- **Temporal Span:** 2015-01-28 to 2025-12-31 ($3,991$ calendar days per cell; $159,640$ total rows)
- **Variables & Units:**
  - `date`: Calendar date (`YYYY-MM-DD`)
  - `latitude`: Cell center latitude ($^\circ\text{N}$)
  - `longitude`: Cell center longitude ($^\circ\text{E}$)
  - `rainfall_mm_per_day`: 24-hour accumulated rainfall ($\text{mm/day}$)
- **Quality Audit:**
  - Duplicate rows: $0$
  - Null / Missing values: $0$
  - Range: $0.0\text{ mm}$ to $465.6\text{ mm/day}$
  - Extreme values ($> 300\text{ mm/day}$): $16$ occurrences (all located at Ghats crest cells; tagged `FLAG_EXTREME_VERIFY` as *"extreme, plausible Western Ghats, verify"*; strictly preserved without clipping)
- **Known Limitations:**
  - 16 of the 40 cells lie outside Pune administrative boundaries (10 cells west of Ghats in Konkan; 6 cells south in Satara/Solapur).
  - IMD gridded products are derived from interpolated gauge networks, not direct station telemetry.
  - Typical operational reporting arrival lag is $T+1\text{ day}$ (modeled as user-editable assumption).

---

### B. Open-Meteo Pune Point Reanalysis
- **Filename:** `data/open-meteo-18_52N73_87E561m.csv`
- **Source:** Open-Meteo Historical Weather API / ERA5-Land Reanalysis
- **Download Date:** TO BE FILLED BY USER
- **License:** Open Database License (ODbL) / Copernicus Open Access
- **Spatial Location:** Point coordinate ($18.523726^\circ\text{N}$, $73.86876^\circ\text{E}$, elevation $561.0\text{ m}$ ASL, Pune city center)
- **Spatial Resolution:** Single-point model reanalysis grid (~9 km native ERA5-Land)
- **Temporal Resolution:** Hourly
- **Temporal Span:** 2015-06-01T00:00 to 2025-10-31T23:00 ($91,344$ hourly observations)
- **Variables & Units:**
  - `time`: Hourly timestamp (parsed as UTC, converted to IST $+05:30$)
  - `rain (mm)`: Hourly rainfall liquid water equivalent ($\text{mm/h}$)
  - `precipitation (mm)`: Total precipitation including hail/snow ($\text{mm/h}$)
  - `soil_moisture_0_to_7cm (m3/m3)`: Volumetric soil water content in rootzone topsoil ($\text{m}^3/\text{m}^3$)
- **Quality Audit:**
  - Header structure: 3 metadata lines before header (ingested with `skiprows=3`)
  - Timezone: UTC converted to IST on load ($+05:30$)
  - Missing Handling: January–May 2015 is unobserved. Strictly preserved as explicit `NaN` (`FLAG_MISSING`); never filled with zero.
- **Known Limitations:**
  - Gridded reanalysis model estimate, NOT a ground-based tipping bucket gauge.
  - Disagrees with IMD on daily aggregations (Pearson $r \approx 0.42$); treated as independent evidence stream with source-agreement indicator.

---

### C. NASA Global Landslide Catalog (GLC)
- **Filename:** `data/Global_Landslide_Catalog_Export_rows__3_.csv`
- **Source:** NASA Cooperative Open Online Landslide Repository (COOLR)
- **Download Date:** TO BE FILLED BY USER
- **License:** Open Access Public Domain (NASA Open Data)
- **Global Coverage:** 11,033 global events (1,265 events in India; 31 candidate events in Western Maharashtra)
- **Derived Product:** `data/derived/glc_pune_candidates.csv`
  - 3 confirmed Pune district events (Malin 2014, Karla 2015, Lavasa 2016)
  - 9 ambiguous border / crestline expressway tunnel events (Adoshi, Khandala, Monkey Hill)
  - 19 non-district events excluded (Mumbai, Thane, Karjat, Ratnagiri)
- **Known Limitations:**
  - Extreme reporting sparsity.
  - **CRITICAL MODELING RULE:** Used exclusively for historical sanity checks and weak spatial priors. Never used to train machine learning models.
  - Malin (2014-07-30) predates the rainfall record (2015-2025) and is displayed for context only.

---

### D. Open-Meteo Live Forecast API
- **Endpoint:** `https://api.open-meteo.com/v1/forecast`
- **Auth:** Free tier, no API key required
- **Parameters:** `latitude={lat}&longitude={lon}&hourly=rain,precipitation,soil_moisture_0_to_7cm&past_days=7&forecast_days=3&timezone=Asia%2FKolkata`
- **Caching:** Disk cache under `data/cache/{cell_id}_forecast.json` with file timestamp tracking.
- **Status Badges:**
  - `LIVE`: API network fetch succeeded.
  - `CACHED (<age>)`: Network unavailable; loaded from disk cache.
  - `OFFLINE-DEMO`: Network and cache unavailable; deterministic fallback template loaded. Safety guarantee: app never crashes on API failure.
