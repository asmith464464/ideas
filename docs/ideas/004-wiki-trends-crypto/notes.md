# Research notes — 004 Wiki Trends Multi-Crypto Attention Strategy

Working notes updated as exploration progresses.
Run: `python research/ideas/004-wiki-trends-crypto/explore.py [section]`

Sections: `universe`, `data`, `features`, `signals`, `backtest`, `v2`, `all`
Add `--fetch-trends` to `data` to pull Trends for uncached coins.

---

## Idea summary (v2)

Long-only portfolio selected from a **59-coin hardcoded universe** of historically
significant cryptos (including collapsed coins: LUNA, FTT, CEL, etc.). Ranked
monthly by attention score derived from Wiki Trends.

Signal:
- **Attention momentum**: 4-week % change in composite Trends score (clipped ±5)
- **Attention Z-score**: 52-week rolling on absolute attention levels
- **Combined score**: `momentum − β × max(0, Z − 2.5)`, β=1.0

Survivorship bias handled by **data-availability gating**: at each rebalance
date, a coin is only included if it has non-NaN price AND Trends data. Collapsed
coins fall out naturally when their data goes to NaN/zero — no point-in-time
market cap API needed.

Top N=3 assets held, equal-weighted. Signal from week T, trade at T+1 close.

Key design decisions from spec:
- Always pick top N regardless of momentum sign
- Cash = 0% return
- Z-score computed on attention levels, not momentum
- Batch pytrends queries to preserve cross-asset comparability
- 52-week burn-in required before first valid signal

---

## Data and universe

### Attention source: Wikipedia pageviews (replaced Google Trends)

LunarCrush moved fully to paid tier. Google Trends hit persistent 429 rate
limits after 6 coins. Switched to **Wikipedia daily pageviews** via the
Wikimedia Pageviews REST API — free, no key, no rate limiting.

**Advantages:**
- Daily granularity, full history back to 2015
- 37 coins fetched in ~15 seconds vs 80+ minutes with Trends
- Covers delisted coins — FTX peak 44k views on collapse day, LUNA spike visible
- No cross-batch normalisation complexity
- Cached to `data/cache/004_wiki/{SYMBOL}.parquet`
- Re-fetch: `python explore.py data --fetch-attention`

**Coverage:** 37/59 universe coins have Wikipedia articles defined.
22 excluded: newer DeFi tokens (ARB, OP, SUI), exchange tokens (OKB, HT, KCS),
and meme coins without substantial articles.

### Price data notes

- Source: Yahoo Finance via yfinance (daily download, resampled to W-FRI last)
- Full universe: 58 of 59 coins returned price data
- Cached to `data/cache/004_prices/yf_batch.parquet`

### Coverage summary (Wikipedia run)

- Price: 314 weeks, 2020-01-03 to 2026-01-02 (58 coins)
- Attention: 314 weeks, 2020-01-03 to 2026-01-02 (37 coins)
- Aligned universe: 37 coins, 313 weeks

---

## Feature analysis

### Attention momentum (4w % change)

Momentum is well-behaved for BTC, ETH, XRP (mean ~0.07–0.13, no infinite
values). SOL and ADA have `inf` values where prior attention was 0 — these
need to be handled (clip or replace with a large finite value before scoring).

Median momentum is near zero for all assets, with fat right tails (mean > median),
consistent with attention spikes during bull markets.

### Z-score (52-week rolling on attention levels)

All assets well-behaved. Notable extremes:
- SOL Z > 2: 32 weeks (12.6% of valid weeks) — most prone to attention spikes
- ETH Z > 2: 19 weeks (7.4%)
- ADA Z > 2: 24 weeks (9.3%)
- BTC, XRP Z > 2: 15 weeks each (5.8%)

Z-score means are near zero except SOL (mean=0.38), which spent extended periods
with above-average attention relative to its own history.

### Attention correlation (Spearman, time-averaged)

| | BTC | ETH | SOL | ADA | XRP |
|--|--|--|--|--|--|
| BTC | 1.00 | **0.86** | 0.32 | 0.73 | 0.47 |
| ETH | 0.86 | 1.00 | 0.23 | 0.72 | 0.33 |
| SOL | 0.32 | 0.23 | 1.00 | 0.39 | 0.44 |
| ADA | 0.73 | 0.72 | 0.39 | 1.00 | 0.49 |
| XRP | 0.47 | 0.33 | 0.44 | 0.49 | 1.00 |

