"""Hash-chained, replayable why-ledger (exportable as JSON / CSV)."""
import csv, hashlib, io, json

MODEL_VERSION = "v2.3"


class Ledger:
    def __init__(self, seed=0):
        self.entries, self.seed, self.prev = [], seed, "0" * 64

    def add(self, t, p_before, p_after, act_from, act_to, contributions, reverses_if, input_hash, notes=()):
        top = sorted(contributions.items(), key=lambda kv: -abs(kv[1]))[:5]
        body = {"t": t, "p_before": [round(float(x), 4) for x in p_before],
                "p_after": [round(float(x), 4) for x in p_after], "action_from": act_from,
                "action_to": act_to, "because": [(k, round(float(v), 3)) for k, v in top],
                "notes": list(notes), "reverses_if": reverses_if, "model": MODEL_VERSION,
                "seed": self.seed, "input_hash": input_hash}
        h = hashlib.sha256((json.dumps(body, sort_keys=True) + self.prev).encode()).hexdigest()
        row = {**body, "prev_hash": self.prev, "hash": h}
        self.entries.append(row); self.prev = h
        return row

    @staticmethod
    def verify_entries(entries):
        prev = "0" * 64
        for r in entries:
            body = {k: v for k, v in r.items() if k not in ("prev_hash", "hash")}
            h = hashlib.sha256((json.dumps(body, sort_keys=True) + prev).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != h:
                return False
            prev = h
        return True

    def verify(self):
        return self.verify_entries(self.entries)

    def to_json(self):
        return json.dumps(self.entries, indent=2)

    def to_csv(self):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["t", "action_from", "action_to", "p_after", "because", "reverses_if", "hash"])
        for r in self.entries:
            w.writerow([r["t"], r["action_from"], r["action_to"], r["p_after"], r["because"],
                        r["reverses_if"], r["hash"]])
        return buf.getvalue()
