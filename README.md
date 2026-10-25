# CASCADE SENTINEL

Calibrated, explainable early-warning inference for the first ten minutes of a cascading urban crisis (CASCADE '26, Theme 2, Problem 1).
Research prototype for analyst decision support. **Not an official warning system.** All results are on a simulator with known ground truth.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tests/run_tests.py          # 12 tests
python -m src.eval.run_eval --quick
streamlit run app.py
```

## What it does
Four-way posterior (NOISE / SENSOR_FAIL / ISOLATED / CASCADE) from a messy event stream, cost-optimal action ladder (WATCH / PREPARE / ALERT / ESCALATE) with hysteresis and cry-wolf fatigue, next-3-event forecast with windows, hash-chained why-ledger, cross-episode trust and prior-shift learning.

## Layout
`src/sim` world + stressors + twins | `src/ingest` quarantine | `src/belief` grid filter | `src/policy` costs and stopping | `src/foresight` causal forecaster | `src/learning` trust + BOCPD | `src/ledger` hash chain | `src/eval` baselines and metrics | `app.py` UI | `docs/` guides

Start with `docs/BUILD_GUIDE.md`, `docs/TASK_SPLIT.md`, `docs/GIT_WORKFLOW.md`. Measured numbers: `reports/RESULTS.md` (quick run, seed 41). Re-run `--full` for final numbers.