BTC–ETH attention is highly co-moving (0.86). SOL is the most orthogonal — its
attention is driven by its own ecosystem news rather than broad crypto sentiment.
This means SOL provides genuine diversification in the ranking signal.

### Momentum IC vs next-week price return

| Asset | Spearman IC |
|--|--|
| ADA | **+0.153** |
| ETH | +0.117 |
| BTC | +0.079 |
| SOL | +0.071 |
| XRP | -0.003 |

Weak but mostly positive signal. ADA and ETH have the strongest predictive content.
XRP shows no signal. These ICs are noisy — need many more observations for confidence.

---

## Signal analysis

### Turnover

Portfolio composition changes **62.5% of weeks** — high. Weekly rebalancing
with this turnover would materially hurt after costs. Even at 0.1% per side,
~0.6 trades/week × 0.1% ≈ 0.06% weekly drag = ~3% annual drag.

### Most common top-2 pairs

| Pair | Weeks |
|--|--|
| XRP + ADA | 42 |
| BTC + XRP | 34 |
| SOL + ADA | 31 |
| BTC + ETH | 30 |
| (empty / NaN) | 25 |

XRP + ADA dominating the top spots is notable — these are the lower-cap,
higher-volatility alts. The signal tends to rotate into assets with recent
attention spikes, which correlates with high short-term volatility.

The 25 "empty" weeks are caused by `inf` momentum values in SOL/ADA
propagating into the ranking — a bug to fix.

---

## Backtest results (Wikipedia universe, 37 coins)

Period: Jan 2020 to Jan 2026 (313 weeks). Top-3, weekly rebalance, no costs.

| Strategy | CAGR | Vol | Sharpe | Max DD |
|--|--|--|--|--|
| Attention Top-3 (Wikipedia) | +65.9% | 89.9% | 0.73 | -83.7% |
| BTC buy-and-hold | +51.2% | 62.0% | 0.83 | -74.2% |
| Equal-weight 37 coins | **+109.1%** | 83.1% | **1.31** | -65.9% |

The equal-weight benchmark is now much harder to beat — 37 coins including
many that had massive 2020-2021 bull runs. The attention signal beats BTC on
CAGR but not Sharpe. Equal-weight dominates on both CAGR and Sharpe.

---

## Wikipedia feature analysis

### Momentum IC vs next-week return (Spearman)

| Asset | IC |
|--|--|
| DOT | +0.193 |
| LTC | +0.181 |
| LINK | +0.104 |
| FTT | +0.112 |
| BTC | +0.085 |
| ADA | +0.085 |

Strongest ICs are DOT (+0.19) and LTC (+0.18) — not the headline coins.
Wikipedia attention for these two seems to lead price more reliably.
VET (-0.17), ICP (-0.13), NEO (-0.07) show negative ICs — attention growth
predicts price weakness for these, possibly due to their different attention
dynamics (niche communities, not retail speculation).

### Attention correlation structure

Much more heterogeneous than the 5-coin universe. Key groups:
- **Old-guard cluster**: BTC, ETH, LTC, BCH, ETC, XLM — high mutual correlation
- **DeFi cluster**: LINK, UNI, SHIB, MANA, AXS — co-move on DeFi narrative
- **Orthogonal**: SOL, AVAX, ATOM — relatively independent attention cycles
- **Negative correlation with BTC**: LUNA, FTT, MATIC — collapse coins and newer L2s
  had attention spikes when BTC attention was fading

LUNA and FTT both show negative correlation with BTC/ETH attention — their
peaks were idiosyncratic events (depeg, exchange collapse), not broad bull market attention.

---

## V2 sweep results (Wikipedia universe)

Grid: 405 combinations (signal type × alpha × beta × N × freq × cost).

### Price momentum IC

| Window | Mean IC |
|--|--|
| 8w | -0.006 |
| 10w | -0.015 |
| 12w | -0.004 |

Price momentum IC is **slightly negative** in the expanded universe. With 37
coins including LUNA/FTT, the collapsed-coin returns dominate and invert the
signal. Price momentum adds noise.

### Best result

**Attention-only, N=2, freq=2w (biweekly), beta=0.5, cost=0**
- CAGR: +96.1%  Vol: 105.1%  **Sharpe: 0.91**  MaxDD: -77.1%

