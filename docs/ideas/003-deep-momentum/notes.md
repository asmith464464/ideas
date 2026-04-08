# Research notes — 003 Deep Momentum Strategy

Working notes updated as exploration progresses.
Run: `python research/ideas/003-deep-momentum/explore.py [section]`

Sections: data, features, baseline, model, backtest, all

---

## Data and universe

**Round 1 (initial):** 169 tickers (FTSE 100 + FTSE 250 candidates). Mean
monthly cross-section = 143 stocks. Total panel: ~25,500 observations.

**Round 2 (expanded):** ~870 tickers attempted (FTSE 100 + 250 + SmallCap + AIM
candidates). 437 successfully fetched; 432 failed (delisted or no data). Mean
monthly cross-section = 386 stocks. Total panel: **60,808 observations** across
164 months and 420 tickers. Unbalanced panel — stocks included as soon as they
have 12 months of history.

---

## Feature analysis (Round 2)

5 features: `m1, m6, m12, vol_6m, size_rank`. Cross-sectionally standardised
per month (except size_rank which is already a percentile rank).

Feature correlations (Spearman rank, time-averaged):
- m6-m12: 0.679 — still correlated but down from 0.85 in round 1
- m1-m6: 0.374, m1-m12: 0.275 — m1 largely orthogonal
- vol_6m-size_rank: -0.314 (small stocks are more volatile)

Forward return decile spread (3-month target): decile 0 median = -26.3%,
decile 9 median = +30.4%. ~56pp spread vs 25pp in round 1 — expanded universe
includes small/AIM stocks with much stronger momentum characteristics.

---

## Baseline: simple 12m momentum (Round 2)

Long top decile, short bottom decile, 3-month forward returns, equal-weighted,
no TC. Expanded universe (420 tickers).

| Metric | Value |
|--------|-------|
| Ann return | 39.0% |
| Sharpe | 1.06 |
| MaxDD | -78.8% |
| Sortino | 1.35 |

High absolute returns driven by small/AIM stocks. MaxDD is large — the expanded
universe includes many illiquid stocks that crash hard in risk-off periods.

---

## DNN model evaluation (Round 2)

### Architecture
- Input: 5 features (m1, m6, m12, vol_6m, size_rank)
- Hidden: Linear(5→32) → ReLU → Dropout(0.4) → Linear(32→16) → ReLU →
  Dropout(0.4) → Linear(16→10), L2 regularisation
- Loss: CrossEntropy, Adam lr=5e-4, 80 epochs, batch 128
- Walk-forward: train on 96 months, retrain every 12 months
- Ensemble of 7 models (different random seeds), predictions averaged

### Results: IC positive and statistically significant

**Rank IC: 0.025 (p<0.001)** — a real signal, up from 0.004 (p=0.58) in round 1.

**Monthly IC: mean=0.021, std=0.074, t-stat=2.30, 63% positive months.**

The 10-step improvements (larger universe, longer training, 3m labels, smaller
model, ensemble) successfully moved the DNN from zero-IC to a detectable signal.

However, the decile calibration table shows predicted ER is nearly flat (2.03%–2.39%)
across all 10 actual deciles — the model has statistically significant rank
correlation but very small spread in predicted values. It knows the direction
slightly but is not confident about magnitude.

### Backtest: DNN long-only vs simple momentum

Long top decile by DNN expected return, monthly rebalance, no TC, no shorts.

| Config | Ann% | Sharpe | MaxDD | Sortino |
|--------|------|--------|-------|---------|
| DNN top-decile (long only) | 43.1% | 1.17 | -49.4% | 1.86 |
| Simple 12m momentum top-decile | 49.6% | 1.28 | -38.3% | 2.25 |

Year-by-year:

| Year | DNN | Baseline | Diff |
|------|-----|----------|------|
| 2019 | -11.2% | +2.3% | -13.5% |
| 2020 | +284.7% | +401.3% | -116.6% |
| 2021 | +30.6% | +22.2% | +8.5% |
| 2022 | +0.0% | -8.1% | +8.1% |
| 2023 | +20.5% | +19.6% | +0.9% |
| 2024 | +41.6% | +42.4% | -0.8% |

The DNN does not beat simple momentum. Baseline is stronger on Sharpe (1.28 vs
1.17) and MaxDD (-38% vs -49%). DNN has a modest edge in 2021-2022 but worse
in 2019-2020 when its predictions are least calibrated (early walk-forward windows
have the least training data).

---

## Conclusion

The 10-step improvements validated the hypothesis that data scarcity was the
primary failure mode. With 3× more training data (33k+ obs vs ~5k) and a
regularised ensemble model, IC jumped from zero to a statistically significant
0.025.

However, **IC of 0.025 is not sufficient to beat simple momentum ranking**.
The DNN adds predictive signal but not enough to overcome its disadvantage vs
a simpler and more stable rule. The baseline's straightforward rank-by-12m-return
is extremely hard to beat in small-universe, short-history settings.

---

## Next steps

### 1. Add short leg to DNN portfolio
The backtest only used the long leg. Adding a short on bottom-decile DNN
predictions might improve Sharpe — the DNN may be better at identifying
low-expected-return stocks than high ones.

### 2. Combine DNN signal with momentum signal
Rather than DNN-only or momentum-only, blend the two:
- DNN expected return as one signal, 12m momentum as another
- Long stocks where both agree (top decile on both); short where both agree bottom
- This captures the DNN's 2021/2022 edge while retaining momentum's 2019/2020
  reliability

### 3. Improve label quality
- Switch from decile classification to direct return regression (MSE loss) —
  avoids discretisation noise from the bin boundaries
- Or binary classification: top/bottom half only (less label noise, simpler task)

### 4. Add transaction cost and signal gate
The backtest has no TC. With 420 stocks monthly, turnover is high. Apply the
signal gate from idea 002 (skip if cross-sectional spread < threshold) and
10bps TC — likely to hurt Sharpe significantly and would be a fairer comparison.

### 5. Reconsider universe scope
Small/AIM stocks drive the extreme returns (2020: +284% DNN, +401% baseline).
These are likely not tradeable at scale. Restricting to FTSE 350 only (more
liquid) may give a cleaner test of whether the DNN adds value over momentum in
a realistic portfolio.
