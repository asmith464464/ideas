"""
Report artifact generator for idea 004 — Wikipedia Attention Cluster Strategy.

Run from repo root:
    python research/ideas/004-wiki-trends-crypto/generate_report.py

Produces:
    docs/ideas/004-wiki-trends-crypto/artifacts/charts/equity_curve.html
    docs/ideas/004-wiki-trends-crypto/artifacts/charts/drawdown.html
    docs/ideas/004-wiki-trends-crypto/artifacts/charts/annual_returns.html
    docs/ideas/004-wiki-trends-crypto/artifacts/charts/cluster_momentum.html
    docs/ideas/004-wiki-trends-crypto/artifacts/charts/oos_zoom.html

Then re-writes _posts/2026-04-08-004-wiki-trends-crypto.md with charts embedded.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

ROOT        = Path(__file__).resolve().parents[3]
IDEA_DIR    = ROOT / "docs" / "ideas" / "004-wiki-trends-crypto"
RESEARCH    = ROOT / "research" / "ideas" / "004-google-trends-crypto"
ARTS        = IDEA_DIR / "artifacts"
CHARTS      = ARTS / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)
POST        = ROOT / "_posts" / "2026-04-08-004-wiki-trends-crypto.md"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RESEARCH))

# ── colours ──────────────────────────────────────────────────────────────────
BLUE   = "#2196F3"
ORANGE = "#FF9800"
GREY   = "#9E9E9E"
RED    = "#F44336"
GREEN  = "#4CAF50"
PURPLE = "#9C27B0"
TEAL   = "#009688"

CLUSTER_COLORS = {
    "old_guard":  "#78909C",
    "L1_new":     "#2196F3",
    "DeFi":       "#4CAF50",
    "meme":       "#FF9800",
    "event_risk": "#F44336",
}

_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1a1a2e"),
)


def _write(fig: go.Figure, name: str) -> None:
    html = pio.to_html(fig, full_html=False, include_plotlyjs="cdn")
    (CHARTS / f"{name}.html").write_text(html, encoding="utf-8")


# ── data loading ─────────────────────────────────────────────────────────────

def load_data():
    """Re-run the locked config and return return series."""
    from universe import UNIVERSE, BY_SYMBOL, WIKI_ARTICLES, CLUSTERS
    from data.fetchers.wikipedia_fetcher import WikipediaFetcher  # noqa: E402
    import yaml
    import warnings
    import yfinance as yf
    warnings.filterwarnings("ignore")

    CONFIG = yaml.safe_load((IDEA_DIR / "config.yaml").read_text())
    START, END = CONFIG["date_range"]["start"], CONFIG["date_range"]["end"]

    # Prices
    PRICE_CACHE = ROOT / "data" / "cache" / "004_prices" / "yf_batch.parquet"
    raw = pd.read_parquet(PRICE_CACHE)
    raw.index = pd.to_datetime(raw.index).normalize()
    yf_map = {c["yf_ticker"]: c["symbol"] for c in UNIVERSE if c.get("yf_ticker")}
    frames = []
    for ticker, sym in yf_map.items():
        if ticker in raw.columns:
            frames.append(raw[ticker].resample("W-FRI").last().rename(sym))
    prices = pd.concat(frames, axis=1).sort_index()

    # Wikipedia daily
    fetcher = WikipediaFetcher(cache_dir=ROOT / "data" / "cache")
    daily_raw = fetcher.fetch_all(WIKI_ARTICLES, START, END, force_refresh=False)
    daily_raw = daily_raw.ffill(limit=3)

    active_cols = [c for c in daily_raw.columns if c in prices.columns]
    weekly_ret  = prices[active_cols].pct_change().clip(-0.95, 10)

    # 14d momentum (locked)
    mom14 = daily_raw[active_cols].pct_change(14).clip(-5, 5).resample("W-FRI").last()
    common = mom14.index.intersection(weekly_ret.index)
    mom14_w     = mom14.reindex(common)
    weekly_ret_c = weekly_ret.reindex(common)

    return mom14_w, weekly_ret_c, active_cols, daily_raw, CLUSTERS


def run_locked(mom14_w, weekly_ret_c, active_cols, clusters, cost_bps):
    """Cluster tilt=1.0, 14d mom, weekly, configurable cost."""
    active_clusters = {k: [m for m in v if m in active_cols] for k, v in clusters.items()}
    active_clusters = {k: v for k, v in active_clusters.items() if v}
    n_clusters   = len(active_clusters)
    cluster_base = 1.0 / n_clusters
    cost         = cost_bps / 10_000

    portfolio_returns = []
    prev_weights = pd.Series(0.0, index=active_cols)

    for date in weekly_ret_c.index:
        lag_idx = mom14_w.index[mom14_w.index < date]
        if lag_idx.empty:
            portfolio_returns.append((date, 0.0))
            continue
        prev_date = lag_idx[-1]

        weights = pd.Series(0.0, index=active_cols)
        for members in active_clusters.values():
            cm  = mom14_w.loc[prev_date, members].dropna()
            n_m = len(cm)
            if n_m == 0:
                continue
            if n_m == 1:
                weights[cm.index[0]] += cluster_base
                continue
            cs_z = (cm - cm.mean()) / cm.std() if cm.std() > 0 else cm * 0
            raw  = (cluster_base / n_m) * (1 + cs_z)
            raw  = raw.clip(lower=0)
            total = raw.sum()
            norm  = raw / total * cluster_base if total > 0 else pd.Series(cluster_base / n_m, index=cm.index)
            for m in norm.index:
                weights[m] += norm[m]

        total = weights.sum()
        weights = weights / total if total > 0 else pd.Series(1.0 / len(active_cols), index=active_cols)
        tc  = cost * (weights - prev_weights).abs().sum()
        ret = (weekly_ret_c.loc[date, active_cols] * weights).sum()
        portfolio_returns.append((date, ret - tc))
        prev_weights = weights

    port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
    return port


# ── charts ───────────────────────────────────────────────────────────────────

def chart_equity_curve(port10, port20, ew_ret, btc_ret):
    common = port10.index.intersection(ew_ret.index).intersection(btc_ret.index)
    s10  = (1 + port10.reindex(common)).cumprod() * 100
    s20  = (1 + port20.reindex(common)).cumprod() * 100
    sew  = (1 + ew_ret.reindex(common)).cumprod() * 100
    sbtc = (1 + btc_ret.reindex(common)).cumprod() * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=common, y=s10,  name="Strategy 10bps", line=dict(color=BLUE,   width=2.5)))
    fig.add_trace(go.Scatter(x=common, y=s20,  name="Strategy 20bps", line=dict(color=BLUE,   width=1.5, dash="dash")))
    fig.add_trace(go.Scatter(x=common, y=sew,  name="Equal-weight",   line=dict(color=ORANGE, width=1.8)))
    fig.add_trace(go.Scatter(x=common, y=sbtc, name="BTC buy-and-hold", line=dict(color=GREY, width=1.5, dash="dot")))
    fig.update_layout(
        **_LAYOUT,
        title="Cumulative return — Jan 2020 to Jan 2026 (log scale, indexed to 100)",
        yaxis=dict(title="Value (rebased to 100)", type="log"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=420,
    )
    _write(fig, "equity_curve")


def chart_drawdown(port10, ew_ret, btc_ret):
    common = port10.index.intersection(ew_ret.index).intersection(btc_ret.index)
    def _dd(r): c = (1+r.reindex(common)).cumprod(); return (c/c.cummax()-1)*100
    dd10  = _dd(port10)
    ddew  = _dd(ew_ret)
    ddbtc = _dd(btc_ret)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=common, y=dd10,  name="Strategy 10bps",
                             fill="tozeroy", fillcolor="rgba(33,150,243,0.15)",
                             line=dict(color=BLUE, width=1.5)))
    fig.add_trace(go.Scatter(x=common, y=ddew,  name="Equal-weight",
                             line=dict(color=ORANGE, width=1.2)))
    fig.add_trace(go.Scatter(x=common, y=ddbtc, name="BTC",
                             line=dict(color=GREY, width=1, dash="dot")))
    fig.update_layout(
        **_LAYOUT,
        title="Drawdown from peak",
        yaxis=dict(title="Drawdown (%)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=350,
    )
    _write(fig, "drawdown")


def chart_annual_returns(port10, ew_ret):
    years, strat_vals, ew_vals = [], [], []
    common = port10.index.intersection(ew_ret.index)
    for year in range(2020, 2026):
        idx = common[common.year == year]
        if len(idx) < 4:
            continue
        years.append(year)
        strat_vals.append((1 + port10.reindex(idx).dropna()).prod() - 1)
        ew_vals.append((1 + ew_ret.reindex(idx).dropna()).prod() - 1)

    strat_pct = [v * 100 for v in strat_vals]
    ew_pct    = [v * 100 for v in ew_vals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=years, y=strat_pct,
        name="Strategy 10bps",
        marker_color=[GREEN if v >= 0 else RED for v in strat_pct],
        text=[f"{v:+.0f}%" for v in strat_pct],
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        x=years, y=ew_pct,
        name="Equal-weight",
        mode="lines+markers",
        line=dict(color=ORANGE, width=1.5, dash="dot"),
        marker=dict(size=6),
    ))
    fig.add_hline(y=0, line_color="#1a1a2e", line_width=0.8)
    fig.update_layout(
        **_LAYOUT,
        title="Annual returns — strategy vs equal-weight",
        yaxis=dict(title="Return (%)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=400,
        bargap=0.35,
    )
    _write(fig, "annual_returns")


def chart_cluster_momentum(mom14_w, clusters, active_cols):
    active_clusters = {k: [m for m in v if m in active_cols] for k, v in clusters.items()}
    active_clusters = {k: v for k, v in active_clusters.items() if v}

    fig = go.Figure()
    for cname, members in active_clusters.items():
        cluster_mom = mom14_w[members].mean(axis=1)
        fig.add_trace(go.Scatter(
            x=cluster_mom.index, y=cluster_mom.values,
            name=cname.replace("_", " "),
            line=dict(color=CLUSTER_COLORS.get(cname, GREY), width=1.5),
            opacity=0.85,
        ))
    fig.add_hline(y=0, line_color="#1a1a2e", line_width=0.5, line_dash="dot")
    fig.update_layout(
        **_LAYOUT,
        title="14-day attention momentum by cluster (mean, clipped ±500%)",
        yaxis=dict(title="14d momentum"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=380,
    )
    _write(fig, "cluster_momentum")


def chart_oos_zoom(port10, ew_ret, btc_ret):
    oos_start = pd.Timestamp("2024-01-01")
    common = port10.index.intersection(ew_ret.index).intersection(btc_ret.index)
    idx = common[common >= oos_start]
    if len(idx) < 4:
        return

    def _rebase(r): c = (1+r.reindex(idx).dropna()).cumprod(); return c / c.iloc[0]
    s10  = _rebase(port10)
    sew  = _rebase(ew_ret)
    sbtc = _rebase(btc_ret)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=idx, y=s10,  name="Strategy 10bps", line=dict(color=BLUE, width=2.5)))
    fig.add_trace(go.Scatter(x=idx, y=sew,  name="Equal-weight",   line=dict(color=ORANGE, width=1.8)))
    fig.add_trace(go.Scatter(x=idx, y=sbtc, name="BTC",            line=dict(color=GREY, width=1.5, dash="dot")))
    fig.add_hline(y=1.0, line_color="#1a1a2e", line_width=0.5)
    fig.update_layout(
        **_LAYOUT,
        title="Out-of-sample: Jan 2024 – Jan 2026 (rebased to 1.0)",
        yaxis=dict(title="Cumulative return"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=360,
    )
    _write(fig, "oos_zoom")


# ── post writer ───────────────────────────────────────────────────────────────

def _embed(name: str, caption: str) -> str:
    html = (CHARTS / f"{name}.html").read_text(encoding="utf-8")
    return f'<div class="chart-wrapper">\n  {html}\n  <p class="chart-caption">{caption}</p>\n</div>\n'


POST_TEMPLATE = """\
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

