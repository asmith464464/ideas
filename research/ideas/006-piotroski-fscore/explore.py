"""
Piotroski F-Score Strategy - Exploration Script (v9: Core-Only)
===============================================================
v9 drops the F-Score satellite entirely. The primary result is the
pure value-bucket strategy: equal-weight all IWM small-caps in the
bottom 30% by P/B, rebalanced event-driven on 10-K filing dates.

Finding from v3-v8: F-Score signals within the value bucket
consistently underperform the diversified value pool itself
(satellite IR = -0.799 in v8). The P/B value bucket IS the alpha.

Key design:
  1. Two-stage P/B filter (Piotroski's original methodology):
       Stage 1: restrict universe to bottom 30% by P/B (the "value bucket").
                P/B cutoff is computed cross-sectionally each month from all
                filings in the trailing 12 months — regime-relative.
       Stage 2: satellite disabled (MIN_SAT_POSITIONS = 9999).
     Core = equal-weight of all value-bucket stocks, always invested.
  2. BVPS fallback: when EDGAR StockholdersEquity is missing, falls back to
     yfinance bookValue (less point-in-time accurate but fills data gaps).
  3. Core vs IWM/SPY as primary result.

Survivorship bias caveat:
  IWM holdings are current (today's survivors). Companies that went bankrupt
  between 2012-2026 are absent. This understates short-side returns and
  overstates long-side returns. No free fix exists.

Data sources:
  - iShares IWM holdings CSV  : current Russell 2000 constituent tickers
  - SEC EDGAR XBRL API        : point-in-time financials (10-K filed dates)
  - yfinance                  : daily price history + current P/B fallback
"""

import io
import json
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CACHE_DIR   = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

EDGAR_HDR   = {"User-Agent": "ideas-research alist@example.com"}
EDGAR_BASE  = "https://data.sec.gov"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
IWM_CSV_URL = (
    "https://www.ishares.com/us/products/239710/"
    "ishares-russell-2000-etf/1467271812596.ajax"
    "?fileType=csv&fileName=IWM_holdings&dataType=fund"
)

START_DATE = "2012-01-01"
END_DATE   = date.today().isoformat()

SHORT_THRESH = 2

# ── Satellite (Alpha Sleeve) — DISABLED in v9 ─────────────────────────────────
# MIN_SAT_POSITIONS = 9999 effectively disables the satellite. Core runs alone.
LONG_THRESH       = 8    # kept for current-signals display
MIN_SAT_POSITIONS = 9999  # satellite never fires → core-only mode

# ── Core / Satellite split ────────────────────────────────────────────────────
CORE_WEIGHT = 1.00
SAT_WEIGHT  = 0.00

# ── Shared universe / risk controls ──────────────────────────────────────────
EXCLUDED_SECTORS = {"Financials", "Real Estate"}
MAX_UNIVERSE     = 300
PB_VALUE_BUCKET  = 0.30   # bottom 30% by P/B — wider core, cross-sectional

MIN_ADV_USD        = 1_000_000
SIGNAL_EXPIRY_DAYS = 375
ENTRY_LAG_DAYS     = 2
MAX_SECTOR_WEIGHT  = 0.25

VOL_INVERSE_SIZING = True
VOL_SIZING_WINDOW  = 30

# Sector-relative momentum: satellite only goes long if stock is in the
# top 50% of its GICS sector by 3-month (63-day) price return.
# Avoids falling knives while being less punishing than universe-wide 12m rank
# (small-cap turnarounds often lag the broad market early in recovery).
# Set 0.0 to disable.
MOMENTUM_SECTOR_THRESHOLD = 0.25   # must be above bottom quartile within sector by 3m return


# ---------------------------------------------------------------------------
# Universe: IWM holdings
# ---------------------------------------------------------------------------
def fetch_iwm_universe() -> pd.DataFrame:
    """Return IWM equity holdings as DataFrame with Ticker and Sector."""
    cache = CACHE_DIR / "iwm_holdings.csv"
    if cache.exists() and (date.today().isoformat() in cache.read_text()[:200]):
        return pd.read_csv(cache)

    r = requests.get(IWM_CSV_URL, headers=EDGAR_HDR, timeout=30)
    r.raise_for_status()
    raw = r.content.decode("utf-8")

    df = pd.read_csv(io.StringIO(raw), skiprows=9)
    df = df[df["Asset Class"] == "Equity"].dropna(subset=["Ticker"])
    df = df[~df["Ticker"].str.contains(r"-|Cash", na=True, regex=True)]
    df = df[["Ticker", "Name", "Sector", "Weight (%)"]].copy()
    df.columns = ["ticker", "name", "sector", "weight"]
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0)
    df = df[~df["sector"].isin(EXCLUDED_SECTORS)]
    df = df.sort_values("weight", ascending=False).reset_index(drop=True)

    # Stamp with today's date in first line via a comment-style header
    out = f"# fetched={date.today().isoformat()}\n" + df.to_csv(index=False)
    cache.write_text(out)
    return df


