"""Shared generative-model constants (the single source of truth for sim AND filter).

The filter uses the NOMINAL parameters below. The simulator can perturb them
(scenario families B/C) so that held-out families are genuinely mis-specified.
"""
import numpy as np

HYPS = ["NOISE", "SENSOR_FAIL", "ISOLATED", "CASCADE"]
H_NOISE, H_SF, H_ISO, H_CAS = 0, 1, 2, 3
KINDS = ["drain", "traffic", "call", "hospital", "sensor", "citizen"]
K = len(KINDS)
KIDX = {k: i for i, k in enumerate(KINDS)}
K_DRAIN, K_TRAFFIC, K_CALL, K_HOSP, K_SENSOR, K_CIT = range(6)
FAMILY = {"drain": "drainage", "traffic": "camera", "call": "dispatch",
          "hospital": "hospital", "sensor": "gateway", "citizen": "social"}
FAMILIES = list(FAMILY.values())
# mean reporting delay (minutes) per source family; heartbeat delay = DELAY + 0.01
DELAY = {"drainage": 0.2, "camera": 0.2, "dispatch": 0.3,
         "hospital": 0.5, "gateway": 0.2, "social": 1.0}
META_KINDS = {"heartbeat", "silence", "retraction", "rain"}

# baseline event rate per minute for every kind (all hypotheses)
BASE = np.array([0.2, 0.2, 0.3, 0.05, 0.3, 0.3])
# extra rate after onset+lag, per hypothesis (rows) and kind (cols)
#               drain traffic call  hosp  sensor citizen
AMP = np.array([[0.40, 0.10, 0.10, 0.00, 0.15, 0.20],   # NOISE   (heavy rain only)
                [0.00, 0.00, 0.00, 0.00, 1.20, 0.00],   # SENSOR_FAIL
                [0.80, 0.20, 0.50, 0.05, 0.50, 0.50],   # ISOLATED
                [1.00, 1.00, 1.50, 1.20, 0.90, 1.50]])  # CASCADE
LAG = np.array([0.0, 2.0, 3.0, 6.0, 0.0, 2.0])          # minutes after onset
# causal chain rain -> drain -> traffic -> call -> hospital
EDGES = [("drain", "traffic"), ("traffic", "call"), ("call", "hospital")]
PRIORS = {"normal": [0.45, 0.20, 0.20, 0.15],
          "monsoon": [0.20, 0.10, 0.25, 0.45]}
TAU = np.arange(0.0, 10.01, 0.5)        # onset grid (minutes)
NT = len(TAU)
M = 24                                    # max minute bins kept
IMPACT_LAG = 9.0                          # cascade impact = onset + 9 min
N_GATEWAYS = 6
SENSORS_PER_GW = 20


def descendants(cut_edges):
    """Kinds that lose their causal parent when the given edges are cut."""
    out = set()
    for parent, child in cut_edges:
        out.add(child)
        stack = [child]
        while stack:
            c = stack.pop()
            for p, ch in EDGES:
                if p == c and ch not in out:
                    out.add(ch)
                    stack.append(ch)
    return out
