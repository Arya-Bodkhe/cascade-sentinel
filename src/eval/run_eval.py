"""Full evaluation on simulated episodes with known ground truth.
Usage:  python -m src.eval.run_eval --quick     (about 1-3 min)
        python -m src.eval.run_eval --full      (2000/500/500 episodes)
All numbers are SIMULATED results; test episodes are never used for tuning or calibration."""
import argparse, json, os, time
import numpy as np
from sklearn.linear_model import LogisticRegression
from src.common.model import HYPS, KINDS, H_CAS, PRIORS
from src.belief.engine import Engine
from src.ingest.ingest import ingest
from src.sim.world import generate_episode, generate_twin, STRESSORS
from src.policy.policy import Policy, CostModel, flips
from src.foresight.forecast import forecast
from src.learning.learning import BOCPD, TrustLearner
from src.runtime import run_episode

TS = (3, 5, 7, 10)
T_RUN = 14


def boot_ci(x, n=1000, seed=0):
    x = np.asarray(x, float)
    if len(x) == 0:
        return (float("nan"),) * 3
    r = np.random.default_rng(seed)
    m = [r.choice(x, len(x)).mean() for _ in range(n)]
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def make_set(n, seed, **kw):
    rng = np.random.default_rng(seed)
    return [generate_episode(rng, T=T_RUN + 2, **kw) for _ in range(n)]


def series(engine, ep):
    return np.array([engine.posterior(engine.evidence(ep["events"], t)).p for t in range(1, T_RUN + 1)])


def onehot(y):
    z = np.zeros(4); z[y] = 1; return z


def brier4(P, Y): return float(np.mean(np.sum((P - Y) ** 2, axis=1)))
def logloss(P, Y): return float(-np.mean(np.sum(Y * np.log(np.clip(P, 1e-6, 1)), axis=1)))


def ece(p, y, bins=10):
    p, y = np.asarray(p), np.asarray(y)
    edges = np.linspace(0, 1, bins + 1); tot = 0.0
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= 1)
        if m.any():
            tot += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(tot)


def feats(ep, t):
    clean, _ = ingest(ep["events"], t)
    cnt = [sum(1 for e in clean if e["kind"] == k and e["event_time"] >= t - 5) for k in KINDS]
    return cnt + [sum(1 for e in clean if e["kind"] == "silence"), t]


def fit_temperature(engine, val):
    S = [(series(engine, ep), ep["hyp"]) for ep in val]
    best, bt = 1e9, 1.0
    for T in np.arange(0.6, 3.01, 0.1):
        e2 = Engine(temperature=T)
        ll = 0
        for ep, (_, y) in zip(val, S):
            for t in TS:
                p = e2.posterior(e2.evidence(ep["events"], t)).p
                ll += -np.log(max(p[y], 1e-6))
        if ll < best:
            best, bt = ll, float(T)
    return bt


def fixed_levels(pcas, theta):
    return [2 if p >= theta else 0 for p in pcas]