def load_iwm_universe() -> list[str]:
    df = fetch_iwm_universe()
    if not isinstance(df, pd.DataFrame) or "ticker" not in df.columns:
        raw = (CACHE_DIR / "iwm_holdings.csv").read_text()
        # Strip leading comment line(s) starting with #
        lines = [l for l in raw.split("\n") if not l.startswith("#")]
        df = pd.read_csv(io.StringIO("\n".join(lines)))
    tickers = df["ticker"].dropna().unique().tolist()
    return tickers[:MAX_UNIVERSE]


def get_sector_map() -> dict[str, str]:
    """Return {ticker: sector} from the IWM CSV (already cached)."""
    df = fetch_iwm_universe()
    if not isinstance(df, pd.DataFrame) or "ticker" not in df.columns:
        raw = (CACHE_DIR / "iwm_holdings.csv").read_text()
        lines = [l for l in raw.split("\n") if not l.startswith("#")]
        df = pd.read_csv(io.StringIO("\n".join(lines)))
    return dict(zip(df["ticker"], df.get("sector", pd.Series(dtype=str)).fillna("Unknown")))


# ---------------------------------------------------------------------------
# EDGAR helpers (same as v1, cached)
# ---------------------------------------------------------------------------
def get_cik_map() -> dict:
    cache = CACHE_DIR / "cik_map.json"
    if cache.exists():
        return json.loads(cache.read_text())
    r = requests.get(SEC_TICKERS, headers=EDGAR_HDR, timeout=30)
    r.raise_for_status()
    mapping = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in r.json().values()}
    cache.write_text(json.dumps(mapping))
    return mapping


def get_company_facts(cik: str) -> dict:
    cache = CACHE_DIR / f"{cik}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
    r   = requests.get(url, headers=EDGAR_HDR, timeout=30)
    if r.status_code != 200:
        return {}
    data = r.json()
    cache.write_text(json.dumps(data))
    time.sleep(0.12)
    return data


