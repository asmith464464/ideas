# 008 — CAPE Regime + Momentum: Iteration Log

## Strategy Summary

Uses Shiller CAPE percentile (20-year rolling window) to classify the market into three regimes
(cheap / fair / expensive), then uses 12-month price momentum as a secondary signal to set
the equity allocation. Remainder goes to bonds (proxied by Shiller monthly bond return series).

| State                   | Equity Weight |
|-------------------------|---------------|
| Cheap + momentum up     | 100%          |
| Cheap + momentum down   | 50%           |
| Fair (either)           | 60%           |
| Expensive + momentum up | 60%           |
| Expensive + momentum dn | 20%           |

Data: Shiller ie_data.xls (monthly, 1871–present)
Backtest start: 1900-01-01

---

## v1 — Initial run (2026-04-22)

Params: cape_window=240, mom_months=12, thresholds=tercile, weights=(1.0/0.5/0.6/0.6/0.6/0.2)

```
Ann. Return    6.76%  vs  6.22% (60/40)  6.80% (equity)
Sharpe         0.750  vs  0.694           0.460
Max Drawdown  -45.6%  vs -55.0%         -76.8%
Beat 60/40: 37% of years
```

Issues: win rate low (37%), expensive regime covers 45% of time with no value-add over 60/40.

## v2 — Grid search (2026-04-22)

Two-pass sweep over 3,888 combinations. Key findings:
- 6-month total-return momentum beats 12-month consistently
- 20-year CAPE window (240m) wins over 10/15-year
- 0% equity when expensive+falling is always best
- Cutting cheap+falling from 50% → 20% and raising fair+rising to 80% cracked Sharpe > 1.0

Best params: cape_window=240, mom_months=6, thresholds=tercile (0.33/0.67),
weights: cheap_up=1.0, cheap_dn=0.2, fair_up=0.8, fair_dn=0.4, exp_up=0.4, exp_dn=0.0

```
Ann. Return    7.82%  vs  6.22% (60/40)  6.80% (equity)
Volatility     7.76%  vs  8.96%          14.79%
Sharpe (rf=0%) 1.008  vs  0.694           0.460
Max Drawdown  -26.6%  vs -55.0%          -76.8%
Beat 60/40: 53.5% of years (127-year backtest, 1900-2026)
```

Note: Sharpe uses rf=0%. Average US T-bill ~3.5% over this period would reduce all Sharpes.

## v3 — ECY + inflation filter (2026-04-22)

Replaced CAPE percentile with Excess CAPE Yield (ECY) percentile as the primary signal.
ECY = 1/CAPE minus real bond yield (adjusts for opportunity cost of bonds).
Added YoY CPI inflation cap: if CPI YoY > 4%, equity capped at 50%.
Tested rate trend filter (cash when rates rising) — it HURTS Sharpe (-0.15) because routing
to cash misses bond yield income during rising-rate periods. Dropped.

Filter contribution (measured independently):
  ECY alone (no filters):        Sharpe 1.062
  ECY + rate filter:             Sharpe 0.915  (-0.147 — dropped)
  ECY + inflation cap:           Sharpe 1.127  (+0.065 — kept)

Best params: ecy_window=240, mom_months=6, thresholds=tercile (0.33/0.67),
weights: cheap_up=1.0, cheap_dn=0.2, fair_up=0.8, fair_dn=0.4, exp_up=0.3, exp_dn=0.0
infl_thresh=4%, infl_eq_cap=50%

```
Ann. Return    8.24%  vs  6.22% (60/40)  6.80% (equity)
Volatility     7.31%  vs  8.96%          14.79%
Sharpe (rf=0%) 1.127  vs  0.694           0.460
Max Drawdown  -17.0%  vs -55.0%          -76.8%
Beat 60/40: 53.5% of years (127-year backtest, 1900-2026)
High inflation months: 464 (30.6%)
```

Key insight: ECY is a better signal than raw CAPE because it accounts for bond opportunity
cost — stocks in 1982 looked cheap on CAPE (~7x) but ECY showed bonds were still very
attractive at 14% rates. Stocks in 2009 (CAPE ~15, rates ~2.5%) had high ECY = strong buy.