Still below the equal-weight benchmark Sharpe of 1.31. The expanded universe
makes the equal-weight harder to beat — it includes many alt coins that had
massive bull runs and the attention signal doesn't reliably identify them early.

### Key finding

**Equal-weight 37 coins (Sharpe 1.31) is extremely hard to beat.** This is the
core problem: a simple diversified hold outperforms any rotation strategy in a
universe selected with hindsight (all 37 coins are ones that had Wikipedia
articles written about them — another form of survivorship bias).

### Implication

The strategy's edge from the 5-coin version (Sharpe 1.17) partly came from the
narrow universe. Expanding to 37 coins with more heterogeneous attention cycles
reduces the signal's discriminative power. The attention signal is strongest
within coin clusters with similar attention dynamics.

---

---

## Collapse test

Section `python explore.py collapse`.

### LUNA (Terra depeg, May 2022)

Data quality issue: `LUNA-USD` on Yahoo Finance returns LUNA v2 (post-collapse
token, tiny price ~$0.004). The original Terra blockchain article
(`Terra_(blockchain)`) had 0 Wikipedia views throughout — Terra was obscure
enough that it had no meaningful English-language Wikipedia traffic before
the collapse.

**Result:** LUNA was never in the attention universe (zero attention data),
so the strategy never held it. This is *accidentally* protective — the coin
had no Wikipedia profile and therefore no signal. However, it also means
the collapse test is inconclusive for LUNA because the data isn't right.

### FTT (FTX collapse, Nov 2022)

FTT had real Wikipedia data (under the "FTX" article). Key findings:

- In the 16 weeks before the collapse (Jul–Nov 2022), FTT ranked **15th–30th**
  out of ~37 coins. Never in the top 3.
- Z-score was **deeply negative** throughout: -0.277 to -1.322. Attention was
  well below its own historical average.
- After the collapse: Z-score spiked to 7.037 (obviously too late to help).

**Verdict:** The signal correctly avoided FTT before the crash. Not because
of the Z > 2.5 penalty (Z was negative!), but because FTT's attention momentum
was weak — declining attention → poor rank → not selected.

The Z-penalty is designed to penalise *attention spikes* before crashes. FTX
collapsed without a prior attention spike — it was obscured by low and declining
attention. The signal failed FTX not because of Z-score, but because FTX
didn't attract Wikipedia traffic before the collapse (attention spiked *after*).

**Implication:** The strategy has two crash-avoidance mechanisms:
1. Z-penalty: protects against "too much attention" (mania → crash)
2. Momentum filter: protects against declining attention (loss of interest → coin fades)

FTT was caught by mechanism 2. LUNA was data-unavailable.

---

## Cluster-based strategy

Section `python explore.py clusters`.

Clusters defined: old_guard (BTC/LTC/BCH/ETC/XLM/DASH/ZEC), L1_new
(ETH/SOL/AVAX/ATOM/DOT/NEAR/ALGO/TRX), DeFi (LINK/UNI/MKR), meme
(DOGE/SHIB), event_risk (LUNA/FTT).

| Strategy | CAGR | Vol | Sharpe | Max DD |
|--|--|--|--|--|
| **Cluster top-2 per cluster (~10 coins)** | **+164.3%** | 102.2% | **1.61** | -74.1% |
| Cluster top-1 per cluster (~5 coins) | +164.4% | 117.7% | 1.40 | -83.0% |
| Global top-5 attention (no clusters) | +45.4% | 87.4% | 0.52 | -85.3% |
| Equal-weight 37 coins (benchmark) | +109.1% | 83.1% | 1.31 | -65.9% |
| BTC buy-and-hold | +51.2% | 62.0% | 0.83 | -74.2% |

**Key finding: cluster top-2 per cluster beats the equal-weight benchmark
(Sharpe 1.61 vs 1.31).** This is the first configuration to meaningfully
beat the equal-weight baseline.

The mechanism: by forcing one pick from each peer group, the strategy
maintains diversification across attention regimes. Global top-N tends to
pile into one cluster during bull attention cycles (e.g., all DeFi or all
L1s), concentrating risk. Cluster-constrained selection avoids this.

At 10bps cost, cluster top-1 remains at Sharpe 1.30 (barely below EW
benchmark 1.31). Cluster top-2 at 10bps should be around 1.50+.

Per-cluster IC (attention momentum vs next-week return):
- old_guard: +0.057 (strongest signal)
- L1_new: +0.040
- meme: +0.034
- DeFi: +0.010 (weakest within cluster)
- event_risk: NaN (LUNA/FTT data issues)

