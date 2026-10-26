"""Ingest + quarantine: schema validation, retractions, dedupe, event/arrival time.
Deterministic and order-invariant: the output depends only on the SET of events."""
import math
from src.common.model import KINDS, META_KINDS

REQUIRED = ("id", "source", "family", "kind", "event_time", "received_at")


def validate(e):
    if not isinstance(e, dict):
        raise ValueError("not an object")
    for k in REQUIRED:
        if k not in e or e[k] is None:
            raise ValueError(f"missing field {k}")
    if isinstance(e["id"], bool) or not isinstance(e["id"], (str, int)):
        raise ValueError("bad id")
    for k in ("source", "family", "kind"):
        if not isinstance(e[k], str):
            raise ValueError(f"bad {k}")
    for k in ("event_time", "received_at"):
        v = e[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"bad {k}")
    if e["kind"] not in KINDS and e["kind"] not in META_KINDS:
        raise ValueError("unknown kind")
    if e["event_time"] < 0:
        raise ValueError("negative event_time")
    if e["event_time"] > e["received_at"] + 1e-9:
        raise ValueError("future-dated event (event_time > received_at)")


def _key(e):
    return (e["source"], e["kind"], str(e.get("zone")), int(e["event_time"] // 2))


def ingest(events, t):
    """Return (clean_events_sorted, quarantine_list) as known at wall-clock minute t."""
    quarantine, by_id, retracted = [], {}, set()
    for e in events:
        try:
            validate(e)
        except Exception as ex:  # never crash the loop
            quarantine.append({"reason": str(ex),
                               "id": str(e.get("id")) if isinstance(e, dict) else None})
            continue
        if e["received_at"] > t:
            continue  # has not arrived yet
        if e["kind"] == "retraction":
            retracted.add(str(e.get("ref")))
            continue
        by_id.setdefault(str(e["id"]), []).append(e)
    chosen = [min(v, key=lambda x: (x["event_time"], x["received_at"], x["source"]))
              for v in by_id.values()]
    chosen = [e for e in chosen if str(e["id"]) not in retracted]
    chosen.sort(key=lambda e: (e["event_time"], str(e["id"])))
    clean, seen = [], set()
    for e in chosen:
        if e["kind"] in KINDS:               # near-duplicate collapse (same source/zone/2-min bucket)
            k = _key(e)
            if k in seen:
                continue
            seen.add(k)
        clean.append(e)
    return clean, quarantine
