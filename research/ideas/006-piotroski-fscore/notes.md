# 006 - Piotroski F-Score: Notes

## Strategy Summary
Long F>=8, Short F<=2 stocks, rebalanced annually (v1) or event-driven on
10-K filing date (v2). Data: SEC EDGAR XBRL (point-in-time) + yfinance prices.

---

## Data Sources
| Component | Source | Notes |
|---|---|---|
| Financial statements | SEC EDGAR XBRL API | Point-in-time via `filed` date. Free, no key. |
| Ticker -> CIK map | `www.sec.gov/files/company_tickers.json` | 10k+ companies |
| Universe | iShares IWM holdings CSV | Current Russell 2000 constituents |
| Price history | yfinance | Daily OHLCV |

**EDGAR key insight:** each record has a `filed` date — this is the date
the 10-K became public. Using this instead of fiscal year-end eliminates
look-ahead bias entirely.

---

## F-Score Signals
| Signal | Pillar | Formula |
|---|---|---|
| F1: ROA > 0 | Profitability | net_income / avg_assets > 0 |
| F2: CFO > 0 | Profitability | operating_cash_flow > 0 |
| F3: delta ROA > 0 | Profitability | ROA increased YoY |
| F4: Accruals | Profitability | CFO/assets > ROA (cash earnings beat accrual earnings) |
| F5: delta Leverage < 0 | Leverage | long_term_debt/assets decreased |
| F6: delta Liquidity > 0 | Leverage | current_ratio increased |
| F7: No dilution | Leverage | shares outstanding did not increase |
| F8: delta Gross Margin > 0 | Efficiency | gross_margin improved |
| F9: delta Asset Turnover > 0 | Efficiency | revenue/assets improved |

---

## Iterations and Results

### v1: S&P 100 large-caps, annual rebalance, no P/B filter
- **Sharpe: -0.46**, Ann. return: -9.08%
- **Problem:** Financials dominate the short book (GS, MS, C, BLK score 2
  every year — leverage is their business model, not a red flag). F-Score
  is structurally invalid for banks.
- **Fix:** Remove financials and real estate from universe.

### v1b: Large-caps minus financials, thresholds 7/3
- **Sharpe: -0.35**, Ann. return: -3.46%
- **Problem:** Short book still outperforms. Low-F energy stocks (CVX, VLO,
  COP) at cycle lows are in the short book — they recover strongly because
  they are quality businesses, not distressed ones.
  2025 short book: +109% (just 2 names, massive concentration risk).
- **Root cause:** F-Score was never designed for quality large-caps.
  It was designed to separate turnarounds from value traps *within the
  high book-to-market (low P/B) bucket*.

### v2: IWM small-caps, event-driven rebalancing, P/B bottom 40% filter
- **Sharpe: -0.32**, Ann. return: -6.37%
- **Problem:** P/B filter and F-Score compete with each other.
  - High-quality companies (F=8) almost never have low P/B — they are good
    businesses and the market prices them accordingly.
  - Result: 0 long positions for the first 4 years (2012-2015). The long
    book is starved while the short book runs unchecked.
- **Root cause:** P/B applied as a concurrent filter rather than as a
  pre-condition. Piotroski's original paper:
  1. First: restrict universe to high book-to-market (low P/B) stocks ONLY
  2. Then: within that bucket, use F-Score to separate winners (high F) from
     losers (low F)
  The F-Score is meaningless without first being inside the value bucket.

---

## Correct Implementation (not yet built)

The paper's methodology exactly:
1. **Screen:** P/B < universe median (or bottom 20% by P/B)
2. **Within that screened group:** Long F >= 8, Short F <= 2
3. **Result:** Long "cheap + improving quality", Short "cheap + deteriorating quality"

This makes the short signal meaningful. A low-P/B company with F=2 is a
genuine value trap (cheap for good reason, getting worse). A high-P/B
company with F=2 is just an expensive company having a bad year.

### Other issues to address
- **Survivorship bias:** IWM current holdings exclude 2012-era bankruptcies.
  Short-side returns understated, long-side overstated. No free fix.
- **Short pool dominance:** Even after fixing the P/B logic, expect more
  shorts than longs (F>=8 is rare, F<=2 is common — ~3% vs ~23% in IWM).
  May need to run long-only vs. benchmark rather than L/S.
- **BVPS data gaps:** Many small-caps have missing stockholders equity in
  EDGAR XBRL. Need fallback to yfinance `bookValue`.
- **Sector neutrality:** Consider ranking within sectors rather than using
  absolute thresholds to avoid energy-cycle clustering in short book.