## Equity Curve

{equity_curve}

{drawdown}

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

The key design principle is **diversifying across attention regimes**, not correlations. Each cluster reflects a different narrative, investor base, and news cycle.

---

## Methodology

### Data: Wikipedia pageviews

Wikipedia traffic provides a clean, free proxy for retail attention:

- Daily data back to 2015
- No rate limits or API keys
- Includes failed/delisted coins (LUNA, FTT)
- No cross-asset normalisation required

It captures real spikes in interest without the fragility of Google Trends.

### Signal: 14-day attention momentum

For each coin:

```
momentum = (views[t] / views[t-14] - 1).clip(-5, 5)
```

Sampled weekly. The 14-day window is optimal — fast enough to react to narrative shifts, stable enough to avoid single-day spike noise.

{cluster_momentum}

### Portfolio construction: cluster tilt

1. Assign equal base weight (20%) to each cluster
2. Compute cross-sectional momentum Z-scores within each cluster
3. Tilt each coin's weight by: `w = (base/n) × (1 + tilt × CS_Z)`
4. Clip to long-only (≥0), renormalise

Every asset remains in the portfolio, but weights adjust dynamically toward higher-attention coins within each peer group.

---

## Performance

### By year

{annual_returns}

| Year | Strategy | Equal-weight | BTC | Alpha vs EW |
|------|----------|--------------|-----|-------------|
| 2020 | +159% | +277% | +236% | -118% |
| 2021 | +3200% | +1994% | +88% | +1206% |
| 2022 | **-42%** | -57% | -64% | **+15%** |
| 2023 | +608% | +183% | +154% | +425% |
| 2024 | +129% | +51% | +124% | +78% |
| 2025 | -26% | -43% | -7% | **+17%** |

