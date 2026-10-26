"""Causal world simulator with hidden ground truth, stressors and twin pairs.

Scenario families: "A" nominal (what the filter assumes), "B" slower/weaker chain
(lags +1, amplitudes x0.8), "C" faster/stronger chain (lags -0.5, amplitudes x1.2).
B and C are used as HELD-OUT, mis-specified test families.
"""
import copy
import numpy as np
from src.common.model import (HYPS, KINDS, FAMILY, FAMILIES, DELAY, BASE, AMP, LAG, PRIORS,
                              IMPACT_LAG, N_GATEWAYS, SENSORS_PER_GW, EDGES, KIDX, descendants)

STRESSORS = ["outage", "cutout", "lie", "rumor", "messy"]
POOL = {"drainage": 12, "camera": 25, "dispatch": 10, "hospital": 8, "gateway": 120, "social": 5000}


def family_params(fam):
    amp, lag = AMP.copy(), LAG.copy()
    if fam == "B":
        amp *= 0.8; lag = lag + np.where(lag > 0, 1.0, 0.0)
    elif fam == "C":
        amp *= 1.2; lag = np.maximum(lag - np.where(lag > 0, 0.5, 0.0), 0.0)
    return amp, lag


class _Ctx:
    def __init__(self, rng, fam="A", cut_edges=()):
        self.rng, self.n = rng, 0
        self.amp, self.lag = family_params(fam)
        for k in descendants(cut_edges):
            self.amp[:, KIDX[k]] = 0.0

    def mk(self, kind, t, inc=False, **extra):
        r = self.rng
        fam = FAMILY[kind]
        self.n += 1
        e = {"id": f"e{self.n}", "source": f"{fam}-{int(r.integers(0, POOL[fam]))}", "family": fam,
             "kind": kind, "event_time": float(t),
             "received_at": float(t + r.uniform(0, DELAY[fam])), "zone": f"z{int(r.integers(0, 8))}",
             "inc": bool(inc)}
        if kind == "sensor":
            e["gateway"] = f"g{int(r.integers(0, N_GATEWAYS))}"
        if kind == "citizen":
            e["origin"] = f"o{int(r.integers(0, 10**7))}"
        e.update(extra)
        return e


def emit_process(ctx, h, tau, t0, t1, outage_gateways=None):
    """Events in [t0, t1) from hypothesis h with onset tau (point-process, per-minute steps)."""
    ev = []
    r = ctx.rng
    for m in range(int(np.floor(t0)), int(np.ceil(t1))):
        a, b = max(m, t0), min(m + 1, t1)
        L = b - a
        if L <= 0:
            continue
        for k, kind in enumerate(KINDS):
            for rate, inc in ((BASE[k], False), (ctx.amp[h, k] * float((m + 0.5 - tau) >= ctx.lag[k]), True)):
                for _ in range(r.poisson(rate * L)):
                    ev.append(ctx.mk(kind, r.uniform(a, b), inc=inc))
        ev.append(_rain(ctx, r.uniform(a, b)))
    return ev


def _rain(ctx, t):
    ctx.n += 1
    return {"id": f"e{ctx.n}", "source": "imd-0", "family": "rain", "kind": "rain",
            "event_time": float(t), "received_at": float(t + 0.1), "zone": "city", "inc": False}


def _heartbeats(ctx, T):
    out = []
    for f in FAMILIES:
        for m in range(T):
            out.append({"id": f"hb-{f}-{m}", "source": f, "family": f, "kind": "heartbeat",
                        "event_time": float(m + 1), "received_at": float(m + 1 + DELAY[f] + 0.01)})
    return out


def _outage(ctx, gws, o1, T):
    """Gateway outage from o1: one silence summary / min / gateway + stuck sensor values."""
    out = []
    r = ctx.rng
    for g in gws:
        for m in range(int(np.ceil(o1)), T):
            t = max(o1, m) + 0.2
            out.append({"id": f"sil-{g}-{m}", "source": g, "family": "gateway", "kind": "silence",
                        "event_time": float(t), "received_at": float(t + 0.2), "gateway": g,
                        "n_silent": SENSORS_PER_GW})
            for _ in range(r.poisson(3.0)):
                e = ctx.mk("sensor", t + r.uniform(0, 0.7)); e["gateway"] = g; e["stuck"] = True
                out.append(e)
    return out


