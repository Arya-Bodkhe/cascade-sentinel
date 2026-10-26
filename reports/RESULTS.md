# Results (SIMULATED episodes, seed 41, sizes {'train': 300, 'val': 150, 'test': 200})

Targets in the blueprint are goals; the numbers below are what this run measured, including misses.

## 1. Honest probabilities (CASCADE, Brier lower=better; ECE per hypothesis for SENTINEL)

| family | method | T+3 | T+5 | T+7 | T+10 |
|---|---|---|---|---|---|
| A | SENTINEL | 0.137 | 0.119 | 0.104 | 0.050 |
| A | SENTINEL-uncalibrated | 0.135 | 0.120 | 0.104 | 0.051 |
| A | B1-naive-bayes | 0.131 | 0.114 | 0.093 | 0.050 |
| A | B2-logreg | 0.142 | 0.138 | 0.106 | 0.051 |
| A | B0-threshold | 0.141 | 0.131 | 0.114 | 0.072 |
| B(held-out) | SENTINEL | 0.141 | 0.140 | 0.122 | 0.085 |
| B(held-out) | SENTINEL-uncalibrated | 0.140 | 0.138 | 0.122 | 0.086 |
| B(held-out) | B1-naive-bayes | 0.139 | 0.132 | 0.133 | 0.098 |
| B(held-out) | B2-logreg | 0.152 | 0.148 | 0.128 | 0.073 |
| B(held-out) | B0-threshold | 0.152 | 0.144 | 0.129 | 0.078 |
| C(held-out) | SENTINEL | 0.161 | 0.120 | 0.074 | 0.019 |
| C(held-out) | SENTINEL-uncalibrated | 0.160 | 0.120 | 0.074 | 0.019 |
| C(held-out) | B1-naive-bayes | 0.155 | 0.106 | 0.057 | 0.014 |
| C(held-out) | B2-logreg | 0.160 | 0.104 | 0.074 | 0.028 |
| C(held-out) | B0-threshold | 0.181 | 0.146 | 0.091 | 0.046 |

SENTINEL 4-way log-loss / mean ECE over hypotheses:

| family | T+3 | T+5 | T+7 | T+10 |
|---|---|---|---|---|
| A | 1.31 / 0.044 | 1.12 / 0.041 | 0.92 / 0.058 | 0.56 / 0.048 |
| B(held-out) | 1.36 / 0.073 | 1.25 / 0.072 | 1.04 / 0.071 | 0.81 / 0.074 |
| C(held-out) | 1.31 / 0.081 | 1.09 / 0.056 | 0.76 / 0.053 | 0.41 / 0.052 |

## 2. Decision policy (total expected cost, lower=better; mean [95% bootstrap CI])

| family | policy | cost | flips/episode | false-ALERT rate |
|---|---|---|---|---|
| A | SENTINEL | 11.5 [8.5, 14.7] | 0.03 | 0.04 |
| A | -hysteresis | 12.9 [10.1, 16.0] | 0.64 | 0.12 |
| A | -fatigue | 12.0 [8.9, 15.0] | 0.04 | 0.06 |
| A | -lookahead | 12.5 [9.6, 15.5] | 0.08 | 0.10 |
| A | fixed-threshold(SENTINEL probs) | 11.7 [8.2, 15.4] | 0.07 | 0.02 |
| A | fixed-threshold(B1 probs) | 11.2 [7.9, 14.9] | 0.04 | 0.01 |
| B(held-out) | SENTINEL | 13.7 [10.0, 18.1] | 0.01 | 0.00 |
| B(held-out) | -hysteresis | 13.2 [9.8, 17.0] | 0.69 | 0.04 |
| B(held-out) | -fatigue | 13.9 [10.2, 18.2] | 0.03 | 0.01 |
| B(held-out) | -lookahead | 13.2 [9.9, 17.1] | 0.09 | 0.04 |
| B(held-out) | fixed-threshold(SENTINEL probs) | 15.6 [11.0, 20.6] | 0.07 | 0.00 |
| B(held-out) | fixed-threshold(B1 probs) | 15.3 [10.8, 20.4] | 0.05 | 0.00 |

## 3. Twin test

```
{
  "pairs": 60,
  "max_pre_split_L1_gap": 0.0,
  "confident_wrong_penalty": 0.0009907010142494034,
  "median_minutes_to_commit_after_first_diff": 6.0,
  "never_committed": 9
}
```

## 4. Foresight

```
{
  "items": 83,
  "event_hit_rate": 1.0,
  "window_coverage_nominal_80": 0.7710843373493976,
  "intervention_mean_P_hospital": {
    "causal_do(cut)": 0.0,
    "correlational_baseline": 0.22678632156519454,
    "actual_rate": 0.0
  }
}
```

## 5. Prior shift

```
{
  "shift_at_episode": 60,
  "episodes_to_recover_BOCPD": 16,
  "frozen_prior_estimate_error_after_shift": 0.30000000000000004,
  "mean_logloss_after_shift": {
    "adaptive": 1.2357961753692441,
    "frozen": 1.4565240034483953
  }
}
```

## 6. Robustness

| stressor | mean cost | false-ALERT rate | Brier(CASCADE)@T+7 | crashes |
|---|---|---|---|---|
| clean | 12.3 | 0.02 | 0.110 | 0 |
| outage | 10.1 | 0.03 | 0.100 | 0 |
| cutout | 12.5 | 0.00 | 0.120 | 0 |
| lie | 8.4 | 0.01 | 0.074 | 0 |
| rumor | 12.5 | 0.03 | 0.093 | 0 |
| messy | 14.2 | 0.02 | 0.129 | 0 |