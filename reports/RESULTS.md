# Results (SIMULATED episodes, seed 41, sizes {'train': 2000, 'val': 500, 'test': 500})

Targets in the blueprint are goals; the numbers below are what this run measured, including misses.

## 1. Honest probabilities (CASCADE, Brier lower=better; ECE per hypothesis for SENTINEL)

| family | method | T+3 | T+5 | T+7 | T+10 |
|---|---|---|---|---|---|
| A | SENTINEL | 0.124 | 0.113 | 0.093 | 0.038 |
| A | SENTINEL-uncalibrated | 0.123 | 0.113 | 0.093 | 0.038 |
| A | B1-naive-bayes | 0.121 | 0.106 | 0.081 | 0.032 |
| A | B2-logreg | 0.128 | 0.121 | 0.090 | 0.032 |
| A | B0-threshold | 0.125 | 0.118 | 0.103 | 0.069 |
| B(held-out) | SENTINEL | 0.130 | 0.124 | 0.116 | 0.082 |
| B(held-out) | SENTINEL-uncalibrated | 0.129 | 0.124 | 0.116 | 0.082 |
| B(held-out) | B1-naive-bayes | 0.129 | 0.127 | 0.121 | 0.080 |
| B(held-out) | B2-logreg | 0.137 | 0.133 | 0.107 | 0.054 |
| B(held-out) | B0-threshold | 0.136 | 0.130 | 0.117 | 0.078 |
| C(held-out) | SENTINEL | 0.153 | 0.118 | 0.082 | 0.029 |
| C(held-out) | SENTINEL-uncalibrated | 0.151 | 0.119 | 0.081 | 0.029 |
| C(held-out) | B1-naive-bayes | 0.144 | 0.106 | 0.065 | 0.018 |
| C(held-out) | B2-logreg | 0.150 | 0.112 | 0.083 | 0.029 |
| C(held-out) | B0-threshold | 0.161 | 0.137 | 0.102 | 0.068 |

SENTINEL 4-way log-loss / mean ECE over hypotheses:

| family | T+3 | T+5 | T+7 | T+10 |
|---|---|---|---|---|
| A | 1.27 / 0.035 | 1.14 / 0.038 | 0.90 / 0.050 | 0.55 / 0.043 |
| B(held-out) | 1.29 / 0.045 | 1.19 / 0.054 | 1.02 / 0.057 | 0.80 / 0.060 |
| C(held-out) | 1.30 / 0.054 | 1.12 / 0.049 | 0.81 / 0.035 | 0.43 / 0.040 |

## 2. Decision policy (total expected cost, lower=better; mean [95% bootstrap CI])

| family | policy | cost | flips/episode | false-ALERT rate |
|---|---|---|---|---|
| A | SENTINEL | 10.3 [8.5, 12.3] | 0.03 | 0.04 |
| A | -hysteresis | 12.1 [10.2, 13.9] | 0.63 | 0.12 |
| A | -fatigue | 10.6 [8.8, 12.5] | 0.04 | 0.05 |
| A | -lookahead | 11.5 [9.6, 13.3] | 0.08 | 0.10 |
| A | fixed-threshold(SENTINEL probs) | 10.8 [8.8, 12.8] | 0.15 | 0.09 |
| A | fixed-threshold(B1 probs) | 9.5 [7.6, 11.4] | 0.12 | 0.04 |
| B(held-out) | SENTINEL | 12.4 [10.1, 15.0] | 0.03 | 0.01 |
| B(held-out) | -hysteresis | 12.4 [10.4, 14.7] | 0.69 | 0.06 |
| B(held-out) | -fatigue | 12.9 [10.6, 15.5] | 0.02 | 0.02 |
| B(held-out) | -lookahead | 12.3 [10.3, 14.6] | 0.09 | 0.05 |
| B(held-out) | fixed-threshold(SENTINEL probs) | 12.4 [10.0, 15.1] | 0.17 | 0.04 |
| B(held-out) | fixed-threshold(B1 probs) | 12.8 [10.2, 15.6] | 0.11 | 0.02 |

## 3. Twin test

```
{
  "pairs": 200,
  "max_pre_split_L1_gap": 0.7850582408738671,
  "confident_wrong_penalty": 0.0006446822746338892,
  "median_minutes_to_commit_after_first_diff": 6.0,
  "never_committed": 20
}
```

## 4. Foresight

```
{
  "items": 198,
  "event_hit_rate": 1.0,
  "window_coverage_nominal_80": 0.7626262626262627,
  "intervention_mean_P_hospital": {
    "causal_do(cut)": 0.0,
    "correlational_baseline": 0.2551591033500136,
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