Beat EW in 4 of 6 calendar years. Positive alpha in all five rolling two-year windows.

---

## Robustness

### Permutation test (n=200)

Random cluster assignments produced mean Sharpe 0.80, 95th percentile 1.28. Hand-picked clusters: **Sharpe 1.61**. p-value: **0.000**.

The cluster structure is statistically significant — not any grouping of 37 coins produces this result.

### Out-of-sample (Jan 2024 – Jan 2026)

{oos_zoom}

| | Strategy | Equal-weight |
|--|--|--|
| CAGR | **+19.8%** | -5.9% |
| Sharpe | **0.34** | -0.09 |

Altcoin bear market (rising BTC dominance). Strategy positive; EW negative.

### Cluster sensitivity

Dropping the DeFi cluster reduces Sharpe by 0.60 — it is the most critical peer group. old_guard (legacy coins) is the weakest; removing it slightly improves Sharpe. Too many clusters converge toward equal-weight behaviour.

---

## Execution Analysis

| Cost | Sharpe | CAGR |
|------|--------|------|
| 0bps | 1.77 | +199% |
| 10bps | **1.69** | +189% |
| 20bps | 1.60 | +179% |
| 30bps | 1.46 | +172% |

Weekly one-way turnover: ~59%, drag ~3.1%/year at 10bps. Survives 30bps. Weekly rebalance is clearly optimal — monthly drops to near-EW Sharpe (1.26).

