"""Hash-chained, replayable why-ledger (exportable as JSON / CSV).

Each entry records:
  - t / timestamp_ist
  - p_before and p_after
  - action_from and action_to
  - triggering evidence / contributions
  - rule fired
  - reverses_if / threshold next
  - human confirmation status (for ESCALATE)
  - SHA-256 hash chained from prev_hash
"""
import csv
import hashlib
import io
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

MODEL_VERSION = "v2.4-pune"


class Ledger:
    def __init__(self, seed: int = 0):
        self.entries: List[Dict[str, Any]] = []
        self.seed = seed
        self.prev = "0" * 64

    def add(self, t: Any, p_before: Any, p_after: Any, act_from: str, act_to: str,
            contributions: Optional[Dict[str, float]] = None,
            reverses_if: str = "",
            input_hash: str = "init",
            notes: Any = (),
            rule_fired: str = "CostLossMinimization",
            timestamp_ist: Optional[str] = None,
            confirmed_by_human: bool = False):
        """Append an action change or significant decision step to the hash chain."""
        if contributions is None:
            contributions = {}

        if timestamp_ist is None:
            timestamp_ist = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")

        # Top 5 contributing factors
        top = sorted(contributions.items(), key=lambda kv: -abs(kv[1]))[:5] if isinstance(contributions, dict) else list(contributions)[:5]

        # Ensure probabilities are clean floats
        p_b = [round(float(x), 4) for x in p_before] if p_before is not None else [0.0, 0.0, 0.0, 0.0]
        p_a = [round(float(x), 4) for x in p_after] if p_after is not None else [0.0, 0.0, 0.0, 0.0]

        body = {
            "t": t,
            "timestamp_ist": timestamp_ist,
            "p_before": p_b,
            "p_after": p_a,
            "action_from": str(act_from),
            "action_to": str(act_to),
            "because": [(k, round(float(v), 3)) for k, v in top],
            "rule_fired": str(rule_fired),
            "notes": list(notes),
            "reverses_if": str(reverses_if),
            "confirmed_by_human": bool(confirmed_by_human),
            "model": MODEL_VERSION,
            "seed": self.seed,
            "input_hash": str(input_hash)
        }

        # SHA-256 chaining: hash of (json of body + prev hash)
        payload = json.dumps(body, sort_keys=True) + self.prev
        h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        row = {**body, "prev_hash": self.prev, "hash": h}
        self.entries.append(row)
        self.prev = h
        return row

    def add_human_confirmation(self, t: Any, action: str, operator_name: str = "District Disaster Officer",
                               notes: str = "Authorized after field validation"):
        """Record human confirmation of ESCALATE recommendation in the ledger."""
        p_curr = self.entries[-1]["p_after"] if self.entries else [0.0, 0.0, 0.0, 1.0]
        return self.add(
            t=t,
            p_before=p_curr,
            p_after=p_curr,
            act_from=action,
            act_to=f"CONFIRMED_{action}",
            contributions={"HumanAuthorization": 1.0},
            reverses_if="Operator revocation or sustained de-escalation",
            input_hash="human-auth",
            notes=[f"Confirmed by: {operator_name}", notes],
            rule_fired="HumanOfficerAuthorization",
            confirmed_by_human=True
        )

    @staticmethod
    def verify_entries(entries: List[Dict[str, Any]]) -> bool:
        """Verify the cryptographic SHA-256 integrity of the ledger chain."""
        prev = "0" * 64
        for r in entries:
            body = {k: v for k, v in r.items() if k not in ("prev_hash", "hash")}
            payload = json.dumps(body, sort_keys=True) + prev
            h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if r.get("prev_hash") != prev or r.get("hash") != h:
                return False
            prev = h
        return True

    def verify(self) -> bool:
        return self.verify_entries(self.entries)

    def to_json(self) -> str:
        return json.dumps(self.entries, indent=2)

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["t", "timestamp_ist", "action_from", "action_to", "rule_fired", "p_cascade", "because", "reverses_if", "confirmed_by_human", "hash"])
        for r in self.entries:
            p_cas = r["p_after"][3] if len(r.get("p_after", [])) > 3 else 0.0
            w.writerow([
                r.get("t"),
                r.get("timestamp_ist", ""),
                r.get("action_from"),
                r.get("action_to"),
                r.get("rule_fired", ""),
                p_cas,
                str(r.get("because", [])),
                r.get("reverses_if", ""),
                r.get("confirmed_by_human", False),
                r.get("hash")
            ])
        return buf.getvalue()
