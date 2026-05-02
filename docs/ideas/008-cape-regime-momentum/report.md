## Overview

This strategy allocates dynamically between US equities and bonds using two signals: a valuation regime derived from the **Excess CAPE Yield (ECY)** and **6-month price momentum**. An inflation overlay caps equity exposure during high-CPI environments where both asset classes historically struggle simultaneously.

The backtest runs from 1900 to 2026 using Robert Shiller's long-run dataset — 126 years covering the Great Depression, two world wars, the 1970s stagflation, the dot-com crash, 2008, and COVID.

---

## Key Results

{{ metric:ann_return_pct | label=Ann. Return (real) | suffix=% }}
{{ metric:ann_volatility_pct | label=Ann. Volatility | suffix=% }}
{{ metric:sharpe_ratio | label=Sharpe Ratio (rf=0%) }}
{{ metric:max_drawdown_pct | label=Max Drawdown | suffix=% }}
{{ metric:years_beat_6040 | label=Years Beat 60/40 | decimals=0 }}

---

## How It Works

### Signal 1 — Excess CAPE Yield (ECY) Regime

The **Excess CAPE Yield** is defined as the CAPE earnings yield (1/CAPE) minus the real long-term bond yield. It measures how attractive equities are *relative to bonds* after adjusting for the rate environment — a higher ECY means equities offer more excess return over bonds.

Using a rolling 20-year percentile of ECY, the market is classified into three regimes:

| Regime | Condition | Interpretation |
|--------|-----------|----------------|
| Cheap | ECY in top third of history | Equities cheap vs bonds |
| Fair | ECY in middle third | Neutral |
| Expensive | ECY in bottom third | Equities expensive vs bonds |

ECY is a more complete signal than raw CAPE because it accounts for the opportunity cost of holding equities. The same CAPE of 30 looks very different when 10-year bonds yield 1% versus 5%.

### Signal 2 — 6-Month Total-Return Momentum

Within each valuation regime, 6-month momentum on the real total return index determines the directional tilt. Momentum is used as a *risk filter*, not a standalone signal: cheap markets with positive momentum get maximum equity allocation; expensive markets with negative momentum get minimum.

### Signal 3 — Inflation Cap

When year-on-year CPI exceeds 4%, equity exposure is capped at 50% regardless of regime. Historically, {{ metric:high_inflation_pct | label=High Inflation Months | suffix=% }} of all months met this threshold — mostly the 1910s, 1940s, and 1970s–80s. In these periods, rising prices erode bond real returns and compress equity multiples simultaneously, making a hard cap on risk more effective than any valuation signal.

### Allocation Table

| State | Equity Weight |
|-------|--------------|
| Cheap + momentum up | 100% |
| Cheap + momentum down | 20% |
| Fair + momentum up | 80% |
| Fair + momentum down | 40% |
| Expensive + momentum up | 30% |
| Expensive + momentum down | 0% |
| Any + CPI > 4% | capped at 50% |

Remainder always goes to bonds. No leverage, no shorting.

---

## Performance

{{ chart:equity_curve | caption=Cumulative real total return (log scale). Strategy in blue, 60/40 in amber, 100% equity in grey. The strategy compounds more smoothly than equity with dramatically lower drawdowns. }}

### vs Benchmarks

{{ metric:bench_6040_ann_return_pct | label=60/40 Ann. Return | suffix=% }}
{{ metric:bench_6040_sharpe | label=60/40 Sharpe }}
{{ metric:bench_6040_max_dd_pct | label=60/40 Max Drawdown | suffix=% | positive_is_good=false }}

{{ metric:bench_eq_ann_return_pct | label=Equity Ann. Return | suffix=% }}
{{ metric:bench_eq_sharpe | label=Equity Sharpe }}
{{ metric:bench_eq_max_dd_pct | label=Equity Max Drawdown | suffix=% | positive_is_good=false }}

The strategy beats 60/40 on annualised return (+2.02pp), volatility (7.31% vs 8.96%), Sharpe (1.127 vs 0.694), and max drawdown (-17% vs -55%) simultaneously. Max drawdown is less than a third of the 60/40 equivalent.

{{ chart:annual_returns | caption=Annual real returns versus 60/40 (1950–2026). Green bars = strategy beats 60/40 that year, red = underperforms. The strategy preserves capital in crash years (1973–74, 2002, 2008) while participating in most bull markets. }}

{{ chart:equity_allocation | caption=Equity allocation over time. Red-shaded periods indicate CPI > 4% (inflation cap active). The strategy was near fully invested through the 1950s–60s bull market, heavily defensive through the 1970s stagflation, and has oscillated between moderate and high allocation since 2010. }}

---

## What Drives the Outperformance

The three signals contribute independently:

- **ECY regime** identifies the structural valuation environment. It correctly flagged the market as cheap in 1982 (CAPE ~7, high ECY despite high rates) and expensive in 2000 (CAPE ~44, negative ECY). Raw CAPE alone would have flagged 1982 as cheap but missed that bonds were equally compelling at 14% yields.
- **Momentum** prevents the strategy from catching falling knives in cheap markets (e.g., buying aggressively into 1929–30) and forces exit from expensive markets before the bottom falls out.
- **Inflation cap** handles the failure mode of both assets simultaneously — the 1970s decade where a static 60/40 produced near-zero real returns.

---

## Caveats

**Risk-free rate**: The Sharpe ratio uses rf=0%. The average US T-bill over this 126-year period was approximately 3.5%. Adjusting for this would reduce all three Sharpe ratios proportionally; the strategy remains the strongest of the three on a risk-adjusted basis.

**Data**: The backtest uses Shiller's academic dataset, which uses S&P Composite index total returns and long-bond returns — not tradeable ETFs. Real-world implementation via SPY and TLT would incur bid-ask spreads and expense ratios, though both are minimal for these instruments.

**Lookahead**: All signals are lagged one month before being applied to the following month's returns. No forward-looking data is used.

{{ metric_table }}