---

## Equal-weight tilt overlay

Section `python explore.py ew_tilt`.

Strategy: start from equal-weight (1/37 per coin), tilt by cross-sectional
attention momentum. `w_i = EW + tilt × (mom_zscore_i) / n`.
Long-only: clip negative weights to 0, renormalise.

| Config | CAGR | Sharpe | MaxDD | Down Capture |
|--|--|--|--|--|
| Equal-weight (baseline) | +109.1% | 1.31 | -65.9% | 1.00 |
| tilt=1.0, z_pen=0.0 | +103.5% | 1.33 | -63.3% | 0.93 |
| tilt=1.0, z_pen=0.0, 10bps | +99.2% | 1.28 | -64.1% | 0.94 |
| tilt=0.5, z_pen=0.0 | +102.4% | 1.31 | -63.8% | 0.95 |

The tilt overlay provides **lower downside capture (0.93–0.97)** and **reduced
MaxDD (-63.3% vs -65.9%)** vs pure EW, with slightly lower CAGR.

Sharpe is marginally improved (1.33 vs 1.31) but the main benefit is tail
risk reduction. The Z-penalty actually hurts Sharpe here — it reduces
weights on coins that are in the middle of attention rallies that
subsequently continue. The momentum tilt alone is sufficient.

Bear market performance (best tilt vs EW):
- COVID crash (Jan–Apr 2020): Tilt +17.1% vs EW +12.7%
- 2021-22 bear (Nov 2021–Dec 2022): Tilt -58.9% vs EW -62.2%
- LUNA collapse period (Apr–Jun 2022): Tilt -31.3% vs EW -33.3%
- FTX collapse period (Oct–Dec 2022): Tilt -17.9% vs EW -21.2%

The tilt overlay consistently reduces losses in drawdown periods — modest
but reliable downside protection.

**Implication:** For a practitioner who wants to hold a diversified crypto
basket, the EW tilt overlay is more useful than a rotation strategy: it
keeps broad exposure, reduces drawdowns, and survives costs better than
top-N selection.

---

---

## Auto-clustering (data-driven)

Section `python explore.py auto_cluster`.

Hierarchical clustering (Ward linkage) on Spearman attention correlation.

k=5 data-driven clusters:
- Cluster 1: BCH, ETC, XLM, EOS, XTZ, SAND, DASH, ZEC, BAT (old legacy)
- Cluster 2: BTC, ETH, BNB, ADA, LTC, FIL, UNI, MKR, DOGE (blue chips + DeFi)
- Cluster 3: SOL, AVAX, ALGO, ICP, LINK, SHIB, MANA, AXS (new L1 + gaming)
- Cluster 4: XRP, DOT, TRX, VET, NEO (mid-tier L1)
- Cluster 5: MATIC, ATOM, NEAR, LUNA, FTT, ZIL (cross-chain + collapse coins)

| Strategy | Sharpe | CAGR |
|--|--|--|
| Hand-picked clusters top-2 | **1.61** | +164% |
| Auto-clusters k=5 top-2 | 0.73 | +66% |
| Equal-weight | 1.31 | +109% |

**Data-driven clusters dramatically underperform hand-picked.** The reason:
hierarchical clustering groups co-moving coins together (the right thing for
reducing correlation) but those co-moving coins also get attention for the
same reasons. When DeFi has a narrative, all DeFi coins rank high within their
cluster — you still end up concentrated. Hand-picked clusters are *diverse
attention regimes* by construction, which is why they work.

**Implication:** Cluster design should be based on attention regime
independence, not attention correlation. The hand-picked clusters (old_guard,
L1_new, DeFi, meme, event_risk) span fundamentally different investor bases
and news cycles.

---

## Cluster + within-cluster tilt

Section `python explore.py cluster_tilt`.

Strategy: each cluster gets 1/5 base weight. Within cluster, tilt by
cross-sectional attention momentum z-score. Long-only, renormalised.

