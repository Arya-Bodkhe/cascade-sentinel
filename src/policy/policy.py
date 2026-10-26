"""Decision policy: cost-aware unified action ladder, cry-wolf fatigue, anti-flapping hysteresis.

LADDER:
  WATCH (0) < PREPARE (1) < ALERT (2) < ESCALATE (3)

CRITICAL SAFETY DESIGN:
  - ESCALATE is a RECOMMENDATION only. Public dispatch requires human confirmation.
  - Escalation is swift when risk crosses threshold.
  - De-escalation requires sustained drop (k_down >= 2 intervals) to prevent flip-flopping.
  - Cry-wolf fatigue raises false-alarm penalty when false alerts accumulate.
"""
from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

ACTIONS = ["WATCH", "PREPARE", "ALERT", "ESCALATE"]
ACTION_WATCH, ACTION_PREPARE, ACTION_ALERT, ACTION_ESCALATE = range(4)

ACTION_COLORS = {
    "WATCH": "#10b981",       # Green
    "PREPARE": "#facc15",     # Yellow
    "ALERT": "#fb923c",       # Orange
    "ESCALATE": "#ef4444"     # Red
}


@dataclass
class ActionThresholds:
    """Editable numeric decision thresholds shown in Policy UI."""
    p_prepare: float = 0.25      # P(CASCADE) candidate for PREPARE
    p_alert: float = 0.50        # P(CASCADE) candidate for ALERT
    p_escalate: float = 0.70     # P(CASCADE) candidate for ESCALATE
    rain_3d_prepare_mm: float = 80.0
    rain_3d_alert_mm: float = 150.0
    rain_3d_escalate_mm: float = 220.0
    rain_24h_alert_mm: float = 80.0
    rain_24h_escalate_mm: float = 120.0

    def __post_init__(self):
        probabilities = (self.p_prepare, self.p_alert, self.p_escalate)
        if not all(math.isfinite(float(value)) for value in probabilities):
            raise ValueError("Probability thresholds must be finite")
        if not (0.0 <= self.p_prepare <= self.p_alert <= self.p_escalate <= 1.0):
            raise ValueError("Probability thresholds must satisfy 0 <= PREPARE <= ALERT <= ESCALATE <= 1")
        rain_thresholds = (
            self.rain_3d_prepare_mm, self.rain_3d_alert_mm, self.rain_3d_escalate_mm,
            self.rain_24h_alert_mm, self.rain_24h_escalate_mm,
        )
        if not all(math.isfinite(float(value)) and float(value) >= 0.0 for value in rain_thresholds):
            raise ValueError("Rainfall thresholds must be finite and non-negative")
        if not (self.rain_3d_prepare_mm <= self.rain_3d_alert_mm <= self.rain_3d_escalate_mm):
            raise ValueError("3-day rainfall thresholds must be ordered PREPARE <= ALERT <= ESCALATE")
        if self.rain_24h_alert_mm > self.rain_24h_escalate_mm:
            raise ValueError("24-hour rainfall thresholds must satisfy ALERT <= ESCALATE")


