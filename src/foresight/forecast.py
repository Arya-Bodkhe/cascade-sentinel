"""Causal lag forecaster: next events with time windows, supports do(cut edge) interventions."""
import numpy as np
from src.common.model import KINDS, K, BASE, AMP, LAG, TAU, NT, descendants

CHAIN = ["drain", "traffic", "call", "hospital"]


def forecast(belief, t, rng, horizon=10.0, n=800, cut_edges=(), top=3):
    flat = belief.joint.ravel()
    idx = rng.choice(flat.size, size=n, p=flat / flat.sum())
    h, ti = np.divmod(idx, NT)
    tau = TAU[ti]
    amp = AMP.copy()
    for k in descendants(cut_edges):
        amp[:, KINDS.index(k)] = 0.0
    out = []
    for kind in CHAIN:
        k = KINDS.index(kind)
        a = amp[h, k]
        start = np.maximum(t, tau + LAG[k])
        arr = np.where(a > 0, start + rng.exponential(1.0 / np.maximum(a, 1e-9)), np.inf)
        ok = arr <= t + horizon
        p = float(ok.mean())
        if p < 0.02:
            continue
        lo, hi = np.percentile(arr[ok], [10, 90])
        out.append({"kind": kind, "p": p, "window": (float(lo), float(hi)),
                    "median": float(np.median(arr[ok]))})
    fut = [o for o in out if o["window"][0] > t + 0.2]       # events that have not started yet
    fut.sort(key=lambda o: -o["p"])
    return fut[:top]