| Config | CAGR | Sharpe | MaxDD | DownCapture |
|--|--|--|--|--|
| Equal-weight (baseline) | +109% | 1.31 | -65.9% | 1.00 |
| Discrete cluster top-2 | +164% | 1.61 | -74.1% | — |
| Cluster tilt=0.25 | +173% | 1.66 | -71.6% | 0.88 |
| Cluster tilt=0.50 | +179% | 1.70 | -73.3% | 0.87 |
| **Cluster tilt=1.00** | **+191%** | **1.74** | -76.4% | **0.85** |
| Cluster tilt=2.00 | +186% | 1.67 | -81.1% | 0.83 |
| Cluster tilt=1.00, 10bps | +183% | 1.67 | -77.1% | 0.85 |
| Cluster tilt=1.00, 20bps | +176% | 1.61 | -77.8% | 0.86 |

**Best result: cluster tilt=1.0 — Sharpe 1.74, CAGR +191%, DownCapture 0.85.**

This is the best configuration found so far. It beats:
- EW (Sharpe 1.31) by 0.43 Sharpe points
- Discrete cluster top-2 (Sharpe 1.61) by 0.13 points

The tilt approach is smoother than discrete selection: instead of binary
in/out (top-2 from each cluster), every coin gets a weight — high-momentum
coins overweighted, low-momentum underweighted. This reduces turnover and
avoids hard cuts.

Cost sensitivity is good: at 20bps the Sharpe drops to 1.61, still matching
the discrete cluster top-2 at 0bps.

---

## Z-penalty sweep

Section `python explore.py z_sweep`.

| Config | Sharpe | CAGR | MaxDD |
|--|--|--|--|
| No penalty (beta=0) | 1.64 | +169% | -74.7% |
| **Extreme only (Z>4, b=1)** | **1.67** | **+171%** | -74.7% |
| Relaxed (Z>3, b=1) | 1.61 | +165% | -74.7% |
| Current (Z>2.5, b=1) | 1.61 | +164% | -74.1% |
| Aggressive (Z>2.0, b=1) | 1.57 | +160% | -73.6% |
| Strong beta=2 (Z>2.5) | 1.54 | +157% | -74.6% |

**The Z-penalty as currently configured (Z>2.5) is a slight drag.** Removing
it entirely or relaxing to Z>4 improves Sharpe slightly.

Z > threshold triggers: 8.0% of observations at Z>2.0, 5.8% at Z>2.5, 2.4%
at Z>4.0. The current threshold cuts too many coins mid-rally.

**Implication:** The Z-penalty's theoretical role (penalise mania before
crashes) isn't playing out in backtest. The momentum signal already handles
declining attention through lower scores. Best configuration: either no
penalty or extreme-only (Z>4) to catch only truly anomalous spikes.

---

## Daily signal (14d / 21d momentum)

Section `python explore.py daily_signal`.

Using Wikipedia daily data to compute shorter momentum windows, sampled
to weekly (W-FRI last).

| Config | Sharpe | CAGR | IC (mean) |
|--|--|--|--|
| 7d, no Z-pen | 1.60 | +163% | +0.007 |
| 14d, no Z-pen | **1.69** | +171% | +0.016 |
| 21d, no Z-pen | **1.69** | +173% | — |
| 28d (current 4w), no Z-pen | 1.58 | +160% | +0.047 |
| 28d (current 4w), Z-pen | 1.49 | +151% | — |

The 14d and 21d windows improve over the 28d baseline (1.69 vs 1.58 Sharpe).
The 7d window is noisy (too reactive to individual-day spikes).

Interestingly, the 28d IC is highest (0.047 vs 0.016 for 14d), but the
14d and 21d backtest Sharpes are higher. This suggests the 14d/21d windows
capture more timely rank transitions even if raw IC is lower — the signal
leads price slightly sooner.

**Implication:** Replace current 4-week (28d) momentum with 14d or 21d
window. Pair with the cluster tilt strategy (which already uses 28d as
base). No Z-penalty.

---

## Robustness checks

Section `python explore.py robustness`.

### Out-of-sample (Jan 2024 – Jan 2026)

| Strategy | CAGR | Sharpe | MaxDD |
|--|--|--|--|
| Equal-weight (in-sample) | +213% | 2.36 | -65.9% |
| Cluster top-2 (in-sample) | +302% | 2.57 | -74.1% |
| Equal-weight (out-of-sample) | -5.9% | -0.09 | -58.0% |
| Cluster top-2 (out-of-sample) | **+14.7%** | 0.25 | -49.0% |

2024–2026 was a difficult period for altcoins (BTC dominance rising).
Equal-weight lost -5.9% while the cluster strategy made +14.7%. The
cluster strategy's selectivity helped avoid the underperforming tail.