@dataclass
class CostModel:
    D: float = 100.0                                   # damage if unmitigated
    rho: tuple = (0.0, 0.25, 0.60, 0.85)               # damage reduction factor per action
    c_fa: tuple = (0.0, 3.0, 30.0, 62.0)               # unvalidated assumed false-alarm costs
    kappa: float = 0.25                                # lead-time benefit rate
    gamma: float = 2.0                                 # fatigue multiplier on false-alarm cost
    switch: float = 1.5                                # cost per level change (anti flip-flop)

    def lead_factor(self, lead: float) -> float:
        return 1.0 - math.exp(-self.kappa * max(lead, 0.0))

    def losses(self, p_cas: float, lead: float, f: float = 0.0) -> np.ndarray:
        """Expected loss of each action given P(CASCADE), lead time, and fatigue."""
        lf = self.lead_factor(lead)
        out = np.zeros(4)
        for a in range(4):
            fa = self.c_fa[a] * (1.0 + (self.gamma * f if a >= 2 else 0.0))
            out[a] = p_cas * self.D * (1.0 - self.rho[a] * lf) + (1.0 - p_cas) * fa
        return out

    def episode_cost(self, is_cascade: bool, levels: List[int], times: List[float], impact: float, f: float = 0.0) -> float:
        """Realised cost of an episode given the level at each minute (ground truth known)."""
        if is_cascade:
            best = 0.0
            for lv, t in zip(levels, times):
                if t <= impact:
                    best = max(best, self.rho[lv] * self.lead_factor(impact - t))
            return self.D * (1.0 - best)
        a = max(levels) if levels else 0
        return self.c_fa[a] * (1.0 + (self.gamma * f if a >= 2 else 0.0))


