import sys, os
sys.path.insert(0, os.path.abspath("."))
from src.replay_engine import ReplayEngine, HISTORICAL_EVENTS

re = ReplayEngine()
print("--- TESTING HISTORICAL REPLAY ENGINE ---")
for k, meta in HISTORICAL_EVENTS.items():
    res = re.run_replay(k)
    peak_step = [s for s in res["timeline"] if s["is_peak"]][0]
    print(f"Key: {k:15} | Dates: {len(res['dates'])} | Ledger: {len(res['ledger_entries'])} | Verified: {res['ledger_verified']} | Peak ({meta.peak_date}): {peak_step['action_name']} (P={peak_step['p_cascade']:.2f})")