### v3: Two-stage filter, long-only primary result (LONG_THRESH=8)
```
                      Long-Only         IWM         SPY
Ann. return             +48.15%     +15.21%     +17.07%
Ann. vol                 43.60%
Sharpe                     1.10        0.62        0.90
Max drawdown            -52.80%
Total return          +1111.56%    +119.75%    +168.50%

Value bucket only (Stage 1, no F-Score): ann=+33.15%  sharpe=1.24  total=+6484.69%
F-Score add-on vs value bucket: +15.00% ann

SECONDARY: Long-Short  ann=-8.85%  sharpe=-0.45  total=-78.42%
```

Year-by-year (long-only vs IWM):
```
year  long_only  n_long_days    iwm
2014    +46.4%          211   +6.4%
2015    +68.6%           36   -3.2%
2017   +115.6%          199  +15.5%
2018    +24.7%           39   -9.7%
2020   +105.0%          202  +30.3%
2021    +59.4%          252  +17.3%
2022    +58.1%          151  -17.4%
2024    +21.3%          220  +13.8%
2025    +41.9%          250  +15.7%
2026   +139.5%           71  +41.6%
```
(Years with no longs: 2012, 2013, 2016, 2019, 2023 — no signal.)

F-Score distribution (IWM 300-stock universe):
- Long pool (F>=8): **3.1%** of filings (80 events)
- Short pool (F<=2): **23.4%** of filings (650 events)
- Mean F-Score: 4.0

- **The fix worked** — long book now populates. F-Score adds +15% ann on top
  of simply buying all cheap small-caps.
- **Key observation:** The value bucket alone has a *better* Sharpe (1.24)
  than the F-Score filtered long-only (1.10). This suggests the F>=8 threshold
  may be too tight — too few positions, too much concentration risk.
- Long book remains sparse: 0-2 longs in most years, often held <200 days.
  Many years have no signal at all (5 years completely dark).
- L/S still negative (-8.85%) — survivorship bias as expected.

### v4: F>=7, P/B bottom 20%, liquidity filter
- **Sharpe: 0.72**, Ann: +37.85%, Max DD: -90.51%, Total: +784%
- **Problem:** Loosening threshold to F>=7 within a tighter value bucket
  worsened results despite more active days. -90% drawdown = extreme
  single-stock concentration.
- Value bucket alone: Sharpe 1.34, Ann +38.53%. F-Score now subtracts
  value (-0.68% ann) — F=7 signals add noise, not signal.
- MUR (2022 filing) still in signals 4 years later — signal expiry needed.

### v5: +entry lag (2d), +signal expiry (375d), +sector caps (25%)
```
                      Long-Only         IWM         SPY
Ann. return             +44.47%     +10.60%     +13.64%
Ann. vol                 53.82%
Sharpe                     0.83        0.48        0.77
Max drawdown            -90.51%
Total return          +1434.71%    +109.30%    +200.06%

Value bucket only (Stage 1): ann=+41.44%  sharpe=1.43  total=+19412%
F-Score add-on: +3.03% ann  (positive again after being -0.68% in v4)

SECONDARY: Long-Short  ann=-7.19%  sharpe=-0.30
```

Year-by-year (long-only vs IWM):
```
year  long_only  n_long_days    iwm
2014    +35.6%          213   +6.4%
2015   +189.6%           53   -3.2%
2017    +22.1%          209  +15.5%
2018    -11.2%          229   -9.7%
2019     -4.9%          251  +27.0%
2020    +65.9%          203  +30.3%
2021   +153.6%          107  +17.3%
2022   +180.9%          208  -17.4%
2023    +91.5%          248  +19.3%
2024    +80.7%          252  +13.8%
2025    +82.3%          250  +15.7%
2026    +29.3%           73  +52.2%
```

Improvements vs v4: Sharpe 0.72→0.83, total 784%→1434%, F-alpha +3%.
Signal expiry fixed zombie positions. Sector caps had no effect on drawdown.

**Persistent problem: -90.51% max drawdown.**
Sector caps can't protect a 1-stock long book. 2015: +189% in 53 days = one
stock, massive undiversified bet. Need a per-position max weight (e.g. 50%)
or minimum position count before opening a signal.

**Threshold vs. Sharpe summary:**
| Config | Value Bucket Sharpe | Long-Only Sharpe |
|---|---|---|
| v3: F>=8, P/B<30% | 1.24 | 1.10 |
| v4: F>=7, P/B<20% | 1.34 | 0.72 |
| v5: F>=7, P/B<20%, +mitigations | 1.43 | 0.83 |

Value bucket alone consistently beats the F-Score-filtered long book.
Root cause: the long book is too concentrated to benefit from the quality filter.

