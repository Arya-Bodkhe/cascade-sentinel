"""Cross-episode learning: source-trust Beta posteriors and Bayesian online change-point detection."""
import numpy as np


class TrustLearner:
    """Beta(a,b) reliability per source family with exponential forgetting; no ground truth needed."""
    def __init__(self, forget=0.97, a0=3.0, b0=2.0):
        self.ab, self.forget, self.a0, self.b0 = {}, forget, a0, b0

    def trust(self):
        return {f: a / (a + b) for f, (a, b) in self.ab.items()}

    def update(self, family, agree, total):
        a, b = self.ab.get(family, (self.a0, self.b0))
        a, b = a * self.forget, b * self.forget
        self.ab[family] = (a + agree, b + max(total - agree, 0))


class BOCPD:
    """Beta-Bernoulli change-point detector over episode outcomes (is the episode a cascade?)."""
    def __init__(self, hazard=1 / 20, a0=1.0, b0=3.0, max_run=80):
        self.h, self.a0, self.b0, self.max_run = hazard, a0, b0, max_run
        self.R = np.array([1.0]); self.a = np.array([a0]); self.b = np.array([b0])

    def update(self, x):
        pred = self.a / (self.a + self.b)
        like = pred if x else 1 - pred
        growth = self.R * like * (1 - self.h)
        cp = float((self.R * like * self.h).sum())
        R = np.concatenate([[cp], growth]); R /= R.sum()
        self.a = np.concatenate([[self.a0], self.a + x]); self.b = np.concatenate([[self.b0], self.b + 1 - x])
        if len(R) > self.max_run:
            R, self.a, self.b = R[:self.max_run], self.a[:self.max_run], self.b[:self.max_run]
            R /= R.sum()
        self.R = R

    def predict(self):
        return float((self.R * self.a / (self.a + self.b)).sum())

    def prior_vector(self, base):
        """Re-weight a 4-way prior so that P(CASCADE) follows the change-point estimate."""
        base = np.array(base, float); pc = min(max(self.predict(), 0.02), 0.9)
        rest = base[:3] / base[:3].sum() * (1 - pc)
        return np.concatenate([rest, [pc]])
