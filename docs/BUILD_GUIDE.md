# CASCADE SENTINEL - step-by-step build guide

Audience: two people, 24 hours, offline, Rs 0 software spend. See `TASK_SPLIT.md` for who does what and `GIT_WORKFLOW.md` for branching.
This repo already contains a working reference implementation of every module. You can (a) follow the steps below and rebuild each module yourselves using the file as the answer key, or (b) run it as-is and spend the time improving the numbers. Either way, every step has an acceptance test.

## Step 0 - Environment (both, 20 min)
```bash
git clone <URL> && cd cascade-sentinel && git switch develop
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tests/run_tests.py                                  # expect 12 PASS
```
Offline note: pip-install everything once while you have network, then the project runs with the network off.

## Step 1 - Freeze the contract (A+B, hours 0-2)
Files: `src/common/model.py`, event schema in `src/ingest/ingest.py`.
1. Agree the 4 hypotheses, 6 event kinds, rates (`BASE`, `AMP`, `LAG`), onset grid, impact lag.
2. Write the event schema (`id, source, family, kind, event_time, received_at`).
3. Commit and tag: `git tag -a v0.1 -m "contract frozen"`.
Accept when: both can import `src.common.model` and run `tests/run_tests.py`.

## Step 2 - Simulator with hidden truth (A, hours 2-6) - `src/sim/world.py`
1. Poisson event streams per minute: `rate = BASE + AMP[h] * 1[minute+0.5-onset >= LAG]`; events flagged `inc=True` when they come from the incident part (used only for scoring foresight).
2. Six source families with delays; one heartbeat per family per minute (lets the engine tell "silent" from "dead").
3. Gateway outage (one `silence` summary per gateway per minute + stuck sensor values).
4. Stressors: `outage, cutout, lie, rumor, messy` (retractions, duplicates, shuffled arrival).
5. Scenario families A (nominal), B (slower, weaker), C (faster, stronger). Held-out families B/C are what the filter has NOT been tuned to.
6. `generate_twin`: shared 7-minute prefix, then branch.
Accept when: 100 episodes generate; twin prefixes are byte-identical (`tests/test_core.py::test_twin_identical_until_split`).

## Step 3 - Ingest and quarantine (A, hours 6-8) - `src/ingest/ingest.py`
Validate schema, drop not-yet-arrived events, apply retractions, dedupe by id then by `(source, kind, zone, 2-min bucket)`, sort deterministically. Malformed/future-dated events go to a quarantine list with a reason.
Accept when: shuffle, duplicate, retraction and fuzz tests pass.

## Step 4 - Belief engine (B, hours 2-12) - `src/belief/engine.py`
1. Bin events per minute and kind into weighted counts `N[k, m]`; validity mask `V[k, m]` from heartbeats (missing-not-at-random: a dead feed is masked, never counted as "nothing happened").
2. Log-likelihood over the `(H, onset)` grid: `sum V * (N * log(lam) - lam)`. Normalise, marginalise to four probabilities.
3. Gateway node: silent gateway counted once, stuck values excluded, outage term favours SENSOR_FAIL.
4. Rumor discount: cluster citizen reports by `(zone, 3-min bucket)`, weight `trust * log2(1 + origins)`; cap CASCADE until physical channels agree.
5. Physics-consistency penalty: hospital reports without upstream drain/traffic/call activity get weight x0.15.
6. Temperature calibration fitted on validation episodes only.
Accept when: `test_order_invariance`, gateway, rumor and cutout tests pass; accuracy rises with time (see RESULTS).

## Step 5 - Decision policy (B, hours 12-14) - `src/policy/policy.py`
Expected loss per action from `P(CASCADE)`, lead time and fatigue. Optimal-stopping look-ahead (`Engine.lookahead`) decides whether waiting is worth it. Hysteresis = switching cost + minimum dwell + k consecutive minutes below threshold before stepping down. Fatigue rises after each false ALERT/ESCALATE and decays between episodes.
Accept when: `test_hysteresis_reduces_flips` passes; flips per episode well below the no-hysteresis ablation.

## Step 6 - Ledger (A, hours 8-12) - `src/ledger/ledger.py`
Entry = minute, before/after probabilities, action change, ranked per-kind log-likelihood-ratio contributions, notes (gateway, rumor), "reverses if", input hash, previous hash, own hash.
Accept when: chain verifies; editing any field breaks verification (`test_ledger_hash_chain_and_tamper_detection`).

## Step 7 - Foresight (B, hours 14-16) - `src/foresight/forecast.py`
Sample `(H, onset)` from the posterior; per downstream kind draw first incident-event time after `max(now, onset + lag)`; report probability and 10th-90th percentile window. `cut_edges` implements do(cut): descendants lose their cause.
Accept when: `test_causal_forecast_responds_to_intervention` passes.

## Step 8 - Learning (B, hours 14-16) - `src/learning/learning.py`
`TrustLearner`: Beta reliability per source family with forgetting. `BOCPD`: Beta-Bernoulli change-point detector over episode outcomes; rescales the prior of CASCADE after a silent regime change.

## Step 9 - UI (React + FastAPI)
```bash
python run.py
```
Open `http://127.0.0.1:8000`. The production React bundle is included in `frontend/dist`; run `npm ci && npm run build` only when changing the frontend.

## Step 10 - Evaluation (B, hours 16-20)
```bash
python -m src.eval.run_eval --quick     # minutes
python -m src.eval.run_eval --full      # 2000/500/500 episodes; run it once, overnight or at hour 16
```
Outputs `reports/results.json`, `reports/RESULTS.md`, `reports/plots.png`. Never tune on test episodes. Publish misses as negative results.

## Step 11 - Hardening and release (both, hours 20-24)
```bash
python tests/run_tests.py && pytest -q
git switch main && git merge --no-ff develop -m "release: v1.0" && git tag -a v1.0 -m "final" && git push origin main --tags
```
Rehearse the 3-minute demo three times (script in the blueprint, section 12). Record a backup video.

## Known limitations of this reference implementation (say them out loud)
* Validation is on a simulator whose chain, rates and lags are our assumptions; real-world transfer needs municipal data.
* The filter is well-specified for family A and deliberately mis-specified for B and C.
* Cost parameters are editable assumptions, not validated numbers.
* The ledger's per-kind decomposition is exact at each hypothesis' most likely onset, not for the onset-marginalised posterior.
* Rain statistics from real records (IMD/Open-Meteo) are not wired in; the simulator uses fixed rates. Add them in `src/sim/world.py` if time allows and record licences in `docs/DATA_NOTES.md`.
