import copy, random
import numpy as np
from src.sim.world import generate_episode, generate_twin
from src.belief.engine import Engine
from src.ingest.ingest import ingest
from src.ledger.ledger import Ledger
from src.learning.learning import BOCPD
from src.foresight.forecast import forecast
from src.policy.policy import Policy, flips
from src.runtime import run_episode

ENG = Engine()


def ep(seed=1, **kw):
    return generate_episode(np.random.default_rng(seed), T=16, **kw)


def test_ingest_quarantines_and_never_crashes():
    bad = [None, 5, {"id": 1}, {"id": "x", "source": "s", "family": "f", "kind": "drain",
                                "event_time": float("nan"), "received_at": 1.0},
           {"id": "y", "source": "s", "family": "drainage", "kind": "drain", "event_time": 5.0, "received_at": 1.0}]
    clean, q = ingest(bad, 10)
    assert clean == [] and len(q) == 5
    ENG.posterior(ENG.evidence(bad, 5))


def test_order_invariance():
    e = ep(3, hyp=3)["events"]
    base = ENG.posterior(ENG.evidence(e, 8)).p
    for s in range(5):
        sh = list(e); random.Random(s).shuffle(sh)
        assert np.allclose(base, ENG.posterior(ENG.evidence(sh, 8)).p, atol=1e-12)


def test_duplicates_and_retractions():
    e = ep(4, hyp=3)["events"]
    base = ENG.posterior(ENG.evidence(e, 8)).p
    dup = e + [dict(x) for x in e[:50]]
    assert np.allclose(base, ENG.posterior(ENG.evidence(dup, 8)).p)
    victim = next(x for x in e if x["kind"] == "call" and x["received_at"] < 6)
    retr = e + [{"id": "r1", "source": "s", "family": "dispatch", "kind": "retraction", "ref": victim["id"],
                 "event_time": 1.0, "received_at": 7.0}]
    clean, _ = ingest(retr, 8)
    assert victim["id"] not in {c["id"] for c in clean}


def test_twin_identical_until_split():
    a, b = generate_twin(np.random.default_rng(5))
    for t in range(1, 8):
        ia = {x["id"] for x in ingest(a["events"], t)[0]}; ib = {x["id"] for x in ingest(b["events"], t)[0]}
        if ia != ib:
            break
        assert np.allclose(ENG.posterior(ENG.evidence(a["events"], t)).p, ENG.posterior(ENG.evidence(b["events"], t)).p)


def test_gateway_outage_counts_once_and_does_not_raise_cascade():
    e = ep(6, hyp=0, stress=("outage",))
    ev = ENG.evidence(e["events"], 10)
    assert 1 <= ev.n_down <= 2
    assert ENG.posterior(ev).p[3] < 0.5


def test_rumor_wave_is_discounted_and_capped():
    e = ep(7, hyp=0, stress=("rumor",))
    ev = ENG.evidence(e["events"], 10)
    assert ev.raw_citizen >= 40 and ev.eff_citizen < ev.raw_citizen * 0.5
    assert ENG.posterior(ev).p[3] <= 0.35 + 1e-9


def test_cutout_widens_not_collapses():
    clean = ep(8, hyp=3)
    cut = ep(8, hyp=3, stress=("cutout",))
    ev = ENG.evidence(cut["events"], 10)
    assert ev.coverage < 1.0
    ENG.posterior(ev)


def test_ledger_hash_chain_and_tamper_detection():
    e = ep(9, hyp=3); L = Ledger(9)
    run_episode(e, ENG, {"p": Policy()}, ledger=L, do_forecast=True)
    assert len(L.entries) >= 1 and L.verify()
    tampered = copy.deepcopy(L.entries); tampered[0]["action_to"] = "WATCH-FAKE"
    assert not Ledger.verify_entries(tampered)


def test_hysteresis_reduces_flips():
    eps = [ep(100 + i) for i in range(25)]
    f_h = f_n = 0
    ph, pn = Policy(), Policy(hysteresis=False)
    for i, e in enumerate(eps):
        r = run_episode(e, ENG, {"h": ph, "n": pn}, seed=i, do_forecast=False)
        f_h += flips([x["levels"]["h"] for x in r]); f_n += flips([x["levels"]["n"] for x in r])
        ph.end_episode(e["hyp"] == 3); pn.end_episode(e["hyp"] == 3)
    assert f_h <= f_n


def test_causal_forecast_responds_to_intervention():
    e = ep(10, hyp=3)
    b = ENG.posterior(ENG.evidence(e["events"], 4))
    rng = np.random.default_rng(0)
    base = {f["kind"]: f["p"] for f in forecast(b, 4, rng)}
    cut = {f["kind"]: f["p"] for f in forecast(b, 4, np.random.default_rng(0), cut_edges=(("drain", "traffic"),))}
    assert cut.get("hospital", 0.0) < base.get("hospital", 1.0)


def test_bocpd_adapts():
    b = BOCPD()
    for _ in range(60): b.update(int(np.random.default_rng(0).random() < 0.15) * 0)
    low = b.predict()
    for _ in range(15): b.update(1)
    assert b.predict() > low + 0.2


def test_fuzz_random_garbage():
    rnd = random.Random(0)
    junk = [None, "x", 1.5, float("inf"), -3, [], {}, True]
    for _ in range(200):
        evs = [{k: rnd.choice(junk + [1.0, "drain", "a"]) for k in
                ("id", "source", "family", "kind", "event_time", "received_at", "zone", "gateway")} for _ in range(10)]
        ENG.posterior(ENG.evidence(evs, 5))
