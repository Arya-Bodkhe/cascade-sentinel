"""Shared, deterministic probability calibration for district rainfall summaries."""
from __future__ import annotations

import math

import numpy as np


def estimate_cascade_probability(
    district_max_3d_mm: float,
    district_max_1d_mm: float,
    max_landslide_trigger_index: float,
    confidence_penalty: float = 0.0,
) -> float:
    """Return the project's documented heuristic P(CASCADE), clamped to [0.02, 0.98].

    This is an engineering heuristic, not a calibrated forecast probability. Inputs are
    sanitized so missing/non-finite values never leak NaNs into the action policy or graph.
    """
    values = (district_max_3d_mm, district_max_1d_mm,
              max_landslide_trigger_index, confidence_penalty)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Risk inputs must be finite numbers")
    rain_3d = max(0.0, float(district_max_3d_mm))
    rain_1d = max(0.0, float(district_max_1d_mm))
    landslide = float(np.clip(max_landslide_trigger_index, 0.0, 1.0))
    penalty = float(np.clip(confidence_penalty, 0.0, 1.0))
    raw = 0.05 + 0.45 * (rain_3d / 200.0) + 0.35 * (rain_1d / 120.0) + 0.15 * landslide
    return float(np.clip(raw * (1.0 - penalty), 0.02, 0.98))
