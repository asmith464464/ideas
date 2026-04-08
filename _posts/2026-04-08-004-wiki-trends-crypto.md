---
layout: idea
title: "Wikipedia Attention Cluster Strategy"
slug: "004-wiki-trends-crypto"
idea_id: "004"
version: "0.2.0"
status: "published"
tags:
  - crypto
  - momentum
  - attention
  - long-only
  - weekly
date_range_start: "2020-01-01"
date_range_end: "2026-01-02"
---

## Overview

A long-only crypto strategy that uses **Wikipedia pageviews as a proxy for retail attention**, allocates across **five fundamental peer-group clusters**, and tilts within each cluster toward the highest-momentum coin.

Backtested Jan 2020 – Jan 2026 across 37 cryptocurrencies, at 10bps per-side transaction costs:

<div class="stat-card">
  <div class="stat-label">Sharpe Ratio</div>
  <div class="stat-value positive">1.69</div>
</div>
<div class="stat-card">
  <div class="stat-label">CAGR</div>
  <div class="stat-value positive">+188.9%</div>
</div>
<div class="stat-card">
  <div class="stat-label">Max Drawdown</div>
  <div class="stat-value positive">-73.9%</div>
</div>
<div class="stat-card">
  <div class="stat-label">Downside Capture vs EW</div>
  <div class="stat-value positive">0.86</div>
</div>

---

## Locked Configuration

```
Signal:       14-day change in Wikipedia pageviews
              pct_change(14).clip(-5, 5), sampled weekly (W-FRI)
Clusters:     5 predefined peer groups
Portfolio:    Equal weight across clusters (20% each)
Tilt:         Within-cluster momentum Z-score (tilt = 1.0)
Z-penalty:    None
Rebalance:    Weekly (Friday close / next open)
Costs:        10bps base case (20bps stress)
Position cap: None (observed max ~18%)
```

### Clusters

| Cluster | Members |
|---------|---------|
| **old_guard** | BTC, LTC, BCH, ETC, XLM, DASH, ZEC |
| **L1_new** | ETH, SOL, AVAX, ATOM, DOT, NEAR, ALGO, TRX |
| **DeFi** | LINK, UNI, MKR |
| **meme** | DOGE, SHIB |
| **event_risk** | LUNA, FTT |

The key idea is **diversifying across attention regimes**, not correlations. Each cluster reflects a different narrative, investor base, and news cycle.

---

## Methodology

### Data: Wikipedia pageviews

Wikipedia traffic provides a clean, free proxy for retail attention:

- Daily data back to 2015
- No rate limits or API keys
- Includes failed/delisted coins (LUNA, FTT)
- No cross-asset normalisation required

It captures real spikes in interest (e.g. FTX collapse peaked at 44k views on collapse day) without the fragility of Google Trends.

### Signal: 14-day attention momentum

For each coin:

```
momentum = (views[t] / views[t-14] - 1).clip(-5, 5)
```

Sampled weekly. The 14-day window is optimal — fast enough to react to narrative shifts, stable enough to avoid single-day spike noise.

### Portfolio construction: cluster tilt

1. Assign equal base weight (20%) to each cluster
2. Compute cross-sectional momentum Z-scores within each cluster
3. Tilt each coin's weight by: `w = (base/n) × (1 + tilt × CS_Z)`
4. Clip to long-only (≥0), renormalise

Every asset remains in the portfolio, but weights adjust dynamically toward higher-attention coins within each peer group.

---

## Performance

### Summary vs benchmarks

| Metric | Strategy | Equal-weight | BTC hold |
|--------|----------|--------------|----------|
| CAGR | **+188.9%** | +109.1% | +51.2% |
| Volatility | 112.0% | 83.1% | 62.0% |
| Sharpe | **1.69** | 1.31 | 0.83 |
| Max drawdown | -73.9% | -65.9% | -74.2% |
| Downside capture vs EW | **0.86** | 1.00 | — |

### By year

| Year | Strategy | Equal-weight | BTC | Alpha vs EW |
|------|----------|--------------|-----|-------------|
| 2020 | +159% | +277% | +236% | -118% |
| 2021 | +3200% | +1994% | +88% | +1206% |
| 2022 | **-42%** | -57% | -64% | **+15%** |
| 2023 | +608% | +183% | +154% | +425% |
| 2024 | +129% | +51% | +124% | +78% |
| 2025 | -26% | -43% | -7% | **+17%** |

Beat EW in 4 of 6 calendar years. The 2020 miss reflects a broad alt bull run where equal-weight captures more of the tail. Elsewhere the strategy adds value, particularly in selective environments (2022, 2023, 2024, 2025).

### Rolling 2-year windows

| Period | Strategy Sharpe | EW Sharpe | Alpha (CAGR) |
|--------|----------------|-----------|--------------|
| 2020–21 | 8.39 | 7.55 | +409% |
| 2021–22 | 2.75 | 1.86 | +227% |
| 2022–23 | 0.41 | 0.15 | +34% |
| 2023–24 | 2.66 | 1.56 | +141% |
| 2024–25 | 0.33 | -0.10 | +27% |

Positive alpha in every two-year window, including the 2022–23 crypto winter.

---

## Robustness

### Permutation test (n=200)

Random cluster assignments (same sizes, random coins) produced mean Sharpe 0.80, 95th percentile 1.28. Hand-picked clusters produced **Sharpe 1.61**. p-value: **0.000** — beats 100% of random groupings.

The cluster structure is statistically significant. Not any grouping of 37 coins into 5 buckets produces this result.

### Out-of-sample (Jan 2024 – Jan 2026)

| | Strategy | Equal-weight |
|--|--|--|
| CAGR | **+19.8%** | -5.9% |
| Sharpe | **0.34** | -0.09 |

Altcoin bear market (rising BTC dominance). Strategy positive; EW negative.

### Cluster stress tests

| Perturbation | Sharpe |
|---|---|
| Baseline (5 clusters) | 1.71 |
| Drop DeFi | 1.11 (−0.60) |
| Drop meme | 1.45 (−0.26) |
| Drop old_guard | 1.83 (+0.12) |
| Merge old_guard + L1_new | 1.69 |
| 8 granular clusters | 1.24 |

DeFi is the most critical cluster. Too many clusters converge toward equal-weight.

---

## Execution Analysis

### Turnover

- Weekly one-way: ~59% of portfolio weight
- Annualised: ~3,083% one-way
- Cost drag at 10bps: **3.1%/year**

### Cost sensitivity

| Cost | Sharpe | CAGR |
|------|--------|------|
| 0bps | 1.77 | +199% |
| 10bps | **1.69** | +189% |
| 20bps | 1.60 | +179% |
| 30bps | 1.46 | +172% |

Survives 30bps — viable on major CEX spot markets.

### Rebalance frequency at 10bps

| Frequency | Sharpe |
|-----------|--------|
| Weekly | **1.61** |
| Biweekly | 1.44 |
| Monthly | 1.26 |

Weekly is clearly optimal. Monthly drops to near-EW Sharpe.

---

## Limitations

- Universe implicitly filtered to coins with Wikipedia pages
- Some assets reflect niche technical communities rather than retail attention (VET, ICP, NEO show negative IC)
- Smaller coins may pose liquidity constraints at scale
- Reliance on a single free data source
- 2020 underperformance shows the strategy can miss broad bull runs that lift all assets equally