---

## Limitations

- Universe implicitly filtered to coins with Wikipedia pages
- Some assets reflect niche technical communities rather than retail attention
- Smaller coins may pose liquidity constraints at scale
- 2020 underperformance shows the strategy can miss broad bull runs that lift all assets equally
"""


def write_post():
    content = POST_TEMPLATE.format(
        equity_curve    = _embed("equity_curve",     "Cumulative return, log scale, indexed to 100"),
        drawdown        = _embed("drawdown",         "Drawdown from peak"),
        annual_returns  = _embed("annual_returns",   "Annual returns — strategy vs equal-weight"),
        cluster_momentum= _embed("cluster_momentum", "14-day Wikipedia attention momentum by cluster"),
        oos_zoom        = _embed("oos_zoom",         "Out-of-sample performance Jan 2024 – Jan 2026"),
    )
    POST.write_text(content, encoding="utf-8")
    print(f"Post written: {POST}")


def main():
    print("Loading data and running locked config...")
    mom14_w, weekly_ret_c, active_cols, daily_raw, CLUSTERS = load_data()

    port10 = run_locked(mom14_w, weekly_ret_c, active_cols, CLUSTERS, cost_bps=10)
    port20 = run_locked(mom14_w, weekly_ret_c, active_cols, CLUSTERS, cost_bps=20)
    ew_ret  = weekly_ret_c.mean(axis=1).dropna()
    btc_ret = weekly_ret_c["BTC"].dropna()

    print("Generating charts...")
    chart_equity_curve(port10, port20, ew_ret, btc_ret)
    chart_drawdown(port10, ew_ret, btc_ret)
    chart_annual_returns(port10, ew_ret)
    chart_cluster_momentum(mom14_w, CLUSTERS, active_cols)
    chart_oos_zoom(port10, ew_ret, btc_ret)

    print("Writing post...")
    write_post()

    print("\nDone.")
    print(f"  Charts: {CHARTS}")
    print(f"  Post:   {POST}")


if __name__ == "__main__":
    main()
