## Overview

US T-Bond futures and USD/JPY are tethered by interest-rate parity: when Treasury yields spike, the dollar must strengthen against the yen. The two markets price the same information — but bond futures (traded on CME GLOBEX) price it first. Currency market-makers, running order books optimised for flow rather than latency, lag by seconds to roughly a minute during US session handoffs.

The **10Y Sniper** exploits this lag. Using native 3-tick bond bar timestamps as signal triggers — not resampled time bars — it enters USD/JPY within seconds of a significant bond yield shock, before the FX market has fully repriced. The strategy is in the market roughly 2% of each session.

{{ metric:sharpe_is | label=Sharpe Ratio (Jan–Mar 2026) }}
{{ metric:win_rate_is_pct | label=Win Rate | suffix=% }}
{{ metric:pnl_is_bps | label=Gross P&L (3 months) | suffix= bps }}
{{ metric:n_trades_is | label=Trades (Jan–Mar 2026) | decimals=0 }}

---

## The Lead-Lag Mechanism

CME bond futures (US T-Bond) trade on a full central limit order book with co-located HFT participants and sub-millisecond matching. EUR/USD and USD/JPY spot FX trades on distributed ECN venues with prime-brokerage credit intermediation — a structurally slower repricing chain.

When a macroeconomic data release, Fed speaker headline, or large institutional bond order moves T-Bond futures by more than 2–3 standard deviations (yield-equivalent), the FX market adjusts — but not instantaneously. Empirically, the full repricing takes 30–120 seconds depending on session liquidity. The strategy captures the first portion of that adjustment.

This is a **structural** microstructure edge, not a data artefact. The lag exists because:
1. FX market-makers process bond moves from their own risk management systems, not as primary signal sources
2. During US session opening and European session overlap (14:00–22:00 EET), liquidity is fragmented across many ECN venues
3. USD/JPY has a uniquely direct link to US yields via the JPY carry trade — unlike EUR/JPY or AUD/JPY, where the cross leg muddies the signal direction

EUR/JPY and AUD/JPY were tested and consistently negative across all parameter combinations. USD/JPY is the right instrument.

---

## Signal Architecture

All logic runs at native bond tick-bar frequency — the bond 3-tick bar timestamp is the event clock.

**Bond yield Z-score** (rolling over 20 bond events):

```
yield_ret  = -bond_return    # price down = yield up
yield_z    = zscore(yield_ret, window=20)
```

**FX quiet filter** — USD/JPY must not have repriced yet:

```
fx_ret_5m  = (fx_mid[T] - fx_mid[T - 5min]) / fx_mid[T - 5min]
fx_z       = zscore(fx_ret_5m, window=30 bond events)
```

**Entry conditions** (session: 14:00–22:00 EET):

| Direction | Bond yield | FX state |
|-----------|-----------|---------|
| Long USD/JPY | yield_z > 2.5 | fx_z < 0.5 |
| Short USD/JPY | yield_z < −2.5 | fx_z > −0.5 |

**Execution**: enter at ask (long) or bid (short) immediately at the bond event timestamp. Exit at bid (long) or ask (short) after 3 minutes. One position at a time. The natural bid/ask spread is embedded — no fixed cost estimate is used.

---

## Performance

{{ chart:cumulative_pnl | caption=Cumulative P&L (basis points) over Jan–Mar 2026 using optimised parameters (bz=2.0, exit=2m). The strategy accumulates steadily with minimal drawdown — consistent with a microstructure edge rather than a macro bet. }}

The daily P&L distribution is narrow and positively skewed. Time in market is approximately 2% of session, which produces very low annualised volatility (~1–2%) and consequently high Sharpe ratios. This is a feature of the strategy's design — it is not leveraged and is not replicating a macro position.

---

## Monthly Consistency

Six consecutive profitable months across two independent periods, using the conservative a-priori parameters (bz=2.5, exit=3m — never adjusted to data).

{{ chart:monthly_pnl | caption=Monthly P&L across Q4 2025 (out-of-sample, amber) and Jan–Mar 2026 (in-sample, blue), a-priori parameters. All six months positive. December 2025 shows lower activity consistent with year-end thin markets. }}

---

## Out-of-Sample Robustness

The strategy was developed exclusively on Jan–Mar 2026 data. Two independent out-of-sample tests were applied:

1. **Walk-forward (March 2026)**: parameters re-optimised on Jan+Feb only, tested on unseen March data
2. **Q4 2025 prior period**: fully independent quarter preceding all development

{{ chart:oos_comparison | caption=Sharpe ratio across three test windows. Grey bars show the a-priori specification (bond_z=2.5) — parameters chosen from the original strategy hypothesis, never adjusted to any data. All six bars are positive; the minimum is 7.3. }}

{{ metric:sharpe_oos_apriori | label=Q4 2025 OOS Sharpe (a-priori) }}
{{ metric:sharpe_wf_apriori | label=Walk-Forward OOS Sharpe (a-priori) }}
{{ metric:win_rate_oos_pct | label=Q4 2025 OOS Win Rate | suffix=% }}
{{ metric:pnl_oos_bps | label=Q4 2025 OOS P&L (3 months) | suffix= bps }}

The a-priori result is the most important: bond_z=2.5 was specified in the original strategy hypothesis before any backtesting began. It achieves Sharpe > 7 on two different unseen quarters. The edge is not a parameter fit.

---

## Execution Costs

The strategy requires genuine execution speed — the lag window is seconds to a few minutes. A standard REST API with sub-5-second round-trip is sufficient; co-location is not required.

{{ chart:cost_scenarios | caption=Sharpe ratio under five combined execution scenarios. ECN retail with tight spreads (0.2 pip slippage + $3/lot commission) still exceeds the Sharpe 1 target. Scenarios with 0.5 pip slippage or 30-second latency are unviable. }}

{{ metric:sharpe_ecn_retail | label=Sharpe — ECN Retail (0.2pip + $3/lot) }}
{{ metric:sharpe_prime | label=Sharpe — Prime Broker (0.1pip + $1/lot) }}

The embedded bid/ask spread from data averages **0.97 pips round-trip** (0.62 bps) — this is the cost already baked into every backtest result above. The slippage and commission in the scenarios above are *additional* costs on top of the natural spread.

**Viable execution profile**: API latency < 5 seconds, extra slippage < 0.2 pip, commission ≤ $3/lot. This matches Interactive Brokers Lite, OANDA, or IC Markets Pro.

**Avoid**: major macro prints (CPI, NFP at 14:30 EET) where spreads widen to 2–5 pips. These events also generate the largest bond Z-scores — but the strategy edge collapses when execution costs spike.

---

## Limitations

- **Short history**: 6 months of data total (3 IS + 3 OOS). The sample covers a specific macro regime — rising US rates with active carry trade. A BOJ intervention period (e.g., Q2 2024) or Treasury market stress could close the lag window entirely.
- **Execution dependency**: unlike daily-rebalanced strategies, the edge disappears at > ~60-second execution latency. It requires a live connection to both a bond futures data feed and an FX execution API, with near-real-time event processing.
- **Signal sparsity at a-priori threshold**: bond_z=2.5 generates ~50–60 signals per month. This is statistically adequate but limits diversification — a single bad month could have outsized impact on reported Sharpe.
- **Spread regime risk**: the 0.97-pip round-trip in the data reflects normal liquid-hours conditions. News-driven spread widening is not modelled and would turn profitable setups into losses.

{{ metric_table }}
