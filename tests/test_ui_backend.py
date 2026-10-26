"""Verification test for all UI helpers, presets, and simulation endpoints."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from src.sim.world import generate_episode, generate_twin
from src.belief.engine import Engine
from src.ledger.ledger import Ledger
from src.policy.policy import Policy, ACTIONS
from src.runtime import run_episode
from src.foresight.forecast import forecast
from app import PRESETS, replay_cached


def test_presets_execute_without_error():
    for name, p in PRESETS.items():
        ep, recs, entries, j_str, c_str, ok = replay_cached(
            p["seed"], p["fam"], p["truth"], tuple(p["stress"])
        )
        assert len(recs) == 14, f"Failed length on {name}"
        assert ok is True, f"Failed ledger verification on {name}"
        assert ep["hyp_name"] in ["NOISE", "SENSOR_FAIL", "ISOLATED", "CASCADE"]


def test_twin_replay_cached():
    twin_a = replay_cached(41, "A", "NOISE", (), which=0, twin=True)
    twin_b = replay_cached(41, "A", "CASCADE", (), which=1, twin=True)
    assert len(twin_a[1]) == 14
    assert len(twin_b[1]) == 14
    assert twin_a[0]["hyp_name"] == "NOISE"
    assert twin_b[0]["hyp_name"] == "CASCADE"


def test_twin_with_custom_hyp_and_stress():
    eng = Engine()
    for s in ["outage", "cutout", "lie", "rumor", "messy"]:
        tw = generate_twin(np.random.default_rng(10), pair=("NOISE", "SENSOR_FAIL"), stress=(s,))
        assert len(tw[0]["events"]) > 0
        assert len(tw[1]["events"]) > 0
        ra = run_episode(tw[0], eng, {"P": Policy()})
        rb = run_episode(tw[1], eng, {"P": Policy()})
        # After minute 7, Twin B should recognize SENSOR_FAIL
        assert rb[9]["p"][1] > ra[9]["p"][1]


def test_causal_interventions_in_ui():
    ep = generate_episode(np.random.default_rng(41), fam="A", hyp="CASCADE")
    eng = Engine()
    ev = eng.evidence(ep["events"], 9)
    b = eng.posterior(ev)
    fc_base = forecast(b, 9, np.random.default_rng(0), cut_edges=())
    fc_cut = forecast(b, 9, np.random.default_rng(0), cut_edges=(("drain", "traffic"),))
    hosp_base = next((f["p"] for f in fc_base if f["kind"] == "hospital"), 0.0)
    hosp_cut = next((f["p"] for f in fc_cut if f["kind"] == "hospital"), 0.0)
    assert hosp_cut <= hosp_base


if __name__ == "__main__":
    test_presets_execute_without_error()
    print("PASS test_presets_execute_without_error")
    test_twin_replay_cached()
    print("PASS test_twin_replay_cached")
    test_causal_interventions_in_ui()
    print("PASS test_causal_interventions_in_ui")
