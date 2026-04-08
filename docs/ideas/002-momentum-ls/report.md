## Overview

This strategy constructs a **market-neutral long/short portfolio** of FTSE 100 and historical constituents, ranking stocks on a **risk-adjusted momentum score across three horizons** (1–3m, 6–12m, 12–18m). Positions are allocated via a **packet-based scheme**: top-ranked stocks receive full long weight, the next tier fades long, the bottom tier fades short, and the lowest-ranked stocks are fully short.

To reduce unnecessary trading and transaction costs, a **signal-quality gate** skips rebalancing when momentum dispersion across stocks is low. Portfolio exposure is scaled dynamically with a **continuous volatility target**, and positions are filtered by a **minimum absolute 12-month return** to focus on high-conviction momentum. Monthly rebalancing captures fresh momentum while avoiding short-term reversal noise.

**Key mechanics in brief:**
- **Momentum scoring:** risk-adjusted 3-horizon composite
- **Packet allocation:** top/bottom bins with fade zones for intermediate ranks
- **Signal gate:** skip weak-signal months
- **Vol targeting:** scale positions by realized volatility (15-day lookback)
- **Absolute filter:** require ≥1% 12m return for longs, ≤−1% for shorts

Backtested on ~102 FTSE 100 and historical constituents, 2013–2024, assuming 10bps per-side transaction costs:

{{ metric: sharpe_ratio }}
{{ metric: annualised_return_pct }}
{{ metric: max_drawdown_pct }}
{{ metric: sortino_ratio }}

---

## Signal Construction

The momentum score is a weighted sum of three risk-adjusted return horizons. The most recent month is excluded to avoid short-term reversal effects.

```
momentum_score = 0.20 × (ret_1–3m / vol_1–3m)
               + 0.50 × (ret_6–12m / vol_6–12m)
               + 0.30 × (ret_12–18m / vol_12–18m)
```

| Component | Window                       | Weight |
| --------- | ---------------------------- | ------ |
| Short     | 1–3 months (skip last month) | 20%    |
| Medium    | 6–12 months                  | 50%    |
| Long      | 12–18 months                 | 30%    |

Each return is divided by realised volatility over the same period to prevent high-volatility stocks from dominating rankings.

---

## Portfolio Construction

At each rebalance:

* Stocks are ranked by momentum score.
* Weights are allocated using a **fade-zone (“packet”) scheme**: top 10% fully long, next 10% faded long, next 10% faded short, bottom 10% fully short.
* Long and short legs are normalized to 100% gross exposure.
* A **5% buffer rule** reduces small weight changes, cutting micro-turnover.

---

## Development Journey

The strategy evolved in stages, each improving risk-adjusted performance:

### Stage 1 — Baseline Signal

* Raw composite signal with monthly rebalancing, no TC.
* Gross Sharpe ~0.33, concentrated in 2013–2015.
* Applying 10bps TC reduced Sharpe to ~0.25.

### Stage 2 — Volatility Target & Absolute Momentum Filter

* **Continuous vol targeting:** scales exposure daily based on actual portfolio volatility over the prior 15 days.
* **Absolute momentum filter:** ignores stocks with <1% absolute 12-month return (long) or >−1% (short).
* These improvements address mis-scaled exposure in volatile periods and eliminate ambiguous signals.
* Sharpe improved to ~0.37.

### Stage 3 — Signal Gate

* At each rebalance, the p90–p10 cross-sectional momentum spread is compared to the 40th percentile of its historical distribution. If below, the rebalance is skipped.
* ~40% of monthly rebalances were skipped, reducing trading in low-signal environments.
* Sharpe jumped from 0.37 → 0.52, with normal-regime Sharpe rising from 0.08 → 0.42.

### Stage 4 — Final Tuning

* Vol target raised 10% → 12%; lookback shortened 20d → 15d.
* Absolute momentum threshold set at ±1%, focusing exposure on stronger signals.
* Final Sharpe 0.58, annualized return 10.4%, MaxDD −34.1%, Sortino 0.55 (using 2% p.a. risk-free rate).

---

## Final Configuration

| Parameter         | Value                                       |
| ----------------- | ------------------------------------------- |
| Universe          | ~102 FTSE 100 + historical constituents     |
| Signal            | Weighted risk-adjusted momentum, 3 horizons |
| Rebalance         | Monthly, last trading day                   |
| Packets           | Base 10/20% fade                            |
| Buffer rule       | 5% weight-change threshold                  |
| Signal gate       | Skip if spread < expanding p40              |
| Vol target        | 12%, 15-day lookback                        |
| Abs filter        | Long ≥ +1% 12m; Short ≤ −1% 12m             |
| Transaction costs | 10bps per side                              |

---

## Performance

{{ chart: equity_curve | caption="Final config cumulative return vs FTSE 100, indexed to 100" }}
{{ chart: annual_returns | caption="Annual returns, final configuration" }}
{{ chart: drawdown | caption="Drawdown from peak, final configuration" }}
{{ metric_table }}

---

## Limitations

* **In-sample optimization:** parameters (gate p40, vol lookback, vol target, abs threshold) were grid-searched across 2013–2024. Out-of-sample Sharpe will likely be lower.
* **2013–2015 concentration:** most cumulative returns came from post-GFC persistent momentum; later years show smaller, low-single-digit returns.
* **Survivorship bias:** excludes delisted/acquired stocks without surviving tickers. Pre-acquisition momentum is missing, likely causing a modestly positive bias.
* **Risk-free rate:** Sharpe and Sortino use a flat 2% p.a. approximation of the BoE base rate average over 2013–2024. The true rate ranged from ~0.1% (2013–2021 ZIRP) to ~5.25% (2023 peak). A time-varying series would require an external data feed; the flat rate understates the hurdle in recent high-rate years.
* **Transaction costs:** 10bps per side assumes block trading in large-caps; real costs (spread, impact, commission) may reach 20bps, reducing Sharpe.
* **Data quality:** yfinance adjusted prices were sometimes imperfect; ±75%/day return cap used to mitigate dodgy data.
* **Short-selling frictions:** no borrow costs modeled; 25–75bps annual short costs may reduce returns.
