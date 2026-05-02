# 007 Heston Vol Strategy — Iteration Log

## Strategy Thesis

The Heston model couples price and variance via the correlation parameter ρ.
When ρ is significantly negative (crypto panic, equity leverage effect), a
deviation of realized variance from the long-term mean θ carries a directional
price implication — not just a volatility implication.

**Core signal logic:**
- Estimate {κ, θ, σ, ρ} by fitting CIR OLS to a GJR-GARCH conditional variance path
- When ν deviates > z_threshold standard deviations from θ AND Feller holds AND ρ < 0:
  - HIGH-VOL (ν >> θ, ρ < 0): vol reverts DOWN → price rises → LONG
  - LOW-VOL (ν << θ, ρ < 0): vol reverts UP → price falls → SHORT
- Hold for calibrated half-life (ln(2)/κ), exit early when z-score reverts past EXIT_Z

**Why crypto:**
- BTC/ETH 24/7 hourly gives ~17,500 bars/2y vs ~5,000 for equities — 3.5× more data
- Genuine negative ρ during fear/panic regimes
- High vol-of-vol → large z-score excursions → more signals

---

## Run 1 — 2026-04-21 (BTC-USD, CALIB_WINDOW=500, SIGNAL_ZSCORE=2.0)

**Config:** BTC-USD 1h 730d, GJR-GARCH, CALIB_WINDOW=500/step=50, SIGNAL_ZSCORE=2.0, EXIT_Z=0.5, RHO<-0.05, TC=10bps

| Metric | Value |
|--------|-------|
| Bars | 16,859 |
| Calibration windows | 328 |
| Feller satisfied | 73.5% |
| Median rho | -0.014 |
| Mean half-life | 2,842 bars (118 days) |
| Entry signals | 1,194 (long: 392, short: 802) |
| Actual trades | 29 |
| Time invested | 14.3% |
| Strategy Sharpe (net) | **0.878** |
| B&H Sharpe | 0.113 |
| Long bps/bar | +0.84 |
| Short bps/bar | +1.93 |

**Diagnosis:**
- Both legs positive immediately. BTC has enough vol-clustering and negative rho during fear events.
- Half-life 118 days is too long — κ is very small (median 0.0006). This means positions hold for months and rarely cycle.
- Only 29 actual trades despite 1,194 entry signals — signals cluster within long hold periods.
- Median rho = -0.014: very small. Only 26.9% of bars satisfy RHO < -0.05. The neg rho filter is the binding constraint.

**Fix (Run 2):**
1. Shrink CALIB_WINDOW to 168 (1 week of hourly crypto) — much more responsive κ/θ
2. Reduce SIGNAL_ZSCORE to 1.5 — more trades
3. Tighten RHO_THRESHOLD to -0.02 — let more bars through (median is -0.014)

---

## Run 2 — 2026-04-21 (CALIB_WINDOW sweep + universe)

| Config | BTC SR(net) | ETH SR(net) | SOL SR(net) |
|--------|-------------|-------------|-------------|
| WINDOW=168, Z=1.5 | -2.359 | - | - |
| WINDOW=336, Z=2.0 | -1.367 | - | - |
| WINDOW=500, Z=2.0, RHO<-0.02 | **+0.398** | -0.556 | -0.080 |

**Structural diagnosis — crypto Heston degeneration:**

All three crypto assets share the same fundamental problem:

- **κ collapses to near-zero**: median κ = 0.0006–0.003 across all assets and window lengths
- **Half-life = 63–118 days**: crypto conditional variance is extremely persistent. The CIR calibration sees almost no mean reversion speed.
- **Practical consequence**: hold periods of months, few actual trades, strategy is essentially a slow-moving momentum bet, not a vol mean-reversion strategy.

The Heston model assumes variance is stationary (mean-reverting). Crypto variance is highly persistent — arguably integrated rather than stationary over short windows. The CIR OLS extracts κ ≈ 0 because the data doesn't exhibit the fast reversion the model assumes.

BTC is the only positive result (+0.398 SR) and only with WINDOW=500. This likely reflects the 2024-2025 bull market rather than a robust edge — ETH and SOL are negative over the same period.

**Conclusion:** The Heston framework as implemented (GJR-GARCH + CIR OLS) does not produce reliable calibration on crypto hourly data. The variance process is too persistent for the CIR mean-reversion assumption to hold over tractable horizons.

**Next direction:**
- Return to equity indices (SPX, NDX) where the leverage effect gives genuine ρ ≈ -0.5 and κ produces half-lives of days not months
- Or: use a different vol proxy (realised vol from tick data, or VIX for SPX) rather than GARCH conditional variance — GARCH on crypto may be producing a near-unit-root variance path

---

## Run 3 — 2026-04-22 (SPX+VIX single-asset, max history)

**Config:** SPY/^VIX daily max (~1993-2026), CIR on VIX levels, Z=1.5, EXIT_Z=0.5, RHO<-0.1, TC=2bps