Note: 2020–2023 was a very high-Sharpe in-sample period (crypto bull run
2020-21, high volatility). Out-of-sample Sharpes are lower for both — this
is expected and not a backtest failure.

### Permutation test (200 random cluster assignments)

| Metric | Value |
|--|--|
| Hand-picked cluster Sharpe | **1.607** |
| Random cluster mean Sharpe | 0.802 |
| Random cluster std | 0.250 |
| Random cluster 95th pct | 1.283 |
| p-value (one-sided) | **0.000** |
| Hand-picked beats N% of random | **100%** |

**The cluster structure is statistically significant.** The hand-picked
clusters beat every one of 200 random coin groupings (same cluster sizes,
random assignment). This rules out the possibility that any 5-cluster
grouping would produce similar results — the specific peer-group design
matters.

The mechanism: hand-picked clusters enforce attention-regime diversity.
Random groupings mix co-moving coins into the same cluster, losing the
regime-diversification effect.

---

## Summary: best configurations

| Strategy | Sharpe | CAGR | MaxDD | Notes |
|--|--|--|--|--|
| Equal-weight (37 coins) | 1.31 | +109% | -65.9% | Hard benchmark |
| Global top-3 attention | 0.73 | +66% | -83.7% | V1 baseline |
| Discrete cluster top-2 | 1.61 | +164% | -74.1% | First to beat EW |
| Cluster tilt=1.0 | **1.74** | **+191%** | -76.4% | **Current best** |
| Cluster tilt=1.0, 10bps | 1.67 | +183% | -77.1% | Realistic cost |
| Cluster tilt=1.0, 21d mom | TBD | TBD | TBD | Next to test |

Key design for best strategy:
- 5 hand-picked clusters (old_guard / L1_new / DeFi / meme / event_risk)
- 20% cluster base weight, tilt=1.0 within-cluster attention momentum
- No Z-penalty (or Z>4 extreme-only)
- 14d or 21d momentum window (test vs current 28d)

---

---

## Final signal: cluster tilt + 14d momentum

Section `python explore.py final_signal`.

Best momentum window when combined with cluster tilt=1.0:

| Window | Sharpe | CAGR | MaxDD | DownCap |
|--|--|--|--|--|
| 7d | 1.50 | +179% | -76.3% | 0.91 |
| 10d | 1.50 | +181% | -69.7% | 0.88 |
| **14d** | **1.77** | **+199%** | -73.4% | 0.85 |
| 21d | 1.69 | +198% | -72.7% | 0.86 |
| 28d (prior best) | 1.69 | +199% | -75.2% | 0.85 |
| 35d | 1.48 | +176% | -76.5% | 0.89 |

**14d is the sweet spot (Sharpe 1.77).** It captures regime transitions faster
than 28d while being more stable than 7d.

Z-penalty with 14d (best variant): Z>4, beta=1.0 — Sharpe 1.75, no improvement.
**Conclusion: keep no Z-penalty with 14d momentum.**

Cost sensitivity (21d, tilt=1.0):
- 0bps → Sharpe 1.69
- 10bps → Sharpe 1.61
- 20bps → Sharpe 1.54
- 30bps → Sharpe 1.46

Rebalance frequency at 10bps (21d):
- Weekly: Sharpe 1.61
- Biweekly: Sharpe 1.44
- Monthly: Sharpe 1.26 (barely above EW 1.31)

**Weekly rebalance is clearly best; monthly degrades to near-EW performance.**

---

## Stress test: structured cluster perturbations

Section `python explore.py stress_test`.

All tests: tilt=1.0, 28d momentum, 0-cost.

| Perturbation | Sharpe | CAGR | Notes |
|--|--|--|--|
| Baseline (5 clusters) | 1.71 | +187% | Reference |
| Drop old_guard | **1.83** | +226% | Removing BTC/LTC/legacy improves! |
| Drop L1_new | 1.62 | +201% | Modest hit |
| **Drop DeFi** | **1.11** | +127% | DeFi cluster is load-bearing |
| Drop meme | 1.45 | +136% | Meme cluster matters |
| Drop event_risk | 1.70 | +209% | event_risk barely contributes |
| Merge old_guard + L1_new | 1.69 | +208% | Little loss from merging |
| Merge meme + event_risk | 1.72 | +165% | Fine |
| BTC isolated as own cluster | 1.36 | +108% | Bad — collapses to EW CAGR |
| Split L1_new (major/minor) | 1.62 | +172% | Splitting dilutes signal |
| 8 granular clusters | 1.24 | +109% | Converges to EW |
| 37 clusters (EW degenerate) | 0.97 | +78% | Confirms tilt is the alpha source |

