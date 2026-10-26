"""Online replay loop shared by the UI, the evaluator and the tests."""
import numpy as np
from src.common.model import HYPS, KINDS, H_CAS
from src.foresight.forecast import forecast
from src.ledger.ledger import Ledger
from src.policy.policy import ACTIONS


def reverses_if(belief, fc, t):
    top = int(np.argmax(belief.p))
    if top == H_CAS:
        h = [f for f in fc if f["kind"] == "hospital"]
        when = f"{h[0]['window'][1]:.0f}" if h else f"{t + 4}"
        return f"no independent hospital-feed arrivals by minute {when}"
    if top == 1:
        return "sensor evidence from healthy gateways fails to continue, or physical channels (drain/traffic) rise"
    return "a downstream channel (traffic -> calls -> hospitals) starts rising in the expected lag window"


def run_episode(ep, engine, policies, T_run=14, seed=0, ledger=None, do_forecast=True, main=None):
    """Replay an episode minute by minute. `policies` is {name: Policy}. Returns per-minute records."""
    rng = np.random.default_rng(seed)
    main = main or next(iter(policies))
    recs, prev_c, prev_p, prev_lv = [], None, None, 0
    for t in range(1, T_run + 1):
        ev = engine.evidence(ep["events"], t)
        b = engine.posterior(ev)
        rec = {"t": t, "p": b.p.tolist(), "entropy": b.entropy, "coverage": ev.coverage,
               "quarantined": ev.n_quarantined, "n_down": ev.n_down, "raw_citizen": ev.raw_citizen,
               "eff_citizen": ev.eff_citizen, "n_origins": ev.n_origins, "levels": {}}
        for name, pol in policies.items():
            rec["levels"][name] = pol.step(t, b, ev, engine, rng)["level"]
        fc = forecast(b, t, rng) if do_forecast else []
        rec["forecast"] = fc
        if ledger is not None:
            lv = rec["levels"][main]
            top = int(np.argmax(b.p))
            alt = int(np.argsort(-b.p)[1]) if top == H_CAS else H_CAS
            c = engine.contributions(ev, top, alt)
            rec["contributions"] = c
            if prev_c is None or lv != prev_lv or (prev_p is not None and abs(b.p - prev_p).max() > 0.2):
                delta = c if prev_c is None else {k: c[k] - prev_c.get(k, 0.0) for k in c}
                notes = []
                if ev.n_down:
                    notes.append(f"{ev.n_down} gateway outage(s) counted once, not per sensor")
                if ev.raw_citizen > ev.eff_citizen + 1:
                    notes.append(f"{ev.raw_citizen} citizen reports counted as {ev.eff_citizen:.1f} effective "
                                 f"({ev.n_origins} origins)")
                ledger.add(t, prev_p if prev_p is not None else engine.prior, b.p, ACTIONS[prev_lv], ACTIONS[lv],
                           {f"{HYPS[top]} vs {HYPS[alt]}: {k}": v for k, v in delta.items()},
                           reverses_if(b, fc, t), ev.input_hash, notes)
            prev_c, prev_p, prev_lv = c, b.p.copy(), lv
        else:
            top = int(np.argmax(b.p))
            alt = int(np.argsort(-b.p)[1]) if top == H_CAS else H_CAS
            rec["contributions"] = engine.contributions(ev, top, alt)
        recs.append(rec)
    return recs
