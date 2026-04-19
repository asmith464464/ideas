## Overview

A nine-version investigation into the Piotroski F-Score — one of the most cited signals in quantitative investing — applied to the IWM small-cap universe using SEC EDGAR point-in-time financials. The headline result is surprising: **the F-Score itself does not add alpha**. Every unit of outperformance comes from the first stage of Piotroski's original methodology: the value screening.

The final strategy is a pure **value bucket** — equal-weight all IWM small-caps in the bottom 30% by P/B, rebalanced event-driven on 10-K EDGAR filing dates.

{{ metric:ann_return_pct | label=Ann. Return (2012–2026) | suffix=% }}
{{ metric:sharpe_ratio | label=Sharpe Ratio }}
{{ metric:iwm_ann_return_pct | label=IWM Ann. Return | suffix=% }}
{{ metric:total_return_pct | label=Total Return | suffix=% }}

---

## The Piotroski F-Score

Joseph Piotroski's 2000 paper showed that within the universe of high book-to-market (low P/B) stocks, a simple nine-point quality score could separate future winners from losers. The nine signals span three pillars:

| Pillar | Signal | Formula |
|---|---|---|
| **Profitability** | F1: ROA > 0 | net_income / avg_assets > 0 |
| | F2: CFO > 0 | operating_cash_flow > 0 |
| | F3: ΔROA > 0 | ROA improved YoY |
| | F4: Accruals | CFO/assets > ROA |
| **Leverage** | F5: ΔLeverage < 0 | long_term_debt/assets decreased |
| | F6: ΔLiquidity > 0 | current_ratio increased |
| | F7: No dilution | shares outstanding didn't increase |
| **Efficiency** | F8: ΔGross Margin > 0 | gross_margin improved |
| | F9: ΔAsset Turnover > 0 | revenue/assets improved |

Total score F = 0–9. Original paper: **Long F≥8, Short F≤2**, but only *within the high book-to-market bucket*. Most implementations miss this critical pre-condition — applying P/B as a concurrent filter alongside F-Score rather than as a prior screening step — and that mistake breaks the strategy entirely.

---

## Data Infrastructure

All financials are sourced from the **SEC EDGAR XBRL API** — free, no key required. Each 10-K filing record contains a `filed` date: the exact day the filing became public. Using this instead of fiscal year-end eliminates look-ahead bias entirely.

```
https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
```

Price history comes from yfinance. Universe is the current IWM ETF holdings (top 300 by weight), minus Financials and Real Estate. The P/B cutoff is cross-sectional and regime-relative: computed monthly from all filings in the trailing 12 months, so it automatically adjusts to the live universe.

---

## Equity Curve

{{ chart:equity_curve | caption=Cumulative return of the value bucket vs IWM and SPY (2012–2026). Beat IWM in 13 of 14 calendar years. }}

---

## Annual Returns

{{ chart:annual_returns | caption=Year-by-year return of the value bucket vs IWM. The strategy posted positive returns in every year IWM was positive, and outperformed in bear years (2018, 2022). }}

---

## The Arc: Nine Versions

{{ chart:version_progression | caption=Sharpe ratio across all nine strategy versions. The breakthrough was v3 (two-stage filter). v6 is an outlier — it only fired 98 days across 14 years. The final answer is v9: core value bucket with no F-Score overlay. }}

### v1–v2: Wrong Universe, Wrong Filter Logic

**v1** (S&P 100 large-caps, Sharpe −0.46): The short book was dominated by Goldman Sachs, Morgan Stanley, and Citigroup. Financial companies score low on F-Score by design — their leverage is their business model, not a red flag.

**v1b** (large-caps minus financials, Sharpe −0.35): Short book now contains energy stocks (CVX, VLO, COP) at commodity cycle lows. Low F-Score in a cyclical downturn is noise. These stocks recovered +109% while sitting in the short book.

**v2** (IWM small-caps, P/B filter applied concurrently, Sharpe −0.32): Applying `F≥8 AND P/B < 40th pctile` as a simultaneous requirement starved the long book. Zero long positions for the first four years. High-quality companies almost never have low P/B — the market prices them accordingly.

### v3: The Breakthrough — Two-Stage Filter

Implementing Piotroski's methodology exactly: first restrict the universe to cheap stocks, then apply F-Score within that bucket. P/B cutoff is computed cross-sectionally each month, regime-relative.

