"""Belief engine: exact grid filter over (hypothesis H, onset tau).

Events are a marked point process binned per minute. Log-likelihood is a SUM over
weighted per-minute counts, so it is order-invariant by construction.
Handles: gateway common-cause, rumor-cluster discount, physics-consistency penalty,
heartbeat-based missing-not-at-random masking, temperature calibration.
"""
import math
from dataclasses import dataclass, replace
import hashlib
import numpy as np
from src.common.model import (HYPS, KINDS, K, KIDX, FAMILY, FAMILIES, DELAY, BASE, AMP, LAG,
                              PRIORS, TAU, NT, M, H_SF, H_CAS, K_CIT, K_SENSOR, K_HOSP,
                              IMPACT_LAG)
from src.ingest.ingest import ingest

PHYS = {"drain", "traffic", "call"}


@dataclass
class Evidence:
    N: np.ndarray            # weighted counts [K, M]
    V: np.ndarray            # validity mask [K, M] (1 = bin fully observed)
    t: int
    n_down: int
    down_gateways: list
    coverage: float
    n_quarantined: int
    quarantine: list
    raw_citizen: int
    eff_citizen: float
    n_origins: int
    input_hash: str
    n_events: int


@dataclass
class Belief:
    p: np.ndarray            # calibrated 4-way marginal
    joint: np.ndarray        # [4, NT]
    entropy: float