def extract_annual(facts: dict, concept: str, unit: str = "USD") -> pd.Series:
    """Annual series indexed by filed date. Earliest filing per fiscal year."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    if concept not in gaap:
        return pd.Series(dtype=float)
    records = [r for r in gaap[concept]["units"].get(unit, [])
               if r.get("form") == "10-K" and r.get("fp") == "FY"
               and "filed" in r and "fy" in r]
    if not records:
        return pd.Series(dtype=float)
    seen: dict = {}
    for rec in sorted(records, key=lambda x: x["filed"]):
        if rec["fy"] not in seen:
            seen[rec["fy"]] = rec
    idx  = pd.to_datetime([v["filed"] for v in seen.values()])
    vals = [v["val"] for v in seen.values()]
    s    = pd.Series(vals, index=idx, dtype=float).sort_index()
    return s[~s.index.duplicated(keep="first")]


# ---------------------------------------------------------------------------
# F-Score + Book Value per Share
# ---------------------------------------------------------------------------
def compute_signals(facts: dict, yf_bvps_fallback: float = np.nan) -> pd.DataFrame:
    """
    Compute all 9 F-Score signals and book value per share for each 10-K.
    Returns DataFrame indexed by filed date.

    yf_bvps_fallback: yfinance bookValue (per share) to use when EDGAR
    StockholdersEquity is missing. Less point-in-time accurate but fills gaps.
    """
    ni  = extract_annual(facts, "NetIncomeLoss")
    cfo = extract_annual(facts, "NetCashProvidedByUsedInOperatingActivities")
    ta  = extract_annual(facts, "Assets")
    ltd = (extract_annual(facts, "LongTermDebtNoncurrent")
           .combine_first(extract_annual(facts, "LongTermDebt")))
    ca  = extract_annual(facts, "AssetsCurrent")
    cl  = extract_annual(facts, "LiabilitiesCurrent")
    sh  = extract_annual(facts, "CommonStockSharesOutstanding", unit="shares")
    gp  = extract_annual(facts, "GrossProfit")
    rev = (extract_annual(facts, "RevenueFromContractWithCustomerExcludingAssessedTax")
           .combine_first(extract_annual(facts, "Revenues"))
           .combine_first(extract_annual(facts, "SalesRevenueNet")))

    # Stockholders equity — try multiple EDGAR tags
    eq = (extract_annual(facts, "StockholdersEquity")
          .combine_first(extract_annual(facts, "CommonStockholdersEquity"))
          .combine_first(extract_annual(facts, "RetainedEarningsAccumulatedDeficit")))

    df = pd.DataFrame({
        "ni": ni, "cfo": cfo, "ta": ta, "ltd": ltd,
        "ca": ca, "cl": cl, "sh": sh, "gp": gp, "rev": rev, "eq": eq,
    }).sort_index().dropna(subset=["ni", "cfo", "ta"])

    if len(df) < 2:
        return pd.DataFrame()

    ta_avg = (df["ta"] + df["ta"].shift(1)) / 2
    roa    = df["ni"]  / ta_avg
    lev    = df["ltd"] / df["ta"]
    liq    = df["ca"]  / df["cl"]
    gm     = df["gp"]  / df["rev"].replace(0, np.nan)
    turn   = df["rev"] / ta_avg

    out = pd.DataFrame(index=df.index)
    out["F1_roa_pos"]     = (roa > 0).astype(int)
    out["F2_cfo_pos"]     = (df["cfo"] > 0).astype(int)
    out["F3_roa_up"]      = (roa > roa.shift(1)).astype(int)
    out["F4_accruals"]    = (df["cfo"] / ta_avg > roa).astype(int)
    out["F5_lev_down"]    = (lev < lev.shift(1)).astype(int)
    out["F6_liq_up"]      = (liq > liq.shift(1)).astype(int)
    out["F7_no_dilution"] = (df["sh"] <= df["sh"].shift(1)).astype(int)
    out["F8_gm_up"]       = (gm > gm.shift(1)).astype(int)
    out["F9_turn_up"]     = (turn > turn.shift(1)).astype(int)

    signal_cols = [c for c in out.columns if c.startswith("F")]
    out["fscore"] = out[signal_cols].sum(axis=1)

    # BVPS: EDGAR equity/shares, fall back to yfinance scalar for all rows
    bvps = df["eq"] / df["sh"]
    if bvps.isna().all() and not np.isnan(yf_bvps_fallback):
        bvps = pd.Series(yf_bvps_fallback, index=df.index)
    out["bvps"] = bvps

    return out.dropna(subset=signal_cols)


# ---------------------------------------------------------------------------
# Shared P/B cutoff helper (used by backtest and current-signals display)
# ---------------------------------------------------------------------------
def build_pb_cutoffs(panel: pd.DataFrame) -> dict:
    """Monthly P/B cutoffs keyed by month-start Timestamp."""
    months = pd.date_range(START_DATE, END_DATE, freq="MS")
    out: dict[pd.Timestamp, float] = {}
    for m in months:
        window = panel[
            (panel["filed"] >= m - pd.Timedelta(days=365)) &
            (panel["filed"] <  m)
        ]["pb"].dropna()
        out[m] = float(window.quantile(PB_VALUE_BUCKET)) if len(window) >= 10 else np.inf
    return out



# ---------------------------------------------------------------------------
# Event-driven backtest
# ---------------------------------------------------------------------------
def _metrics(ret: pd.Series) -> dict:
    cum = (1 + ret).cumprod()
    ann = float(ret.mean() * 252)
    vol = float(ret.std()  * np.sqrt(252))
    sr  = ann / vol if vol > 0 else 0.0
    mdd = float((cum / cum.cummax() - 1).min())
    return {"ann_return": round(ann, 4), "ann_vol": round(vol, 4),
            "sharpe": round(sr, 4), "max_drawdown": round(mdd, 4),
            "cum": cum}


def _build_weights(tickers: list[str],
                   sector_of: dict[str, str],
                   vol_series: dict[str, float]) -> dict[str, float]:
    """
    Compute final long-book weights:
      1. Start from inverse-vol (or equal) base weights
      2. Iteratively cap any sector to MAX_SECTOR_WEIGHT
    """
    if not tickers:
        return {}

    # Base: inverse-vol or equal
    if VOL_INVERSE_SIZING and vol_series:
        weights = {}
        for t in tickers:
            v = vol_series.get(t, np.nan)
            weights[t] = 1.0 / v if (not np.isnan(v) and v > 0) else 1.0
    else:
        weights = {t: 1.0 for t in tickers}

    # Sector cap — iterate to convergence
    for _ in range(20):
        total = sum(weights.values())
        capped = False
        sector_totals: dict[str, float] = {}
        for t, w in weights.items():
            s = sector_of.get(t, "Unknown")
            sector_totals[s] = sector_totals.get(s, 0.0) + w / total
        for s, sw in sector_totals.items():
            if sw > MAX_SECTOR_WEIGHT + 1e-9:
                scale = MAX_SECTOR_WEIGHT / sw
                for t in tickers:
                    if sector_of.get(t, "Unknown") == s:
                        weights[t] *= scale
                capped = True
        if not capped:
            break

    total = sum(weights.values())
    return {t: w / total for t, w in weights.items()}


def run_backtest(panel: pd.DataFrame, prices: pd.DataFrame,
                 adv: pd.DataFrame | None = None,
                 sector_of: dict[str, str] | None = None) -> dict:
    """
    Two-stage event-driven backtest (Piotroski's original methodology):

    Stage 1 — Value bucket: at each filing date, compute the P/B cutoff
      from all filings filed in the trailing 12 months. Only tickers in the
      bottom PB_VALUE_BUCKET% are eligible for any signal (long or short).

    Stage 2 — F-Score within value bucket:
      Long  = value bucket AND F >= LONG_THRESH AND ADV >= MIN_ADV_USD
              AND price > MOMENTUM_MA_DAYS MA  AND >=MIN_LONG_POSITIONS active
      Short = value bucket AND F <= SHORT_THRESH AND ADV >= MIN_ADV_USD

    Three return series computed in parallel:
      - long_only:  vol-inverse + sector-capped long book, gated by MIN_LONG_POSITIONS
      - value_univ (core): equal-weight of all value-bucket stocks (always invested)
      - satellite:   vol-inverse F-Score sniper, fires only when >=MIN_SAT_POSITIONS
      - sleeve:      CORE_WEIGHT * core + SAT_WEIGHT * satellite (composite)
                     when satellite is inactive, sleeve = 100% core

    Robustness features:
      - ENTRY_LAG_DAYS: positions open N trading days after the EDGAR filed date
      - SIGNAL_EXPIRY_DAYS: auto-expire if no new filing within this window
      - MAX_SECTOR_WEIGHT: no sector exceeds this fraction of the satellite book
      - MIN_SAT_POSITIONS: satellite only fires when this many longs are available
      - VOL_INVERSE_SIZING: satellite weights by 1/realized_vol
      - MOMENTUM_SECTOR_THRESHOLD: satellite only enters if stock is in top X%
        by 3-month return within its own GICS sector (sector-relative, not universe)

    panel columns: ticker, filed, fscore, bvps, sector
    prices: DataFrame of daily closes, columns = tickers
    adv: DataFrame of 60-day rolling median ADV (price * volume), same index as prices
    sector_of: {ticker: sector} for weight capping and sector-relative momentum
    """
    import time as _time
    from pandas.tseries.offsets import BusinessDay

    daily_ret = prices.pct_change()
    _sector_of = sector_of or {}

    # Rolling vol for satellite sizing
    rolling_vol = prices.pct_change().rolling(VOL_SIZING_WINDOW, min_periods=10).std()

    # Sector-relative 3-month momentum rank
    # For each ticker on each day: rank within its sector (pct=True, 0=worst, 1=best)
    mom_63 = prices.pct_change(63)   # 3-month return
    if MOMENTUM_SECTOR_THRESHOLD > 0 and sector_of:
        # Build sector groups; rank within each sector group per day
        sector_groups: dict[str, list[str]] = {}
        for t, s in sector_of.items():
            if t in mom_63.columns:
                sector_groups.setdefault(s, []).append(t)
        # Compute sector-relative rank as DataFrame aligned to mom_63 index
        rank_frames = []
        for s, tickers in sector_groups.items():
            sub = mom_63[tickers]
            rank_frames.append(sub.rank(axis=1, pct=True))
        sector_mom_rank: pd.DataFrame | None = pd.concat(rank_frames, axis=1).reindex(
            columns=mom_63.columns)
    else:
        sector_mom_rank = None

    def liquid_on(ticker: str, dt: pd.Timestamp) -> bool:
        if adv is None or ticker not in adv.columns:
            return True
        loc = min(adv.index.searchsorted(dt), len(adv) - 1)
        val = adv[ticker].iloc[loc]
        return bool(not pd.isna(val) and val >= MIN_ADV_USD)

    def above_sector_mom(ticker: str, dt: pd.Timestamp) -> bool:
        """True if stock is in top (1-MOMENTUM_SECTOR_THRESHOLD) of its sector by 3m return."""
        if sector_mom_rank is None or ticker not in sector_mom_rank.columns:
            return True
        loc  = min(sector_mom_rank.index.searchsorted(dt), len(sector_mom_rank) - 1)
        rank = sector_mom_rank[ticker].iloc[loc]
        return bool(not np.isnan(rank) and rank >= MOMENTUM_SECTOR_THRESHOLD)

    def get_vol(ticker: str, dt: pd.Timestamp) -> float:
        if ticker not in rolling_vol.columns:
            return np.nan
        loc = min(rolling_vol.index.searchsorted(dt), len(rolling_vol) - 1)
        return float(rolling_vol[ticker].iloc[loc])

    # --- Attach P/B to each filing ---
    def price_on(ticker: str, dt: pd.Timestamp) -> float:
        if ticker not in prices.columns:
            return np.nan
        loc = min(prices.index.searchsorted(dt), len(prices) - 1)
        return float(prices[ticker].iloc[loc])

    panel = panel.copy()
    panel["price_at_filing"] = panel.apply(
        lambda r: price_on(r["ticker"], r["filed"]), axis=1)
    panel["pb"] = panel["price_at_filing"] / panel["bvps"]
    panel = panel.replace([np.inf, -np.inf], np.nan)

    # --- Stage 1: build monthly P/B cutoffs ---
    pb_cutoffs = build_pb_cutoffs(panel)

    def get_pb_cutoff(dt: pd.Timestamp) -> float:
        return pb_cutoffs.get(dt.replace(day=1), np.inf)

    # --- Apply ENTRY_LAG_DAYS: offset filing dates to entry dates ---
    lag = BusinessDay(ENTRY_LAG_DAYS)
    filings_by_entry: dict[pd.Timestamp, pd.DataFrame] = {}
    for fd, grp in panel.groupby("filed"):
        entry_dt = pd.Timestamp(fd) + lag
        filings_by_entry.setdefault(entry_dt, []).append(grp)  # type: ignore[arg-type]
    filings_by_date: dict[pd.Timestamp, pd.DataFrame] = {
        k: pd.concat(v) for k, v in filings_by_entry.items()
    }

    # --- Active positions ---
    # active_sat: satellite candidates — passed F>=LONG_THRESH + ADV + sector-mom
    #   ticker -> filed_date
    active_sat:   dict[str, pd.Timestamp] = {}
    active_short: dict[str, pd.Timestamp] = {}
    active_value: dict[str, pd.Timestamp] = {}

    trade_dates = daily_ret.index
    n_days      = len(trade_dates)
    bt_t0       = _time.time()
    interval    = max(1, n_days // 20)

    sat_rets    = []   # satellite return (when active)
    sleeve_rets = []   # composite: core_w * core + sat_w * sat (or 100% core)
    val_rets    = []   # core: equal-weight value bucket (always computed)
    ls_rets     = []   # long-short secondary
    expiry_delta = pd.Timedelta(days=SIGNAL_EXPIRY_DAYS)

    for day_i, dt in enumerate(trade_dates):
        # --- Signal expiry ---
        for book in (active_sat, active_short, active_value):
            to_drop = [t for t, filed in book.items() if dt - filed > expiry_delta]
            for t in to_drop:
                del book[t]

        if day_i % interval == 0:
            pct     = day_i / n_days * 100
            elapsed = _time.time() - bt_t0
            eta_sec = int(elapsed / max(day_i, 1) * (n_days - day_i))
            print(f"  backtest {pct:>5.1f}%  {dt.date()}  "
                  f"sat: {len(active_sat)}  shorts: {len(active_short)}  "
                  f"core: {len(active_value)}  "
                  f"ETA {eta_sec//60}m{eta_sec%60:02d}s", flush=True)

        if dt in filings_by_date:
            cutoff = get_pb_cutoff(dt)
            for _, row in filings_by_date[dt].iterrows():
                ticker = row["ticker"]
                pb     = row["pb"]
                score  = int(row["fscore"])
                filed  = row["filed"]

                active_sat.pop(ticker, None)
                active_short.pop(ticker, None)
                active_value.pop(ticker, None)

                if pd.isna(pb) or pd.isna(score):
                    continue
                if pb > cutoff:
                    continue

                active_value[ticker] = filed   # all value-bucket stocks → core

                if score >= LONG_THRESH:
                    if liquid_on(ticker, dt) and above_sector_mom(ticker, dt):
                        active_sat[ticker] = filed
                elif score <= SHORT_THRESH:
                    if liquid_on(ticker, dt):
                        active_short[ticker] = filed

        day_ret = daily_ret.loc[dt]

        # Core: equal-weight all value-bucket stocks
        vals  = [t for t in active_value if t in daily_ret.columns]
        core_ret_day = float(day_ret[vals].mean()) if vals else np.nan

        # Satellite: vol-inverse, sector-capped, gated by MIN_SAT_POSITIONS
        sats   = [t for t in active_sat if t in daily_ret.columns]
        if len(sats) >= MIN_SAT_POSITIONS:
            vol_now = {t: get_vol(t, dt) for t in sats}
            sat_weights = _build_weights(sats, _sector_of, vol_now)
            sat_ret_day = float(sum(sat_weights[t] * day_ret[t] for t in sats))
        else:
            sat_ret_day = np.nan

        # Sleeve composite
        if not np.isnan(core_ret_day):
            if not np.isnan(sat_ret_day):
                sleeve_day = CORE_WEIGHT * core_ret_day + SAT_WEIGHT * sat_ret_day
            else:
                sleeve_day = core_ret_day   # satellite inactive → 100% core
        else:
            sleeve_day = np.nan

        val_rets.append(core_ret_day)
        sat_rets.append(sat_ret_day)
        sleeve_rets.append(sleeve_day)

        shorts = [t for t in active_short if t in daily_ret.columns]
        lr = sat_ret_day if not np.isnan(sat_ret_day) else 0.0
        sr = float(day_ret[shorts].mean()) if shorts else 0.0
        ls_rets.append((lr - sr) / 2 if (sats or shorts) else np.nan)

    idx = trade_dates

    def to_series(arr: list) -> pd.Series:
        return pd.Series(arr, index=idx, dtype=float)

    core_ret   = to_series(val_rets).dropna()
    sat_ret    = to_series(sat_rets).dropna()
    sleeve_ret = to_series(sleeve_rets).dropna()
    ls_ret     = to_series(ls_rets).dropna()

    if core_ret.empty or len(core_ret) < 50:
        return {}

    # Information Ratio: excess return of sleeve over core / tracking error
    common = core_ret.index.intersection(sleeve_ret.index)
    excess = sleeve_ret.loc[common] - core_ret.loc[common]
    ir = float((excess.mean() * 252) / (excess.std() * np.sqrt(252))) if len(excess) > 10 else 0.0

    # Annual breakdown for sleeve
    yearly = []
    for yr, grp in sleeve_ret.groupby(sleeve_ret.index.year):
        core_yr  = core_ret.reindex(grp.index)
        n_sat    = int(to_series(sat_rets).reindex(grp.index).notna().sum())
        yearly.append({
            "year":        yr,
            "sleeve":      round(float((1 + grp.mean()) ** 252 - 1), 4),
            "core":        round(float((1 + core_yr.mean()) ** 252 - 1), 4),
            "n_sat_days":  n_sat,
        })

    return {
        "core":         core_ret,
        "satellite":    sat_ret,
        "sleeve":       sleeve_ret,
        "ls":           ls_ret,
        "metrics_core": _metrics(core_ret),
        "metrics_sat":  _metrics(sat_ret)    if not sat_ret.empty    else {},
        "metrics_sl":   _metrics(sleeve_ret),
        "metrics_ls":   _metrics(ls_ret)     if not ls_ret.empty     else {},
        "ir":           round(ir, 3),
        "yearly":       pd.DataFrame(yearly),
        "panel_with_pb": panel,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> None:
    print("=" * 70)
    print("PIOTROSKI F-SCORE v9 - CORE-ONLY VALUE BUCKET")
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Core: equal-weight all P/B < {PB_VALUE_BUCKET:.0%} IWM small-caps (event-driven)")
    print(f"Satellite: DISABLED (MIN_SAT_POSITIONS={MIN_SAT_POSITIONS})")
    print(f"ADV >= ${MIN_ADV_USD/1e6:.0f}M  |  "
          f"Entry lag: {ENTRY_LAG_DAYS}d  |  Expiry: {SIGNAL_EXPIRY_DAYS}d  |  "
          f"Sector cap: {MAX_SECTOR_WEIGHT:.0%}")
    print(f"Excluded sectors: {', '.join(EXCLUDED_SECTORS)}")
    print("=" * 70)
    print("\nWARNING: Survivorship bias - IWM holdings are current survivors.")
    print("  Short-side returns will be understated vs a true 2012 universe.\n")

    # --- Universe ---
    print("Loading IWM universe...")
    universe    = load_iwm_universe()
    cik_map     = get_cik_map()
    sector_map  = get_sector_map()
    print(f"  {len(universe)} tickers (capped at MAX_UNIVERSE={MAX_UNIVERSE})")

    # --- EDGAR signals ---
    import sys
    import time as _time

    all_rows: list[dict] = []
    tickers_ok: list[str] = []
    n = len(universe)
    t0 = _time.time()

    print(f"\nFetching EDGAR data for {n} tickers (cached tickers are instant)...")
    for i, ticker in enumerate(universe):
        # Always show current ticker so progress is visible even on skips
        elapsed = _time.time() - t0
        eta_str = ""
        if i > 0:
            rate    = elapsed / i
            eta_sec = int(rate * (n - i))
            eta_str = f"  ETA {eta_sec//60}m{eta_sec%60:02d}s"
        print(f"  [{i+1:>3}/{n}] {ticker:<6}", end="", flush=True)

        cik = cik_map.get(ticker)
        if not cik:
            print("  no CIK"); continue

        facts = get_company_facts(cik)
        if not facts:
            print("  no XBRL"); continue

        # yfinance bvps fallback (only fetched if EDGAR equity will be missing)
        yf_bvps = np.nan
        try:
            info    = yf.Ticker(ticker).info
            yf_bvps = float(info.get("bookValue") or np.nan)
        except Exception:
            pass

        df = compute_signals(facts, yf_bvps_fallback=yf_bvps)
        if df.empty:
            print("  insufficient data"); continue

        tickers_ok.append(ticker)
        latest = df.iloc[-1]
        sig = ("LONG"  if latest["fscore"] >= LONG_THRESH else
               "SHORT" if latest["fscore"] <= SHORT_THRESH else "-")
        cached = "" if not (CACHE_DIR / f"{cik}.json").exists() else ""
        bvps_str = f"{latest['bvps']:.2f}" if not pd.isna(latest["bvps"]) else "n/a"
        print(f"  F={int(latest['fscore'])} [{sig:<5}]  bvps={bvps_str:<8}  "
              f"filed={df.index[-1].date()}{eta_str}")

        for filed, row in df.iterrows():
            all_rows.append({
                "ticker": ticker,
                "filed":  filed,
                "fscore": row["fscore"],
                "bvps":   row["bvps"],
                "sector": sector_map.get(ticker, "Unknown"),
            })

    elapsed_total = int(_time.time() - t0)
    panel = pd.DataFrame(all_rows)
    print(f"\nSuccessful: {len(tickers_ok)}/{n} tickers, "
          f"{len(panel)} filing events  ({elapsed_total}s)")

    if panel.empty:
        print("No data. Exiting.")
        return

    # --- Score distribution ---
    print("\nF-Score distribution:")
    counts = panel["fscore"].value_counts().sort_index()
    for score, cnt in counts.items():
        bar = "#" * int(float(cnt) / float(counts.max()) * 40)
        print(f"  {score!s:>2}  {bar:<40}  {cnt:>4}")
    print(f"\n  Mean: {panel['fscore'].mean():.2f}  "
          f"Satellite pool (F>={LONG_THRESH}): {(panel['fscore'] >= LONG_THRESH).mean():.1%}  "
          f"Short pool (F<={SHORT_THRESH}): {(panel['fscore'] <= SHORT_THRESH).mean():.1%}")

    # --- Prices + Volume ---
    print(f"\nFetching prices for {len(tickers_ok)} tickers + SPY  (this may take ~30s)...")
    raw = yf.download(tickers_ok + ["SPY"], start=START_DATE, end=END_DATE,
                      auto_adjust=True, progress=False)
    prices: pd.DataFrame = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw  # type: ignore[assignment]
    assert prices is not None
    prices.index = pd.to_datetime(prices.index).tz_localize(None)

    spy_ret = prices["SPY"].pct_change().dropna()
    stock_prices = prices.drop(columns=["SPY"], errors="ignore")

    # 60-day rolling median ADV (price × volume) for liquidity filter
    adv: pd.DataFrame | None = None
    if isinstance(raw.columns, pd.MultiIndex) and "Volume" in raw.columns.get_level_values(0):
        vol_df = raw["Volume"].copy()
        vol_df.index = pd.to_datetime(vol_df.index).tz_localize(None)
        vol_df = vol_df.drop(columns=["SPY"], errors="ignore")
        adv_daily = stock_prices * vol_df
        adv = adv_daily.rolling(60, min_periods=20).median()
        liquid_pct = (adv >= MIN_ADV_USD).mean().mean()
        print(f"  Liquidity filter (ADV >= ${MIN_ADV_USD:,.0f}): "
              f"{liquid_pct:.0%} of ticker-days are liquid")

    # Sector-relative 3m momentum rank — also used in current-signals display
    mom_63 = stock_prices.pct_change(63)
    if MOMENTUM_SECTOR_THRESHOLD > 0:
        _sg: dict[str, list[str]] = {}
        for t, s in sector_map.items():
            if t in mom_63.columns:
                _sg.setdefault(s, []).append(t)
        _rf = [mom_63[ts].rank(axis=1, pct=True) for ts in _sg.values()]
        sector_mom_rank: pd.DataFrame | None = pd.concat(_rf, axis=1).reindex(
            columns=mom_63.columns)
    else:
        sector_mom_rank = None

    # --- Backtest ---
    n_days_est = len(pd.bdate_range(START_DATE, END_DATE))
    print(f"Running event-driven backtest (~{n_days_est} trading days)...")
    result = run_backtest(panel, stock_prices, adv=adv, sector_of=sector_map)

    if not result:
        print("Insufficient data for backtest.")
        return

    # IWM benchmark over same period as long-only
    iwm_raw = yf.download("IWM", start=START_DATE, end=END_DATE,
                           auto_adjust=True, progress=False)
    iwm_ret = iwm_raw["Close"].squeeze().pct_change()
    iwm_ret.index = pd.to_datetime(iwm_ret.index).tz_localize(None)

    def bench_stats(bench: pd.Series, ret: pd.Series) -> tuple[float, float, float]:
        b = bench.reindex(ret.index).fillna(0)
        b_ann = float(b.mean() * 252)
        b_sr  = b_ann / float(b.std() * np.sqrt(252))
        b_cum = float((1 + b).prod() - 1)
        return b_ann, b_sr, b_cum

    iwm_ann, iwm_sr, iwm_cum = bench_stats(iwm_ret, result["sleeve"])
    spy_ann, spy_sr, spy_cum = bench_stats(spy_ret, result["sleeve"])

    m_sl   = result["metrics_sl"]
    m_core = result["metrics_core"]
    m_sat  = result["metrics_sat"]
    m_ls   = result["metrics_ls"]
    ir     = result["ir"]

    print("\n" + "=" * 70)
    print("BACKTEST RESULTS  (Sleeve: Core + Satellite)")
    print("=" * 70)

    sl_cum   = float(m_sl["cum"].iloc[-1] - 1)
    core_cum = float(m_core["cum"].iloc[-1] - 1)

    print(f"\n  PRIMARY: Sleeve ({CORE_WEIGHT:.0%} core + {SAT_WEIGHT:.0%} satellite) vs benchmarks")
    print(f"  {'':22} {'Sleeve':>10}  {'Core':>10}  {'IWM':>10}  {'SPY':>10}")
    print(f"  {'Ann. return':22} {m_sl['ann_return']:>+10.2%}  {m_core['ann_return']:>+10.2%}  "
          f"{iwm_ann:>+10.2%}  {spy_ann:>+10.2%}")
    print(f"  {'Ann. vol':22} {m_sl['ann_vol']:>10.2%}  {m_core['ann_vol']:>10.2%}")
    print(f"  {'Sharpe':22} {m_sl['sharpe']:>10.2f}  {m_core['sharpe']:>10.2f}  "
          f"{iwm_sr:>10.2f}  {spy_sr:>10.2f}")
    print(f"  {'Max drawdown':22} {m_sl['max_drawdown']:>10.2%}  {m_core['max_drawdown']:>10.2%}")
    print(f"  {'Total return':22} {sl_cum:>+10.2%}  {core_cum:>+10.2%}  "
          f"{iwm_cum:>+10.2%}  {spy_cum:>+10.2%}")
    print(f"  {'Information Ratio':22} {ir:>10.3f}  (sleeve excess return / tracking error vs core)")

    if m_sat:
        sat_cum = float(m_sat["cum"].iloc[-1] - 1)
        sat_days = int(result["satellite"].notna().sum()) if "satellite" in result else 0
        print(f"\n  Satellite standalone: ann={m_sat['ann_return']:+.2%}  "
              f"sharpe={m_sat['sharpe']:.2f}  total={sat_cum:+.2%}  "
              f"active days={len(result['satellite'])}")
        print(f"  Satellite alpha vs core: {m_sat['ann_return'] - m_core['ann_return']:+.2%} ann")

    if m_ls:
        ls_cum = float(m_ls["cum"].iloc[-1] - 1)
        print(f"\n  SECONDARY: Long-Short  ann={m_ls['ann_return']:+.2%}  "
              f"sharpe={m_ls['sharpe']:.2f}  total={ls_cum:+.2%}")
        print(f"  (Note: short-side understated due to survivorship bias)")

    if not result["yearly"].empty:
        print("\nYear-by-year:")
        ydf = result["yearly"].copy()
        yearly_iwm = {yr: float((1 + grp.mean()) ** 252 - 1)
                      for yr, grp in iwm_ret.groupby(iwm_ret.index.year)}
        ydf["sleeve"] = ydf["sleeve"].map("{:+.1%}".format)
        ydf["core"]   = ydf["core"].map("{:+.1%}".format)
        ydf["iwm"]    = ydf["year"].map(lambda y: f"{yearly_iwm.get(y, 0):+.1%}")
        print(ydf.to_string(index=False))

    # --- Current signals ---
    print("\n" + "=" * 70)
    print("CURRENT SIGNALS (latest 10-K, two-stage: value bucket then F-Score)")
    print("=" * 70)

    # Current P/B cutoff: compute from panel (which has pb column after backtest)
    # Use trailing 12m filings from today
    today_ts = pd.Timestamp(END_DATE)
    panel_pb  = result["panel_with_pb"]
    pb_window = panel_pb[
        (panel_pb["filed"] >= today_ts - pd.Timedelta(days=365)) &
        (panel_pb["filed"] <= today_ts)
    ]["pb"].dropna()
    curr_cut = float(pb_window.quantile(PB_VALUE_BUCKET)) if len(pb_window) >= 10 else np.inf

    curr_rows = []
    expiry_cutoff = today_ts - pd.Timedelta(days=SIGNAL_EXPIRY_DAYS)
    latest_panel = panel.sort_values("filed").groupby("ticker").last().reset_index()
    # Apply signal expiry: skip tickers whose most recent 10-K is too old
    latest_panel = latest_panel[latest_panel["filed"] >= expiry_cutoff]
    for _, row in latest_panel.iterrows():
        ticker = row["ticker"]
        if ticker not in prices.columns:
            continue
        last_price = float(prices[ticker].dropna().iloc[-1])
        bvps       = float(row["bvps"]) if not pd.isna(row["bvps"]) else np.nan
        pb         = last_price / bvps  if bvps > 0 else np.nan
        score      = row["fscore"]
        in_val     = (not pd.isna(pb)) and pb <= curr_cut

        # Current ADV (last available value)
        adv_val = np.nan
        if adv is not None and ticker in adv.columns:
            adv_series = adv[ticker].dropna()
            if not adv_series.empty:
                adv_val = float(adv_series.iloc[-1])
        is_liquid = pd.isna(adv_val) or adv_val >= MIN_ADV_USD

        # Sector-relative 3m momentum rank (last available day)
        sec_mom_val = np.nan
        if sector_mom_rank is not None and ticker in sector_mom_rank.columns:
            sm_series = sector_mom_rank[ticker].dropna()
            if not sm_series.empty:
                sec_mom_val = float(sm_series.iloc[-1])
        above_mom = pd.isna(sec_mom_val) or sec_mom_val >= MOMENTUM_SECTOR_THRESHOLD

        if in_val:
            if score >= LONG_THRESH:
                if is_liquid and above_mom:
                    sig = "SAT"    # satellite — full quality filter passed
                elif not is_liquid:
                    sig = "SAT*"   # satellite candidate, illiquid
                else:
                    sig = "SAT~"   # satellite candidate, below sector momentum
            elif score <= SHORT_THRESH:
                sig = "SHORT" if is_liquid else "SHORT*"
            else:
                sig = "core"       # in value bucket (core), no satellite signal
        else:
            sig = "-"

        curr_rows.append({
            "ticker":  ticker,
            "filed":   row["filed"].date(),
            "fscore":  int(score),
            "pb":      round(pb, 2) if not pd.isna(pb) else None,
            "adv_m":   round(adv_val / 1e6, 1) if not pd.isna(adv_val) else None,
            "sector":  sector_map.get(ticker, ""),
            "in_val":  in_val,
            "signal":  sig,
        })

    curr_df = pd.DataFrame(curr_rows)
    print(f"\n  P/B cutoff (bottom {PB_VALUE_BUCKET:.0%}): {curr_cut:.2f}")
    print(f"  SAT = satellite (F>={LONG_THRESH} + sector-mom + ADV)  |  * = illiquid  |  ~ = below sector momentum")
    for sig_label in ["SAT", "SAT*", "SAT~", "SHORT", "SHORT*", "core"]:
        subset = curr_df[curr_df["signal"] == sig_label]
        if not subset.empty:
            print(f"\n{sig_label} ({len(subset)}):")
            print(subset[["ticker", "filed", "fscore", "pb", "adv_m", "sector"]].to_string(index=False))


if __name__ == "__main__":
    run()