**Sharpe: 1.10 | Ann: +33.2% | Max DD: −52.8%**

Long book now populates. But immediately a pattern emerges: the value bucket alone (Sharpe 1.24) outperforms the F-Score filtered long book (Sharpe 1.10). Concentration risk — often 1–2 positions — drives the difference.

### v4–v5: Tightening Everything, Same Problem

**v4** (F≥7, P/B bottom 20%, liquidity filter): Sharpe 0.72, Max DD **−90.5%**. MUR (Murphy Oil) became the sole long position for four years. A one-stock long book has no diversification.

**v5** (+2-day entry lag, 375-day signal expiry, 25% sector cap): Sharpe 0.83, Max DD still −90.5%. Sector caps can't protect a one-stock book.

**Key insight:** The −90% drawdown is a portfolio construction problem, not a signal problem.

### v6: Best Sharpe, Worst Practicality

Added minimum position floor (≥3 simultaneous), vol-inverse sizing (1/realized_vol), and 200-day MA momentum filter.

**Sharpe: 2.24 | Max DD: −8.5% | Active: 98 days in 14 years**

The drawdown problem solved. But the strategy fired for only **98 trading days** — 6 per year on average. The combination of requirements almost never aligns.

### v7: Breadth via Dilution

Step-down F-Score (prefer F≥8, fill to F≥7, then F≥6) to recover activity.

**Sharpe: 0.81 | Max DD: −78.1% | Active: 2,263 days**

Breadth recovered, but F-Score add-on turned **negative** (−2.3% ann). F=6 stocks filling the minimum position count are mediocre businesses, not quality turnarounds. Including them degrades the portfolio.

### v8: Core + Satellite Architecture

80% always in value bucket (core), 20% tilted to F≥8 sniper (satellite) when ≥3 qualify.

**IR: −0.799** (satellite return vs core). In both years the satellite fired (2025, 2026), it dragged the composite below the pure core:

- 2025: sleeve +58.7% vs core +75.5%
- 2026: sleeve +182.5% vs core +205.0%

### v9: Core Only — The Final Answer

Remove the satellite entirely. Pure value bucket, equal-weight, always invested.

{{ metric_table }}

---

## Why F-Score Doesn't Add Alpha Here

Across all nine configurations, the value bucket Sharpe consistently matched or exceeded the F-Score-filtered subset:

| Config | Value Bucket Sharpe | Signal Sharpe | F-Alpha |
|---|---|---|---|
| v3: F≥8, P/B<30% | 1.24 | 1.10 | −0.14 |
| v4: F≥7, P/B<20% | 1.34 | 0.72 | −0.62 |
| v5: + mitigations | 1.43 | 0.83 | −0.60 |
| v8: core+sat sleeve | 1.33 | 0.40 (sat) | −0.93 |
| **v9: core only** | **1.33** | — | — |

Three possible explanations:

1. **Arbitrage:** Piotroski's original sample was 1976–1996. The signal became widely known after the 2000 paper and may have been arbitraged away in small-caps where institutional capacity is limited but quant attention is high.

2. **Survivorship:** The IWM universe is pre-filtered for survival. Companies that scored F≤2 and went bankrupt are absent from the short book, understating the short-side returns that make the L/S strategy work.

3. **Sample size:** F≥8 is rare (~3% of filings). On 300 stocks, that's ~9 events per year. Too small to distinguish signal from noise — idiosyncratic concentration risk dominates.

The P/B screen, by contrast, covers ~30% of stocks (~80–90 positions at any time). Diversification lets the underlying factor — cheap small-caps — express itself without single-stock blow-ups.

---

## Limitations

- **Survivorship bias** is real and unresolved. The results overstate what was achievable in real-time 2012–2014 when the IWM universe included companies that subsequently went bankrupt.
- **Max drawdown of {{ metric:max_drawdown_pct | label=Max Drawdown | suffix=% | positive_is_good=false }}** is severe. COVID 2020 and the 2022 growth selloff both hit cheap small-caps hard. A market regime filter would reduce this at the cost of tracking error.
- **Transaction costs** are unmodelled. Equal-weight across 80+ stocks with event-driven rebalancing implies substantial turnover.
- **Capacity:** IWM small-caps can be illiquid. The $1M daily ADV filter excludes the most illiquid names but not all capacity constraints.