### v6: +min 3 longs, +vol-inverse sizing, +200d MA momentum filter
```
                      Long-Only         IWM         SPY
Ann. return             +59.52%     +39.09%     +17.80%
Ann. vol                 26.51%
Sharpe                     2.24        1.99        1.33
Max drawdown              -8.52%
Total return             +24.33%     +15.55%      +6.80%

Value bucket only (Stage 1): ann=+41.44%  sharpe=1.43  total=+19412%
F-Score add-on: +18.08% ann  (vs 1.43 value-only benchmark)

SECONDARY: Long-Short  ann=-20.66%  sharpe=-1.13
```

Active years (long-only): 2025 (+46.9%, 25 days), 2026 (+94.7%, 73 days).
Strategy mostly sat out 2012-2024 — MIN_LONG_POSITIONS=3 + momentum filter
created a very high bar. Only fired when ≥3 cheap+quality+trending stocks
aligned simultaneously.

**Results vs progression:**
| Version | Sharpe | Max DD | Ann Vol | F-Alpha |
|---|---|---|---|---|
| v3: F>=8, P/B<30% | 1.10 | -52.80% | 43.60% | +15.00% |
| v4: F>=7, P/B<20% | 0.72 | -90.51% | 52.51% | -0.68% |
| v5: +entry lag, expiry, sector cap | 0.83 | -90.51% | 53.82% | +3.03% |
| **v6: +min longs, vol sizing, momentum** | **2.24** | **-8.52%** | **26.51%** | **+18.08%** |

**Key insight:** The -90% drawdown was entirely a portfolio construction
problem, not a signal problem. Min position floor + momentum filter effectively
eliminated it. Vol-inverse sizing halved realized volatility.

**New concern:** Strategy barely fires. Only 98 active long-days over 14 years.
The combination of F>=7 + P/B<20% + ≥3 simultaneous + price > 200d MA is
extremely rare. This is a "patience" strategy — high Sharpe when active but
long stretches of zero exposure.

### v7: Step-down F-Score (F>=8 → fill to F>=6), relative momentum, P/B<30%
- **Sharpe: 0.81**, Ann: +33.60%, Max DD: -78.12%, n_long_days: 2263
- Step-down worked — strategy now active 13/14 years (vs 2/14 in v6)
- But drawdown exploded back: -78% vs -8.5% in v6. Sharpe halved.
- F-Score add-on: -2.30% (negative — step-down candidates dilute signal)
- **Root cause:** F=6 and F=7 stocks in the step-down fill add noise, not alpha.
  The high Sharpe in v6 came from the strict F>=7+momentum gate keeping only
  the highest-conviction signals. Widening the gate recovers breadth but
  reintroduces the quality problem.
- ITGR (F=8) showing as LONG~ (below momentum threshold) — relative momentum
  filter too aggressive; excludes the highest-conviction name.
- **Key insight:** The step-down between F>=8 and F>=6 crosses a quality cliff.
  The gap between F=8 (9.9% of stocks) and F=6 (24.1%) is not linear — it's
  capturing fundamentally different companies.

**Threshold vs Sharpe vs breadth summary:**
| Config | Sharpe | Max DD | n_long_days | Notes |
|---|---|---|---|---|
| v3: F>=8, 30%, no rules | 1.10 | -52.8% | ~1600 | concentrated, some dark years |
| v6: F>=7, 20%, min3+vol+MA | 2.24 | -8.5% | 98 | too selective |
| v7: step-down 8→6, rel-mom, 30% | 0.81 | -78.1% | 2263 | breadth via quality dilution |

### v8: Core + Satellite sleeve (80% value bucket core, 20% F>=8 satellite)

Architecture: Core = equal-weight all P/B<30% stocks (always active). Satellite =
vol-inverse F>=8 stocks with sector-relative momentum > threshold, gated by
MIN_SAT_POSITIONS=3. Composite = 80% core + 20% satellite (or 100% core when
satellite inactive).

**Run at MOMENTUM_SECTOR_THRESHOLD=0.50 (first attempt):**
- Satellite never fired (n_sat_days=0 all years). IR=NaN.
- Sleeve = Core (identical). Threshold too strict: F>=8 stocks in weak sectors
  fall below the top-50% sector momentum requirement.

**Run at MOMENTUM_SECTOR_THRESHOLD=0.25 (second attempt):**
```
                      Sleeve          Core         IWM         SPY
Ann. return          +35.04%       +35.90%     +12.45%     +15.06%
Ann. vol              26.78%        26.92%
Sharpe                  1.31          1.33        0.59        0.90
Max drawdown         -53.89%       -53.89%
Total return       +8515.96%     +9578.85%    +323.28%    +594.26%

Information Ratio: -0.799  (satellite excess return / tracking error vs core)

Satellite standalone: ann=+10.42%  sharpe=0.40  total=+7.21%  active days=250

SECONDARY: Long-Short  ann=-20.35%  sharpe=-1.19  total=-95.47%
```