class Policy:
    def __init__(self,
                 cost: Optional[CostModel] = None,
                 thresholds: Optional[ActionThresholds] = None,
                 hysteresis: bool = True,
                 fatigue: bool = True,
                 lookahead: bool = True,
                 k_down: int = 2,
                 min_dwell: int = 1,
                 name: str = "CASCADE_SENTINEL"):
        self.cost = cost or CostModel()
        self.thresholds = thresholds or ActionThresholds()
        self.hysteresis = hysteresis
        self.use_fatigue = fatigue
        self.lookahead = lookahead
        self.k_down = max(1, k_down)
        self.min_dwell = min_dwell
        self.name = name
        self.f = 0.0  # cry-wolf fatigue state [0, 1]
        self.reset()

    def reset(self):
        self.level = ACTION_WATCH
        self.dwell = 0
        self.below_count = 0
        self.max_level = ACTION_WATCH
        self.history: List[int] = []

    def _effective_fatigue(self) -> float:
        return self.f if self.use_fatigue else 0.0

    def evaluate_recommended_level(self, p_cas: float, lead: float = 24.0,
                                   rain_3d: float = 0.0, rain_24h: float = 0.0,
                                   susceptibility: float = 0.5) -> Tuple[int, str, Dict[str, float]]:
        """Combine CostModel loss minimization with explicit risk safety thresholds.
        
        Returns:
            (candidate_level, rule_fired, contributing_factors)
        """
        losses = self.cost.losses(p_cas, lead, self._effective_fatigue())
        cm_action = int(np.argmin(losses))

        # Check explicit hydro-hazard threshold overrides and eligibility
        th = self.thresholds
        elig_action = ACTION_WATCH
        rule = "CostLossMinimization"

        # Escalate trigger
        if (p_cas >= th.p_escalate
                or (rain_3d >= th.rain_3d_escalate_mm and susceptibility >= 0.60)
                or rain_24h >= th.rain_24h_escalate_mm):
            elig_action = ACTION_ESCALATE
            rule = "ThresholdExceeded(ESCALATE: Severe Hazard)"
        # Alert trigger
        elif p_cas >= th.p_alert or (rain_3d >= th.rain_3d_alert_mm and susceptibility >= 0.50) or (rain_24h >= th.rain_24h_alert_mm):
            elig_action = ACTION_ALERT
            rule = "ThresholdExceeded(ALERT: Imminent Deluge)"
        # Prepare trigger
        elif p_cas >= th.p_prepare or rain_3d >= th.rain_3d_prepare_mm or (rain_24h >= 40.0 and susceptibility >= 0.50):
            elig_action = ACTION_PREPARE
            rule = "ThresholdExceeded(PREPARE: Elevated Catchment Risk)"

        # Direct evidence triggers are a safety floor; expected-loss optimization
        # may elevate the response but must never suppress a threshold-triggered action.
        candidate = max(cm_action, elig_action)

        contribs = {
            "P(CASCADE)": p_cas,
            "Rain_3Day_mm": rain_3d,
            "Rain_24h_mm": rain_24h,
            "SusceptibilityPrior": susceptibility,
            "CostLossOptAction": float(cm_action),
            "EligibleAction": float(elig_action)
        }
        return candidate, rule, contribs

    def step_decision(self, p_cas: float, lead: float = 24.0,
                      rain_3d: float = 0.0, rain_24h: float = 0.0,
                      susceptibility: float = 0.5,
                      pct_rank: float = 0.0) -> Dict[str, Any]:
        """Apply anti-flapping hysteresis and produce explainable recommendation."""
        candidate, rule, contribs = self.evaluate_recommended_level(
            p_cas, lead, rain_3d, rain_24h, susceptibility
        )
        old_level = self.level

        if not self.hysteresis:
            self.level = candidate
            self.below_count = 0
            self.dwell = 1
        elif candidate > self.level:
            # Immediate escalation to protect lives
            self.level = candidate
            self.below_count = 0
            self.dwell = 1
        elif candidate < self.level:
            # Require sustained drop to prevent flip-flopping
            self.below_count += 1
            if self.below_count >= self.k_down:
                self.level = candidate
                self.below_count = 0
                self.dwell = 1
            else:
                self.dwell += 1
                rule += f" (Hysteresis hold at {ACTIONS[self.level]}, below {self.below_count}/{self.k_down})"
        else:
            self.below_count = 0
            self.dwell += 1

        self.max_level = max(self.max_level, self.level)
        self.history.append(self.level)

        action_name = ACTIONS[self.level]
        if self.level > candidate:
            explanation = (
                f"{action_name} held by hysteresis: current evidence supports {ACTIONS[candidate]}, "
                f"but de-escalation requires {self.k_down} consecutive lower-risk checks "
                f"({self.below_count}/{self.k_down} completed)."
            )
        elif candidate > int(contribs["EligibleAction"]):
            explanation = (
                f"{action_name} selected by expected-loss minimization at P(CASCADE)={p_cas:.2f}; "
                f"direct evidence triggers reach {ACTIONS[int(contribs['EligibleAction'])]}. "
                "Cost parameters are unvalidated assumptions; verify operationally."
            )
        else:
            explanation = self.generate_plain_reason(
                action_name, p_cas, rain_3d, rain_24h, pct_rank, susceptibility
            )
        reverses_if = self.generate_reverses_if(
            action_name, p_cas, rain_3d, rain_24h
        )

        return {
            "action_level": self.level,
            "action_name": action_name,
            "old_action_name": ACTIONS[old_level],
            "action_changed": (self.level != old_level),
            "candidate_level": candidate,
            "candidate_name": ACTIONS[candidate],
            "rule_fired": rule,
            "contributions": contribs,
            "plain_reason": explanation,
            "reverses_if": reverses_if,
            "dwell": self.dwell,
            "fatigue": self.f,
            "requires_human_confirm": (self.level == ACTION_ESCALATE)
        }

    def generate_plain_reason(self, action: str, p_cas: float, rain_3d: float,
                              rain_24h: float, pct_rank: float, susceptibility: float) -> str:
        """One-sentence plain reason for district disaster managers."""
        th = self.thresholds
        reasons = []
        if action == "ESCALATE":
            if p_cas >= th.p_escalate:
                reasons.append(f"P(CASCADE) {p_cas:.2f} >= {th.p_escalate:.2f}")
            if rain_3d >= th.rain_3d_escalate_mm and susceptibility >= 0.60:
                reasons.append(f"3-day rain {rain_3d:.1f} mm >= {th.rain_3d_escalate_mm:.1f} mm with susceptibility {susceptibility:.2f}")
            if rain_24h >= th.rain_24h_escalate_mm:
                reasons.append(f"24-hour rain {rain_24h:.1f} mm >= {th.rain_24h_escalate_mm:.1f} mm")
            trigger = " or ".join(reasons) or "severe-hazard threshold"
            return f"ESCALATE is recommended because {trigger}. Human confirmation is required; no public alert is dispatched by this system."
        if action == "ALERT":
            if p_cas >= th.p_alert:
                reasons.append(f"P(CASCADE) {p_cas:.2f} >= {th.p_alert:.2f}")
            if rain_3d >= th.rain_3d_alert_mm and susceptibility >= 0.50:
                reasons.append(f"3-day rain {rain_3d:.1f} mm >= {th.rain_3d_alert_mm:.1f} mm at susceptibility {susceptibility:.2f}")
            if rain_24h >= th.rain_24h_alert_mm:
                reasons.append(f"24-hour rain {rain_24h:.1f} mm >= {th.rain_24h_alert_mm:.1f} mm")
            trigger = " or ".join(reasons) or f"cost-loss optimization at P(CASCADE)={p_cas:.2f}"
            return f"ALERT because {trigger}; selected-cell historical percentile is {pct_rank:.0f}%."
        if action == "PREPARE":
            if p_cas >= th.p_prepare:
                reasons.append(f"P(CASCADE) {p_cas:.2f} >= {th.p_prepare:.2f}")
            if rain_3d >= th.rain_3d_prepare_mm:
                reasons.append(f"3-day rain {rain_3d:.1f} mm >= {th.rain_3d_prepare_mm:.1f} mm")
            if rain_24h >= 40.0 and susceptibility >= 0.50:
                reasons.append(f"24-hour rain {rain_24h:.1f} mm with susceptibility {susceptibility:.2f}")
            trigger = " or ".join(reasons) or f"cost-loss optimization at P(CASCADE)={p_cas:.2f}"
            return f"PREPARE because {trigger}; susceptibility prior is {susceptibility:.2f}."
        return (
            f"WATCH selected at P(CASCADE)={p_cas:.2f}; no direct PREPARE rainfall or probability trigger is active. "
            f"3-day rainfall is {rain_3d:.1f} mm."
        )

    def generate_reverses_if(self, action: str, p_cas: float, rain_3d: float, rain_24h: float) -> str:
        """Explains what threshold cross would alter the current recommendation."""
        th = self.thresholds
        if action == "WATCH":
            return f"P(CASCADE) >= {th.p_prepare:.2f} or 3-day rainfall >= {th.rain_3d_prepare_mm:.1f} mm steps up to PREPARE"
        elif action == "PREPARE":
            return (
                f"Steps up to ALERT if P(CASCADE) >= {th.p_alert:.2f} or 24h rainfall >= {th.rain_24h_alert_mm:.1f} mm; "
                f"de-escalates to WATCH if P(CASCADE) drops below {th.p_prepare:.2f} for {self.k_down} consecutive steps"
            )
        elif action == "ALERT":
            return (
                f"Steps up to ESCALATE if P(CASCADE) >= {th.p_escalate:.2f} or 3-day rainfall >= {th.rain_3d_escalate_mm:.1f} mm; "
                f"de-escalates to PREPARE if P(CASCADE) drops below {th.p_alert:.2f} for {self.k_down} consecutive steps"
            )
        else:
            return f"De-escalates to ALERT if risk subsides below {th.p_escalate:.2f} for {self.k_down} consecutive checks"

    def record_episode_outcome(self, is_cascade: bool):
        """Update cry-wolf fatigue state after an episode finishes."""
        if self.max_level >= ACTION_ALERT and not is_cascade:
            # Penalize false alarm
            self.f = min(1.0, self.f + 0.25)
        else:
            # Gradual fatigue recovery
            self.f *= 0.85
        self.reset()

    # Backwards compatibility for synthetic simulation engine
    def step(self, t, belief, ev, engine, rng):
        from src.common.model import H_CAS
        p_cas = float(belief.p[H_CAS])
        lead = max(engine.expected_impact(belief) - t, 2.0)
        info = self.step_decision(p_cas=p_cas, lead=lead)
        info["level"] = self.level
        info["L"] = self.cost.losses(p_cas, lead, self._effective_fatigue()).tolist()
        info["wait"] = None
        return info

    def end_episode(self, is_cascade: bool):
        self.record_episode_outcome(is_cascade)