def world_cost(cm, eps, levels_by_ep, fatigue=True):
    f, costs = 0.0, []
    for ep, lv in zip(eps, levels_by_ep):
        costs.append(cm.episode_cost(ep["hyp"] == H_CAS, lv, list(range(1, T_RUN + 1)), ep["impact"], f))
        if fatigue and max(lv) >= 2 and ep["hyp"] != H_CAS:
            f = min(1.0, f + 0.25)
        f *= 0.9
    return costs


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true"); g.add_argument("--full", action="store_true")
    ap.add_argument("--seed", type=int, default=41); ap.add_argument("--out", default="reports")
    a = ap.parse_args()
    ntr, nva, nte = (2000, 500, 500) if a.full else (300, 150, 200)
    os.makedirs(a.out, exist_ok=True); t_start = time.time()
    R = {"sizes": {"train": ntr, "val": nva, "test": nte}, "seed": a.seed, "note": "SIMULATED results"}
    train = make_set(ntr, a.seed, fam="A"); val = make_set(nva, a.seed + 1, fam="A")
    tests = {"A": make_set(nte, a.seed + 2, fam="A"), "B(held-out)": make_set(nte, a.seed + 3, fam="B"),
             "C(held-out)": make_set(nte, a.seed + 4, fam="C")}

    # ---- calibration (fit on validation only)
    T_cal = fit_temperature(Engine(), val[:80]); R["temperature"] = T_cal
    S, B1 = Engine(temperature=T_cal), Engine(gateway=False, rumor=False, physics=False, heartbeat=False)
    S_uncal = Engine()
    X = [feats(ep, t) for ep in train for t in range(1, T_RUN + 1)]
    Y = [ep["hyp"] for ep in train for t in range(1, T_RUN + 1)]
    B2 = LogisticRegression(max_iter=2000, C=1.0).fit(X, Y)
    Xv = [feats(ep, t)[:4] + [0] for ep in val for t in TS]
    b0_score = lambda ep, t: sum(feats(ep, t)[:4])
    B0 = LogisticRegression().fit([[b0_score(ep, t)] for ep in val for t in TS],
                                  [int(ep["hyp"] == H_CAS) for ep in val for t in TS])

    def b2_p(ep, t):
        p = np.zeros(4); p[B2.classes_] = B2.predict_proba([feats(ep, t)])[0]; return p

    # ---- honest probabilities
    R["calibration"] = {}
    for fname, eps in tests.items():
        yh = np.array([ep["hyp"] for ep in eps]); Y4 = np.array([onehot(y) for y in yh])
        res = {}
        for t in TS:
            P = {"SENTINEL": np.array([S.posterior(S.evidence(ep["events"], t)).p for ep in eps]),
                 "SENTINEL-uncalibrated": np.array([S_uncal.posterior(S_uncal.evidence(ep["events"], t)).p for ep in eps]),
                 "B1-naive-bayes": np.array([B1.posterior(B1.evidence(ep["events"], t)).p for ep in eps]),
                 "B2-logreg": np.array([b2_p(ep, t) for ep in eps])}
            pb0 = B0.predict_proba([[b0_score(ep, t)] for ep in eps])[:, 1]
            for m, Pm in P.items():
                res[f"{m}@T+{t}"] = {"brier4": brier4(Pm, Y4), "logloss": logloss(Pm, Y4),
                                     "ece_per_hyp": {HYPS[h]: ece(Pm[:, h], Y4[:, h]) for h in range(4)},
                                     "brier_cascade": float(np.mean((Pm[:, 3] - Y4[:, 3]) ** 2))}
            res[f"B0-threshold@T+{t}"] = {"brier_cascade": float(np.mean((pb0 - Y4[:, 3]) ** 2)),
                                          "ece_cascade": ece(pb0, Y4[:, 3])}
            if fname == "A" and t == 7:
                R["_rel"] = {"S": P["SENTINEL"][:, 3].tolist(), "B1": P["B1-naive-bayes"][:, 3].tolist(), "y": Y4[:, 3].tolist()}
        R["calibration"][fname] = res

    # ---- policy / cost / stability on test family A and held-out B
    R["policy"] = {}
    cm = CostModel()
    for fname in ("A", "B(held-out)"):
        eps = tests[fname]
        sp = {"SENTINEL": Policy(name="SENTINEL"), "-hysteresis": Policy(hysteresis=False, name="-hyst"),
              "-fatigue": Policy(fatigue=False, name="-fatigue"), "-lookahead": Policy(lookahead=False, name="-look")}
        lv = {k: [] for k in sp}; pc = []
        for i, ep in enumerate(eps):
            recs = run_episode(ep, S, sp, T_run=T_RUN, seed=i, do_forecast=False)
            for k in sp:
                lv[k].append([r["levels"][k] for r in recs])
            pc.append([r["p"][3] for r in recs])
            for k, p in sp.items():
                p.end_episode(ep["hyp"] == H_CAS)
        # fixed thresholds tuned on validation (SENTINEL probabilities and B1 probabilities)
        vp = [series(S, ep)[:, 3] for ep in val]; vb = [series(B1, ep)[:, 3] for ep in val]
        bp = [series(B1, ep)[:, 3] for ep in eps]
        grid = np.arange(0.1, 0.96, 0.05)
        def best_theta(vser):
            costs = [np.mean(world_cost(cm, val, [fixed_levels(s, th) for s in vser])) for th in grid]
            return float(grid[int(np.argmin(costs))]), costs
        th_s, cs_curve = best_theta(vp); th_b, _ = best_theta(vb)
        curve = [float(np.mean(world_cost(cm, eps, [fixed_levels(s, th) for s in pc]))) for th in grid]
        out = {}
        for k in sp:
            c = world_cost(cm, eps, lv[k], fatigue=True)
            out[k] = {"cost": boot_ci(c), "flips_per_episode": boot_ci([flips(l) for l in lv[k]]),
                      "false_alert_rate": float(np.mean([max(l) >= 2 for l, ep in zip(lv[k], eps) if ep["hyp"] != H_CAS]))}
        for name, lev in (("fixed-threshold(SENTINEL probs)", [fixed_levels(s, th_s) for s in pc]),
                          ("fixed-threshold(B1 probs)", [fixed_levels(s, th_b) for s in bp])):
            c = world_cost(cm, eps, lev)
            out[name] = {"cost": boot_ci(c), "flips_per_episode": boot_ci([flips(l) for l in lev]),
                         "theta": th_s if "SENT" in name else th_b,
                         "false_alert_rate": float(np.mean([max(l) >= 2 for l, ep in zip(lev, eps) if ep["hyp"] != H_CAS]))}
        out["cost_vs_threshold"] = {"theta": grid.tolist(), "cost": curve}
        R["policy"][fname] = out

    # ---- twin test
    tw = []
    rng = np.random.default_rng(a.seed + 9)
    npairs = 200 if a.full else 60
    for _ in range(npairs):
        A_, B_ = generate_twin(rng)
        gaps, pen, ids_ = [], [], None
        first_diff = None
        pa = [S.posterior(S.evidence(A_["events"], t)) for t in range(1, 17)]
        pb = [S.posterior(S.evidence(B_["events"], t)) for t in range(1, 17)]
        for t in range(1, 17):
            ia = {e["id"] for e in ingest(A_["events"], t)[0]}; ib = {e["id"] for e in ingest(B_["events"], t)[0]}
            if ia != ib and first_diff is None:
                first_diff = t
            if first_diff is None:
                gaps.append(float(np.abs(pa[t - 1].p - pb[t - 1].p).sum()))
                pen.append(max(0.0, max(pa[t - 1].p[0], pa[t - 1].p[3]) - 0.8))
        commit = next((t for t in range(1, 17) if pb[t - 1].p[3] >= 0.7), None)
        tw.append({"gap": max(gaps) if gaps else 0.0, "pen": float(np.mean(pen)) if pen else 0.0,
                   "first_diff": first_diff, "ttc": (commit - first_diff) if (commit and first_diff) else None})
    R["twin"] = {"pairs": npairs, "max_pre_split_L1_gap": float(max(x["gap"] for x in tw)),
                 "confident_wrong_penalty": float(np.mean([x["pen"] for x in tw])),
                 "median_minutes_to_commit_after_first_diff": float(np.median([x["ttc"] for x in tw if x["ttc"] is not None])),
                 "never_committed": int(sum(x["ttc"] is None for x in tw))}

    # ---- foresight
    rng = np.random.default_rng(a.seed + 11)
    cas = [ep for ep in tests["A"] if ep["hyp"] == H_CAS]
    hits = cov = tot = n_in = 0
    for ep in cas:
        t = 5; b = S.posterior(S.evidence(ep["events"], t))
        for f in forecast(b, t, rng):
            tot += 1
            act = [e["event_time"] for e in ep["events"] if e["kind"] == f["kind"] and e.get("inc") and e["event_time"] > t]
            if act and min(act) <= t + 10:
                hits += 1; n_in += 1
                cov += f["window"][0] <= min(act) <= f["window"][1]
    cut = (("drain", "traffic"),)
    rng2 = np.random.default_rng(a.seed + 12); causal, corr, actual = [], [], []
    lr_c = LogisticRegression().fit(
        [[feats(ep, 5)[0]] for ep in train], [int(any(e["kind"] == "hospital" and e.get("inc") for e in ep["events"])) for ep in train])
    for _ in range(60):
        ep = generate_episode(rng2, hyp=3, cut_edges=cut, T=T_RUN + 2)
        b = S.posterior(S.evidence(ep["events"], 5))
        f_c = {f["kind"]: f["p"] for f in forecast(b, 5, rng2, cut_edges=cut)}
        causal.append(f_c.get("hospital", 0.0)); corr.append(float(lr_c.predict_proba([[feats(ep, 5)[0]]])[0, 1]))
        actual.append(float(any(e["kind"] == "hospital" and e.get("inc") for e in ep["events"])))
    R["foresight"] = {"items": tot, "event_hit_rate": hits / max(tot, 1),
                      "window_coverage_nominal_80": cov / max(n_in, 1),
                      "intervention_mean_P_hospital": {"causal_do(cut)": float(np.mean(causal)),
                                                       "correlational_baseline": float(np.mean(corr)),
                                                       "actual_rate": float(np.mean(actual))}}

    # ---- prior-shift learning
    rng = np.random.default_rng(a.seed + 13); bo = BOCPD(); est, truth_p = [], []
    adaptive_ll, frozen_ll = [], []
    for i in range(100):
        reg = "normal" if i < 60 else "monsoon"
        ep = generate_episode(rng, regime=reg, T=T_RUN + 2)
        ad = Engine(temperature=T_cal, prior=bo.prior_vector(PRIORS["normal"])); fr = Engine(temperature=T_cal)
        pa = ad.posterior(ad.evidence(ep["events"], 5)).p; pf = fr.posterior(fr.evidence(ep["events"], 5)).p
        adaptive_ll.append(-np.log(max(pa[ep["hyp"]], 1e-6))); frozen_ll.append(-np.log(max(pf[ep["hyp"]], 1e-6)))
        final = int(np.argmax(ad.posterior(ad.evidence(ep["events"], T_RUN)).p))     # label-free consensus
        bo.update(int(final == H_CAS)); est.append(bo.predict()); truth_p.append(PRIORS[reg][3])
    ok = [abs(e - 0.45) <= 0.10 for e in est[60:]]
    rec = next((i + 1 for i in range(len(ok) - 2) if all(ok[i:i + 3])), None)
    R["prior_shift"] = {"shift_at_episode": 60, "episodes_to_recover_BOCPD": rec,
                        "frozen_prior_estimate_error_after_shift": abs(PRIORS["normal"][3] - 0.45),
                        "mean_logloss_after_shift": {"adaptive": float(np.mean(adaptive_ll[60:])), "frozen": float(np.mean(frozen_ll[60:]))},
                        "estimate_curve": est}

    # ---- robustness under stressors (family A, SENTINEL policy)
    R["robustness"] = {}
    for st in [()] + [(s,) for s in STRESSORS]:
        eps = make_set(80, a.seed + 21, fam="A", stress=st)
        sp = {"SENTINEL": Policy()}; lv, ent, pcs = [], [], []
        for i, ep in enumerate(eps):
            recs = run_episode(ep, S, sp, T_run=T_RUN, seed=i, do_forecast=False)
            lv.append([r["levels"]["SENTINEL"] for r in recs]); ent.append(recs[-1]["entropy"]); pcs.append(recs[6]["p"][3])
            sp["SENTINEL"].end_episode(ep["hyp"] == H_CAS)
        c = world_cost(cm, eps, lv)
        R["robustness"]["+".join(st) or "clean"] = {
            "mean_cost": float(np.mean(c)), "false_alert_rate": float(np.mean([max(l) >= 2 for l, ep in zip(lv, eps) if ep["hyp"] != H_CAS])),
            "brier_cascade@T+7": float(np.mean([(p - (ep["hyp"] == H_CAS)) ** 2 for p, ep in zip(pcs, eps)])), "crashes": 0}
    R["runtime_seconds"] = time.time() - t_start
    json.dump({k: v for k, v in R.items() if k != "_rel"}, open(os.path.join(a.out, "results.json"), "w"), indent=2)
    write_report(R, a.out)
    print(open(os.path.join(a.out, "RESULTS.md")).read())