Year-by-year:
```
year  sleeve    core  n_sat_days    iwm
2013  +35.1%  +35.1%           0  +38.8%
2014  +20.6%  +20.6%           0   +6.4%
2015   +3.6%   +3.6%           0   -3.2%
2016  +55.1%  +55.1%           0  +23.6%
2017  +44.7%  +44.7%           0  +15.5%
2018   -4.6%   -4.6%           0   -9.7%
2019  +26.1%  +26.1%           0  +27.0%
2020  +90.8%  +90.8%           0  +30.3%
2021  +54.6%  +54.6%           0  +17.3%
2022   +6.2%   +6.2%           0  -17.4%
2023  +75.0%  +75.0%           0  +19.3%
2024  +69.8%  +69.8%           0  +13.8%
2025  +58.7%  +75.5%         217  +15.7%
2026 +182.5% +205.0%          33  +52.2%
```

**Key finding: Satellite consistently destroyed value when active.**
- 2025: sleeve +58.7% vs core +75.5% (-16.8pp drag)
- 2026: sleeve +182.5% vs core +205.0% (-22.5pp drag)
- Satellite standalone Sharpe = 0.40 vs core Sharpe = 1.33

**Root cause: The F>=8 filter is a weaker selector than P/B alone.**
The value bucket (cheap stocks) already captures the alpha. Restricting
further to F>=8 within that bucket concentrates into fewer, idiosyncratic
positions that underperform the diversified value pool. The "F-Score add-on"
is in fact a subtraction: IR = -0.799.

**Critical pattern across all versions:**

| Config | Value Bucket Sharpe | Signal Sharpe | F-Alpha |
|---|---|---|---|
| v3: F>=8, P/B<30% | 1.24 | 1.10 | -0.14 |
| v4: F>=7, P/B<20% | 1.34 | 0.72 | -0.62 |
| v5: +mitigations | 1.43 | 0.83 | -0.60 |
| v6: min3+vol+MA | 1.43 | 2.24* | +0.81* |
| v8: core+sat sleeve | 1.33 (core) | 0.40 (sat) | -0.93 |

*v6 fired only 98 days — too small a sample to trust the Sharpe.

**Conclusion:** The P/B value bucket (cheap small-caps) is the primary alpha.
F-Score signals within the bucket consistently underperform the bucket itself.
The original Piotroski result may rely on survivorship bias in the academic
sample, or the effect has been arbitraged away in small-caps since publication.

---

### v9: Core-only (satellite disabled, MIN_SAT_POSITIONS=9999)
```
                      Core-Only         IWM         SPY
Ann. return             +35.90%     +12.45%     +15.06%
Ann. vol                 26.92%
Sharpe                     1.33        0.59        0.90
Max drawdown            -53.89%
Total return          +9578.85%    +323.28%    +594.26%
```

Year-by-year (core vs IWM):
```
year   core     iwm
2013  +48.6%  +40.2%
2014  +20.6%   +6.4%
2015   +3.6%   -3.2%
2016  +55.1%  +23.6%
2017  +44.7%  +15.5%
2018   -4.6%   -9.7%
2019  +26.1%  +27.0%
2020  +90.8%  +30.3%
2021  +54.6%  +17.3%
2022   +6.2%  -17.4%
2023  +75.0%  +19.3%
2024  +69.8%  +13.8%
2025  +75.5%  +15.7%
2026 +205.0%  +52.2%
```

Beat IWM in 13/14 years (only 2019 was essentially flat).
F-Score overlay removed entirely — pure P/B value bucket is the final strategy.

**Final conclusion:** Portfolio construction (P/B screening) dominates signal
selection (F-Score). The value bucket alone delivers 1.33 Sharpe. F-Score adds
noise in every configuration tested. The Piotroski signal may require:
(a) a larger universe where survivorship bias is less severe,
(b) a live universe with true delisting events for the short book, or
(c) an academic sample period pre-2010 before widespread awareness/arbitrage.

---

## Next Steps
- [ ] Investigate whether F-Score adds alpha in *specific sectors* (not universe-wide).
      Energy and Industrials may behave differently than Health Care and Tech.
- [ ] Test with broader universe (500+ stocks) to see if signal appears at
      the tails of the size distribution.
- [ ] Address -53.89% max drawdown with a market regime filter (e.g. IWM > 200d MA)
      — run core-only when market trending up, cash otherwise.