def flips(levels: List[int]) -> int:
    """Direction reversals in the action level sequence (up->down or down->up)."""
    d = [b - a for a, b in zip(levels, levels[1:]) if b != a]
    return sum(1 for x, y in zip(d, d[1:]) if x * y < 0)


def run_scripted_scenarios(policy: Optional[Policy] = None) -> pd.DataFrame:
    """Run required scripted validation scenarios and verify expected vs actual action."""
    pol = policy or Policy()
    scenarios = [
        {
            "name": "1. Quiet Day",
            "desc": "Dry monsoon break; rain < 5mm, prior 0.15",
            "p_cas": 0.05,
            "rain_3d": 4.2,
            "rain_24h": 0.5,
            "susc": 0.20,
            "pct": 10.0,
            "expected": "WATCH"
        },
        {
            "name": "2. Moderate Rain",
            "desc": "Active monsoon spell; 3d rain 95mm, prior 0.50",
            "p_cas": 0.35,
            "rain_3d": 95.0,
            "rain_24h": 38.0,
            "susc": 0.50,
            "pct": 82.0,
            "expected": "PREPARE"
        },
        {
            "name": "3. Intense Rain (Low Susceptibility)",
            "desc": "Downpour in flat rainshadow east (Baramati/Indapur, prior 0.22)",
            "p_cas": 0.52,
            "rain_3d": 110.0,
            "rain_24h": 72.0,
            "susc": 0.22,
            "pct": 92.0,
            "expected": "ALERT"
        },
        {
            "name": "4. Intense Rain (High Susceptibility)",
            "desc": "Extreme Ghats deluge in catchment (Mulshi/Lavasa, prior 0.88)",
            "p_cas": 0.82,
            "rain_3d": 240.0,
            "rain_24h": 140.0,
            "susc": 0.88,
            "pct": 99.5,
            "expected": "ESCALATE"
        },
        {
            "name": "5. Data Outage (Live API Down)",
            "desc": "Network failure, cached fallback; single-source uncertainty",
            "p_cas": 0.28,
            "rain_3d": 65.0,
            "rain_24h": 22.0,
            "susc": 0.45,
            "pct": 70.0,
            "expected": "PREPARE"
        },
        {
            "name": "6. Source Conflict (IMD High, OM Low)",
            "desc": "IMD reports 110mm, OM reports 15mm; confidence penalty applied",
            "p_cas": 0.44,
            "rain_3d": 110.0,
            "rain_24h": 65.0,
            "susc": 0.55,
            "pct": 88.0,
            "expected": "PREPARE"  # High divergence holds back escalation until verified
        }
    ]

    results = []
    for sc in scenarios:
        # Reset policy to test isolated scenario
        pol.reset()
        # For conflict scenario, apply divergence penalty
        p_eval = sc["p_cas"]
        if "Conflict" in sc["name"]:
            p_eval *= 0.75  # 25% confidence discount on divergence

        res = pol.step_decision(
            p_cas=p_eval,
            rain_3d=sc["rain_3d"],
            rain_24h=sc["rain_24h"],
            susceptibility=sc["susc"],
            pct_rank=sc["pct"]
        )
        actual = res["action_name"]
        match = (actual == sc["expected"])

        results.append({
            "Scenario": sc["name"],
            "Description": sc["desc"],
            "P(CASCADE)": round(p_eval, 2),
            "Rain 3D (mm)": sc["rain_3d"],
            "Susceptibility": sc["susc"],
            "Expected Action": sc["expected"],
            "Actual Action": actual,
            "Match": "[PASS]" if match else "[FAIL]",
            "Rule Fired": res["rule_fired"]
        })

    return pd.DataFrame(results)