| Metric | Value |
|--------|-------|
| Data | 8,362 bars |
| Calibration windows | 387 |
| Feller satisfied | 99% |
| Median rho | -0.808 |
| Half-life | 8.8 days |
| Time invested | 14.2% (Z=1.5, EXIT_Z=0.5) |
| SR(xrf) | 0.172 |
| SR(invested) | 0.59 |
| Best config | Z=2.0, EXIT_Z=0.0 → SR=0.309, invested=12.3% |

**Key finding:** The SPX+VIX signal is genuine and positive across all configurations. SR(invested) is 0.59–0.79 depending on threshold. But the structural dilution `SR ≈ √(f) × SR(invested)` caps overall SR at ~0.31 because the signal is only active ~12–15% of the time (by design — it only fires at extreme VIX).

---

## Run 4 — 2026-04-22 (Multi-index portfolio: SPY/VIX, QQQ/VXN, GLD/GVZ)

**Hypothesis tested:** Multiple uncorrelated vol cycles across indices should increase invested time without sacrificing signal quality, breaking the time-dilution constraint.

**Config:** SPY/^VIX + QQQ/^VXN + GLD/^GVZ, daily max, CIR per pair, Z=2.0, EXIT_Z=0.0, TC=2bps

| Pair | Invested% | bps/day | SR(invested) |
|------|-----------|---------|--------------|
| SPY/VIX | 10.0% | +5.25 | — |
| QQQ/VXN | 13.2% | +3.97 | 0.29 |
| GLD/GVZ | 3.8% | +9.09 | 1.01 |
| **Portfolio** | **15.0%** | **+12.45** | **0.98** |

| Metric | Value |
|--------|-------|
| Portfolio SR(xrf) | **0.354** |
| SR(active) | 0.98 |
| Time invested | 15.0% |

**Diagnosis:** The multi-index approach improves SR from 0.31 (single-asset) to 0.35. SR(active) is nearly 1.0 at Z=2.0 — the signal quality is high. But the fundamental constraint is unchanged: `SR ≈ √(0.15) × 0.98 ≈ 0.38`. Reaching SR=1.0 would require ~100% time invested at this signal quality — impossible for an extremes-based entry signal.

**Structural conclusion:** The Heston CIR signal on index implied vol produces a genuine, economically-grounded edge. It cannot reach Sharpe ≥ 1 as a tactical overlay on cash because:
1. The signal only fires at extreme vol (z > 2) — correct by design
2. High SR(active) and high time-invested are in direct tension (lowering threshold adds noise)
3. The √(f) dilution factor caps overall SR at ~0.3–0.4

**Options:**
- Accept SR ≈ 0.35 and publish — modest but genuine edge with clear economic rationale
- Reformulate as a volatility risk premium strategy (always invested, sizing by signal strength)
- Combine with a complementary always-invested strategy

---

## Run 5 — 2026-04-22 (VRP cross-sectional, 3-asset, intersection)

**Hypothesis shift:** Replace the binary CIR z-score signal with a continuous VRP signal. VRP = implied_vol - realised_vol is the direct market expression of the Heston deviation — when implied vol exceeds realised vol, the market overprices future variance, which via ρ < 0 implies positive expected returns. Always invested proportional to signal strength; no binary thresholds.

**Config:** SPY/^VIX + QQQ/^VXN + GLD/^GVZ, daily max (intersection ~2008-2026), RV_WINDOW=20, RHO_WINDOW=60, REBAL_STEP=21 (monthly), TC=2bps

| Metric | Value |
|--------|-------|
| Period | 2008-08-27 to 2026-04-22 |
| Strategy SR(xrf) | **0.758** |
| Strategy Ann Ret | 13.27% |
| Strategy Max DD | -22.77% |
| EW B&H SR | 0.717 |
| EW B&H Max DD | -42.09% |
| Avg invested | 88% |
| TC drag | 0.14% ann |

**Per-pair allocations:**

| Pair | Avg weight | Avg VRP | Avg rho | rho<-0.1% |
|------|-----------|---------|---------|-----------|
| SPY/VIX | 41.6% | 3.7 | -0.820 | 100% |
| QQQ/VXN | 34.7% | 3.2 | -0.784 | 100% |
| GLD/GVZ | 11.7% | 2.7 | +0.067 | 35% |

**Key findings:**
- SR improved from 0.35 (binary signal) to 0.758 (continuous VRP)
- Max DD reduced from -42% (B&H) to -22.77% — natural de-risking when VRP goes negative during crashes
- GLD contributes via its negative-rho episodes (35% of time); rho filter correctly excludes it during safe-haven demand (positive-rho periods)
- The strategy beats B&H on both Sharpe and drawdown

**Experiments that did NOT improve SR:**
- Normalised VRP (z-score of VRP vs own 252d history): SR=0.346 — too conservative, goes to cash when VRP is positive but below its own average
- Union of dates (extending pre-2008): SR=0.458 — dot-com crash period hurts QQQ without GLD diversification
- MA200 filter added: SR=0.714 — reduces drawdown further (-17.24%) but costs more return than vol saved

**Conclusion:** SR=0.758 is the clean, reproducible result for this 3-asset strategy from 2008+. This likely represents close to the natural ceiling for this type of long-only equity VRP strategy without leverage or additional uncorrelated assets.

---