class Engine:
    def __init__(self, trust=None, prior=None, temperature=1.0, gateway=True, rumor=True,
                 physics=True, heartbeat=True, cap=0.35):
        self.trust = dict(trust or {})
        self.trust.setdefault("social", 0.6)
        self.prior = np.array(prior if prior is not None else PRIORS["normal"], float)
        self.prior = self.prior / self.prior.sum()
        self.T = float(temperature)
        self.gateway, self.rumor, self.physics, self.heartbeat = gateway, rumor, physics, heartbeat
        self.cap = cap
        m_mid = np.arange(M) + 0.5
        # lam[h, tau, k, m] = BASE[k] + AMP[h,k] * 1[m+0.5-tau >= LAG[k]]
        on = (m_mid[None, None, None, :] - TAU[None, :, None, None]) >= LAG[None, None, :, None]
        self.LAM = BASE[None, None, :, None] + AMP[:, None, :, None] * on
        self.LOGLAM = np.log(self.LAM)

    # ------------------------------------------------------------------ evidence
    def evidence(self, events, t):
        clean, quar = ingest(events, t)
        N = np.zeros((K, M)); V = np.zeros((K, M))
        hb = {}
        sil = {}
        for e in clean:
            if e["kind"] == "heartbeat":
                hb[e["family"]] = max(hb.get(e["family"], 0.0), float(e["event_time"]))
            elif e["kind"] == "silence":
                g = str(e.get("gateway", "?"))
                a, b = sil.get(g, (1e9, -1e9))
                sil[g] = (min(a, e["event_time"]), max(b, e["event_time"]))
        for k, kind in enumerate(KINDS):
            f = FAMILY[kind]
            if self.heartbeat:
                horizon = hb.get(f, max(0.0, t - 1.0 - DELAY[f]))
            else:
                horizon = float(t)
            nvalid = int(min(M, max(0, math.floor(horizon + 1e-9))))
            V[k, :nvalid] = 1
        phys_times = sorted(e["event_time"] for e in clean if e["kind"] in PHYS)
        clusters = {}
        raw_cit = 0
        for e in clean:
            kind = e["kind"]
            if kind not in KIDX:
                continue
            k = KIDX[kind]
            m = int(e["event_time"] // 1)
            if m >= M or not V[k, m]:
                continue
            w = self.trust.get(e["family"], 1.0)
            if kind == "sensor" and self.gateway:
                g = str(e.get("gateway", "?"))
                if g in sil and e["event_time"] >= sil[g][0] - 1e-9:
                    continue                       # stuck values from a down gateway
            if kind == "citizen":
                raw_cit += 1
                if self.rumor:
                    clusters.setdefault((str(e.get("zone")), int(e["event_time"] // 3)), []).append(e)
                    continue
            if kind == "hospital" and self.physics:
                th = e["event_time"]
                n_ph = sum(1 for x in phys_times if th - 6.0 <= x <= th)
                if n_ph < 3:
                    w *= 0.15                      # structured-lie / physics-lag penalty
            N[k, m] += w
        origins = set()
        for (_, _), evs in clusters.items():
            og = {str(x.get("origin", x["source"])) for x in evs}
            origins |= og
            wc = self.trust.get("social", 0.6) * math.log2(1 + len(og))
            for x in evs:
                N[K_CIT, int(x["event_time"] // 1)] += wc / len(evs)
        alive = sum(1 for f in FAMILIES if hb.get(f, -1e9) >= t - 2.0)
        ids = hashlib.sha256("|".join(sorted(str(e["id"]) for e in clean)).encode()).hexdigest()[:12]
        return Evidence(N=N, V=V, t=t, n_down=len(sil) if self.gateway else 0,
                        down_gateways=sorted(sil), coverage=alive / len(FAMILIES),
                        n_quarantined=len(quar), quarantine=quar[:20], raw_citizen=raw_cit,
                        eff_citizen=float(N[K_CIT].sum()), n_origins=len(origins),
                        input_hash=ids, n_events=len(clean))

    # ------------------------------------------------------------------ inference
    def outage_term(self, n_down):
        return (1.8 + 0.4 * math.log(n_down)) if (self.gateway and n_down > 0) else 0.0

    def logjoint(self, ev, drop_citizen=False):
        V = ev.V.copy()
        if drop_citizen:
            V[K_CIT] = 0
        ll = (V[None, None] * (ev.N[None, None] * self.LOGLAM - self.LAM)).sum(axis=(2, 3))
        ll[H_SF, :] += self.outage_term(ev.n_down)
        return np.log(self.prior)[:, None] - math.log(NT) + ll

    @staticmethod
    def _norm(lj):
        lj = lj - lj.max()
        p = np.exp(lj)
        return p / p.sum()

    def posterior(self, ev):
        joint = self._norm(self.logjoint(ev) / self.T)
        marg = joint.sum(axis=1)
        if self.rumor:
            nocit = self._norm(self.logjoint(ev, True) / self.T).sum(axis=1)
            cap = max(self.cap, nocit[H_CAS])
            if marg[H_CAS] > cap:                   # citizen-only evidence cannot lift CASCADE past cap
                joint[H_CAS] *= cap / marg[H_CAS]
                rest = 1 - marg[H_CAS]
                joint[:H_CAS] *= (1 - cap) / max(rest, 1e-12)
                marg = joint.sum(axis=1)
        ent = float(-(marg * np.log(marg + 1e-12)).sum())
        return Belief(p=marg, joint=joint, entropy=ent)

    def lookahead(self, ev, belief, n, rng):
        """Sample n plausible next observations; return posterior vectors after each."""
        flat = belief.joint.ravel()
        idx = rng.choice(flat.size, size=n, p=flat / flat.sum())
        nb = ev.V.sum(axis=1).astype(int)
        out = []
        for i in idx:
            h, ti = divmod(int(i), NT)
            N2, V2 = ev.N.copy(), ev.V.copy()
            for k in range(K):
                m = nb[k]
                if m < M:
                    N2[k, m] += rng.poisson(self.LAM[h, ti, k, m]) * (1.0 if k != K_CIT else self.trust["social"])
                    V2[k, m] = 1
            out.append(self.posterior(replace(ev, N=N2, V=V2)).p)
        return out

    def cas_onset_mean(self, belief):
        w = belief.joint[H_CAS]
        return float((w * TAU).sum() / max(w.sum(), 1e-12))

    def expected_impact(self, belief):
        return self.cas_onset_mean(belief) + IMPACT_LAG

    # ------------------------------------------------------------------ explanation
    def kind_ll(self, ev, h):
        LLk = (ev.V[None] * (ev.N[None] * self.LOGLAM[h] - self.LAM[h])).sum(axis=2)  # [NT, K]
        tot = LLk.sum(axis=1)
        ti = int(np.argmax(tot))
        return LLk[ti], ti

    def contributions(self, ev, ha, hb):
        """Exact per-kind log-likelihood ratio of ha vs hb at each hypothesis' MAP onset."""
        la, _ = self.kind_ll(ev, ha)
        lb, _ = self.kind_ll(ev, hb)
        c = {KINDS[k]: float(la[k] - lb[k]) for k in range(K)}
        c["gateway_outage"] = float((self.outage_term(ev.n_down) if ha == H_SF else 0.0)
                                    - (self.outage_term(ev.n_down) if hb == H_SF else 0.0))
        c["prior"] = float(math.log(self.prior[ha]) - math.log(self.prior[hb]))
        return c