def write_report(R, out):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    L = [f"# Results (SIMULATED episodes, seed {R['seed']}, sizes {R['sizes']})", "",
         "Targets in the blueprint are goals; the numbers below are what this run measured, including misses.", ""]
    L += ["## 1. Honest probabilities (CASCADE, Brier lower=better; ECE per hypothesis for SENTINEL)", "",
          "| family | method | T+3 | T+5 | T+7 | T+10 |", "|---|---|---|---|---|---|"]
    for fam, res in R["calibration"].items():
        for m in ("SENTINEL", "SENTINEL-uncalibrated", "B1-naive-bayes", "B2-logreg", "B0-threshold"):
            L.append(f"| {fam} | {m} | " + " | ".join(f"{res[f'{m}@T+{t}']['brier_cascade']:.3f}" for t in TS) + " |")
    L += ["", "SENTINEL 4-way log-loss / mean ECE over hypotheses:", "", "| family | T+3 | T+5 | T+7 | T+10 |", "|---|---|---|---|---|"]
    for fam, res in R["calibration"].items():
        L.append(f"| {fam} | " + " | ".join(f"{res[f'SENTINEL@T+{t}']['logloss']:.2f} / {np.mean(list(res[f'SENTINEL@T+{t}']['ece_per_hyp'].values())):.3f}" for t in TS) + " |")
    L += ["", "## 2. Decision policy (total expected cost, lower=better; mean [95% bootstrap CI])", "",
          "| family | policy | cost | flips/episode | false-ALERT rate |", "|---|---|---|---|---|"]
    for fam, pol_out in R["policy"].items():
        for k, v in pol_out.items():
            if k == "cost_vs_threshold": continue
            c, f = v["cost"], v["flips_per_episode"]
            L.append(f"| {fam} | {k} | {c[0]:.1f} [{c[1]:.1f}, {c[2]:.1f}] | {f[0]:.2f} | {v['false_alert_rate']:.2f} |")
    L += ["", "## 3. Twin test", "", "```", json.dumps(R["twin"], indent=2), "```", "",
          "## 4. Foresight", "", "```", json.dumps(R["foresight"], indent=2), "```", "",
          "## 5. Prior shift", "", "```", json.dumps({k: v for k, v in R["prior_shift"].items() if k != "estimate_curve"}, indent=2), "```", "",
          "## 6. Robustness", "", "| stressor | mean cost | false-ALERT rate | Brier(CASCADE)@T+7 | crashes |", "|---|---|---|---|---|"]
    for k, v in R["robustness"].items():
        L.append(f"| {k} | {v['mean_cost']:.1f} | {v['false_alert_rate']:.2f} | {v['brier_cascade@T+7']:.3f} | {v['crashes']} |")
    open(os.path.join(out, "RESULTS.md"), "w").write("\n".join(L))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    rel = R["_rel"]; y = np.array(rel["y"])
    for name, key in (("SENTINEL", "S"), ("B1 naive Bayes", "B1")):
        p = np.array(rel[key]); bins = np.linspace(0, 1, 6); xs, ys = [], []
        for i in range(5):
            m = (p >= bins[i]) & (p <= bins[i + 1])
            if m.sum() >= 3: xs.append(p[m].mean()); ys.append(y[m].mean())
        ax[0].plot(xs, ys, "o-", label=name)
    ax[0].plot([0, 1], [0, 1], "k--"); ax[0].set_title("Reliability: P(CASCADE) at T+7"); ax[0].legend()
    cv = R["policy"]["A"]["cost_vs_threshold"]; ax[1].plot(cv["theta"], cv["cost"], label="fixed threshold")
    ax[1].axhline(R["policy"]["A"]["SENTINEL"]["cost"][0], color="r", label="SENTINEL policy"); ax[1].set_title("Cost vs threshold (family A)"); ax[1].legend()
    ax[2].plot(R["prior_shift"]["estimate_curve"]); ax[2].axvline(60, color="k", ls=":"); ax[2].axhline(0.45, color="g", ls="--")
    ax[2].axhline(0.15, color="r", ls="--"); ax[2].set_title("BOCPD estimate of P(CASCADE); frozen prior=0.15")
    plt.tight_layout(); plt.savefig(os.path.join(out, "plots.png"), dpi=110)


if __name__ == "__main__":
    main()
