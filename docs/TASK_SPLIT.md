# Task split for two people (24 hours)

**Person A = Systems & Product** (world, data plumbing, UI, demo)
**Person B = Inference & Evaluation** (belief, decisions, foresight, learning, numbers)

Rule that prevents merge conflicts: **each directory has exactly one owner.** Shared files change only through a small PR that the other person approves.

| Path | Owner | Notes |
|---|---|---|
| `src/sim/` (world, stressors, twins) | A | exposes `generate_episode`, `generate_twin` |
| `src/ingest/` (schema, quarantine, dedupe) | A | exposes `ingest(events, t)` |
| `src/ledger/` (hash chain, export) | A | exposes `Ledger` |
| `app.py`, `docs/`, `README.md`, demo script | A | |
| `tests/` for sim, ingest, ledger, fuzz | A | |
| `src/belief/` (grid filter, gateway, rumor, calibration) | B | exposes `Engine.evidence/posterior/lookahead/contributions` |
| `src/policy/` (costs, fatigue, stopping, hysteresis) | B | exposes `Policy.step`, `CostModel` |
| `src/foresight/` (lag graph, interventions) | B | exposes `forecast` |
| `src/learning/` (trust, BOCPD) | B | |
| `src/eval/` (baselines, metrics, plots) | B | exposes `python -m src.eval.run_eval` |
| `src/common/model.py` (shared constants) | **shared** | B edits, A reviews. Changing a constant changes sim AND filter. |
| `src/runtime.py` (replay loop) | **shared** | tiny PRs only |

## Interface contract (freeze in hours 0-2, change only via PR + both approve)

* Event = dict with `id, source, family, kind, event_time, received_at` (+ optional `zone, gateway, origin, ref`). Kinds: `drain, traffic, call, hospital, sensor, citizen` plus meta kinds `heartbeat, silence, retraction, rain`.
* `generate_episode(rng, fam, hyp, stress, T, regime, cut_edges) -> {"events", "hyp", "tau", "impact", ...}`
* `Engine.evidence(events, t) -> Evidence`; `Engine.posterior(ev) -> Belief(p[4], joint[4,NT], entropy)`
* `Policy.step(t, belief, ev, engine, rng) -> {"level": 0..3}`
* `run_episode(ep, engine, {name: Policy}, ledger=...) -> list of per-minute records`

## Hour-by-hour plan

| Hours | Person A | Person B | Sync point |
|---|---|---|---|
| 0-2 | Repo, CI, `bootstrap_git.sh`, event schema, interface contract | Read blueprint, confirm `common/model.py` constants and cost numbers | **S0** contract frozen, tag `v0.1` |
| 2-6 | Simulator: rain, chain, 6 sources, 4 hypotheses, outage / cutout / lie / rumor / messy stressors | Belief engine v1: grid filter, per-minute bins, priors | |
| 6-8 | Ingest: validation, quarantine, retractions, dedupe; shuffle tests | Engine meets simulator: first accuracy table | **S1 (h6-8)** merge to `develop`; engine runs on sim output |
| 8-12 | Twin generator, heartbeat feeds, ledger hash chain | Gateway node, rumor discount, physics penalty, temperature calibration | |
| 12-14 | Streamlit panels 1-2 (picture, timeline) | Policy: costs, fatigue, hysteresis, look-ahead stopping | **S2 (h12-14)** `run_episode` end-to-end |
| 14-18 | Panels 3-5, replay lab, twin mode, ledger view and export | Foresight, trust learning, BOCPD, baselines B0-B2 | |
| 18-20 | Fuzz suite, offline run check, dataset/licence notes | Full evaluation, ablations, plots | **S3 (h18-20)** numbers frozen |
| 20-22 | README, results tables into the demo, backup video | Fix calibration/threshold misses; write negative-results section | |
| 22-24 | Rehearse demo x3, final tag `v1.0` | Rehearse Q&A on method, equations, limitations | **S4** release |

## Cut line (if time slips, cut in this order)
VOI module -> map view -> BOCPD (use windowed prior reset) -> gradient-boosting baseline -> extra ablations.
**Never cut:** simulator, four-way posterior, twin test, decision policy with hysteresis, ledger.

## Demo roles
A drives the UI (twin mode, stress toggles, ledger). B narrates numbers (calibration, cost, flips) and answers method questions.