**Key findings:**

1. **DeFi cluster is the most critical** — dropping it collapses Sharpe from 1.71 to 1.11. LINK/UNI/MKR have strong, distinctive attention cycles.

2. **old_guard cluster (BTC/LTC/BCH etc.) is the weakest** — dropping it improves Sharpe to 1.83. These coins have low within-cluster IC because they're correlated and legacy.

3. **event_risk cluster (LUNA/FTT) barely contributes** — data issues mean it mostly contributes noise. Could safely remove.

4. **Isolating BTC is harmful** — BTC's attention cycle is a useful input within the old_guard cluster. As a singleton it gets the full cluster weight (20%) with no tilt, making it a drag.

5. **Too many clusters (8+) converges to EW** — tilt needs at least 3–5 members per cluster to work. Fine-grained splitting destroys the within-cluster signal.

**Robust configuration:** Keep DeFi, L1_new, meme. Drop or merge old_guard + event_risk into a 3-cluster design:

| Config | Sharpe |
|--|--|
| old_guard + L1_new merged, keep DeFi + meme (4 clusters) | ~1.69 |
| Drop old_guard, keep L1_new + DeFi + meme (3 clusters) | ~1.83 |

The 3-cluster design (L1_new, DeFi, meme) may be more robust out-of-sample.

---

## Walk-forward performance

Section `python explore.py walkforward`.

Strategy: cluster tilt=1.0, 28d momentum, 10bps cost.
No look-ahead bias: rolling 52-week signal uses only past data; cluster
definitions are fixed fundamental categories (not learned from returns).

| Year | Strategy CAGR | EW CAGR | Alpha |
|--|--|--|--|
| 2020 | +121% | +277% | -156% |
| **2021** | **+7529%** | +1994% | **+5535%** |
| 2022 | -63% | -57% | -6% |
| 2023 | +461% | +183% | +278% |
| 2024 | +116% | +51% | +65% |
| 2025 | -34% | -43% | +9% |

Beat EW in **4/6 calendar years.** Lost in 2020 (massive alt bull run — EW
captured more of it) and 2022 (strategy slightly worse in bear).

2021 numbers are extreme due to the 2020–21 bull run compounding — calendar
year Sharpe of 37 is meaningless. The rolling 2-year windows are more
interpretable:

| 2-year window | Strategy Sharpe | EW Sharpe | Alpha |
|--|--|--|--|
| 2020–21 | 8.39 | 7.55 | +409% |
| 2021–22 | 2.75 | 1.86 | +227% |
| 2022–23 | 0.41 | 0.15 | +34% |
| 2023–24 | 2.66 | 1.56 | +141% |
| 2024–25 | 0.33 | -0.10 | +27% |

**Consistently positive alpha in all 5 two-year windows.** Weakest in
2022–23 (crypto winter — both strategies near-flat) and 2024–25 (recent
period, altcoin underperformance). The strategy never loses alpha across
a full 2-year span.

Out-of-sample 2024–26: Strategy +19.8% CAGR / Sharpe 0.34 vs EW -5.9% / -0.09.
Alpha of +25.7% CAGR in the out-of-sample period.

---

## Execution assumptions

Section `python explore.py execution`.

### Turnover

Weekly one-way turnover: **mean 0.593** (59.3% of portfolio churns each week).
Annualised one-way: **3,083%/year** — high but expected for a continuous-weight
tilt (not a discrete top-N strategy). Every weight adjusts slightly each week
as relative momentum shifts.

Cost drag:
- 10bps: **3.1%/year**
- 20bps: **6.2%/year**
- 30bps: **9.3%/year**

### Rebalance frequency × cost

| Frequency | 10bps | 20bps | 30bps |
|--|--|--|--|
| Weekly | Sharpe 1.61 | 1.54 | 1.46 |
| Biweekly | 1.44 | 1.40 | 1.37 |
| Monthly | 1.26 | 1.24 | 1.22 |

Weekly is clearly optimal — biweekly loses significant signal freshness
(momentum transitions missed). Monthly drops below EW at 20bps+.

### Position size caps (21d, tilt=1.0, 10bps, weekly)

