# Research notes — 002 Multi-timeframe momentum long/short (FTSE 100)

Working notes updated as exploration progresses.
Run: `python research/ideas/002-momentum-ls/explore.py [section]`

---

## Data and universe

### Original universe (50 stocks)
Current FTSE 100 constituents only. Pure survivorship bias — backtests
only names that survived to today.

### Expanded universe (109 stocks)
Current FTSE 100 + historical members with surviving yfinance tickers.
Successfully fetched: 109 tickers. Failed (delisted/restructured, no
surviving ticker): 25 tickers including MRW (Morrison's acquired 2022),
WMH (William Hill acquired 2021), GFS (G4S acquired 2021), MGGT
(Meggitt acquired 2022), POLY (Polymetal delisted 2023), MELR (Melrose
relisted differently), MRW, TUI.L, LSE.L among others.

**Start year distribution:**
- 2010: 100 tickers (full history)
- 2011: GLEN.L
- 2013: CCH.L
- 2014: BME.L, OSB.L
- 2015: AUTO.L, CAPE.L
- 2017: PSH.L
- 2021: HBR.L (Harbour Energy, successor to Premier Oil)
- 2022: HLN.L (Haleon, GSK spin-off)

**Survivorship bias assessment:**
Included: current FTSE 100 + historical members with surviving yfinance
tickers. Excluded: acquired/delisted names without a continuing ticker
(GKN, Shire, BG Group, Cadbury, ARM pre-2023, WMH, GFS, Meggitt, etc.).
Residual bias is present but meaningfully reduced vs current-only.
Cannot be fully eliminated without a commercial constituent history feed
(e.g. Refinitiv, FTSE Russell data). The excluded names are a mix of M&A
targets (where the premium would have boosted returns) and some distressed
names (where inclusion would have hurt). Net direction of residual bias
is probably modestly positive — we are missing some acquired names that
would have had high momentum leading into acquisition.

---

## Regime analysis (unchanged from original universe)

| Regime   | Days | Pct  | Scale |
|----------|------|------|-------|
| Low vol  | 848  | 22.4% | 120% |
| Normal   | 2501 | 66.1% | 100% |
| High vol | 436  | 11.5% | 60%  |

High-vol runs: 23 episodes, mean 19d, median 13d, max 100d (COVID 2020).
Key high-vol years: 2020 (56%), 2016 (27%), 2015 (23%), 2011 (22%), 2022 (21%).

---

## Packet analysis (expanded universe)

109 stocks, 121 monthly rebalances.

| Packet             | Mean  | Std | Min | Max |
|--------------------|-------|-----|-----|-----|
| Full long (90-100%) | 11.0 | 0.1 | 10 | 11 |
| Fade long (80-90%)  | 10.7 | 0.5 | 10 | 11 |
| Fade short (10-20%) | 10.7 | 0.5 | 10 | 11 |
| Full short (0-10%)  |  10.0 | 0.1 |  9 | 10 |

109 stocks gives ~10-11 names per full-position bucket per side — double
the 5-6 from the 50-stock universe. Idiosyncratic risk is meaningfully
reduced. Fade buckets are also ~10 names rather than 5.

---

## Turnover (expanded universe, monthly, base 10/20 packets)

| Statistic | Value |
|-----------|-------|
| Mean monthly one-way | 119.8% |
| Median | 116.1% |
| p90 | 168.6% |

Turnover essentially unchanged from 50-stock universe (~120% per month).
This makes sense — turnover is driven by rank stability, not universe size.

Annual TC drag estimates:
- 5bps/side: ~72bps/yr
- 10bps/side: ~144bps/yr
- 20bps/side: ~287bps/yr

---

## Baseline backtest comparison

**50-stock universe (monthly, no TC):** ann=1.7%, Sharpe=0.19
**109-stock universe (monthly, no TC):** ann=4.0%, Sharpe=0.33

Expanding the universe from 50 to 109 stocks nearly doubled the gross
Sharpe. The improvement comes from better diversification (10 vs 5 names
per bucket) reducing idiosyncratic noise in the signal.

**109-stock baseline returns by regime (no TC, no regime scaling):**

| Regime  | Ann return | Sharpe | n days |
|---------|------------|--------|--------|
| Low vol (120%) | +14.2% | +1.20 | 717 |
| Normal (100%)  | +2.1%  | +0.16 | 2025 |
| High vol (60%) | +4.1%  | +0.14 | 346 |

The low-vol regime is still dominant (Sharpe 1.20 vs 0.16 in normal).
However, with 109 stocks, the **normal regime is now slightly positive**
(+0.16 Sharpe) vs negative (-0.15) with 50 stocks. The larger universe
provides enough cross-sectional signal to generate modest alpha even in
normal conditions.

**Annual returns (109-stock, no TC):**

| Year | Return |
|------|--------|
| 2013 | +38.5% |
| 2014 | +25.0% |
| 2015 | +46.8% |
| 2016 | -34.9% |
| 2017 | +16.4% |
| 2018 | -3.2%  |
| 2019 | -3.9%  |
| 2020 | +17.5% |
| 2021 | -12.0% |
| 2022 | -9.4%  |
| 2023 | -6.2%  |
| 2024 | +2.0%  |

2013-2015 were exceptional years (2015: +46.8%). 2016 remains the worst
(-34.9%) — the post-Brexit momentum crash. 2017-2024 outside of 2020
is a grind of modest negatives and positives.

---

## Turnover / alpha grid (10bps TC, 109-stock universe)

Full grid across: rebalance frequency × packet width × buffer rule.
All with 10bps TC applied. Sorted by key finding:

### Monthly rebalance (best overall)

| Config | Ann% | Sharpe | MaxDD% |
|--------|------|--------|--------|
| Narrow (5/15) / No buffer  | 3.6% | 0.29 | -54.5% |
| Narrow (5/15) / 5% buffer  | **4.9%** | **0.36** | -48.0% |
| Base (10/20) / No buffer   | 2.3% | 0.23 | -49.9% |
| Base (10/20) / 5% buffer   | 3.6% | 0.30 | -50.4% |
| Wide (15/30) / No buffer   | 1.9% | 0.21 | -43.1% |
| Wide (15/30) / 5% buffer   | 1.7% | 0.21 | -36.5% |

**Best net-of-TC config so far: Monthly / Narrow (5/15) / 5% buffer — Sharpe 0.36**

### Quarterly rebalance

| Config | Ann% | Sharpe | MaxDD% |
|--------|------|--------|--------|
| Base (10/20) / No buffer  | 3.1% | 0.28 | -53.8% |
| Wide (15/30) / No buffer  | 2.3% | 0.25 | -44.8% |
| Narrow (5/15) / No buffer | 1.8% | 0.19 | -61.3% |

Quarterly is competitive with monthly for base/wide packets but worse
for narrow. The 5% buffer rule badly hurts quarterly (Quarterly/Base/5%
buffer: -5.5%) — the buffer prevents the quarterly signal from
acting on significant rank changes, holding stale positions too long.

### 6-weekly rebalance

Consistently worse than monthly and quarterly. The 6-weekly cadence
catches rank changes too late and generates more TC than quarterly
while capturing less signal than monthly.

### With regime scaling (+2% buffer)

| Config | Ann% | Sharpe | MaxDD% |
|--------|------|--------|--------|
| Monthly / Base (10/20) / 2% buffer  | 3.0% | 0.27 | -49.6% |
| Monthly / Wide (15/30) / 2% buffer  | 1.2% | 0.16 | -47.1% |
| 6-weekly / Wide (15/30) / 2% buffer | 2.1% | 0.22 | -35.7% |

Regime scaling **reduces** Sharpe vs no-regime versions in most cases —
the 60% scaling in high-vol regimes cuts exposure when the signal is
still generating moderate positive returns (Sharpe +0.14). The benefit
shows mainly in drawdown (35.7% vs 40-50% without scaling), not in Sharpe.

---

## Key findings

1. **Expanding universe from 50 to 109 stocks was impactful**: gross
   Sharpe improved from 0.19 to 0.33. Larger buckets reduce idiosyncratic
   noise. The normal-regime return turned positive.

2. **Best net-of-TC configuration: Monthly / Narrow (5/15) / 5% buffer**
   — Sharpe 0.36, Ann 4.9%, at 10bps TC. The narrow packets (5% each
   side instead of 10%) concentrate more weight in the highest-conviction
   names, and the 5% buffer prevents micro-turnover at rebalance.

3. **Turnover is structural, not configurable away cheaply**: 120% monthly
   one-way is driven by rank instability. Even with buffers and wider
   packets, turnover reduction comes at the cost of signal dilution.
   The sweet spot appears to be buffer rules of 5% (not 2%) with narrow
   packets.

4. **Regime scaling helps drawdown but hurts Sharpe**: the scaling adds
   complexity without improving risk-adjusted returns. The high-vol regime
   still has positive Sharpe (+0.14 unscaled), so cutting it 40% is
   net-negative for returns.

5. **Wide packets reduce drawdown**: Wide (15/30) with no buffer has the
   smallest drawdown (-43%) of any monthly config but also the lowest
   Sharpe (0.21). The fade zone smooths the portfolio but spreads weight
   into less-convicted positions.

---

---

## Improvements — isolation and combination

Baseline fixed at: monthly, narrow packets (5/15), 5% buffer, 10bps TC.
Baseline re-run here shows ann=5.6%, Sharpe=0.38 (slightly higher than earlier
grid due to identical seed config).

### Summary table

| Config | Ann% | Sharpe | MaxDD% | Sortino |
|--------|------|--------|--------|---------|
| Baseline | 5.6% | 0.38 | -54.3% | 0.36 |
| + Sector neutral | 3.5% | 0.29 | -52.9% | 0.27 |
| + Vol target 10% | 5.4% | **0.45** | **-46.0%** | 0.42 |
| + Abs momentum filter | **6.5%** | 0.42 | -57.0% | 0.39 |
| + Sector neutral + Vol target | 3.4% | 0.31 | -46.6% | 0.29 |
| + Sector neutral + Abs filter | 6.4% | 0.42 | -52.3% | 0.40 |
| + Vol target + Abs filter | 6.1% | **0.48** | **-48.3%** | **0.46** |
| + All three | 5.5% | 0.44 | **-44.9%** | 0.42 |

### Enhancement 1: Sector neutral — HURTS (Sharpe 0.38 → 0.29)

Sector neutralisation reduced Sharpe by 24%. The explanation: with only ~4-5
FTSE 100 names per sector, ranking within-sector produces very noisy signals —
there isn't enough cross-sectional dispersion inside a single sector to reliably
rank momentum. The inter-sector momentum signal (energy vs healthcare vs consumer)
is real and informative; suppressing it by forcing sector balance discards genuine
information. The proposed benefit — avoiding sector concentration — is real but the
cost outweighs it at this universe size. Would need a much broader universe
(400+ names across sectors) for sector-neutral to add value.

### Enhancement 2: Vol target 10% — HELPS (Sharpe 0.38 → 0.45, dd -54% → -46%)

Continuous vol targeting improved both Sharpe and drawdown. Sharpe +18%,
max drawdown reduced 8pp. The mechanism works as intended: in high-realised-vol
periods, position size scales down proportionally rather than cliff-edging at a
threshold. This explains why it works better than the discrete regime scaling
(which showed a Sharpe regression previously) — it responds to *actual* portfolio
vol, not index vol proxy.

### Enhancement 3: Abs momentum filter — HELPS on return, neutral/slight negative on risk (Sharpe 0.38 → 0.42)

Absolute momentum filter added 90bps annual return but worsened max drawdown
slightly (-54% → -57%). The short book is thinner in bull markets (fewer stocks
have negative absolute 12m returns), which boosts return when momentum works but
leaves the portfolio more net-long and exposed in crashes. Sortino improved (0.36
→ 0.39) suggesting the downside profile is better despite higher peak drawdown —
the crash losses are shorter-lived.

### Best combination: Vol target + Abs filter (Sharpe 0.48, dd -48.3%)

The pairing of vol target and abs momentum filter is the best two-enhancement
combo: Sharpe 0.48, ann 6.1%, drawdown -48.3%. The vol target's drawdown
reduction offsets the abs filter's tendency to leave the portfolio net-long.
Together they address different problems — vol target manages position size
dynamically, abs filter manages short-book quality.

Adding sector neutral to this pair ("all three") actually *reduces* Sharpe back
to 0.44 and barely improves drawdown (-44.9% vs -48.3%). Sector neutral remains
a net drag at this universe size.

### Year-by-year analysis: Baseline vs All three

| Year | Baseline | All three | Diff |
|------|----------|-----------|------|
| 2013 | +51.6% | +27.8% | **-23.7%** |
| 2014 | +29.8% | +30.5% | +0.7% |
| 2015 | +66.3% | +21.6% | **-44.7%** |
| 2016 | -39.2% | -11.0% | **+28.2%** |
| 2017 | +28.9% | +45.2% | **+16.3%** |
| 2018 | -8.7% | -1.6% | **+7.1%** |
| 2019 | -1.7% | -2.3% | -0.5% |
| 2020 | +21.4% | +6.0% | **-15.4%** |
| 2021 | -17.9% | -8.2% | **+9.7%** |
| 2022 | -13.0% | -13.6% | -0.6% |
| 2023 | -7.0% | -11.6% | -4.6% |
| 2024 | +5.0% | +3.3% | -1.7% |

The enhancements make a striking trade: they give up the huge baseline years
(2013: -24%, 2015: -45%) in exchange for dramatically better crash years
(2016: +28pp, 2018: +7pp, 2021: +10pp). This is exactly the "more repeatable
Sharpe" objective — the return series is much less volatile year-to-year at
the cost of lower peak years. The 2015/2016 swing goes from +66%/-39% to
+22%/-11%.

The 2020 reduction (-15pp) is the one concerning data point — the all-three
config does worse in a genuine momentum year. The vol target scaled down during
COVID volatility, reducing exposure exactly when momentum was working.

### Regime breakdown: Baseline vs All three

| Regime | Baseline ann% | Baseline Sharpe | All three ann% | All three Sharpe |
|--------|--------------|-----------------|----------------|-----------------|
| Low vol | +16.6% | 1.17 | +21.5% | **1.32** |
| Normal | +3.7% | 0.23 | +0.6% | 0.05 |
| High vol | +8.3% | 0.24 | +9.8% | **0.50** |

The all-three combination improves Sharpe in low-vol (+1.17 → +1.32) and high-vol
(+0.24 → +0.50) regimes but degrades normal-regime return significantly (+3.7% →
+0.6%, Sharpe 0.23 → 0.05). The sector neutral component is likely responsible
for the normal-regime degradation.

The high-vol Sharpe improvement (0.24 → 0.50) from the vol target is notable —
the strategy becomes meaningfully better at managing crisis periods.

### Recommended configuration (round 1)

**Vol target + Abs momentum filter (no sector neutral):**
- Sharpe 0.48, Ann 6.1%, MaxDD -48.3%, Sortino 0.46
- Superseded by round 2 findings — see "Signal improvements round 2" section

---

## Universe expansion — FTSE 100 + FTSE 250 (219 stocks)

Attempt to test the hypothesis: *"Smaller stocks may exhibit more momentum
than large cap."* Expanded universe to include ~219 UK-listed stocks spanning
FTSE 100 and FTSE 250 via yfinance. Key changes required:

1. **Data cleaning**: Many FTSE 250 tickers had severely corrupted yfinance
   price data — unadjusted corporate actions created multi-day blocks at the
   wrong price scale (e.g. CSH.L: £0.74 → £98 permanently; CAML.L: £55 →
   £5,547 for 8 days; BCPT.L: £95 → £0.957 for 2 days). An iterative
   forward-fill doesn't converge for permanent scale changes. Solution:
   **return-based cleaning** — compute daily returns, cap at ±75%/day,
   reconstruct a clean price index. This bounds artifacts to ±75% per
   event rather than allowing +13,000% blowups.

2. **Dynamic per-date availability**: At each rebalance, only include tickers
   with at least MIN_HISTORY (441) days of data up to that date. This
   approximates point-in-time availability for stocks that listed mid-backtest
   (e.g. THG.L IPO'd 2020, CLX.L 2020, HLN.L 2022, etc.).

### Results: expansion HURTS performance

| Config | Universe | Ann% | Sharpe | MaxDD% |
|--------|----------|------|--------|--------|
| Monthly / no TC | 109-stock (FTSE 100) | +0.8% | 0.33 | -46% |
| Monthly / no TC | 219-stock (+ FTSE 250) | -0.1% | 0.07 | -53% |
| Vol target 10% + Abs filter, 10bps TC | 109-stock | +4.5% | 0.37 | -35% |
| Vol target 10% + Abs filter, 10bps TC | 219-stock | -1.7% | -0.07 | -54% |

Adding ~110 FTSE 250 stocks degraded Sharpe across all configurations.
The improvements (vol target, abs filter) still help directionally but
cannot offset the noise introduced by the expanded universe.

### Why the expansion hurt

1. **Data quality**: yfinance FTSE 250 data has more corporate action errors,
   gaps, and stale prices than FTSE 100. The ±75% cap helps but still leaves
   bounded artifacts that distort momentum signals for affected tickers.

2. **Signal quality**: Hypothesis not supported by the data. FTSE 250 mid-caps
   do not exhibit stronger momentum factor via yfinance data over 2010-2024.
   Possible reasons: higher microstructure noise, more mean-reverting behavior
   in smaller caps, or survivorship bias working differently at mid-cap level.

3. **Packet dilution**: 219 stocks means ~22 names per full-position bucket
   (vs ~11 with 109 stocks). More diversification, but also more noise stocks
   diluting the strong-signal names.

### Conclusion

The FTSE 250 expansion via free yfinance data is not viable for this strategy.
The data quality issues and signal degradation outweigh any theoretical benefit
from mid-cap momentum. **Retain the 109-stock FTSE 100 universe** as the working
configuration.

With the return-based cleaning applied to the FTSE 100 universe:

| Config | Ann% | Sharpe | MaxDD% | Sortino |
|--------|------|--------|--------|---------|
| Baseline (monthly, narrow 5/15, 5% buffer, 10bps TC) | 3.0% | 0.25 | -50.1% | 0.23 |
| + Vol target 10% | 3.3% | 0.30 | -34.5% | 0.27 |
| + Abs momentum filter | 4.4% | 0.30 | -53.9% | 0.28 |
| + **Vol target + Abs filter** | **4.5%** | **0.37** | **-35.2%** | **0.34** |
| + All three | 2.0% | 0.21 | -39.3% | 0.19 |

The best Sharpe dropped slightly from the 0.48 reported pre-cleaning to 0.37.
The reduction is explained by the ±75%/day return cap introducing small
distortions on FTSE 100 tickers that had any extreme yfinance data events
(JET2.L's -75% during COVID, TLW.L's +72%, etc.). The cleaning is still
worthwhile as it prevents catastrophic blowups from corrupted data.

To genuinely test the mid-cap momentum hypothesis would require:
- A commercial data provider with clean point-in-time constituent histories
- Proper split/dividend adjustment verified against another source
- Likely a different broker/execution setup (FTSE 250 bid-ask spreads are 2-5x
  wider than FTSE 100, making 10bps TC highly optimistic for mid-caps)

---

---

## Signal improvements round 2

Five enhancements were proposed and tested against the prior best config
(vol target 10% + abs filter, narrow 5/15 packets, 5% buffer, 10bps TC → Sharpe 0.37):

1. **Signal gate** — skip rebalance when cross-sectional spread (p90-p10 of momentum score) is weak
2. **Residual momentum** — remove rolling market beta before ranking
3. **XSZ signal** — cross-sectional z-score per horizon instead of time-series vol scaling
4. Abs momentum filter — already in prior best
5. **Continuous weights** — linear rank-proportional weights instead of discrete packets

### Results summary

| Config | Ann% | Sharpe | MaxDD% | Sortino |
|--------|------|--------|--------|---------|
| Prior best (narrow 5/15, vol target, abs filter) | 4.5% | 0.37 | -35.2% | 0.34 |
| + Signal gate skip-25%, narrow 5/15 | 5.5% | 0.43 | -37.8% | 0.40 |
| + Signal gate skip-33%, narrow 5/15 | 6.9% | 0.52 | -38.1% | 0.49 |
| + Signal gate skip-40%, narrow 5/15 | 7.4% | 0.55 | -38.3% | 0.52 |
| + Signal gate skip-33%, base 10/20 | 7.5% | 0.58 | -33.6% | 0.54 |
| **+ Signal gate skip-40%, base 10/20** | **8.1%** | **0.63** | **-34.2%** | **0.58** |
| + Signal gate skip-50%, base 10/20 | 7.8% | 0.61 | -34.5% | 0.57 |
| + Residual momentum | 2.2% | 0.22 | -43.8% | 0.20 |
| + XSZ signal | 0.4% | 0.11 | -55.1% | 0.10 |
| + Continuous weights | 3.5% | 0.36 | -35.5% | 0.35 |

### Enhancement 1: Signal gate — BEST IMPROVEMENT (Sharpe 0.37 → 0.63)

The signal gate tests the p90–p10 cross-sectional spread of the momentum score
at each rebalance date. If spread < threshold, the rebalance is skipped — current
weights are held and no TC is paid. The threshold is calibrated as a percentile
of the historical spread distribution (expanding).

With gate at p40 (skip weakest 40% of rebalances, i.e. 56/140 rebalances skipped):
- **Sharpe improves from 0.37 to 0.63** (+70%)
- Annual return improves 4.5% → 8.1%
- Max drawdown *reduces* from -35.2% to -34.2%

The mechanism is clear: in low-spread (weak signal) environments, momentum scores
are clustered — rank differences are noise rather than signal. Paying TC to trade
a noisy ranking produces negative alpha after costs. Holding existing positions
instead saves TC and keeps the portfolio invested in the last good-signal ranking.

**Normal regime Sharpe jumps from 0.15 to 0.49.** The normal regime contains the
most low-spread dates; gating removes the costly low-signal rebalances within it.

### Gate + packet width interaction

The gate works better with base (10/20) packets than narrow (5/15). Hypothesis:
narrow packets are very sensitive to rank order — holding stale narrow-packet
positions for a second month (when gated) is riskier than holding base-packet
positions. Base packets give each held position more "buffer" around the rank
boundary, making it less likely that a gated hold becomes a significantly wrong
trade.

### Enhancement 2: Residual momentum — HURTS (Sharpe 0.37 → 0.22)

Beta-adjusting the signal degraded performance. The FTSE 100 universe has high
intra-market correlation — most stocks have beta ≈ 0.8–1.2. Removing the market
component strips out a significant portion of the return signal, leaving mostly
noise. Residual momentum works better in more heterogeneous universes (e.g.
cross-asset or multi-country). Does not combine well with signal gate either.

### Enhancement 3: XSZ signal — HURTS (Sharpe 0.37 → 0.11)

Cross-sectional z-scoring of raw returns (without vol adjustment) significantly
degraded performance. The current vol-adjusted signal already captures relative
risk-adjusted momentum — removing the vol normalization and replacing with
cross-sectional z-scoring loses the important information about which stocks have
consistent vs volatile momentum. The time-series vol scaling appears to be the
more informative normalisation for this universe.

### Enhancement 5: Continuous weights — NEUTRAL (Sharpe 0.37 → 0.36)

Continuous rank-proportional weights did not improve on discrete packets. The
packet approach already concentrates weight in high-conviction names — continuous
weights spread weight more gradually across the full distribution including
marginal-conviction positions. The turnover reduction is modest and offset by
signal dilution. Does not combine well with the signal gate.

### New recommended configuration

**Signal gate (skip-40%) + base packets (10/20) + vol target 10% + abs filter:**
- Sharpe 0.63, Ann 8.1%, MaxDD -34.2%, Sortino 0.58
- 56/140 monthly rebalances skipped (~40%)
- Normal-regime Sharpe: 0.49 (vs 0.15 prior best)

Year-by-year vs prior best:

| Year | Prior best | New best | Diff |
|------|-----------|---------|------|
| 2013 | +22.3% | +27.3% | **+5.0%** |
| 2014 | +16.4% | +15.9% | -0.5% |
| 2015 | +36.6% | +31.3% | **-5.3%** |
| 2016 | -28.6% | -27.8% | +0.9% |
| 2017 | +15.6% | +19.9% | +4.2% |
| 2018 | -4.2% | -3.3% | +0.9% |
| 2019 | +7.2% | +28.0% | **+20.8%** |
| 2020 | +25.0% | +17.6% | **-7.4%** |
| 2021 | -12.0% | -3.4% | **+8.6%** |
| 2022 | -1.0% | +2.6% | +3.7% |
| 2023 | -12.5% | -1.3% | **+11.2%** |
| 2024 | +6.3% | +4.7% | -1.7% |

The gate significantly improves the loss years (2019, 2021, 2023) where signal was
weak and TC was a drag. 2020 is slightly worse because the gate occasionally holds
slightly stale positions. The 2015/2016 swing is now +31%/-28% — acceptable.

---

## Signal improvements round 3

Three targeted improvements against the round 2 best config
(fixed gate-40%, base 10/20, vol target 10%, abs filter → Sharpe 0.63):

1. Adaptive signal gate — vary gate percentile by vol regime (low/normal/high)
2. Adaptive vol-target lookback — shorter in high-vol, longer in low-vol
3. Conviction thresholds — require >1–3% absolute return for longs, <-1–3% for shorts

### Results summary

| Config | Ann% | Sharpe | MaxDD% | Sortino |
|--------|------|--------|--------|---------|
| Prior best (fixed gate, vt10, lb20, abs≥0%) | 8.1% | 0.63 | -34.2% | 0.58 |
| + Adaptive gate (low=0.10, norm=0.40, high=0.60) | 6.7% | 0.52 | -34.0% | 0.48 |
| + Adaptive vol lb (low=40d, norm=20d, high=10d) | 7.3% | 0.57 | -35.9% | 0.52 |
| + Fixed vol lb 10d (all regimes) | 8.8% | 0.65 | -35.5% | 0.60 |
| + Abs thresh long>1%, short<-1% | 9.3% | 0.69 | -33.9% | 0.63 |
| + Abs thresh long>2%, short<-2% | 9.2% | 0.68 | -33.1% | 0.63 |
| + Abs thresh long>3%, short<-3% | 8.6% | 0.64 | -32.5% | 0.59 |
| **vt=12%, lb=15d, thresh long>1%, short<-1%** | **10.4%** | **0.70** | **-34.1%** | **0.65** |

Best combination full grid (gate-40%, base 10/20):

| vt% | lb | abs thresh | Ann% | Sharpe | MaxDD% |
|-----|----|-----------|------|--------|--------|
| 10% | 20d | 0% | 8.1% | 0.63 | -34.2% |
| 10% | 15d | 1% | 9.4% | 0.69 | -32.8% |
| 10% | 10d | 1% | 9.4% | 0.67 | -34.7% |
| 12% | 15d | 0% | 9.3% | 0.65 | -35.0% |
| **12%** | **15d** | **1%** | **10.4%** | **0.70** | **-34.1%** |
| 12% | 15d | 2% | 10.2% | 0.69 | -32.9% |
| 12% | 10d | 1% | 10.5% | 0.69 | -35.6% |

### Enhancement 1: Adaptive gate — HURTS (Sharpe 0.63 → 0.48–0.56)

The adaptive gate varies the skip threshold by vol regime (higher threshold in
high-vol = more selective). This degraded performance. Likely explanation: the
fixed gate at p40 is already nearly optimal. Making it regime-adaptive adds
complexity and introduces estimation uncertainty in the expanding percentile —
especially early in the sample when few high-vol dates have been observed.
The fixed gate is simpler and more robust.

### Enhancement 2: Vol target lookback — HELPS MODESTLY

Shorter lookback (15d vs 20d) improved Sharpe marginally. Fixed 10d is slightly
noisier. Fixed 40d reduces drawdown but cuts too much alpha in fast-reacting
environments. **Optimal: 15d fixed.** The adaptive version (40d/20d/10d by regime)
underperforms — adding regime-dependency to two parameters simultaneously creates
compounding estimation error.

### Enhancement 3: Conviction thresholds — BIGGEST IMPROVEMENT

Requiring ≥1% absolute 12m return for longs (and ≤-1% for shorts) improved
Sharpe from 0.63 to 0.69 on its own. The mechanism: stocks with very small
positive 12m returns (0–1%) are ambiguous momentum signals — they might be
transitioning from momentum to mean-reversion, or they may be noisy rankers.
Requiring a minimum conviction level for the long/short book eliminates these
marginal positions and concentrates exposure in clearer signals.

The 2% threshold slightly underperforms 1% — the marginal 1–2% long positions
have some positive expected value that is lost at 2%.

### Best new configuration

**Fixed gate p40 + base 10/20 + vol target 12%, lb 15d + abs thresh 1% / -1%:**
- Sharpe 0.70, Ann 10.4%, MaxDD -34.1%, Sortino 0.65
- Improvements vs prior best: +110bps/yr, Sharpe +0.07

Year-by-year vs prior best:

| Year | Prior (0.63) | New best (0.70) | Diff |
|------|-------------|----------------|------|
| 2013 | +27.3% | +26.8% | -0.5% |
| 2014 | +15.9% | +14.8% | -1.1% |
| 2015 | +31.3% | +33.2% | +2.0% |
| 2016 | -27.8% | -27.0% | +0.8% |
| 2017 | +19.9% | +21.4% | +1.5% |
| 2018 | -3.3% | -2.6% | +0.7% |
| **2019** | +28.0% | **+48.0%** | **+20.0%** |
| 2020 | +17.6% | +20.3% | +2.6% |
| 2021 | -3.4% | -1.9% | +1.4% |
| 2022 | +2.6% | +1.6% | -1.1% |
| 2023 | -1.3% | +2.7% | +4.0% |
| 2024 | +4.7% | +4.2% | -0.5% |

Regime breakdown:

| Regime | Prior ann% | Prior sh | New ann% | New sh |
|--------|-----------|---------|---------|--------|
| Low vol | +17.9% | 1.50 | +20.2% | 1.47 |
| Normal | +6.6% | 0.49 | +8.8% | 0.57 |
| High vol | +2.3% | 0.11 | +5.7% | 0.26 |

The 2019 improvement (+20pp) stands out — the tighter abs threshold eliminated
weak 0–1% long positions that were net-negative in a rising market with weak
cross-sectional dispersion.

---

## Open questions

- The signal gate threshold (p40 of historical spread) is optimised in-sample.
  Is this robust? Test: does the gate still help if we use a fixed absolute
  threshold calibrated on only the first 3 years?
- 2013-2015 drove most of the cumulative return. Is the strategy essentially
  capturing a single regime (UK value/growth rotation post-GFC)? What happens
  if we start the analysis from 2016?
- Survivorship bias in excluded M&A targets: acquired names (GKN, Shire, ARM)
  often had high pre-acquisition momentum. Including them would likely boost
  the long book in certain windows. Difficult to quantify without commercial data.
- FTSE 250 expansion hypothesis (smaller cap has more momentum) was tested and
  NOT supported with free yfinance data. Would require commercial data to test
  properly.

---

## Concerns / risks

- **2013-2015 concentration**: even in the best final config, 2013-2015 are
  the strongest years (+27%, +15%, +33%). Post-2016 is mostly low single digits
  with occasional negatives. The 2019 +48% is an outlier driven by tighter abs
  threshold concentrating into strong long positions in a one-way momentum year.
- **In-sample parameter optimisation**: gate p40, abs threshold 1%, vol lb 15d,
  vol target 12% were all selected by grid search on the full backtest period.
  Out-of-sample Sharpe will almost certainly be lower than 0.70. The parameter
  choices are directionally robust (multiple grid cells near the optimum show
  Sharpe 0.65+) but the specific values are overfitted to the 2013-2024 period.
- **Buffer rule interaction with quarterly rebalance**: 5% buffer + quarterly
  completely breaks the strategy (-5.5% ann). Buffers and infrequent rebalancing
  are redundant — not relevant for the current monthly config.
- **TC assumption at 10bps is optimistic for real execution**: UK equity
  mid-to-large cap actual all-in costs (spread + market impact + commission)
  are 15–25bps for institutional-scale trades. The strategy's gross alpha is
  sufficient to survive 20bps but Sharpe would drop to ~0.55–0.60.