def _apply_stress(ctx, ev, stress, truth_h, tau, T):
    r = ctx.rng
    if "outage" in stress:
        gws = [f"g{i}" for i in r.choice(N_GATEWAYS, size=int(r.integers(1, 3)), replace=False)]
        ev += _outage(ctx, gws, 3.0 + r.uniform(0, 1), T)
    if "rumor" in stress:                                   # 47 reports, 3 origins, no physical corroboration
        origins = [f"rumor{i}" for i in range(3)]
        for i in range(47):
            t = r.uniform(4, 8)
            e = ctx.mk("citizen", t, rumor=True); e["origin"] = origins[i % 3]; e["zone"] = f"z{1 + (i % 2)}"
            ev.append(e)
    if "lie" in stress and truth_h != 3:                    # coordinated hospital surge that violates physics lags
        for i in range(8):
            t = 4.0 + 0.6 * i
            e = ctx.mk("hospital", t, lie=True); e["source"] = f"hospital-{90 + i % 3}"
            ev.append(e)
    if "cutout" in stress:                                  # all cameras vanish at t=5
        ev[:] = [e for e in ev if not (e["family"] == "camera" and e["event_time"] >= 5.0)]
    return ev


def _messy(ctx, ev):
    r = ctx.rng
    extra = []
    for e in ev:
        if e["kind"] in KINDS and r.random() < 0.10:        # retraction
            extra.append({"id": f"rt-{e['id']}", "source": e["source"], "family": e["family"],
                          "kind": "retraction", "ref": e["id"], "event_time": e["event_time"] + 0.1,
                          "received_at": e["received_at"] + r.uniform(0.5, 2.0)})
        if r.random() < 0.10:                               # replayed duplicate (same id)
            d = dict(e); d["received_at"] = e["received_at"] + r.uniform(0.3, 2.0); extra.append(d)
    ev = ev + extra
    r.shuffle(ev)
    return ev


def generate_episode(rng, fam="A", hyp=None, stress=(), T=16, regime="normal", cut_edges=(), prior=None):
    p = np.array(prior if prior is not None else PRIORS[regime], float)
    if hyp is None or hyp == "random":
        h = int(rng.choice(4, p=p / p.sum()))
    elif isinstance(hyp, str):
        h = HYPS.index(hyp) if hyp in HYPS else int(hyp)
    else:
        h = int(hyp)
    tau = float(rng.uniform(1, 6))
    ctx = _Ctx(rng, fam, cut_edges)
    ev = emit_process(ctx, h, tau, 0.0, T)
    if h == 1 and rng.random() < 0.8:                       # sensor-failure episodes usually have a gateway outage
        gws = [f"g{i}" for i in rng.choice(N_GATEWAYS, size=int(rng.integers(1, 3)), replace=False)]
        ev += _outage(ctx, gws, tau + rng.uniform(0, 1), T)
    ev = _apply_stress(ctx, ev, set(stress), h, tau, T)
    ev += _heartbeats(ctx, T)
    if "cutout" in stress:
        ev = [e for e in ev if not (e["kind"] == "heartbeat" and e["family"] == "camera" and e["event_time"] > 5.0)]
    if "messy" in stress:
        ev = _messy(ctx, ev)
    return {"events": ev, "hyp": h, "hyp_name": HYPS[h], "tau": tau,
            "impact": tau + IMPACT_LAG if h == 3 else None, "family": fam, "stress": sorted(stress),
            "T": T, "regime": regime}


def generate_twin(rng, split=7.0, pair=("NOISE", "CASCADE"), fam="A", stress=(), T=20, cut_edges=()):
    """Two episodes whose events are IDENTICAL before `split`, then branch (e.g. NOISE vs CASCADE)."""
    ctx = _Ctx(rng, fam, cut_edges=cut_edges)
    prefix = emit_process(ctx, 0, 2.0, 0.0, split)
    beats = _heartbeats(ctx, T)
    onset = split + float(rng.uniform(0, 0.8))
    twins = []
    for name in pair:
        h = HYPS.index(name) if isinstance(name, str) else int(name)
        h_name = HYPS[h]
        c2 = copy.copy(ctx)
        c2.rng = np.random.default_rng(int(rng.integers(1 << 31)))
        post = emit_process(c2, h if h != 0 else 0, onset if h != 0 else 2.0, split, T)
        ev = copy.deepcopy(prefix) + copy.deepcopy(beats) + post
        if h == 1 and c2.rng.random() < 0.8:
            gws = [f"g{i}" for i in c2.rng.choice(N_GATEWAYS, size=int(c2.rng.integers(1, 3)), replace=False)]
            ev += _outage(c2, gws, onset + c2.rng.uniform(0, 1), T)
        if stress:
            ev = _apply_stress(c2, ev, set(stress), h, onset, T)
            if "cutout" in stress:
                ev = [e for e in ev if not (e["kind"] == "heartbeat" and e["family"] == "camera" and e["event_time"] > 5.0)]
            if "messy" in stress:
                ev = _messy(c2, ev)
        twins.append({"events": ev, "hyp": h,
                      "hyp_name": h_name, "tau": onset, "impact": onset + IMPACT_LAG if h == 3 else None,
                      "family": fam, "stress": sorted(stress), "T": T, "regime": "normal", "split": split})
    return twins