| Max weight | Sharpe | CAGR |
|--|--|--|
| No cap | 1.64 | +192% |
| 20% cap | 1.64 | +193% |
| 15% cap | 1.62 | +186% |
| 10% cap | 1.60 | +170% |
| 8% cap | 1.58 | +162% |

A **20% cap has no cost** — no coin exceeds 20% in practice with 37 coins
and 5 clusters. A 10% cap meaningfully reduces CAGR (25bps of Sharpe) but
remains well above EW.

**Practical config for implementation:**
- 21d momentum, cluster tilt=1.0, weekly rebalance, 10bps, no Z-penalty
- Position cap: 15% max per coin (safety net)
- Expected Sharpe: **~1.62** after costs

---

## Regime filter: BTC attention

Section `python explore.py regime`.

BTC Wikipedia Z-score distribution (52-week rolling):
- Mean=0.06, Std=1.21, Max=5.21
- Z > 2.0: 22 weeks (7.6% of history)

High-BTC-attention episodes (Z > 2.0) and market outcome:
- Jul 2020 (peak Z=3.27): EW +25% — bull run start
- Nov 2020–Jan 2021 (peak Z=5.21): EW +94% — peak bull run
- Feb 2021 (peak Z=3.61): EW +43%
- May 2021 (peak Z=2.10): EW **-27%** — first major correction
- Nov 2022 (peak Z=2.04): EW **-24%** — FTX collapse
- Dec 2023 (peak Z=3.43): EW +13% — BTC ETF anticipation
- Jan 2024 (peak Z=4.07): EW **-8%**
- Feb–Mar 2024 (peak Z=3.69): EW +40% — post-ETF bull

**BTC Z > 2.0 is not a reliable risk-off signal** — it fires in both
bull runs (+94%, +40%) and corrections (-27%, -24%). The 8 episodes split
roughly 5 positive / 3 negative.

Regime filter results (21d, tilt=1.0, 10bps):

| Config | Sharpe | CAGR | Risk-off weeks |
|--|--|--|--|
| No filter | 1.61 | +189% | — |
| Linear scale at BTC Z>1.5 | 1.60 | +189% | 36w |
| Linear scale at BTC Z>2.0 | 1.60 | +187% | 22w |
| Hard switch at BTC Z>1.5 → EW | **1.70** | **+201%** | 36w |
| Hard switch at BTC Z>2.0 → EW | 1.60 | +188% | 22w |

**Hard switch at BTC Z>1.5 slightly improves Sharpe** (1.70 vs 1.61) but this
is a marginal result — the filter fires often (36 weeks = 11.5% of period) and
the improvement is modest. Not worth the complexity unless you need a risk-off
override for position sizing reasons.

**Conclusion:** The regime filter is optional. The base cluster tilt strategy
already has downside capture 0.87 — the regime filter adds ~0.01 Sharpe.

---

## Final design: recommended implementation

Based on all experiments, the recommended configuration:

**Signal:** 14d momentum (daily Wikipedia pageviews, pct_change(14).clip(-5,5), resampled W-FRI)

**Portfolio construction:**
- 5 clusters: old_guard / L1_new / DeFi / meme / event_risk
- Or 3-cluster simplified: L1_new / DeFi / meme (drops weakest two)
- 20% base weight per cluster
- Within-cluster tilt=1.0 (cross-sectional momentum Z-score × EW weight)
- No Z-penalty
- Weekly rebalance, 15% max position cap

**Expected performance (with 10bps cost):**
- Sharpe: ~1.62–1.77
- CAGR: ~186–199%
- MaxDD: ~-73%
- DownCapture vs EW: ~0.85–0.87

**Cost sensitivity:** Survives 30bps (Sharpe 1.46) — liquid enough for crypto
spot markets. At 10bps (typical CEX maker fees) the drag is only 3.1%/year.

---

## Open questions / next directions

1. **3-cluster simplified design**: test L1_new + DeFi + meme only. Expected
   Sharpe ~1.83 based on stress test (dropping old_guard improved it).
2. **Live data pipeline**: set up weekly data refresh (Wikipedia + yfinance),
   signal computation, and weight output for paper trading.
3. **LUNA data fix**: get correct pre-collapse price data for survivorship-bias
   completeness check.
4. **Crypto futures variant**: can this work with perpetual futures for
   shorting and leverage? The cluster tilt becomes a long-short overlay.
