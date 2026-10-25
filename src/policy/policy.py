"""Decision policy: cost-aware action ladder, cry-wolf fatigue, optimal-stopping look-ahead, hysteresis."""
from dataclasses import dataclass
import math
import numpy as np
from src.common.model import H_CAS

ACTIONS = ["WATCH", "PREPARE", "ALERT", "ESCALATE"]


@dataclass
class CostModel:
    D: float = 100.0                                   # damage if cascade is unmitigated
    rho: tuple = (0.0, 0.25, 0.60, 0.85)               # damage reduction factor per action
    c_fa: tuple = (0.0, 1.5, 15.0, 45.0)               # cost if action taken but no cascade
    kappa: float = 0.25                                # lead-time benefit rate
    gamma: float = 2.0                                 # fatigue multiplier on false-alarm cost
    switch: float = 1.5                                # cost per level change (anti flip-flop)

    def lead_factor(self, lead):
        return 1.0 - math.exp(-self.kappa * max(lead, 0.0))

    def losses(self, p_cas, lead, f):
        """Expected loss of each action given P(CASCADE) and lead time to impact."""
        lf = self.lead_factor(lead)
        out = np.zeros(4)
        for a in range(4):
            fa = self.c_fa[a] * (1 + (self.gamma * f if a >= 2 else 0.0))
            out[a] = p_cas * self.D * (1 - self.rho[a] * lf) + (1 - p_cas) * fa
        return out

    def episode_cost(self, is_cascade, levels, times, impact, f=0.0):
        """Realised cost of an episode given the level at each minute (ground truth known)."""
        if is_cascade:
            best = 0.0
            for lv, t in zip(levels, times):
                if t <= impact:
                    best = max(best, self.rho[lv] * self.lead_factor(impact - t))
            return self.D * (1 - best)
        a = max(levels) if levels else 0
        return self.c_fa[a] * (1 + (self.gamma * f if a >= 2 else 0.0))


class Policy:
    def __init__(self, cost=None, hysteresis=True, fatigue=True, lookahead=True,
                 k_down=3, min_dwell=2, n_look=10, name="SENTINEL"):
        self.cost = cost or CostModel()
        self.hysteresis, self.use_fatigue, self.lookahead = hysteresis, fatigue, lookahead
        self.k_down, self.min_dwell, self.n_look, self.name = k_down, min_dwell, n_look, name
        self.f = 0.0
        self.reset()

    def reset(self):
        self.level, self.dwell, self.below, self.max_level = 0, 0, 0, 0
        self.history = []

    def _f(self):
        return self.f if self.use_fatigue else 0.0

    def step(self, t, belief, ev, engine, rng):
        cm, f = self.cost, self._f()
        lead = max(engine.expected_impact(belief) - t, 2.0)   # an ongoing incident keeps mitigation valuable
        L = cm.losses(belief.p[H_CAS], lead, f)
        sw = cm.switch if self.hysteresis else 0.0
        Lsw = L + sw * np.abs(np.arange(4) - self.level)
        a_star = int(np.argmin(Lsw))
        info = {"L": L.tolist(), "wait": None}
        if not self.hysteresis:
            self.level = a_star
        elif a_star > self.level:
            commit = True
            if self.lookahead:                                  # value of waiting (one-step look-ahead)
                nxt = engine.lookahead(ev, belief, self.n_look, rng)
                Lw = float(np.mean([cm.losses(p[H_CAS], lead - 1.0, f).min() for p in nxt]))
                info["wait"] = Lw
                commit = L[a_star] <= Lw + 1e-9
            if commit:
                self.level, self.dwell, self.below = a_star, 0, 0
        elif a_star < self.level:
            self.below += 1
            if self.below >= self.k_down and self.dwell >= self.min_dwell:
                self.level, self.dwell, self.below = a_star, 0, 0
        else:
            self.below = 0
        self.dwell += 1
        self.max_level = max(self.max_level, self.level)
        self.history.append(self.level)
        info["level"] = self.level
        return info

    def end_episode(self, is_cascade):
        """Update the cry-wolf fatigue state across episodes."""
        if self.max_level >= 2 and not is_cascade:
            self.f = min(1.0, self.f + 0.25)
        self.f *= 0.9
        self.reset()


def flips(levels):
    """Direction reversals in the action level sequence (up->down or down->up)."""
    d = [b - a for a, b in zip(levels, levels[1:]) if b != a]
    return sum(1 for x, y in zip(d, d[1:]) if x * y < 0)
