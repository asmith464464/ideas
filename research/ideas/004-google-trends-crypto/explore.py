"""
Exploratory analysis for idea 004 -- Google Trends Multi-Crypto Attention Strategy.
Run from repo root: python research/ideas/004-google-trends-crypto/explore.py [section]

Sections:
  universe     -- show master coin list, coverage, and data-availability gating
  data         -- fetch price and Trends data for the active universe
  features     -- attention momentum, Z-score distributions and correlations
  signals      -- combined score, rank stability, turnover estimate
  backtest     -- v1 backtest: attention-only, monthly, N=3 (best config from sweep)
  v2           -- v2 sweep: grid over beta/N/freq/costs with dynamic universe
  collapse     -- collapse test: did Z-score reduce exposure before LUNA/FTX crashes?
  clusters     -- cluster-based strategy: rank within peer groups (L1, DeFi, etc.)
  ew_tilt      -- equal-weight baseline + attention momentum tilt overlay
  auto_cluster -- data-driven clustering from attention correlation (hierarchical)
  cluster_tilt -- EW-per-cluster base + within-cluster attention tilt
  z_sweep      -- Z-penalty sensitivity: none vs relaxed (Z>4) vs current (Z>2.5)
  daily_signal -- 7/14-day momentum using daily Wikipedia data
  robustness   -- cluster edge robustness: permutation test + out-of-sample 2024-25
  final_signal -- cluster tilt with 21d momentum (best config integration test)
  stress_test  -- structured cluster stress tests: remove / merge / split clusters
  walkforward  -- rolling annual walk-forward: per-year and 2-year window performance
  execution    -- realistic execution: biweekly rebalance + liquidity assumptions
  regime       -- BTC attention regime filter: scale tilt on BTC Z-score
  all          -- run all sections (default)
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import yaml

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[3]
IDEA_DIR = ROOT / "docs" / "ideas" / "004-google-trends-crypto"
CONFIG_PATH = IDEA_DIR / "config.yaml"

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

# Import universe definition
sys.path.insert(0, str(Path(__file__).parent))
from universe import UNIVERSE, BY_SYMBOL, WIKI_ARTICLES, TRENDS_KEYWORDS, filter_available

START = CONFIG["date_range"]["start"]
END   = CONFIG["date_range"]["end"]

PRICE_CACHE_DIR = ROOT / "data" / "cache" / "004_prices"
PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Wikipedia fetcher (primary attention source)
sys.path.insert(0, str(ROOT))
from data.fetchers.wikipedia_fetcher import WikipediaFetcher
WIKI_FETCHER = WikipediaFetcher(cache_dir=ROOT / "data" / "cache")

TOP_N            = 3
MOMENTUM_WINDOW  = 4    # weeks
ZSCORE_WINDOW    = 52   # weeks
ZSCORE_THRESHOLD = 2.5
W_PENALTY        = 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sep(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def fetch_prices(symbols: list[str] | None = None) -> pd.DataFrame:
    """
    Weekly (Friday) close prices for all universe coins.

    Uses yfinance for coins with a yf_ticker; falls back to CryptoCompare
    for those without (exchange tokens, delisted coins).  Per-coin parquet
    cache means delisted coins are never re-fetched once cached.

    Pass `symbols` to restrict to a subset; defaults to full universe.
    """
    if symbols is None:
        symbols = [c["symbol"] for c in UNIVERSE]

    yf_coins = [(s, BY_SYMBOL[s]["yf_ticker"]) for s in symbols
                if s in BY_SYMBOL and BY_SYMBOL[s].get("yf_ticker")]
    cc_coins  = [s for s in symbols
                 if s in BY_SYMBOL and not BY_SYMBOL[s].get("yf_ticker")]

    frames: list[pd.Series] = []

    # --- yfinance batch ---
    if yf_coins:
        tickers = [t for _, t in yf_coins]
        sym_map = {t: s for s, t in yf_coins}
        cache = PRICE_CACHE_DIR / "yf_batch.parquet"
        if cache.exists():
            raw_close = pd.read_parquet(cache)
        else:
            raw = yf.download(tickers, start=START, end=END, interval="1d",
                              progress=False, auto_adjust=True)
            raw_close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
            raw_close.to_parquet(cache)
        raw_close.index = pd.to_datetime(raw_close.index).normalize()
        for ticker, sym in sym_map.items():
            col = ticker if ticker in raw_close.columns else sym
            if col in raw_close.columns:
                s = raw_close[col].resample("W-FRI").last().rename(sym)
                frames.append(s)

    # --- CryptoCompare fallback ---
    if cc_coins:
        sys.path.insert(0, str(ROOT))
        from data.fetchers.cryptocompare_fetcher import CryptoCompareFetcher
        cc = CryptoCompareFetcher(cache_dir=PRICE_CACHE_DIR)
        for sym in cc_coins:
            s = cc.fetch_weekly_close(sym, START, END)
            if not s.empty:
                frames.append(s.rename(sym))

    if not frames:
        return pd.DataFrame()

    prices = pd.concat(frames, axis=1).sort_index()
    return prices


def fetch_attention(
    symbols: list[str] | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch daily Wikipedia pageviews for all coins that have a WIKI_ARTICLES entry,
    resampled to weekly (Friday sum).  Returns DataFrame (week x symbol).

    Wikipedia is used instead of Google Trends because:
    - Daily granularity (vs weekly from Trends)
    - No rate limiting — full history fetched in seconds
    - Covers delisted coins (LUNA, FTX) with accurate collapse peaks
    - No cross-batch normalisation complexity
    """
    if symbols is None:
        symbols = [c["symbol"] for c in UNIVERSE]

    # Only fetch coins that have a Wikipedia article defined
    articles = {s: WIKI_ARTICLES[s] for s in symbols if s in WIKI_ARTICLES}
    missing  = [s for s in symbols if s not in WIKI_ARTICLES]
    if missing:
        print(f"  No Wikipedia article for: {', '.join(missing)} — excluded from attention signal")

    daily = WIKI_FETCHER.fetch_all(articles, START, END, force_refresh=force_refresh)
    if daily.empty:
        return pd.DataFrame()

    # Normalise: divide each coin by its own rolling 52-week mean so that
    # large-cap coins (BTC: 10k views/day) and small-cap coins (SOL: 100 views/day)
    # are on a comparable scale before computing cross-coin scores
    weekly = WIKI_FETCHER.weekly(daily)
    return weekly


def build_features(trends: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (momentum_df, zscore_df) — both indexed by week.
    Z-score computed on absolute attention levels (52-week rolling window).
    Momentum = 4-week % change in composite attention, clipped to [-5, 5]
    to avoid inf from zero-attention prior periods.
    """
    momentum = trends.pct_change(MOMENTUM_WINDOW).clip(-5, 5)
    rolling_mean = trends.rolling(ZSCORE_WINDOW, min_periods=26).mean()
    rolling_std = trends.rolling(ZSCORE_WINDOW, min_periods=26).std()
    zscore = (trends - rolling_mean) / rolling_std.replace(0, np.nan)
    return momentum, zscore


def build_price_momentum(prices: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """
    N-week price momentum: cumulative return over past `window` weeks,
    excluding the most recent week (skip-1 to reduce short-term reversal noise).
    Cross-sectionally z-scored each week so it is on the same scale as
    the attention signal.
    """
    # Return from T-window to T-1 (skip most recent week)
    raw = prices.shift(1).pct_change(window - 1)
    # Cross-sectional z-score per row
    mu = raw.mean(axis=1)
    sigma = raw.std(axis=1).replace(0, np.nan)
    cs_zscore = raw.sub(mu, axis=0).div(sigma, axis=0)
    return cs_zscore


def build_combined_score(
    attention_momentum: pd.DataFrame,
    zscore: pd.DataFrame,
    price_momentum: pd.DataFrame | None = None,
    alpha: float = 0.0,
    beta: float = W_PENALTY,
    z_threshold: float = ZSCORE_THRESHOLD,
) -> pd.DataFrame:
    """
    Combined score per asset per week.

    score = price_momentum + alpha * attention_momentum - beta * max(0, Z - z_threshold)

    When price_momentum is None (attention-only mode), price momentum is excluded.
    When alpha=0 (price-only mode), attention momentum is excluded.
    """
    penalty = (zscore - z_threshold).clip(lower=0)
    score = -beta * penalty  # start with penalty term

    if price_momentum is not None:
        score = score.add(price_momentum, fill_value=0)

    if alpha != 0:
        score = score.add(alpha * attention_momentum, fill_value=0)

    return score


def run_backtest(
    score: pd.DataFrame,
    prices: pd.DataFrame,
    top_n: int = 2,
    rebalance_freq: int = 1,
    cost_bps: float = 0.0,
) -> dict:
    """
    Generalized backtest engine.

    score      : weekly score per asset (signal from week T, trade at T+1)
    prices     : weekly close prices
    top_n      : number of assets to hold
    rebalance_freq : rebalance every N weeks (1=weekly, 2=biweekly, 4=monthly)
    cost_bps   : one-way transaction cost in basis points per asset traded

    Returns dict with keys: returns (pd.Series), metrics (dict), turnover (float).
    """
    weekly_ret = prices.pct_change()
    score_lagged = score.shift(1)

    cost = cost_bps / 10_000

    holdings: frozenset = frozenset()
    portfolio_returns = []
    weeks_since_rebalance = 0

    for date in weekly_ret.index:
        if date not in score_lagged.index:
            continue

        # Rebalance decision
        if weeks_since_rebalance >= rebalance_freq:
            row = score_lagged.loc[date].dropna()
            if len(row) >= top_n:
                new_holdings = frozenset(row.nlargest(top_n).index)
            else:
                new_holdings = frozenset(row.index)

            # Transaction cost: assets entering or exiting the portfolio
            entries = new_holdings - holdings
            exits = holdings - new_holdings
            traded = len(entries) + len(exits)
            tc = cost * traded / max(len(new_holdings), 1) if new_holdings else 0.0

            holdings = new_holdings
            weeks_since_rebalance = 0
        else:
            tc = 0.0

        weeks_since_rebalance += 1

        if not holdings:
            portfolio_returns.append((date, 0.0))
            continue

        ret = weekly_ret.loc[date, list(holdings)].mean()
        portfolio_returns.append((date, ret - tc))

    port = pd.Series(
        {d: r for d, r in portfolio_returns},
        name="return",
    ).dropna()

    ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
    ann_vol = port.std() * np.sqrt(52)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    cum = (1 + port).cumprod()
    max_dd = (cum / cum.cummax() - 1).min()

    return {
        "returns": port,
        "cagr": ann_ret,
        "vol": ann_vol,
        "sharpe": sharpe,
        "max_dd": max_dd,
    }


# ---------------------------------------------------------------------------
# Section: universe
# ---------------------------------------------------------------------------

def section_universe() -> None:
    sep("UNIVERSE")

    coins = UNIVERSE
    print(f"\n  Master list: {len(coins)} coins")

    # Classify
    with_yf  = [c for c in coins if c.get("yf_ticker")]
    cc_only  = [c for c in coins if not c.get("yf_ticker")]
    noted    = [c for c in coins if c.get("notes")]

    print(f"  Price source — yfinance: {len(with_yf)}  |  CryptoCompare only: {len(cc_only)}")
    print(f"  Survivorship-bias additions (noted failures): {len(noted)}")

    print("\n  Notable historical coins (will fall out when data goes NaN):")
    for c in noted:
        print(f"    {c['symbol']:<6s}  {c['name']:<25s}  {c['notes']}")

    # Wikipedia article coverage
    wiki_covered = [c["symbol"] for c in coins if c["symbol"] in WIKI_ARTICLES]
    wiki_missing  = [c["symbol"] for c in coins if c["symbol"] not in WIKI_ARTICLES]
    print(f"\n  Wikipedia attention source: {len(wiki_covered)} coins have articles defined")
    if wiki_missing:
        print(f"  No Wikipedia article: {', '.join(wiki_missing)}")

    # Which are already cached locally
    wiki_cached   = [s for s in wiki_covered if WIKI_FETCHER._cache_path(s).exists()]
    wiki_uncached = [s for s in wiki_covered if not WIKI_FETCHER._cache_path(s).exists()]
    print(f"  Cached: {len(wiki_cached)}  |  Not yet fetched: {len(wiki_uncached)}")
    if wiki_uncached:
        print(f"  Run: explore.py data --fetch-attention")

    # Price cache
    yf_cache = PRICE_CACHE_DIR / "yf_batch.parquet"
    print(f"\n  Price cache (yfinance batch): {'exists' if yf_cache.exists() else 'not yet fetched'}")


# ---------------------------------------------------------------------------
# Section: data
# ---------------------------------------------------------------------------

def section_data(symbols: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    sep("DATA")

    if symbols is None:
        symbols = [c["symbol"] for c in UNIVERSE]

    print(f"\n--- Price data ({len(symbols)} coins) ---")
    prices = fetch_prices(symbols)
    if prices.empty:
        print("  No price data returned.")
        return pd.DataFrame(), pd.DataFrame()
    print(f"  Shape: {prices.shape}  ({prices.index[0].date()} to {prices.index[-1].date()})")

    # Coverage summary
    coverage = prices.notna().sum().sort_values(ascending=False)
    full = (coverage == coverage.max()).sum()
    print(f"  Full history ({coverage.max()} weeks): {full} coins")
    partial = ((coverage > 0) & (coverage < coverage.max())).sum()
    print(f"  Partial history: {partial} coins")
    no_data = (coverage == 0).sum()
    if no_data:
        print(f"  No data at all: {no_data} coins — "
              f"{list(prices.columns[coverage == 0])}")

    print("\n--- Wikipedia attention data ---")
    attention = fetch_attention(symbols)
    if attention.empty:
        print("  No attention data returned.")
        return prices, pd.DataFrame()

    print(f"  Shape: {attention.shape}  "
          f"({attention.index[0].date()} to {attention.index[-1].date()})")

    # Coins with at least some data
    coverage_a = attention.notna().sum()
    print(f"  Coins with data: {(coverage_a > 0).sum()}/{len(attention.columns)}")

    # Align on common dates
    common_idx = prices.index.intersection(attention.index)
    prices_a   = prices.loc[common_idx]
    attn_a     = attention.loc[common_idx]

    # Data-availability gate at final date
    last      = common_idx[-1]
    available = filter_available(list(prices_a.columns), prices_a, attn_a, last)
    print(f"\n  Available (price + attention) at {last.date()}: "
          f"{len(available)}/{len(symbols)} coins")
    print(f"  {', '.join(available)}")

    return prices_a, attn_a


# ---------------------------------------------------------------------------
# Section: features
# ---------------------------------------------------------------------------

def section_features(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("FEATURES")

    if trends.empty:
        print("  No Trends data — skipping.")
        return

    momentum, zscore = build_features(trends)
    valid_from = momentum.dropna(how="all").index[0]
    print(f"\n  First valid signal week (after burn-in): {valid_from.date()}")
    print(f"  (52-week Z-score burn-in + 4-week momentum window)")

    print("\n--- Attention momentum (4w % chg) summary ---")
    print(momentum.describe().round(3).to_string())

    print("\n--- Z-score summary ---")
    print(zscore.describe().round(3).to_string())

    print("\n--- Attention level correlation (Spearman, time-averaged) ---")
    corr = trends.corr(method="spearman")
    print(corr.round(3).to_string())

    print("\n--- Momentum vs next-week price return (Spearman rank IC) ---")
    weekly_ret = prices.pct_change().shift(-1)  # next week return
    ics = {}
    for asset in trends.columns:
        combined = pd.concat([momentum[asset], weekly_ret[asset]], axis=1).dropna()
        if len(combined) < 20:
            continue
        ic = combined.iloc[:, 0].corr(combined.iloc[:, 1], method="spearman")
        ics[asset] = round(ic, 4)
    for asset, ic in ics.items():
        print(f"    {asset}: IC = {ic}")

    print("\n--- Z > 2 event frequency per asset ---")
    for col in zscore.columns:
        n = (zscore[col] > ZSCORE_THRESHOLD).sum()
        total = zscore[col].notna().sum()
        print(f"    {col}: {n} weeks ({100*n/total:.1f}% of valid weeks)" if total > 0 else f"    {col}: no data")


# ---------------------------------------------------------------------------
# Section: signals
# ---------------------------------------------------------------------------

def section_signals(prices: pd.DataFrame, trends: pd.DataFrame) -> pd.DataFrame:
    sep("SIGNALS")

    if trends.empty:
        print("  No Trends data — skipping.")
        return pd.DataFrame()

    momentum, zscore = build_features(trends)
    score = build_combined_score(momentum, zscore)

    # Rank assets each week (higher = better)
    ranks = score.rank(axis=1, ascending=False)

    print("\n--- Combined score summary ---")
    print(score.describe().round(3).to_string())

    print("\n--- Weekly rank distribution (1 = best) ---")
    print(ranks.describe().round(2).to_string())

    # Turnover: how often does the top-N set change week-to-week?
    top_n_sets = ranks.apply(lambda row: frozenset(row[row <= TOP_N].index), axis=1)
    changes = (top_n_sets != top_n_sets.shift()).sum()
    total = top_n_sets.notna().sum()
    print(f"\n  Portfolio changes: {changes} / {total} weeks ({100*changes/total:.1f}%)")

    # Most common top-2 pairs
    from collections import Counter
    counter = Counter(top_n_sets.dropna())
    print("\n  Most common top-2 pairs:")
    for pair, count in counter.most_common(5):
        print(f"    {set(pair)}: {count} weeks")

    return score


# ---------------------------------------------------------------------------
# Section: backtest (v1)
# ---------------------------------------------------------------------------

def section_backtest(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("BACKTEST (v1 — attention only, weekly, no costs)")

    if trends.empty:
        print("  No Trends data — skipping.")
        return

    momentum, zscore = build_features(trends)
    score = build_combined_score(attention_momentum=momentum, zscore=zscore, alpha=1.0)

    # Restrict to coins that have both price and Trends data — avoids inf/NaN
    # from collapsed coins (LUNA etc.) polluting the equal-weight benchmark
    active_cols = [c for c in trends.columns if c in prices.columns]
    prices_active = prices[active_cols]
    weekly_ret = prices_active.pct_change().clip(-0.95, 10)  # cap extreme single-week moves
    btc_ret = weekly_ret["BTC"].dropna()
    ew_ret  = weekly_ret.mean(axis=1).dropna()

    result = run_backtest(score, prices_active, top_n=TOP_N, rebalance_freq=1, cost_bps=0)
    port = result["returns"]

    idx = port.index.intersection(btc_ret.index).intersection(ew_ret.index)
    port    = port.loc[idx]
    btc_ret = btc_ret.loc[idx]
    ew_ret  = ew_ret.loc[idx]

    def stats(r: pd.Series, label: str) -> None:
        ann_ret = (1 + r).prod() ** (52 / len(r)) - 1
        ann_vol = r.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + r).cumprod()
        drawdown = (cum / cum.cummax() - 1).min()
        print(f"  {label:40s}  CAGR={ann_ret:+.1%}  Vol={ann_vol:.1%}  Sharpe={sharpe:.2f}  MaxDD={drawdown:.1%}")

    print(f"\n  Universe: {active_cols}")
    print(f"  Period: {idx[0].date()} to {idx[-1].date()}  ({len(idx)} weeks)\n")
    stats(port, f"Attention Top-{TOP_N}")
    stats(btc_ret, "Benchmark: BTC buy-and-hold")
    stats(ew_ret, f"Benchmark: Equal-weight ({len(active_cols)} coins)")


# ---------------------------------------------------------------------------
# Section: v2 — combined signal sweep
# ---------------------------------------------------------------------------

def section_v2(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("V2 SWEEP — price + attention combined signal")

    if trends.empty:
        print("  No Trends data — skipping.")
        return

    active_cols = [c for c in trends.columns if c in prices.columns]
    prices_active = prices[active_cols]
    attention_momentum, zscore = build_features(trends[active_cols])
    weekly_ret = prices_active.pct_change().clip(-0.95, 10)
    btc_ret = weekly_ret["BTC"].dropna()
    ew_ret  = weekly_ret.mean(axis=1).dropna()

    # --- Price momentum IC check ---
    print("\n--- Price momentum IC vs next-week return (Spearman) ---")
    for window in (8, 10, 12):
        pm = build_price_momentum(prices_active, window=window)
        ics = []
        for asset in active_cols:
            combined = pd.concat([pm[asset], weekly_ret[asset].shift(-1)], axis=1).dropna()
            if len(combined) < 20:
                continue
            ics.append(combined.iloc[:, 0].corr(combined.iloc[:, 1], method="spearman"))
        print(f"  {window}w price momentum: mean IC = {np.mean(ics):+.4f}  ({len(ics)} assets)")

    price_momentum = build_price_momentum(prices_active, window=10)

    # --- Benchmarks ---
    def _bench_stats(r: pd.Series, label: str) -> str:
        ann_ret = (1 + r).prod() ** (52 / len(r)) - 1
        ann_vol = r.std() * np.sqrt(52)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum = (1 + r).cumprod()
        dd = (cum / cum.cummax() - 1).min()
        return f"  {label:50s}  CAGR={ann_ret:+.1%}  Vol={ann_vol:.1%}  Sharpe={sharpe:.2f}  MaxDD={dd:.1%}"

    # --- Grid sweep ---
    ALPHAS = [0.0, 0.25, 0.5, 1.0]   # attention weight (0 = price-only)
    BETAS  = [0.25, 0.5, 1.0]         # Z-penalty weight
    NS     = [1, 2, 3]                 # top-N assets
    FREQS  = [1, 2, 4]                 # rebalance every N weeks
    COSTS  = [0, 10, 30]               # bps per side

    rows = []
    for alpha in ALPHAS:
        for beta in BETAS:
            for n in NS:
                for freq in FREQS:
                    for cost in COSTS:
                        pm = price_momentum if alpha < 1.0 or True else None
                        score = build_combined_score(
                            attention_momentum=attention_momentum,
                            zscore=zscore,
                            price_momentum=pm,
                            alpha=alpha,
                            beta=beta,
                        )
                        if alpha == 0.0:
                            # price-only: no attention momentum, still apply Z penalty
                            score = build_combined_score(
                                attention_momentum=attention_momentum,
                                zscore=zscore,
                                price_momentum=price_momentum,
                                alpha=0.0,
                                beta=beta,
                            )
                            signal_type = "price+Zpen"
                        elif pm is None or alpha == 0.0:
                            signal_type = "attn_only"
                        else:
                            signal_type = "combined"

                        # Simplify label
                        if alpha == 0.0:
                            signal_type = "price+Zpen"
                        else:
                            signal_type = "combined" if True else "attn_only"

                        res = run_backtest(score, prices, top_n=n, rebalance_freq=freq, cost_bps=cost)
                        rows.append({
                            "signal": signal_type,
                            "alpha": alpha,
                            "beta": beta,
                            "N": n,
                            "freq": freq,
                            "cost_bps": cost,
                            "cagr": res["cagr"],
                            "vol": res["vol"],
                            "sharpe": res["sharpe"],
                            "max_dd": res["max_dd"],
                        })

    # Also run pure attention-only (no price momentum)
    for beta in BETAS:
        for n in NS:
            for freq in FREQS:
                for cost in COSTS:
                    score = build_combined_score(
                        attention_momentum=attention_momentum,
                        zscore=zscore,
                        price_momentum=None,
                        alpha=1.0,
                        beta=beta,
                    )
                    res = run_backtest(score, prices, top_n=n, rebalance_freq=freq, cost_bps=cost)
                    rows.append({
                        "signal": "attn_only",
                        "alpha": 1.0,
                        "beta": beta,
                        "N": n,
                        "freq": freq,
                        "cost_bps": cost,
                        "cagr": res["cagr"],
                        "vol": res["vol"],
                        "sharpe": res["sharpe"],
                        "max_dd": res["max_dd"],
                    })

    grid = pd.DataFrame(rows)

    # --- Benchmarks for reference ---
    idx_full = grid  # just for period reference
    bench_idx = btc_ret.index.intersection(ew_ret.index)
    b_btc = btc_ret.loc[bench_idx]
    b_ew  = ew_ret.loc[bench_idx]

    print(f"\n--- Benchmarks ---")
    print(_bench_stats(b_btc, "BTC buy-and-hold"))
    print(_bench_stats(b_ew,  "Equal-weight all 5"))

    # --- Top results by Sharpe ---
    print(f"\n--- Top 15 combinations by Sharpe ({len(grid)} total) ---")
    top = grid.nlargest(15, "sharpe")
    for _, row in top.iterrows():
        label = f"sig={row['signal']:10s} a={row['alpha']} b={row['beta']} N={int(row['N'])} freq={int(row['freq'])}w cost={int(row['cost_bps'])}bps"
        print(f"  {label}  CAGR={row['cagr']:+.1%}  Vol={row['vol']:.1%}  Sharpe={row['sharpe']:.2f}  MaxDD={row['max_dd']:.1%}")

    # --- Signal type summary: best Sharpe per signal type ---
    print(f"\n--- Best Sharpe by signal type (0-cost, N=2, freq=1) ---")
    subset = grid[(grid["cost_bps"] == 0) & (grid["N"] == 2) & (grid["freq"] == 1)]
    for sig_type in subset["signal"].unique():
        best = subset[subset["signal"] == sig_type].nlargest(1, "sharpe").iloc[0]
        label = f"{sig_type:12s} a={best['alpha']} b={best['beta']}"
        print(f"  {label}  CAGR={best['cagr']:+.1%}  Vol={best['vol']:.1%}  Sharpe={best['sharpe']:.2f}  MaxDD={best['max_dd']:.1%}")

    # --- N sensitivity (best alpha/beta, 0-cost, freq=1) ---
    print(f"\n--- N sensitivity (0-cost, freq=1w, best combined alpha/beta) ---")
    combined = grid[(grid["signal"] == "combined") & (grid["cost_bps"] == 0) & (grid["freq"] == 1)]
    for n in NS:
        best = combined[combined["N"] == n].nlargest(1, "sharpe").iloc[0]
        label = f"N={int(n)} a={best['alpha']} b={best['beta']}"
        print(f"  {label}  CAGR={best['cagr']:+.1%}  Sharpe={best['sharpe']:.2f}  MaxDD={best['max_dd']:.1%}")

    # --- Rebalance frequency sensitivity (best combined, N=2, 0-cost) ---
    print(f"\n--- Rebalance frequency (0-cost, N=2, best combined alpha/beta) ---")
    combined_n2 = grid[(grid["signal"] == "combined") & (grid["cost_bps"] == 0) & (grid["N"] == 2)]
    for freq in FREQS:
        best = combined_n2[combined_n2["freq"] == freq].nlargest(1, "sharpe").iloc[0]
        label = f"freq={int(freq)}w a={best['alpha']} b={best['beta']}"
        print(f"  {label}  CAGR={best['cagr']:+.1%}  Sharpe={best['sharpe']:.2f}  MaxDD={best['max_dd']:.1%}")

    # --- Cost sensitivity: best no-cost config at different cost levels ---
    print(f"\n--- Cost sensitivity for best no-cost combined config ---")
    best_nocost = grid[(grid["signal"] == "combined") & (grid["cost_bps"] == 0)].nlargest(1, "sharpe").iloc[0]
    a_star, b_star, n_star, f_star = best_nocost["alpha"], best_nocost["beta"], int(best_nocost["N"]), int(best_nocost["freq"])
    for cost in COSTS:
        row = grid[
            (grid["signal"] == "combined") &
            (grid["alpha"] == a_star) &
            (grid["beta"] == b_star) &
            (grid["N"] == n_star) &
            (grid["freq"] == f_star) &
            (grid["cost_bps"] == cost)
        ]
        if row.empty:
            continue
        r = row.iloc[0]
        print(f"  cost={int(cost):2d}bps  CAGR={r['cagr']:+.1%}  Sharpe={r['sharpe']:.2f}  MaxDD={r['max_dd']:.1%}")


# ---------------------------------------------------------------------------
# Section: collapse test
# ---------------------------------------------------------------------------

# Key collapse events to test
COLLAPSE_EVENTS = [
    {
        "coin":       "LUNA",
        "name":       "Terra LUNA depeg",
        "crash_date": "2022-05-09",  # UST depeg collapse began ~May 9 2022
        "window":     16,            # weeks to show before crash
    },
    {
        "coin":       "FTT",
        "name":       "FTX collapse",
        "crash_date": "2022-11-07",  # FTX halted withdrawals Nov 8 2022
        "window":     16,
    },
]


def section_collapse_test(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("COLLAPSE TEST — Did Z-score reduce exposure before LUNA / FTX crashes?")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    momentum, zscore = build_features(trends)
    score = build_combined_score(attention_momentum=momentum, zscore=zscore, alpha=1.0)

    # Active universe coins (have both price + attention)
    active_cols = [c for c in trends.columns if c in prices.columns]
    prices_active = prices[active_cols]

    for event in COLLAPSE_EVENTS:
        coin = event["coin"]
        if coin not in trends.columns:
            print(f"\n  [{coin}] Not in attention universe — skipping.")
            continue
        if coin not in prices.columns:
            print(f"\n  [{coin}] No price data — skipping.")
            continue

        crash_date = pd.Timestamp(event["crash_date"])
        # Find the nearest Friday on or before crash_date
        dates_before = trends.index[trends.index <= crash_date]
        if dates_before.empty:
            print(f"\n  [{coin}] No data before crash date — skipping.")
            continue
        crash_week = dates_before[-1]

        # Take window weeks ending at crash_week
        window_dates = trends.index[trends.index <= crash_week][-event["window"]:]

        print(f"\n  {'=' * 55}")
        print(f"  {event['name']} — crash week: {crash_week.date()}")
        print(f"  Showing {len(window_dates)} weeks leading up to collapse")
        print(f"  {'=' * 55}")
        print(f"  {'Week':<12} {'Views':>10} {'4w Momentum':>13} {'Z-score':>9} {'Score':>8} {'Rank':>6} {'In Top-3':>9} {'Price':>12}")
        print(f"  {'-' * 80}")

        # How many coins are ranked each week (need for rank context)
        for date in window_dates:
            views   = trends.loc[date, coin] if not pd.isna(trends.loc[date, coin]) else float("nan")
            mom     = momentum.loc[date, coin] if not pd.isna(momentum.loc[date, coin]) else float("nan")
            z       = zscore.loc[date, coin] if not pd.isna(zscore.loc[date, coin]) else float("nan")
            sc      = score.loc[date, coin] if not pd.isna(score.loc[date, coin]) else float("nan")
            price   = prices.loc[date, coin] if not pd.isna(prices.loc[date, coin]) else float("nan")

            # Rank among all active coins this week
            row_scores = score.loc[date, active_cols].dropna()
            if not pd.isna(sc) and len(row_scores) > 0:
                rank = int((row_scores >= sc).sum())  # how many coins score >= this coin (1 = best)
                in_top3 = "YES" if rank <= 3 else "-"
            else:
                rank = float("nan")
                in_top3 = "n/a"

            z_flag = " <<< Z HIGH" if not pd.isna(z) and z > ZSCORE_THRESHOLD else ""
            print(
                f"  {str(date.date()):<12} "
                f"{views:>10,.0f} "
                f"{mom:>+13.3f} "
                f"{z:>9.3f} "
                f"{sc:>8.3f} "
                f"{rank:>6} "
                f"{in_top3:>9} "
                f"{price:>12.4f}"
                f"{z_flag}"
            )

        # Post-crash: show a few weeks after
        dates_after = trends.index[trends.index > crash_week][:4]
        if not dates_after.empty:
            print(f"  --- collapse ---")
            for date in dates_after:
                price = prices.loc[date, coin] if date in prices.index and not pd.isna(prices.loc[date, coin]) else float("nan")
                mom   = momentum.loc[date, coin] if date in momentum.index and not pd.isna(momentum.loc[date, coin]) else float("nan")
                z     = zscore.loc[date, coin] if date in zscore.index and not pd.isna(zscore.loc[date, coin]) else float("nan")
                sc    = score.loc[date, coin] if date in score.index and not pd.isna(score.loc[date, coin]) else float("nan")
                row_scores = score.loc[date, active_cols].dropna() if date in score.index else pd.Series()
                if not pd.isna(sc) and len(row_scores) > 0:
                    rank = int((row_scores >= sc).sum())
                    in_top3 = "YES" if rank <= 3 else "-"
                else:
                    rank = float("nan")
                    in_top3 = "n/a"
                print(
                    f"  {str(date.date()):<12} "
                    f"{'n/a':>10} "
                    f"{mom:>+13.3f} "
                    f"{z:>9.3f} "
                    f"{sc:>8.3f} "
                    f"{rank:>6} "
                    f"{in_top3:>9} "
                    f"{price:>12.4f}"
                )

    # Summary interpretation
    print(f"\n  --- Interpretation ---")
    print(f"  Does Z > {ZSCORE_THRESHOLD} flag precede the crash?")
    print(f"  If coin exits top-3 before crash week: Z-penalty is a risk management tool.")
    print(f"  If coin stays in top-3 until crash: signal failed to protect.")


# ---------------------------------------------------------------------------
# Section: clusters
# ---------------------------------------------------------------------------

# Coin clusters — rank within peer groups, pick top-1 per cluster
CLUSTERS: dict[str, list[str]] = {
    "old_guard":  ["BTC", "LTC", "BCH", "ETC", "XLM", "DASH", "ZEC"],
    "L1_new":     ["ETH", "SOL", "AVAX", "ATOM", "DOT", "NEAR", "ALGO", "TRX"],
    "DeFi":       ["LINK", "UNI", "AAVE", "MKR", "CRV", "SNX", "SUSHI"],
    "meme":       ["DOGE", "SHIB", "PEPE"],
    "event_risk": ["LUNA", "FTT", "WAVES", "CEL"],
}


def section_clusters(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("CLUSTER-BASED STRATEGY — Rank within peer groups, pick top-1 per cluster")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    momentum, zscore = build_features(trends)
    score = build_combined_score(attention_momentum=momentum, zscore=zscore, alpha=1.0)

    active_cols = [c for c in trends.columns if c in prices.columns]
    prices_active = prices[active_cols]
    weekly_ret = prices_active.pct_change().clip(-0.95, 10)

    print(f"\n  Cluster definitions:")
    for cluster, members in CLUSTERS.items():
        in_universe = [m for m in members if m in active_cols]
        print(f"    {cluster:<15}: {', '.join(in_universe)} ({len(in_universe)} active coins)")

    # Build cluster score: for each week, score is the cluster-rank-normalised signal
    # Strategy: pick the top-1 coin from each cluster (or skip cluster if no data),
    # then equal-weight the selected coins.

    def run_cluster_backtest(top_per_cluster: int = 1, cost_bps: float = 0.0) -> dict:
        cost = cost_bps / 10_000
        holdings: frozenset = frozenset()
        portfolio_returns = []
        score_lagged = score.shift(1)

        for date in weekly_ret.index:
            if date not in score_lagged.index:
                continue

            # Rebalance: pick top-N from each cluster
            new_holdings = set()
            row = score_lagged.loc[date]
            for cluster, members in CLUSTERS.items():
                cluster_active = [m for m in members if m in active_cols and not pd.isna(row.get(m, float("nan")))]
                if not cluster_active:
                    continue
                cluster_scores = row[cluster_active].sort_values(ascending=False)
                top_coins = list(cluster_scores.head(top_per_cluster).index)
                new_holdings.update(top_coins)

            new_holdings_frozen = frozenset(new_holdings)
            entries = new_holdings_frozen - holdings
            exits   = holdings - new_holdings_frozen
            traded  = len(entries) + len(exits)
            tc = cost * traded / max(len(new_holdings_frozen), 1) if new_holdings_frozen else 0.0
            holdings = new_holdings_frozen

            if not holdings:
                portfolio_returns.append((date, 0.0))
                continue

            ret = weekly_ret.loc[date, list(holdings)].mean()
            portfolio_returns.append((date, ret - tc))

        port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + port).cumprod()
        max_dd  = (cum / cum.cummax() - 1).min()
        return {"returns": port, "cagr": ann_ret, "vol": ann_vol, "sharpe": sharpe, "max_dd": max_dd}

    def fmt(res: dict, label: str) -> None:
        print(f"  {label:50s}  CAGR={res['cagr']:+.1%}  Vol={res['vol']:.1%}  Sharpe={res['sharpe']:.2f}  MaxDD={res['max_dd']:.1%}")

    # Benchmarks
    btc_ret = weekly_ret["BTC"].dropna()
    ew_ret  = weekly_ret.mean(axis=1).dropna()
    def bench_stats(r: pd.Series, label: str) -> None:
        ann_ret = (1 + r).prod() ** (52 / len(r)) - 1
        ann_vol = r.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + r).cumprod()
        dd      = (cum / cum.cummax() - 1).min()
        print(f"  {label:50s}  CAGR={ann_ret:+.1%}  Vol={ann_vol:.1%}  Sharpe={sharpe:.2f}  MaxDD={dd:.1%}")

    print(f"\n--- Benchmarks ---")
    bench_stats(btc_ret, "BTC buy-and-hold")
    bench_stats(ew_ret,  f"Equal-weight ({len(active_cols)} coins)")

    # Also compare global top-N attention strategy
    global_score = score.reindex(columns=active_cols)
    global_result = run_backtest(global_score, prices_active, top_n=5, rebalance_freq=1, cost_bps=0)

    print(f"\n--- Cluster vs global attention strategy ---")
    fmt(global_result, "Global top-5 attention (no clusters)")

    for top_n in (1, 2):
        result = run_cluster_backtest(top_per_cluster=top_n, cost_bps=0)
        n_clusters = len([c for c in CLUSTERS if any(m in active_cols for m in CLUSTERS[c])])
        n_held = top_n * n_clusters
        fmt(result, f"Cluster top-{top_n} per cluster (~{n_held} coins, 0-cost)")

    for top_n in (1,):
        result = run_cluster_backtest(top_per_cluster=top_n, cost_bps=10)
        fmt(result, f"Cluster top-{top_n} per cluster (~{top_n * len(CLUSTERS)} coins, 10bps)")

    # Per-cluster IC: does attention momentum predict returns within each cluster?
    print(f"\n--- Per-cluster attention momentum IC (Spearman) ---")
    next_ret = weekly_ret.shift(-1)
    for cluster, members in CLUSTERS.items():
        cluster_active = [m for m in members if m in active_cols]
        if not cluster_active:
            continue
        ics = []
        for coin in cluster_active:
            combined = pd.concat([momentum[coin], next_ret[coin]], axis=1).dropna()
            if len(combined) < 20:
                continue
            ic = combined.iloc[:, 0].corr(combined.iloc[:, 1], method="spearman")
            ics.append(ic)
        if ics:
            print(f"    {cluster:<15}: mean IC = {np.mean(ics):+.4f}  ({len(ics)} coins,  "
                  f"coins: {', '.join(cluster_active[:4])}{'...' if len(cluster_active) > 4 else ''})")


# ---------------------------------------------------------------------------
# Section: equal-weight tilt overlay
# ---------------------------------------------------------------------------

def section_ew_tilt(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("EW TILT OVERLAY — Equal-weight base + attention momentum tilt")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    momentum, zscore = build_features(trends)

    active_cols = [c for c in trends.columns if c in prices.columns]
    prices_active = prices[active_cols]
    weekly_ret = prices_active.pct_change().clip(-0.95, 10)

    n = len(active_cols)
    ew_weight = 1.0 / n

    def run_tilt_backtest(
        tilt_strength: float = 0.5,     # how aggressively to tilt (0 = pure EW)
        z_penalty: float = 1.0,         # reduce weight for high-Z coins
        z_threshold: float = ZSCORE_THRESHOLD,
        cost_bps: float = 0.0,
    ) -> dict:
        """
        Each week: start from equal-weight, adjust by attention momentum signal.
        w_i = EW + tilt_strength * (mom_z_i - mean) - z_penalty * max(0, Z_i - z_thresh)
        Weights are then normalised to sum to 1 and clipped to >= 0 (long-only).
        """
        cost = cost_bps / 10_000

        # Cross-sectional z-score of momentum for tilt
        mom_active = momentum.reindex(columns=active_cols)
        mom_cs_mean = mom_active.mean(axis=1)
        mom_cs_std  = mom_active.std(axis=1).replace(0, np.nan)
        mom_cs_z    = mom_active.sub(mom_cs_mean, axis=0).div(mom_cs_std, axis=0)

        z_active = zscore.reindex(columns=active_cols)
        penalty  = (z_active - z_threshold).clip(lower=0)

        portfolio_returns = []
        prev_weights = pd.Series(ew_weight, index=active_cols)

        for date in weekly_ret.index:
            if date not in mom_cs_z.index:
                continue

            # Compute tilt weights using lagged signal
            lag = mom_cs_z.index[mom_cs_z.index < date]
            if lag.empty:
                portfolio_returns.append((date, 0.0))
                continue
            prev_date = lag[-1]

            tilt = mom_cs_z.loc[prev_date].fillna(0)
            pen  = penalty.loc[prev_date].fillna(0)

            raw_weights = ew_weight + tilt_strength * tilt / n - z_penalty * pen / n
            # Long-only: clip to 0
            raw_weights = raw_weights.clip(lower=0)
            total = raw_weights.sum()
            if total == 0:
                weights = pd.Series(ew_weight, index=active_cols)
            else:
                weights = raw_weights / total

            # Transaction cost: L1 change in weights
            weight_change = (weights - prev_weights).abs().sum()
            tc = cost * weight_change

            ret = (weekly_ret.loc[date] * weights).sum()
            portfolio_returns.append((date, ret - tc))
            prev_weights = weights

        port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + port).cumprod()
        max_dd  = (cum / cum.cummax() - 1).min()

        # Downside capture vs EW
        ew_port = weekly_ret.mean(axis=1).dropna()
        common_idx = port.index.intersection(ew_port.index)
        down_weeks = ew_port.loc[common_idx][ew_port.loc[common_idx] < 0]
        if len(down_weeks) > 0:
            strat_down = port.loc[down_weeks.index].mean()
            ew_down    = down_weeks.mean()
            down_capture = strat_down / ew_down if ew_down != 0 else float("nan")
        else:
            down_capture = float("nan")

        return {
            "returns": port, "cagr": ann_ret, "vol": ann_vol,
            "sharpe": sharpe, "max_dd": max_dd, "down_capture": down_capture,
        }

    def fmt_tilt(res: dict, label: str) -> None:
        dc = f"{res['down_capture']:+.2f}" if not pd.isna(res["down_capture"]) else "n/a"
        print(f"  {label:55s}  CAGR={res['cagr']:+.1%}  Sharpe={res['sharpe']:.2f}  MaxDD={res['max_dd']:.1%}  DownCapture={dc}")

    # Benchmarks
    ew_ret  = weekly_ret.mean(axis=1).dropna()
    btc_ret = weekly_ret["BTC"].dropna()
    def bench_stats(r: pd.Series, label: str) -> dict:
        ann_ret = (1 + r).prod() ** (52 / len(r)) - 1
        ann_vol = r.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + r).cumprod()
        dd      = (cum / cum.cummax() - 1).min()
        print(f"  {label:55s}  CAGR={ann_ret:+.1%}  Sharpe={sharpe:.2f}  MaxDD={dd:.1%}  DownCapture=1.00 (reference)")
        return {"cagr": ann_ret, "vol": ann_vol, "sharpe": sharpe, "max_dd": dd}

    print(f"\n  Universe: {len(active_cols)} active coins  (EW weight per coin: {ew_weight:.3f})")
    print(f"\n--- Benchmarks ---")
    bench_stats(btc_ret, "BTC buy-and-hold")
    bench_stats(ew_ret,  f"Equal-weight ({len(active_cols)} coins) — baseline")

    print(f"\n--- Tilt overlay (0 cost) ---")
    print(f"  Tilt strength controls how aggressively weights deviate from EW.")
    print(f"  Z penalty reduces weight for coins with abnormally high attention.\n")

    for tilt in (0.0, 0.1, 0.25, 0.5, 1.0):
        for zpen in (0.0, 0.5, 1.0):
            if tilt == 0.0 and zpen == 0.0:
                continue  # skip pure EW (already shown as benchmark)
            res = run_tilt_backtest(tilt_strength=tilt, z_penalty=zpen, cost_bps=0)
            label = f"tilt={tilt:.2f}  z_pen={zpen:.1f}"
            fmt_tilt(res, label)

    # Best config with 10bps cost
    print(f"\n--- Best tilt config at 10bps cost ---")
    best_sharpe = -999.0
    best_params = None
    for tilt in (0.0, 0.1, 0.25, 0.5, 1.0):
        for zpen in (0.0, 0.5, 1.0):
            res = run_tilt_backtest(tilt_strength=tilt, z_penalty=zpen, cost_bps=0)
            if res["sharpe"] > best_sharpe:
                best_sharpe = res["sharpe"]
                best_params = (tilt, zpen)

    if best_params:
        tilt_star, zpen_star = best_params
        print(f"  Best 0-cost config: tilt={tilt_star:.2f}  z_pen={zpen_star:.1f}")
        for cost in (0, 5, 10, 20):
            res = run_tilt_backtest(tilt_strength=tilt_star, z_penalty=zpen_star, cost_bps=cost)
            fmt_tilt(res, f"  cost={cost}bps  tilt={tilt_star:.2f}  z_pen={zpen_star:.1f}")

    # Crash-period analysis: how does tilt perform during the two major crypto bear markets?
    print(f"\n--- Bear market performance (EW tilt vs pure EW) ---")
    BEAR_MARKETS = [
        ("COVID crash",     "2020-01-01", "2020-04-30"),
        ("2021-22 bear",    "2021-11-01", "2022-12-31"),
        ("LUNA collapse",   "2022-04-01", "2022-06-30"),
        ("FTX collapse",    "2022-10-01", "2022-12-31"),
    ]

    res_best = run_tilt_backtest(tilt_strength=best_params[0], z_penalty=best_params[1], cost_bps=0)
    port_best = res_best["returns"]

    for label, start, end in BEAR_MARKETS:
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        idx  = port_best.index[(port_best.index >= s) & (port_best.index <= e)]
        if len(idx) < 4:
            print(f"  {label:22s}: insufficient data")
            continue
        strat_ret = (1 + port_best.loc[idx]).prod() - 1
        ew_period  = ew_ret.reindex(idx).dropna()
        ew_ret_p   = (1 + ew_period).prod() - 1
        btc_period = btc_ret.reindex(idx).dropna()
        btc_ret_p  = (1 + btc_period).prod() - 1 if len(btc_period) > 0 else float("nan")
        print(f"  {label:22s} ({start} to {end}):  "
              f"Tilt={strat_ret:+.1%}  EW={ew_ret_p:+.1%}  BTC={btc_ret_p:+.1%}")


# ---------------------------------------------------------------------------
# Section: auto-clustering from attention correlation
# ---------------------------------------------------------------------------

def section_auto_cluster(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("AUTO-CLUSTER — Data-driven clusters from attention correlation")

    try:
        from scipy.cluster.hierarchy import linkage, fcluster, dendrogram
        from scipy.spatial.distance import squareform
    except ImportError:
        print("  scipy not installed — run: pip install scipy")
        return

    if trends.empty:
        print("  No attention data — skipping.")
        return

    active_cols = [c for c in trends.columns if c in prices.columns]
    weekly_ret  = prices[active_cols].pct_change().clip(-0.95, 10)

    # Spearman correlation on weekly attention levels
    corr = trends[active_cols].corr(method="spearman")
    dist = (1 - corr) / 2  # convert to [0, 1] distance
    np.fill_diagonal(dist.values, 0)
    dist_condensed = squareform(dist.values, checks=False)

    Z = linkage(dist_condensed, method="ward")

    print(f"\n  Coins: {len(active_cols)}")
    print(f"  Spearman correlation computed; Ward linkage applied.\n")

    # Try cutting at k=3, 4, 5, 6 clusters
    for k in (3, 4, 5, 6):
        labels = fcluster(Z, k, criterion="maxclust")
        cluster_map: dict[int, list[str]] = {}
        for coin, label in zip(active_cols, labels):
            cluster_map.setdefault(label, []).append(coin)

        print(f"  --- k={k} clusters ---")
        for cid in sorted(cluster_map):
            members = cluster_map[cid]
            print(f"    Cluster {cid}: {', '.join(members)}")

        # Compare to hand-picked clusters
        hand_picked_flat = {coin: clust for clust, coins in CLUSTERS.items() for coin in coins if coin in active_cols}
        agreement = sum(
            1 for coin in active_cols if coin in hand_picked_flat
            and sum(1 for c2 in active_cols
                    if hand_picked_flat.get(c2) == hand_picked_flat.get(coin)
                    and labels[active_cols.index(c2)] == labels[active_cols.index(coin)]) > 1
        )
        print(f"    Agreement with hand-picked clusters: {agreement}/{len(active_cols)} coins co-clustered consistently")
        print()

    # Run backtest with best data-driven clusters (k=5 to match hand-picked count)
    print(f"  --- Backtest: data-driven k=5 clusters (top-2 per cluster, 0-cost) ---")
    k_best = 5
    labels = fcluster(Z, k_best, criterion="maxclust")
    auto_clusters: dict[str, list[str]] = {
        f"auto_{i}": [] for i in range(1, k_best + 1)
    }
    for coin, label in zip(active_cols, labels):
        auto_clusters[f"auto_{label}"].append(coin)

    momentum, zscore = build_features(trends[active_cols])
    score = build_combined_score(attention_momentum=momentum, zscore=zscore, alpha=1.0)
    score_lagged = score.shift(1)

    def _run_cluster_backtest_generic(cluster_def: dict, top_n: int = 2, cost_bps: float = 0.0) -> dict:
        cost = cost_bps / 10_000
        holdings: frozenset = frozenset()
        portfolio_returns = []
        for date in weekly_ret.index:
            if date not in score_lagged.index:
                continue
            row = score_lagged.loc[date]
            new_holdings = set()
            for members in cluster_def.values():
                avail = [m for m in members if m in active_cols and not pd.isna(row.get(m, float("nan")))]
                if avail:
                    top = list(pd.Series({m: row[m] for m in avail}).nlargest(top_n).index)
                    new_holdings.update(top)
            new_h = frozenset(new_holdings)
            entries = new_h - holdings
            exits   = holdings - new_h
            tc = cost * (len(entries) + len(exits)) / max(len(new_h), 1) if new_h else 0.0
            holdings = new_h
            if not holdings:
                portfolio_returns.append((date, 0.0))
                continue
            ret = weekly_ret.loc[date, list(holdings)].mean()
            portfolio_returns.append((date, ret - tc))
        port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + port).cumprod()
        return {"cagr": ann_ret, "vol": ann_vol, "sharpe": sharpe, "max_dd": (cum / cum.cummax() - 1).min()}

    def _fmt(res: dict, label: str) -> None:
        print(f"  {label:55s}  CAGR={res['cagr']:+.1%}  Sharpe={res['sharpe']:.2f}  MaxDD={res['max_dd']:.1%}")

    ew_ret  = weekly_ret.mean(axis=1).dropna()
    ann_ew  = (1 + ew_ret).prod() ** (52 / len(ew_ret)) - 1
    vol_ew  = ew_ret.std() * np.sqrt(52)
    sh_ew   = ann_ew / vol_ew
    dd_ew   = ((1 + ew_ret).cumprod() / (1 + ew_ret).cumprod().cummax() - 1).min()
    _fmt({"cagr": ann_ew, "vol": vol_ew, "sharpe": sh_ew, "max_dd": dd_ew},
         f"Equal-weight ({len(active_cols)} coins) — baseline")
    _fmt(_run_cluster_backtest_generic(CLUSTERS, top_n=2, cost_bps=0),
         "Hand-picked clusters top-2 per cluster (0-cost)")
    _fmt(_run_cluster_backtest_generic(auto_clusters, top_n=2, cost_bps=0),
         f"Auto-clusters k={k_best} top-2 per cluster (0-cost)")
    for k in (3, 4, 6):
        labels_k = fcluster(Z, k, criterion="maxclust")
        ac = {f"auto_{i}": [] for i in range(1, k + 1)}
        for coin, lbl in zip(active_cols, labels_k):
            ac[f"auto_{lbl}"].append(coin)
        _fmt(_run_cluster_backtest_generic(ac, top_n=2, cost_bps=0),
             f"Auto-clusters k={k} top-2 per cluster (0-cost)")


# ---------------------------------------------------------------------------
# Section: cluster + tilt combined
# ---------------------------------------------------------------------------

def section_cluster_tilt(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("CLUSTER TILT — EW-per-cluster base + within-cluster attention tilt")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    momentum, zscore = build_features(trends)

    active_cols = [c for c in trends.columns if c in prices.columns]
    prices_active = prices[active_cols]
    weekly_ret    = prices_active.pct_change().clip(-0.95, 10)

    # Per-cluster base weight: 1 / n_clusters (regardless of cluster size)
    # Within cluster: tilt by cross-sectional attention momentum z-score
    active_clusters: dict[str, list[str]] = {
        name: [m for m in members if m in active_cols]
        for name, members in CLUSTERS.items()
    }
    active_clusters = {k: v for k, v in active_clusters.items() if v}
    n_clusters = len(active_clusters)
    cluster_base_weight = 1.0 / n_clusters

    def run_cluster_tilt_backtest(
        tilt_strength: float = 0.5,
        cost_bps: float = 0.0,
    ) -> dict:
        cost = cost_bps / 10_000

        # Pre-compute within-cluster momentum z-scores (lagged)
        mom_active = momentum.reindex(columns=active_cols)
        portfolio_returns = []
        prev_weights = pd.Series(0.0, index=active_cols)

        for date in weekly_ret.index:
            lag_idx = mom_active.index[mom_active.index < date]
            if lag_idx.empty:
                portfolio_returns.append((date, 0.0))
                continue
            prev_date = lag_idx[-1]

            weights = pd.Series(0.0, index=active_cols)
            for cluster_name, members in active_clusters.items():
                # Within-cluster cross-sectional z-score of momentum
                cluster_mom = mom_active.loc[prev_date, members].dropna()
                n_m = len(cluster_mom)
                if n_m == 0:
                    continue
                if n_m == 1:
                    # Only one coin in cluster — assign full cluster weight
                    weights[cluster_mom.index[0]] += cluster_base_weight
                    continue
                cs_mean = cluster_mom.mean()
                cs_std  = cluster_mom.std()
                if cs_std == 0 or pd.isna(cs_std):
                    # All coins equal momentum — equal weight within cluster
                    for m in cluster_mom.index:
                        weights[m] += cluster_base_weight / n_m
                else:
                    cs_z = (cluster_mom - cs_mean) / cs_std
                    # Base EW within cluster + tilt
                    raw = (cluster_base_weight / n_m) + tilt_strength * cs_z * (cluster_base_weight / n_m)
                    raw = raw.clip(lower=0)
                    total = raw.sum()
                    if total > 0:
                        normalised = raw / total * cluster_base_weight
                    else:
                        normalised = pd.Series(cluster_base_weight / n_m, index=cluster_mom.index)
                    for m in normalised.index:
                        weights[m] += normalised[m]

            # Renormalise full portfolio
            total = weights.sum()
            if total > 0:
                weights = weights / total
            else:
                weights = pd.Series(1.0 / len(active_cols), index=active_cols)

            tc = cost * (weights - prev_weights).abs().sum()
            ret = (weekly_ret.loc[date] * weights).sum()
            portfolio_returns.append((date, ret - tc))
            prev_weights = weights

        port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + port).cumprod()
        max_dd  = (cum / cum.cummax() - 1).min()
        ew_port = weekly_ret.mean(axis=1).dropna()
        down_weeks = ew_port[ew_port < 0]
        strat_down = port.reindex(down_weeks.index).dropna().mean()
        ew_down    = down_weeks.mean()
        down_cap   = strat_down / ew_down if ew_down != 0 else float("nan")
        return {"cagr": ann_ret, "vol": ann_vol, "sharpe": sharpe, "max_dd": max_dd, "down_cap": down_cap}

    def fmt(res: dict, label: str) -> None:
        dc = f"{res['down_cap']:+.2f}" if not pd.isna(res["down_cap"]) else "n/a"
        print(f"  {label:55s}  CAGR={res['cagr']:+.1%}  Sharpe={res['sharpe']:.2f}  MaxDD={res['max_dd']:.1%}  DownCap={dc}")

    # Benchmarks
    ew_ret = weekly_ret.mean(axis=1).dropna()
    ann_ew = (1 + ew_ret).prod() ** (52 / len(ew_ret)) - 1
    vol_ew = ew_ret.std() * np.sqrt(52)
    dd_ew  = ((1 + ew_ret).cumprod() / (1 + ew_ret).cumprod().cummax() - 1).min()
    print(f"\n  Clusters: {n_clusters}  |  Base weight per cluster: {cluster_base_weight:.3f}")
    print(f"\n--- Benchmarks ---")
    print(f"  {'Equal-weight (37 coins)':55s}  CAGR={ann_ew:+.1%}  Sharpe={ann_ew/vol_ew:.2f}  MaxDD={dd_ew:.1%}  DownCap=1.00")

    # Hand-picked cluster top-2 (discrete rotation) — inline for reference
    score_disc = build_combined_score(momentum, zscore, alpha=1.0)
    score_lagged_disc = score_disc.shift(1)
    holdings_disc: frozenset = frozenset()
    disc_returns = []
    for date in weekly_ret.index:
        if date not in score_lagged_disc.index:
            continue
        row = score_lagged_disc.loc[date]
        new_h = set()
        for members in active_clusters.values():
            avail = [m for m in members if not pd.isna(row.get(m, float("nan")))]
            if avail:
                top = list(pd.Series({m: row[m] for m in avail}).nlargest(2).index)
                new_h.update(top)
        new_h_f = frozenset(new_h)
        holdings_disc = new_h_f
        if not holdings_disc:
            disc_returns.append((date, 0.0))
        else:
            disc_returns.append((date, weekly_ret.loc[date, list(holdings_disc)].mean()))
    disc_port = pd.Series({d: r for d, r in disc_returns}).dropna()
    ann_d = (1 + disc_port).prod() ** (52 / len(disc_port)) - 1
    vol_d = disc_port.std() * np.sqrt(52)
    dd_d  = ((1 + disc_port).cumprod() / (1 + disc_port).cumprod().cummax() - 1).min()
    print(f"  {'Discrete cluster top-2 (hand-picked, 0-cost)':55s}  CAGR={ann_d:+.1%}  Sharpe={ann_d/vol_d:.2f}  MaxDD={dd_d:.1%}")

    print(f"\n--- Cluster tilt (0 cost) ---")
    for tilt in (0.0, 0.25, 0.5, 1.0, 2.0):
        res = run_cluster_tilt_backtest(tilt_strength=tilt, cost_bps=0)
        fmt(res, f"cluster_tilt={tilt:.2f}  z_pen=0.0")

    # Best tilt at 10bps
    best_sh, best_tilt = -999.0, 0.5
    for tilt in (0.0, 0.25, 0.5, 1.0, 2.0):
        res = run_cluster_tilt_backtest(tilt_strength=tilt, cost_bps=0)
        if res["sharpe"] > best_sh:
            best_sh, best_tilt = res["sharpe"], tilt

    print(f"\n--- Best tilt={best_tilt:.2f} at various costs ---")
    for cost in (0, 5, 10, 20):
        res = run_cluster_tilt_backtest(tilt_strength=best_tilt, cost_bps=cost)
        fmt(res, f"cost={cost}bps  cluster_tilt={best_tilt:.2f}")


# ---------------------------------------------------------------------------
# Section: Z-penalty sweep (none / relaxed / current)
# ---------------------------------------------------------------------------

def section_z_sweep(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("Z-PENALTY SWEEP — None vs relaxed (Z>4) vs current (Z>2.5)")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    momentum, zscore = build_features(trends)
    active_cols = [c for c in trends.columns if c in prices.columns]
    prices_active = prices[active_cols]
    weekly_ret    = prices_active.pct_change().clip(-0.95, 10)

    # Use cluster top-2 strategy (best performer from section_clusters)
    active_clusters: dict[str, list[str]] = {
        name: [m for m in members if m in active_cols]
        for name, members in CLUSTERS.items()
    }
    active_clusters = {k: v for k, v in active_clusters.items() if v}

    def run_z_test(beta: float, z_threshold: float, cost_bps: float = 0.0) -> dict:
        score = build_combined_score(
            attention_momentum=momentum, zscore=zscore,
            alpha=1.0, beta=beta, z_threshold=z_threshold,
        )
        score_lagged = score.shift(1)
        cost = cost_bps / 10_000
        holdings: frozenset = frozenset()
        portfolio_returns = []
        for date in weekly_ret.index:
            if date not in score_lagged.index:
                continue
            row = score_lagged.loc[date]
            new_h = set()
            for members in active_clusters.values():
                avail = [m for m in members if not pd.isna(row.get(m, float("nan")))]
                if avail:
                    top = list(pd.Series({m: row[m] for m in avail}).nlargest(2).index)
                    new_h.update(top)
            new_h_f = frozenset(new_h)
            entries = new_h_f - holdings
            exits   = holdings - new_h_f
            tc = cost * (len(entries) + len(exits)) / max(len(new_h_f), 1) if new_h_f else 0.0
            holdings = new_h_f
            ret = weekly_ret.loc[date, list(holdings)].mean() if holdings else 0.0
            portfolio_returns.append((date, ret - tc))
        port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + port).cumprod()
        return {"cagr": ann_ret, "vol": ann_vol, "sharpe": sharpe, "max_dd": (cum / cum.cummax() - 1).min()}

    def fmt(res: dict, label: str) -> None:
        print(f"  {label:45s}  CAGR={res['cagr']:+.1%}  Sharpe={res['sharpe']:.2f}  MaxDD={res['max_dd']:.1%}")

    ew_ret = weekly_ret.mean(axis=1).dropna()
    ann_ew = (1 + ew_ret).prod() ** (52 / len(ew_ret)) - 1
    vol_ew = ew_ret.std() * np.sqrt(52)
    dd_ew  = ((1 + ew_ret).cumprod() / (1 + ew_ret).cumprod().cummax() - 1).min()
    print(f"\n  Base strategy: cluster top-2 per cluster (hand-picked, 0-cost)")
    print(f"\n--- Benchmarks ---")
    print(f"  {'Equal-weight (37 coins)':45s}  CAGR={ann_ew:+.1%}  Sharpe={ann_ew/vol_ew:.2f}  MaxDD={dd_ew:.1%}")

    print(f"\n--- Z-penalty sweep (0 cost) ---")
    configs = [
        ("No penalty",          0.0,  99.0),   # effectively disabled
        ("Extreme only (Z>4)",  1.0,   4.0),
        ("Relaxed (Z>3)",       1.0,   3.0),
        ("Current (Z>2.5)",     1.0,   2.5),
        ("Aggressive (Z>2.0)",  1.0,   2.0),
        ("Strong beta=2 (Z>2.5)", 2.0, 2.5),
        ("Extreme+strong (Z>4,b=2)", 2.0, 4.0),
    ]
    for label, beta, z_thr in configs:
        res = run_z_test(beta=beta, z_threshold=z_thr, cost_bps=0)
        fmt(res, label)

    # Show how many times Z > threshold is triggered per coin
    print(f"\n--- Z > threshold frequency per coin ---")
    for z_thr in (2.0, 2.5, 3.0, 4.0):
        triggered = (zscore[active_cols] > z_thr).sum().sum()
        total_obs = zscore[active_cols].notna().sum().sum()
        pct = 100 * triggered / total_obs if total_obs > 0 else 0
        print(f"  Z > {z_thr:.1f}: {triggered} coin-weeks ({pct:.1f}% of valid observations)")


# ---------------------------------------------------------------------------
# Section: daily signal (7d / 14d momentum from daily Wikipedia data)
# ---------------------------------------------------------------------------

def section_daily_signal(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("DAILY SIGNAL — 7d/14d momentum using daily Wikipedia granularity")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    # Reload raw daily data (not resampled to weekly)
    print("\n  Loading daily Wikipedia data from cache ...")
    daily_articles = {s: WIKI_ARTICLES[s] for s in WIKI_ARTICLES}
    daily_raw = WIKI_FETCHER.fetch_all(daily_articles, START, END, force_refresh=False)

    if daily_raw.empty:
        print("  Could not load daily data — skipping.")
        return

    daily_raw = daily_raw.ffill(limit=3)  # fill short gaps (weekends etc.)
    print(f"  Daily data shape: {daily_raw.shape}  ({daily_raw.index[0].date()} to {daily_raw.index[-1].date()})")

    # Compute momentum at daily frequency, then resample signal to weekly Friday
    active_cols = [c for c in daily_raw.columns if c in prices.columns]
    prices_active = prices[active_cols]
    weekly_ret    = prices_active.pct_change().clip(-0.95, 10)

    # Active clusters for cluster-based comparison
    active_clusters: dict[str, list[str]] = {
        name: [m for m in members if m in active_cols]
        for name, members in CLUSTERS.items()
    }
    active_clusters = {k: v for k, v in active_clusters.items() if v}

    def _daily_to_weekly_signal(window_days: int) -> pd.DataFrame:
        """Compute daily momentum, resample to weekly by taking Friday value."""
        mom_daily = daily_raw[active_cols].pct_change(window_days).clip(-5, 5)
        # Take Friday (W-FRI) value of daily signal = last day of the trading week
        return mom_daily.resample("W-FRI").last()

    def _rolling_zscore_weekly(window_weeks: int = 52) -> pd.DataFrame:
        """52-week rolling Z-score on weekly attention levels (resampled from daily)."""
        weekly_att = daily_raw[active_cols].resample("W-FRI").sum()
        rm = weekly_att.rolling(window_weeks, min_periods=26).mean()
        rs = weekly_att.rolling(window_weeks, min_periods=26).std()
        return (weekly_att - rm) / rs.replace(0, np.nan)

    zscore_weekly = _rolling_zscore_weekly()

    def run_daily_backtest(window_days: int, use_z_penalty: bool = False, cost_bps: float = 0.0) -> dict:
        mom_weekly = _daily_to_weekly_signal(window_days)
        # Align indices
        common = mom_weekly.index.intersection(weekly_ret.index).intersection(zscore_weekly.index)
        mom_w  = mom_weekly.reindex(common)
        zs_w   = zscore_weekly.reindex(common)
        wr     = weekly_ret.reindex(common)

        if use_z_penalty:
            score = build_combined_score(mom_w, zs_w, alpha=1.0, beta=1.0, z_threshold=2.5)
        else:
            score = mom_w.copy()

        score_lagged = score.shift(1)
        cost = cost_bps / 10_000
        holdings: frozenset = frozenset()
        portfolio_returns = []
        for date in wr.index:
            if date not in score_lagged.index:
                continue
            row = score_lagged.loc[date]
            new_h = set()
            for members in active_clusters.values():
                avail = [m for m in members if not pd.isna(row.get(m, float("nan")))]
                if avail:
                    top = list(pd.Series({m: row[m] for m in avail}).nlargest(2).index)
                    new_h.update(top)
            new_h_f = frozenset(new_h)
            entries = new_h_f - holdings
            exits   = holdings - new_h_f
            tc = cost * (len(entries) + len(exits)) / max(len(new_h_f), 1) if new_h_f else 0.0
            holdings = new_h_f
            ret = wr.loc[date, list(holdings)].mean() if holdings else 0.0
            portfolio_returns.append((date, ret - tc))
        port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
        cum     = (1 + port).cumprod()
        return {"cagr": ann_ret, "vol": ann_vol, "sharpe": sharpe, "max_dd": (cum / cum.cummax() - 1).min()}

    def fmt(res: dict, label: str) -> None:
        print(f"  {label:55s}  CAGR={res['cagr']:+.1%}  Sharpe={res['sharpe']:.2f}  MaxDD={res['max_dd']:.1%}")

    ew_ret = weekly_ret.mean(axis=1).dropna()
    ann_ew = (1 + ew_ret).prod() ** (52 / len(ew_ret)) - 1
    vol_ew = ew_ret.std() * np.sqrt(52)
    dd_ew  = ((1 + ew_ret).cumprod() / (1 + ew_ret).cumprod().cummax() - 1).min()
    print(f"\n--- Benchmarks ---")
    print(f"  {'Equal-weight (37 coins)':55s}  CAGR={ann_ew:+.1%}  Sharpe={ann_ew/vol_ew:.2f}  MaxDD={dd_ew:.1%}")

    # Reference: 4-week (28-day) weekly signal (same as current)
    fmt(run_daily_backtest(28, use_z_penalty=False, cost_bps=0), "4-week (28d) momentum — cluster top-2, no Z-pen")
    fmt(run_daily_backtest(28, use_z_penalty=True,  cost_bps=0), "4-week (28d) momentum — cluster top-2, Z-pen")

    print(f"\n--- Daily momentum windows (cluster top-2, 0-cost) ---")
    for days in (7, 10, 14, 21, 28):
        res_no_z = run_daily_backtest(days, use_z_penalty=False, cost_bps=0)
        res_z    = run_daily_backtest(days, use_z_penalty=True,  cost_bps=0)
        fmt(res_no_z, f"{days:2d}d momentum  no Z-pen")
        fmt(res_z,    f"{days:2d}d momentum  Z-pen (>2.5, b=1)")

    # IC: daily momentum vs next-week return
    print(f"\n--- IC: daily momentum windows vs next-week return (Spearman) ---")
    for days in (7, 14, 28):
        mom_w = _daily_to_weekly_signal(days)
        # Align to common weekly index before computing IC
        common_ic = mom_w.index.intersection(weekly_ret.index)
        mom_aligned = mom_w.reindex(common_ic)
        nxt = weekly_ret.reindex(common_ic).shift(-1)
        ics = []
        for coin in active_cols:
            if coin not in mom_aligned.columns:
                continue
            combined = pd.concat([mom_aligned[coin], nxt[coin]], axis=1).dropna()
            if len(combined) < 20:
                continue
            ics.append(combined.iloc[:, 0].corr(combined.iloc[:, 1], method="spearman"))
        if ics:
            valid_ics = [x for x in ics if not np.isnan(x)]
            print(f"  {days:2d}d momentum: mean IC = {np.mean(valid_ics):+.4f}  n_coins={len(valid_ics)}/{len(ics)}")
        else:
            print(f"  {days:2d}d momentum: no valid pairs found")


# ---------------------------------------------------------------------------
# Section: robustness — permutation + out-of-sample
# ---------------------------------------------------------------------------

def section_robustness(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("ROBUSTNESS — Permutation test + out-of-sample 2024-2025")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    import random

    momentum, zscore = build_features(trends)
    active_cols = [c for c in trends.columns if c in prices.columns]
    prices_active = prices[active_cols]
    weekly_ret    = prices_active.pct_change().clip(-0.95, 10)

    active_clusters: dict[str, list[str]] = {
        name: [m for m in members if m in active_cols]
        for name, members in CLUSTERS.items()
    }
    active_clusters = {k: v for k, v in active_clusters.items() if v}
    n_clusters = len(active_clusters)

    score = build_combined_score(attention_momentum=momentum, zscore=zscore, alpha=1.0)

    def _cluster_backtest(cluster_def: dict, idx: pd.DatetimeIndex | None = None) -> dict:
        sl = score.shift(1)
        wr = weekly_ret if idx is None else weekly_ret.loc[idx]
        holdings: frozenset = frozenset()
        portfolio_returns = []
        for date in wr.index:
            if date not in sl.index:
                continue
            row = sl.loc[date]
            new_h = set()
            for members in cluster_def.values():
                avail = [m for m in members if not pd.isna(row.get(m, float("nan")))]
                if avail:
                    top = list(pd.Series({m: row[m] for m in avail}).nlargest(2).index)
                    new_h.update(top)
            holdings = frozenset(new_h)
            ret = wr.loc[date, list(holdings)].mean() if holdings else 0.0
            portfolio_returns.append((date, ret))
        port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
        if len(port) < 10:
            return {"sharpe": float("nan"), "cagr": float("nan"), "max_dd": float("nan")}
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else float("nan")
        cum     = (1 + port).cumprod()
        return {"cagr": ann_ret, "sharpe": sharpe, "max_dd": (cum / cum.cummax() - 1).min()}

    # --- Out-of-sample split ---
    OOS_START = pd.Timestamp("2024-01-01")
    IS_END    = pd.Timestamp("2023-12-31")

    is_idx  = weekly_ret.index[weekly_ret.index <= IS_END]
    oos_idx = weekly_ret.index[weekly_ret.index >= OOS_START]

    ew_ret = weekly_ret.mean(axis=1).dropna()

    def _ew_stats(idx: pd.DatetimeIndex, label: str) -> None:
        r = ew_ret.reindex(idx).dropna()
        ann_ret = (1 + r).prod() ** (52 / len(r)) - 1
        ann_vol = r.std() * np.sqrt(52)
        sharpe  = ann_ret / ann_vol if ann_vol > 0 else float("nan")
        cum     = (1 + r).cumprod()
        dd      = (cum / cum.cummax() - 1).min()
        print(f"  {label:50s}  CAGR={ann_ret:+.1%}  Sharpe={sharpe:.2f}  MaxDD={dd:.1%}")

    def _fmt(res: dict, label: str) -> None:
        if pd.isna(res["sharpe"]):
            print(f"  {label:50s}  (insufficient data)")
        else:
            print(f"  {label:50s}  CAGR={res['cagr']:+.1%}  Sharpe={res['sharpe']:.2f}  MaxDD={res['max_dd']:.1%}")

    print(f"\n--- In-sample (Jan 2020 – Dec 2023, {len(is_idx)} weeks) ---")
    _ew_stats(is_idx, "Equal-weight")
    _fmt(_cluster_backtest(active_clusters, is_idx), "Hand-picked cluster top-2")

    print(f"\n--- Out-of-sample (Jan 2024 – Jan 2026, {len(oos_idx)} weeks) ---")
    _ew_stats(oos_idx, "Equal-weight")
    _fmt(_cluster_backtest(active_clusters, oos_idx), "Hand-picked cluster top-2")

    # --- Permutation test ---
    # Randomly reassign coins to clusters (preserving cluster sizes), run 200 simulations
    print(f"\n--- Permutation test (n=200 random cluster assignments, full period) ---")
    print(f"  Question: is the cluster top-2 Sharpe better than random grouping?")

    true_result = _cluster_backtest(active_clusters)
    true_sharpe = true_result["sharpe"]
    print(f"  Hand-picked cluster Sharpe: {true_sharpe:.3f}")

    cluster_sizes = [len(v) for v in active_clusters.values()]
    perm_sharpes = []
    rng = random.Random(42)
    for _ in range(200):
        # Shuffle coins randomly into same-size clusters
        shuffled = active_cols.copy()
        rng.shuffle(shuffled)
        perm_clusters: dict[str, list[str]] = {}
        idx_start = 0
        for i, size in enumerate(cluster_sizes):
            perm_clusters[f"perm_{i}"] = shuffled[idx_start: idx_start + size]
            idx_start += size
        # Any remaining coins (if cluster sizes don't sum to len(active_cols)) go into last cluster
        if idx_start < len(shuffled):
            perm_clusters[f"perm_{len(cluster_sizes) - 1}"].extend(shuffled[idx_start:])
        res = _cluster_backtest(perm_clusters)
        if not pd.isna(res["sharpe"]):
            perm_sharpes.append(res["sharpe"])

    perm_arr = np.array(perm_sharpes)
    pct_below = (perm_arr < true_sharpe).mean() * 100
    print(f"  Random cluster mean Sharpe: {perm_arr.mean():.3f}  std: {perm_arr.std():.3f}")
    print(f"  Random cluster 95th pct:    {np.percentile(perm_arr, 95):.3f}")
    print(f"  Hand-picked beats {pct_below:.1f}% of random assignments")
    print(f"  p-value (one-sided): {(perm_arr >= true_sharpe).mean():.3f}")

    if pct_below >= 95:
        print(f"  => Cluster structure is statistically significant (p < 0.05).")
    elif pct_below >= 80:
        print(f"  => Cluster structure shows moderate edge over random grouping.")
    else:
        print(f"  => Cluster structure not significantly better than random grouping.")
        print(f"     The Sharpe improvement may partly reflect lucky coin selection.")

    # Distribution summary
    percentiles = [10, 25, 50, 75, 90, 95]
    pctile_vals = np.percentile(perm_arr, percentiles)
    print(f"\n  Random assignment Sharpe distribution:")
    for p, v in zip(percentiles, pctile_vals):
        bar = "#" * int((v - perm_arr.min()) / (perm_arr.max() - perm_arr.min()) * 30)
        marker = " <-- hand-picked" if abs(v - true_sharpe) < 0.02 else ""
        print(f"    p{p:2d}: {v:.3f}  {bar}{marker}")
    print(f"  Hand-picked: {true_sharpe:.3f}")


# ---------------------------------------------------------------------------
# Shared helper: generalized cluster-tilt backtest engine
# ---------------------------------------------------------------------------

def _run_cluster_tilt(
    cluster_def: dict,          # {name: [coin, ...]}
    momentum_weekly: pd.DataFrame,   # (date x coin) weekly momentum signal
    weekly_ret: pd.DataFrame,        # (date x coin) weekly price returns
    active_cols: list[str],
    tilt_strength: float = 1.0,
    z_penalty: float = 0.0,
    zscore_weekly: pd.DataFrame | None = None,
    z_threshold: float = 4.0,
    cost_bps: float = 0.0,
    rebalance_freq: int = 1,         # 1=weekly, 2=biweekly, 4=monthly
    regime_z: pd.Series | None = None,  # BTC Z-score; when > regime_threshold, scale tilt
    regime_threshold: float = 2.5,
) -> dict:
    """
    Generalized cluster-tilt backtest.

    Base weight: 1 / n_clusters per cluster, distributed equally within cluster.
    Tilt: within each cluster, overweight high-attention-momentum coins by
          tilt_strength × within-cluster CS-Z of momentum.
    Z-penalty: optionally reduce weight for coins with extreme Z-score.
    Regime filter: scale tilt toward 0 when BTC attention is anomalously high.
    """
    active_clusters = {k: [m for m in v if m in active_cols] for k, v in cluster_def.items()}
    active_clusters = {k: v for k, v in active_clusters.items() if v}
    n_clusters = len(active_clusters)
    if n_clusters == 0:
        return {"cagr": float("nan"), "vol": float("nan"), "sharpe": float("nan"),
                "max_dd": float("nan"), "down_cap": float("nan")}

    cluster_base = 1.0 / n_clusters
    cost = cost_bps / 10_000

    portfolio_returns = []
    prev_weights = pd.Series(0.0, index=active_cols)
    weeks_since_rebalance = 0

    for date in weekly_ret.index:
        lag_idx = momentum_weekly.index[momentum_weekly.index < date]
        if lag_idx.empty:
            portfolio_returns.append((date, 0.0))
            continue
        prev_date = lag_idx[-1]

        if weeks_since_rebalance >= rebalance_freq:
            # Regime scale factor
            if regime_z is not None and prev_date in regime_z.index:
                rz = regime_z.loc[prev_date]
                regime_scale = max(0.0, 1.0 - max(0.0, rz - regime_threshold))
            else:
                regime_scale = 1.0

            weights = pd.Series(0.0, index=active_cols)
            for members in active_clusters.values():
                cluster_mom = momentum_weekly.loc[prev_date, members].dropna()
                n_m = len(cluster_mom)
                if n_m == 0:
                    continue
                if n_m == 1:
                    weights[cluster_mom.index[0]] += cluster_base
                    continue

                cs_mean = cluster_mom.mean()
                cs_std  = cluster_mom.std()
                if cs_std == 0 or pd.isna(cs_std):
                    for m in cluster_mom.index:
                        weights[m] += cluster_base / n_m
                else:
                    cs_z = (cluster_mom - cs_mean) / cs_std
                    effective_tilt = tilt_strength * regime_scale
                    raw = (cluster_base / n_m) * (1 + effective_tilt * cs_z)
                    # Z-penalty
                    if z_penalty > 0 and zscore_weekly is not None and prev_date in zscore_weekly.index:
                        for m in cluster_mom.index:
                            if m in zscore_weekly.columns:
                                z = zscore_weekly.loc[prev_date, m]
                                if not pd.isna(z) and z > z_threshold:
                                    raw[m] *= max(0.0, 1.0 - z_penalty * (z - z_threshold))
                    raw = raw.clip(lower=0)
                    total = raw.sum()
                    if total > 0:
                        for m in raw.index:
                            weights[m] += raw[m] / total * cluster_base
                    else:
                        for m in cluster_mom.index:
                            weights[m] += cluster_base / n_m

            total = weights.sum()
            if total > 0:
                weights = weights / total
            else:
                weights = pd.Series(1.0 / len(active_cols), index=active_cols)

            tc = cost * (weights - prev_weights).abs().sum()
            prev_weights = weights
            weeks_since_rebalance = 0
        else:
            tc = 0.0

        weeks_since_rebalance += 1
        ret = (weekly_ret.loc[date, active_cols] * prev_weights).sum()
        portfolio_returns.append((date, ret - tc))

    port = pd.Series({d: r for d, r in portfolio_returns}).dropna()
    if len(port) < 10:
        return {"cagr": float("nan"), "vol": float("nan"), "sharpe": float("nan"),
                "max_dd": float("nan"), "down_cap": float("nan")}
    ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
    ann_vol = port.std() * np.sqrt(52)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else float("nan")
    cum     = (1 + port).cumprod()
    max_dd  = (cum / cum.cummax() - 1).min()
    ew_port = weekly_ret[active_cols].mean(axis=1).dropna()
    down_weeks = ew_port[ew_port < 0]
    strat_down = port.reindex(down_weeks.index).dropna().mean()
    ew_down    = down_weeks.mean()
    down_cap   = strat_down / ew_down if ew_down != 0 else float("nan")
    return {"returns": port, "cagr": ann_ret, "vol": ann_vol,
            "sharpe": sharpe, "max_dd": max_dd, "down_cap": down_cap}


def _fmt_res(res: dict, label: str, width: int = 60) -> None:
    dc = f"{res['down_cap']:+.2f}" if not pd.isna(res.get("down_cap", float("nan"))) else "n/a"
    print(f"  {label:{width}s}  CAGR={res['cagr']:+.1%}  Sharpe={res['sharpe']:.2f}  MaxDD={res['max_dd']:.1%}  DownCap={dc}")


def _load_daily_momentum(prices: pd.DataFrame, window_days: int) -> tuple[pd.DataFrame, list[str]]:
    """Return weekly-resampled daily momentum + active_cols from daily Wikipedia cache."""
    daily_articles = {s: WIKI_ARTICLES[s] for s in WIKI_ARTICLES}
    daily_raw = WIKI_FETCHER.fetch_all(daily_articles, START, END, force_refresh=False)
    if daily_raw.empty:
        return pd.DataFrame(), []
    daily_raw = daily_raw.ffill(limit=3)
    active_cols = [c for c in daily_raw.columns if c in prices.columns]
    mom = daily_raw[active_cols].pct_change(window_days).clip(-5, 5).resample("W-FRI").last()
    return mom, active_cols


# ---------------------------------------------------------------------------
# Section: final_signal — cluster tilt with optimised momentum window
# ---------------------------------------------------------------------------

def section_final_signal(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("FINAL SIGNAL — Cluster tilt with 14d/21d momentum (best config integration)")

    daily_articles = {s: WIKI_ARTICLES[s] for s in WIKI_ARTICLES}
    print("\n  Loading daily Wikipedia data ...")
    daily_raw = WIKI_FETCHER.fetch_all(daily_articles, START, END, force_refresh=False)
    if daily_raw.empty:
        print("  No daily data — skipping.")
        return
    daily_raw = daily_raw.ffill(limit=3)

    active_cols = [c for c in daily_raw.columns if c in prices.columns]
    weekly_ret  = prices[active_cols].pct_change().clip(-0.95, 10)
    ew_ret      = weekly_ret.mean(axis=1).dropna()

    # Compute 52-week Z-score from weekly-resampled attention (for Z-penalty tests)
    weekly_att = daily_raw[active_cols].resample("W-FRI").sum()
    rm = weekly_att.rolling(52, min_periods=26).mean()
    rs = weekly_att.rolling(52, min_periods=26).std()
    zscore_weekly = (weekly_att - rm) / rs.replace(0, np.nan)

    def _mom(days: int) -> pd.DataFrame:
        return daily_raw[active_cols].pct_change(days).clip(-5, 5).resample("W-FRI").last()

    def _bench(label: str) -> None:
        ann_ret = (1 + ew_ret).prod() ** (52 / len(ew_ret)) - 1
        ann_vol = ew_ret.std() * np.sqrt(52)
        dd = ((1 + ew_ret).cumprod() / (1 + ew_ret).cumprod().cummax() - 1).min()
        print(f"  {label:60s}  CAGR={ann_ret:+.1%}  Sharpe={ann_ret/ann_vol:.2f}  MaxDD={dd:.1%}  DownCap=1.00")

    print(f"\n--- Benchmarks ---")
    _bench(f"Equal-weight ({len(active_cols)} coins)")

    # Baseline: 28d momentum (what all prior sections use)
    mom28 = _mom(28)
    common = mom28.index.intersection(weekly_ret.index)
    res_base = _run_cluster_tilt(CLUSTERS, mom28.reindex(common), weekly_ret.reindex(common),
                                  active_cols, tilt_strength=1.0, z_penalty=0.0, cost_bps=0)
    _fmt_res(res_base, "28d momentum  tilt=1.0  z_pen=0  (prior best)")

    print(f"\n--- Momentum window sweep (cluster tilt=1.0, no Z-pen, 0-cost) ---")
    for days in (7, 10, 14, 21, 28, 35):
        mom = _mom(days)
        common = mom.index.intersection(weekly_ret.index)
        res = _run_cluster_tilt(CLUSTERS, mom.reindex(common), weekly_ret.reindex(common),
                                 active_cols, tilt_strength=1.0, z_penalty=0.0, cost_bps=0)
        _fmt_res(res, f"{days:2d}d momentum  tilt=1.0  z_pen=0")

    # Best window + Z-penalty variants
    print(f"\n--- 21d momentum: Z-penalty sweep ---")
    mom21 = _mom(21)
    common21 = mom21.index.intersection(weekly_ret.index).intersection(zscore_weekly.index)
    for z_thr in (99.0, 4.0, 3.0, 2.5):
        label = "no Z-pen" if z_thr > 10 else f"Z>{z_thr:.1f}"
        for z_pen in ((0.0,) if z_thr > 10 else (0.5, 1.0)):
            res = _run_cluster_tilt(CLUSTERS, mom21.reindex(common21), weekly_ret.reindex(common21),
                                     active_cols, tilt_strength=1.0,
                                     z_penalty=z_pen, zscore_weekly=zscore_weekly.reindex(common21),
                                     z_threshold=z_thr, cost_bps=0)
            lbl = f"21d  tilt=1.0  {label}  beta={z_pen:.1f}" if z_thr <= 10 else f"21d  tilt=1.0  {label}"
            _fmt_res(res, lbl)

    # Best config: tilt sweep at 21d
    print(f"\n--- 21d momentum: tilt sweep (no Z-pen, 0-cost) ---")
    for tilt in (0.25, 0.5, 1.0, 1.5, 2.0):
        res = _run_cluster_tilt(CLUSTERS, mom21.reindex(common21), weekly_ret.reindex(common21),
                                 active_cols, tilt_strength=tilt, z_penalty=0.0, cost_bps=0)
        _fmt_res(res, f"21d  tilt={tilt:.2f}  z_pen=0")

    # Best config cost sensitivity
    print(f"\n--- 21d momentum, tilt=1.0: cost sensitivity ---")
    for cost in (0, 5, 10, 20, 30):
        res = _run_cluster_tilt(CLUSTERS, mom21.reindex(common21), weekly_ret.reindex(common21),
                                 active_cols, tilt_strength=1.0, z_penalty=0.0, cost_bps=cost)
        _fmt_res(res, f"21d  tilt=1.0  cost={cost}bps")

    # Best config rebalance frequency
    print(f"\n--- 21d momentum, tilt=1.0, 10bps: rebalance frequency ---")
    for freq in (1, 2, 4):
        label = {1: "weekly", 2: "biweekly", 4: "monthly"}[freq]
        res = _run_cluster_tilt(CLUSTERS, mom21.reindex(common21), weekly_ret.reindex(common21),
                                 active_cols, tilt_strength=1.0, z_penalty=0.0,
                                 cost_bps=10, rebalance_freq=freq)
        _fmt_res(res, f"21d  tilt=1.0  10bps  {label} ({freq}w)")


# ---------------------------------------------------------------------------
# Section: stress_test — structured cluster perturbations
# ---------------------------------------------------------------------------

def section_stress_test(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("STRESS TEST — Structured cluster perturbations")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    momentum, _ = build_features(trends)
    active_cols  = [c for c in trends.columns if c in prices.columns]
    weekly_ret   = prices[active_cols].pct_change().clip(-0.95, 10)
    ew_ret       = weekly_ret.mean(axis=1).dropna()

    def _run(cluster_def: dict, label: str) -> None:
        res = _run_cluster_tilt(cluster_def, momentum, weekly_ret, active_cols,
                                 tilt_strength=1.0, z_penalty=0.0, cost_bps=0)
        _fmt_res(res, label)

    ann_ew  = (1 + ew_ret).prod() ** (52 / len(ew_ret)) - 1
    vol_ew  = ew_ret.std() * np.sqrt(52)
    dd_ew   = ((1 + ew_ret).cumprod() / (1 + ew_ret).cumprod().cummax() - 1).min()
    print(f"\n  Base: hand-picked clusters, tilt=1.0, 28d momentum, 0-cost")
    print(f"\n--- Benchmarks ---")
    print(f"  {'Equal-weight':60s}  CAGR={ann_ew:+.1%}  Sharpe={ann_ew/vol_ew:.2f}  MaxDD={dd_ew:.1%}  DownCap=1.00")
    _run(CLUSTERS, "Baseline (all 5 clusters)")

    print(f"\n--- Leave-one-cluster-out ---")
    for dropped in CLUSTERS:
        reduced = {k: v for k, v in CLUSTERS.items() if k != dropped}
        _run(reduced, f"Drop '{dropped}' (4 clusters)")

    print(f"\n--- Merge similar clusters ---")
    merged_L1 = {
        "L1_all":     CLUSTERS["old_guard"] + CLUSTERS["L1_new"],
        "DeFi":       CLUSTERS["DeFi"],
        "meme":       CLUSTERS["meme"],
        "event_risk": CLUSTERS["event_risk"],
    }
    _run(merged_L1, "Merge old_guard + L1_new (4 clusters)")

    merged_fragile = {
        "old_guard":  CLUSTERS["old_guard"],
        "L1_new":     CLUSTERS["L1_new"],
        "DeFi":       CLUSTERS["DeFi"],
        "meme_event": CLUSTERS["meme"] + CLUSTERS["event_risk"],
    }
    _run(merged_fragile, "Merge meme + event_risk (4 clusters)")

    merged_btc_only = {
        "BTC_only":   ["BTC"],
        "L1_new":     CLUSTERS["L1_new"],
        "DeFi_meme":  CLUSTERS["DeFi"] + CLUSTERS["meme"],
        "legacy":     [c for c in CLUSTERS["old_guard"] if c != "BTC"],
        "event_risk": CLUSTERS["event_risk"],
    }
    _run(merged_btc_only, "BTC as own cluster (5 clusters, BTC isolated)")

    print(f"\n--- Split largest cluster (L1_new) ---")
    l1_new = CLUSTERS["L1_new"]
    split_a = {
        "old_guard":   CLUSTERS["old_guard"],
        "L1_major":    l1_new[:4],   # ETH, SOL, AVAX, ATOM
        "L1_minor":    l1_new[4:],   # DOT, NEAR, ALGO, TRX
        "DeFi":        CLUSTERS["DeFi"],
        "meme":        CLUSTERS["meme"],
        "event_risk":  CLUSTERS["event_risk"],
    }
    _run(split_a, f"Split L1_new: major={l1_new[:4]} / minor={l1_new[4:]} (6 clusters)")

    print(f"\n--- Single-coin clusters (degenerate: no within-cluster tilt) ---")
    all_as_own = {c: [c] for c in active_cols}
    _run(all_as_own, f"Every coin its own cluster ({len(active_cols)} clusters) = EW")

    print(f"\n--- Granular: 8 clusters (split old_guard, split L1_new, keep rest) ---")
    eight_clusters = {
        "BTC_group":    ["BTC", "LTC", "BCH"],
        "legacy_alt":   ["ETC", "XLM", "DASH", "ZEC", "BAT"],
        "ETH_L2":       ["ETH", "MATIC"],
        "new_L1":       ["SOL", "AVAX", "ATOM", "DOT", "NEAR", "ALGO"],
        "infra":        ["TRX", "EOS", "XTZ", "ICP", "FIL"],
        "DeFi_DApp":    CLUSTERS["DeFi"] + ["MANA", "SAND", "AXS"],
        "meme":         CLUSTERS["meme"],
        "event_risk":   CLUSTERS["event_risk"],
    }
    _run(eight_clusters, "8 clusters (granular split)")


# ---------------------------------------------------------------------------
# Section: walkforward — annual rolling walk-forward performance
# ---------------------------------------------------------------------------

def section_walkforward(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("WALK-FORWARD — Per-year and rolling 2-year window performance")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    momentum, _ = build_features(trends)
    active_cols  = [c for c in trends.columns if c in prices.columns]
    weekly_ret   = prices[active_cols].pct_change().clip(-0.95, 10)
    ew_ret       = weekly_ret.mean(axis=1).dropna()

    def _period_stats(port: pd.Series, label: str, ew: pd.Series) -> None:
        idx   = port.index.intersection(ew.index)
        port  = port.reindex(idx).dropna()
        ew_p  = ew.reindex(idx).dropna()
        if len(port) < 4:
            print(f"  {label:35s}  (insufficient data)")
            return
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sh      = ann_ret / ann_vol if ann_vol > 0 else float("nan")
        dd      = ((1 + port).cumprod() / (1 + port).cumprod().cummax() - 1).min()
        ew_ret_ = (1 + ew_p).prod() ** (52 / len(ew_p)) - 1
        ew_vol  = ew_p.std() * np.sqrt(52)
        ew_sh   = ew_ret_ / ew_vol if ew_vol > 0 else float("nan")
        print(f"  {label:35s}  "
              f"Strat: CAGR={ann_ret:+.1%} Sharpe={sh:.2f} MaxDD={dd:.1%}  "
              f"EW: CAGR={ew_ret_:+.1%} Sharpe={ew_sh:.2f}  "
              f"Alpha={ann_ret-ew_ret_:+.1%}")

    # Full backtest to get return series
    full_res = _run_cluster_tilt(CLUSTERS, momentum, weekly_ret, active_cols,
                                  tilt_strength=1.0, z_penalty=0.0, cost_bps=10)
    port = full_res["returns"]

    print(f"\n  Strategy: cluster tilt=1.0, 28d momentum, 10bps cost")
    print(f"  Note: signal computation (rolling 52w) is already time-correct — no look-ahead.")
    print(f"  Cluster definitions are fixed (fundamental categories, not learned from returns).")

    # Per calendar year
    print(f"\n--- Per-year performance ---")
    for year in range(2020, 2026):
        idx = port.index[port.index.year == year]
        if len(idx) == 0:
            continue
        _period_stats(port.reindex(idx), f"{year}", ew_ret)

    # Rolling 2-year windows
    print(f"\n--- Rolling 2-year windows ---")
    years = list(range(2020, 2025))
    for start_year in years:
        s = pd.Timestamp(f"{start_year}-01-01")
        e = pd.Timestamp(f"{start_year + 1}-12-31")
        idx = port.index[(port.index >= s) & (port.index <= e)]
        if len(idx) < 20:
            continue
        _period_stats(port.reindex(idx), f"{start_year}–{start_year+1}", ew_ret)

    # In-sample / out-of-sample split
    print(f"\n--- In-sample vs out-of-sample ---")
    is_idx  = port.index[port.index < pd.Timestamp("2024-01-01")]
    oos_idx = port.index[port.index >= pd.Timestamp("2024-01-01")]
    _period_stats(port.reindex(is_idx),  "In-sample  (Jan 2020 – Dec 2023)", ew_ret)
    _period_stats(port.reindex(oos_idx), "Out-of-sample (Jan 2024 – Jan 2026)", ew_ret)

    # Consistency: how many years does strategy beat EW?
    print(f"\n--- Year-by-year consistency ---")
    beats = 0
    n_years = 0
    for year in range(2020, 2026):
        idx = port.index[port.index.year == year]
        if len(idx) < 10:
            continue
        n_years += 1
        strat_ret = (1 + port.reindex(idx).dropna()).prod() - 1
        ew_year   = (1 + ew_ret.reindex(idx).dropna()).prod() - 1
        beat = strat_ret > ew_year
        if beat:
            beats += 1
        print(f"  {year}: Strat={strat_ret:+.1%}  EW={ew_year:+.1%}  {'BEAT' if beat else 'LOST':5s} ({strat_ret - ew_year:+.1%})")
    print(f"  Beat EW in {beats}/{n_years} calendar years")


# ---------------------------------------------------------------------------
# Section: execution — realistic execution assumptions
# ---------------------------------------------------------------------------

def section_execution(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("EXECUTION — Realistic implementation: rebalance freq + costs + position constraints")

    daily_articles = {s: WIKI_ARTICLES[s] for s in WIKI_ARTICLES}
    print("\n  Loading daily Wikipedia data ...")
    daily_raw = WIKI_FETCHER.fetch_all(daily_articles, START, END, force_refresh=False)
    if daily_raw.empty:
        print("  No daily data — skipping.")
        return
    daily_raw = daily_raw.ffill(limit=3)

    active_cols = [c for c in daily_raw.columns if c in prices.columns]
    weekly_ret  = prices[active_cols].pct_change().clip(-0.95, 10)
    ew_ret      = weekly_ret.mean(axis=1).dropna()

    # 21d momentum (best window from daily_signal section)
    mom21 = daily_raw[active_cols].pct_change(21).clip(-5, 5).resample("W-FRI").last()
    common = mom21.index.intersection(weekly_ret.index)
    mom21_w = mom21.reindex(common)
    weekly_ret_c = weekly_ret.reindex(common)

    ew_c = weekly_ret_c.mean(axis=1).dropna()
    ann_ew  = (1 + ew_c).prod() ** (52 / len(ew_c)) - 1
    vol_ew  = ew_c.std() * np.sqrt(52)
    dd_ew   = ((1 + ew_c).cumprod() / (1 + ew_c).cumprod().cummax() - 1).min()
    print(f"\n--- Benchmark: Equal-weight ---")
    print(f"  {'EW':60s}  CAGR={ann_ew:+.1%}  Sharpe={ann_ew/vol_ew:.2f}  MaxDD={dd_ew:.1%}")

    # Reference: 21d + tilt=1.0 + 0-cost weekly (best unconstrained)
    ref = _run_cluster_tilt(CLUSTERS, mom21_w, weekly_ret_c, active_cols,
                             tilt_strength=1.0, z_penalty=0.0, cost_bps=0, rebalance_freq=1)
    _fmt_res(ref, "21d tilt=1.0  0bps  weekly (theoretical max)", width=60)

    print(f"\n--- Rebalance frequency × cost (21d momentum, tilt=1.0) ---")
    print(f"  {'Config':60s}  CAGR  Sharpe  MaxDD  DownCap")
    for freq, freq_label in ((1, "weekly"), (2, "biweekly"), (4, "monthly")):
        for cost in (0, 10, 20, 30):
            res = _run_cluster_tilt(CLUSTERS, mom21_w, weekly_ret_c, active_cols,
                                     tilt_strength=1.0, z_penalty=0.0,
                                     cost_bps=cost, rebalance_freq=freq)
            _fmt_res(res, f"{freq_label:10s}  {cost:2d}bps", width=60)

    # Position size constraints: cap max weight per coin at X%
    print(f"\n--- Max position size cap (21d, tilt=1.0, 10bps, weekly) ---")
    for max_weight in (0.20, 0.15, 0.10, 0.08, 1.0):
        cost = 10 / 10_000
        port_returns = []
        prev_weights = pd.Series(0.0, index=active_cols)
        active_clusters = {k: [m for m in v if m in active_cols] for k, v in CLUSTERS.items()}
        active_clusters = {k: v for k, v in active_clusters.items() if v}
        n_clusters = len(active_clusters)
        cluster_base = 1.0 / n_clusters

        for date in weekly_ret_c.index:
            lag_idx = mom21_w.index[mom21_w.index < date]
            if lag_idx.empty:
                port_returns.append((date, 0.0))
                continue
            prev_date = lag_idx[-1]
            weights = pd.Series(0.0, index=active_cols)
            for members in active_clusters.values():
                cm = mom21_w.loc[prev_date, members].dropna()
                n_m = len(cm)
                if n_m == 0:
                    continue
                if n_m == 1:
                    weights[cm.index[0]] += cluster_base
                    continue
                cs_z = (cm - cm.mean()) / cm.std() if cm.std() > 0 else cm * 0
                raw = (cluster_base / n_m) * (1 + cs_z)
                raw = raw.clip(lower=0)
                total = raw.sum()
                normalised = raw / total * cluster_base if total > 0 else pd.Series(cluster_base / n_m, index=cm.index)
                for m in normalised.index:
                    weights[m] += normalised[m]
            total = weights.sum()
            weights = weights / total if total > 0 else pd.Series(1.0 / len(active_cols), index=active_cols)
            # Apply max weight cap
            if max_weight < 1.0:
                weights = weights.clip(upper=max_weight)
                total = weights.sum()
                weights = weights / total
            tc = cost * (weights - prev_weights).abs().sum()
            ret = (weekly_ret_c.loc[date, active_cols] * weights).sum()
            port_returns.append((date, ret - tc))
            prev_weights = weights

        port = pd.Series({d: r for d, r in port_returns}).dropna()
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sh = ann_ret / ann_vol if ann_vol > 0 else float("nan")
        dd = ((1 + port).cumprod() / (1 + port).cumprod().cummax() - 1).min()
        cap_label = f"max_weight={max_weight:.0%}" if max_weight < 1.0 else "no cap"
        print(f"  {cap_label:60s}  CAGR={ann_ret:+.1%}  Sharpe={sh:.2f}  MaxDD={dd:.1%}")

    # Turnover analysis
    print(f"\n--- Turnover analysis (21d, tilt=1.0, weekly) ---")
    active_clusters = {k: [m for m in v if m in active_cols] for k, v in CLUSTERS.items()}
    active_clusters = {k: v for k, v in active_clusters.items() if v}
    n_clusters = len(active_clusters)
    cluster_base = 1.0 / n_clusters
    prev_w = pd.Series(0.0, index=active_cols)
    turnovers = []
    for date in weekly_ret_c.index:
        lag_idx = mom21_w.index[mom21_w.index < date]
        if lag_idx.empty:
            continue
        prev_date = lag_idx[-1]
        weights = pd.Series(0.0, index=active_cols)
        for members in active_clusters.values():
            cm = mom21_w.loc[prev_date, members].dropna()
            n_m = len(cm)
            if n_m == 0:
                continue
            if n_m == 1:
                weights[cm.index[0]] += cluster_base
                continue
            cs_z = (cm - cm.mean()) / cm.std() if cm.std() > 0 else cm * 0
            raw = (cluster_base / n_m) * (1 + cs_z)
            raw = raw.clip(lower=0)
            total = raw.sum()
            normalised = raw / total * cluster_base if total > 0 else pd.Series(cluster_base / n_m, index=cm.index)
            for m in normalised.index:
                weights[m] += normalised[m]
        total = weights.sum()
        weights = weights / total if total > 0 else pd.Series(1.0 / len(active_cols), index=active_cols)
        turnovers.append((weights - prev_w).abs().sum())
        prev_w = weights

    t_arr = np.array(turnovers[1:])  # skip first (from 0)
    print(f"  Weekly one-way turnover: mean={t_arr.mean():.3f}  median={np.median(t_arr):.3f}  max={t_arr.max():.3f}")
    print(f"  Annualised one-way turnover: {t_arr.mean() * 52:.1%}")
    print(f"  Cost drag at 10bps:  {t_arr.mean() * 52 * 0.001:.2%}/year")
    print(f"  Cost drag at 20bps:  {t_arr.mean() * 52 * 0.002:.2%}/year")
    print(f"  Cost drag at 30bps:  {t_arr.mean() * 52 * 0.003:.2%}/year")


# ---------------------------------------------------------------------------
# Section: regime — BTC attention regime filter
# ---------------------------------------------------------------------------

def section_regime(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("REGIME — BTC attention regime filter: scale tilt on BTC Z-score")

    if trends.empty:
        print("  No attention data — skipping.")
        return

    daily_articles = {s: WIKI_ARTICLES[s] for s in WIKI_ARTICLES}
    print("\n  Loading daily Wikipedia data ...")
    daily_raw = WIKI_FETCHER.fetch_all(daily_articles, START, END, force_refresh=False)
    if daily_raw.empty:
        print("  No daily data — skipping.")
        return
    daily_raw = daily_raw.ffill(limit=3)

    active_cols = [c for c in daily_raw.columns if c in prices.columns]
    weekly_ret  = prices[active_cols].pct_change().clip(-0.95, 10)

    mom21 = daily_raw[active_cols].pct_change(21).clip(-5, 5).resample("W-FRI").last()
    common = mom21.index.intersection(weekly_ret.index)
    mom21_w     = mom21.reindex(common)
    weekly_ret_c = weekly_ret.reindex(common)

    # BTC attention Z-score (52-week rolling on weekly Wikipedia views)
    btc_weekly_att = daily_raw["BTC"].resample("W-FRI").sum().reindex(common)
    btc_rm = btc_weekly_att.rolling(52, min_periods=26).mean()
    btc_rs = btc_weekly_att.rolling(52, min_periods=26).std()
    btc_z  = ((btc_weekly_att - btc_rm) / btc_rs.replace(0, np.nan)).rename("BTC_Z")

    ew_ret = weekly_ret_c.mean(axis=1).dropna()
    ann_ew  = (1 + ew_ret).prod() ** (52 / len(ew_ret)) - 1
    vol_ew  = ew_ret.std() * np.sqrt(52)
    dd_ew   = ((1 + ew_ret).cumprod() / (1 + ew_ret).cumprod().cummax() - 1).min()

    print(f"\n  BTC attention Z-score distribution:")
    print(f"    Mean={btc_z.mean():.3f}  Std={btc_z.std():.3f}  Max={btc_z.max():.2f}")
    for z_thr in (1.5, 2.0, 2.5, 3.0):
        n = (btc_z > z_thr).sum()
        print(f"    BTC Z > {z_thr}: {n} weeks ({100*n/btc_z.notna().sum():.1f}%)")

    print(f"\n--- Benchmarks ---")
    print(f"  {'Equal-weight':60s}  CAGR={ann_ew:+.1%}  Sharpe={ann_ew/vol_ew:.2f}  MaxDD={dd_ew:.1%}  DownCap=1.00")

    res_no_regime = _run_cluster_tilt(CLUSTERS, mom21_w, weekly_ret_c, active_cols,
                                       tilt_strength=1.0, z_penalty=0.0, cost_bps=10)
    _fmt_res(res_no_regime, "21d tilt=1.0  10bps  no regime filter", width=60)

    print(f"\n--- Regime filter: linear tilt scale-down when BTC Z > threshold ---")
    print(f"  Mechanism: tilt_effective = tilt × max(0, 1 - (BTC_Z - threshold)) when BTC_Z > threshold")
    for z_thr in (1.5, 2.0, 2.5, 3.0):
        res = _run_cluster_tilt(CLUSTERS, mom21_w, weekly_ret_c, active_cols,
                                 tilt_strength=1.0, z_penalty=0.0, cost_bps=10,
                                 regime_z=btc_z, regime_threshold=z_thr)
        _fmt_res(res, f"21d tilt=1.0  10bps  regime BTC_Z>{z_thr:.1f} (linear scale)", width=60)

    print(f"\n--- Regime filter: hard switch (tilt=0 when BTC Z > threshold) ---")
    # Implement hard switch inline
    for z_thr in (1.5, 2.0, 2.5, 3.0):
        cost = 10 / 10_000
        active_clusters = {k: [m for m in v if m in active_cols] for k, v in CLUSTERS.items()}
        active_clusters = {k: v for k, v in active_clusters.items() if v}
        n_clusters = len(active_clusters)
        cluster_base = 1.0 / n_clusters
        prev_w = pd.Series(0.0, index=active_cols)
        port_returns = []
        for date in weekly_ret_c.index:
            lag_idx = mom21_w.index[mom21_w.index < date]
            if lag_idx.empty:
                port_returns.append((date, 0.0))
                continue
            prev_date = lag_idx[-1]
            # Regime check
            btc_z_val = btc_z.loc[prev_date] if prev_date in btc_z.index else 0.0
            use_tilt = btc_z_val <= z_thr
            weights = pd.Series(0.0, index=active_cols)
            for members in active_clusters.values():
                cm = mom21_w.loc[prev_date, members].dropna()
                n_m = len(cm)
                if n_m == 0:
                    continue
                if n_m == 1 or not use_tilt:
                    for m in cm.index:
                        weights[m] += cluster_base / n_m
                    continue
                cs_z = (cm - cm.mean()) / cm.std() if cm.std() > 0 else cm * 0
                raw = (cluster_base / n_m) * (1 + cs_z)
                raw = raw.clip(lower=0)
                total = raw.sum()
                normalised = raw / total * cluster_base if total > 0 else pd.Series(cluster_base / n_m, index=cm.index)
                for m in normalised.index:
                    weights[m] += normalised[m]
            total = weights.sum()
            weights = weights / total if total > 0 else pd.Series(1.0 / len(active_cols), index=active_cols)
            tc = cost * (weights - prev_w).abs().sum()
            ret = (weekly_ret_c.loc[date, active_cols] * weights).sum()
            port_returns.append((date, ret - tc))
            prev_w = weights
        port = pd.Series({d: r for d, r in port_returns}).dropna()
        ann_ret = (1 + port).prod() ** (52 / len(port)) - 1
        ann_vol = port.std() * np.sqrt(52)
        sh  = ann_ret / ann_vol if ann_vol > 0 else float("nan")
        dd  = ((1 + port).cumprod() / (1 + port).cumprod().cummax() - 1).min()
        ew_down = ew_ret[ew_ret < 0].mean()
        strat_down = port.reindex(ew_ret[ew_ret < 0].index).dropna().mean()
        dc = strat_down / ew_down if ew_down != 0 else float("nan")
        n_risk_off = (btc_z.dropna() > z_thr).sum()
        dc_str = f"{dc:+.2f}" if not pd.isna(dc) else "n/a"
        print(f"  {'21d tilt=1.0  10bps  BTC_Z>'+str(z_thr)+' -> EW (hard switch)':60s}  "
              f"CAGR={ann_ret:+.1%}  Sharpe={sh:.2f}  MaxDD={dd:.1%}  DownCap={dc_str}  "
              f"[risk-off: {n_risk_off}w]")

    # Show BTC Z timeline vs strategy performance
    print(f"\n--- BTC attention regime context: high-Z episodes ---")
    high_z_weeks = btc_z[btc_z > 2.0].dropna()
    if not high_z_weeks.empty:
        print(f"  Weeks where BTC Wikipedia Z > 2.0 ({len(high_z_weeks)} total):")
        # Group into episodes (consecutive or near-consecutive weeks)
        dates = sorted(high_z_weeks.index)
        episodes = []
        start = dates[0]
        prev  = dates[0]
        for d in dates[1:]:
            if (d - prev).days <= 21:  # within 3 weeks = same episode
                prev = d
            else:
                episodes.append((start, prev, high_z_weeks.loc[start:prev].max()))
                start = d
                prev  = d
        episodes.append((start, prev, high_z_weeks.loc[start:prev].max()))
        for ep_start, ep_end, peak_z in episodes:
            # Return of strategy vs EW during episode
            idx = weekly_ret_c.index[(weekly_ret_c.index >= ep_start) & (weekly_ret_c.index <= ep_end)]
            if len(idx) == 0:
                continue
            ew_ep = (1 + ew_ret.reindex(idx).dropna()).prod() - 1
            print(f"    {ep_start.date()} to {ep_end.date()}  peak BTC Z={peak_z:.2f}  EW return={ew_ep:+.1%}")


# ---------------------------------------------------------------------------
# Section: charts — locked config validation + chart generation
# ---------------------------------------------------------------------------

# LOCKED CONFIGURATION — do not change
LOCKED = {
    "momentum_days": 14,
    "tilt": 1.0,
    "z_penalty": 0.0,
    "rebalance_freq": 1,   # weekly
    "cost_bps_primary": 10,
    "cost_bps_secondary": 20,
    "max_weight": None,    # uncapped
}


def section_charts(prices: pd.DataFrame, trends: pd.DataFrame) -> None:
    sep("CHARTS + FINAL VALIDATION — Locked config: 14d momentum, tilt=1.0, weekly, 10bps")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("  matplotlib not installed — run: pip install matplotlib")
        return

    CHART_DIR = IDEA_DIR
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    # --- Load daily data ---
    print("\n  Loading daily Wikipedia data ...")
    daily_articles = {s: WIKI_ARTICLES[s] for s in WIKI_ARTICLES}
    daily_raw = WIKI_FETCHER.fetch_all(daily_articles, START, END, force_refresh=False)
    if daily_raw.empty:
        print("  No daily data — skipping.")
        return
    daily_raw = daily_raw.ffill(limit=3)

    active_cols = [c for c in daily_raw.columns if c in prices.columns]
    weekly_ret  = prices[active_cols].pct_change().clip(-0.95, 10)

    # 14d momentum (locked)
    mom14 = daily_raw[active_cols].pct_change(14).clip(-5, 5).resample("W-FRI").last()
    common = mom14.index.intersection(weekly_ret.index)
    mom14_w     = mom14.reindex(common)
    weekly_ret_c = weekly_ret.reindex(common)

    # --- Run locked configs ---
    res_10 = _run_cluster_tilt(CLUSTERS, mom14_w, weekly_ret_c, active_cols,
                                tilt_strength=1.0, z_penalty=0.0, cost_bps=10, rebalance_freq=1)
    res_20 = _run_cluster_tilt(CLUSTERS, mom14_w, weekly_ret_c, active_cols,
                                tilt_strength=1.0, z_penalty=0.0, cost_bps=20, rebalance_freq=1)
    res_0  = _run_cluster_tilt(CLUSTERS, mom14_w, weekly_ret_c, active_cols,
                                tilt_strength=1.0, z_penalty=0.0, cost_bps=0, rebalance_freq=1)

    ew_ret  = weekly_ret_c.mean(axis=1).dropna()
    btc_ret = weekly_ret_c["BTC"].dropna() if "BTC" in weekly_ret_c.columns else ew_ret

    def _cum(r: pd.Series) -> pd.Series:
        return (1 + r).cumprod()

    def _dd(r: pd.Series) -> pd.Series:
        c = _cum(r)
        return c / c.cummax() - 1

    def _stats(r: pd.Series) -> dict:
        n = len(r)
        ann = (1 + r).prod() ** (52 / n) - 1 if n > 0 else float("nan")
        vol = r.std() * np.sqrt(52)
        sh  = ann / vol if vol > 0 else float("nan")
        dd  = _dd(r).min()
        ew_d = ew_ret.reindex(r.index)
        ew_down = ew_d[ew_d < 0].mean()
        s_down  = r.reindex(ew_d[ew_d < 0].index).dropna().mean()
        dc = s_down / ew_down if ew_down != 0 else float("nan")
        return {"cagr": ann, "vol": vol, "sharpe": sh, "max_dd": dd, "down_cap": dc}

    s10  = _stats(res_10["returns"])
    s20  = _stats(res_20["returns"])
    s0   = _stats(res_0["returns"])
    sew  = _stats(ew_ret)
    sbtc = _stats(btc_ret)

    # --- Print final validation table ---
    print(f"\n{'='*75}")
    print(f"  FINAL VALIDATION — Jan 2020 to Jan 2026")
    print(f"{'='*75}")
    print(f"  {'Strategy':40s}  {'CAGR':>7}  {'Vol':>6}  {'Sharpe':>7}  {'MaxDD':>7}  {'DownCap':>8}")
    print(f"  {'-'*75}")
    rows = [
        ("Strategy (14d, tilt=1.0, 0bps)",   s0),
        ("Strategy (14d, tilt=1.0, 10bps)",  s10),
        ("Strategy (14d, tilt=1.0, 20bps)",  s20),
        ("Equal-weight 37 coins",             sew),
        ("BTC buy-and-hold",                  sbtc),
    ]
    for label, s in rows:
        dc = f"{s['down_cap']:+.2f}" if not pd.isna(s.get("down_cap", float("nan"))) else "  n/a"
        print(f"  {label:40s}  {s['cagr']:+7.1%}  {s['vol']:6.1%}  {s['sharpe']:7.2f}  {s['max_dd']:7.1%}  {dc:>8}")

    # Year-by-year
    print(f"\n  {'Year':6s}  {'Strat 10bps':>12}  {'EW':>10}  {'BTC':>10}  {'Alpha vs EW':>12}")
    print(f"  {'-'*55}")
    port10 = res_10["returns"]
    for year in range(2020, 2026):
        idx = port10.index[port10.index.year == year]
        if len(idx) < 4:
            continue
        s_yr  = (1 + port10.reindex(idx).dropna()).prod() - 1
        ew_yr = (1 + ew_ret.reindex(idx).dropna()).prod() - 1
        bt_yr = (1 + btc_ret.reindex(idx).dropna()).prod() - 1
        print(f"  {year}    {s_yr:+12.1%}  {ew_yr:+10.1%}  {bt_yr:+10.1%}  {s_yr-ew_yr:+12.1%}")

    # --- CHART 1: Equity curves ---
    port10 = res_10["returns"]
    port20 = res_20["returns"]
    common_plot = port10.index.intersection(ew_ret.index).intersection(btc_ret.index)

    fig, axes = plt.subplots(3, 1, figsize=(12, 14), gridspec_kw={"height_ratios": [3, 1.5, 1.5]})
    fig.suptitle("Wikipedia Attention Cluster Strategy — Final Validation\n"
                 "14d momentum · 5 clusters · tilt=1.0 · weekly rebalance",
                 fontsize=13, fontweight="bold", y=0.98)

    # Panel 1: Equity curves (log scale)
    ax = axes[0]
    c10 = _cum(port10.reindex(common_plot))
    c20 = _cum(port20.reindex(common_plot))
    c_ew  = _cum(ew_ret.reindex(common_plot))
    c_btc = _cum(btc_ret.reindex(common_plot))
    ax.semilogy(common_plot, c10,  color="#2196F3", lw=2.0, label=f"Strategy 10bps (Sharpe {s10['sharpe']:.2f})")
    ax.semilogy(common_plot, c20,  color="#90CAF9", lw=1.5, linestyle="--", label=f"Strategy 20bps (Sharpe {s20['sharpe']:.2f})")
    ax.semilogy(common_plot, c_ew, color="#FF9800", lw=1.8, label=f"Equal-weight (Sharpe {sew['sharpe']:.2f})")
    ax.semilogy(common_plot, c_btc,color="#9E9E9E", lw=1.5, linestyle=":", label=f"BTC buy-and-hold (Sharpe {sbtc['sharpe']:.2f})")
    ax.set_ylabel("Cumulative return (log scale)", fontsize=10)
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_title("Equity Curves (Jan 2020 – Jan 2026)", fontsize=10)

    # Panel 2: Drawdown
    ax2 = axes[1]
    dd10  = _dd(port10.reindex(common_plot)) * 100
    dd_ew = _dd(ew_ret.reindex(common_plot)) * 100
    dd_btc = _dd(btc_ret.reindex(common_plot)) * 100
    ax2.fill_between(common_plot, dd10,  0, alpha=0.4, color="#2196F3", label="Strategy 10bps")
    ax2.plot(common_plot, dd_ew,  color="#FF9800", lw=1.2, label="Equal-weight")
    ax2.plot(common_plot, dd_btc, color="#9E9E9E", lw=1.0, linestyle=":", label="BTC")
    ax2.set_ylabel("Drawdown (%)", fontsize=10)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.set_title("Drawdown", fontsize=10)

    # Panel 3: Annual alpha vs EW
    ax3 = axes[2]
    years_list, alpha_list, colors_list = [], [], []
    for year in range(2020, 2026):
        idx = port10.index[port10.index.year == year]
        if len(idx) < 4:
            continue
        s_yr  = (1 + port10.reindex(idx).dropna()).prod() - 1
        ew_yr = (1 + ew_ret.reindex(idx).dropna()).prod() - 1
        alpha = s_yr - ew_yr
        years_list.append(year)
        alpha_list.append(alpha * 100)
        colors_list.append("#2196F3" if alpha >= 0 else "#F44336")
    bars = ax3.bar(years_list, alpha_list, color=colors_list, alpha=0.8, width=0.6)
    ax3.axhline(0, color="black", lw=0.8)
    ax3.set_ylabel("Annual alpha vs EW (%)", fontsize=10)
    ax3.set_xlabel("")
    ax3.set_title("Annual Alpha vs Equal-Weight", fontsize=10)
    ax3.grid(True, alpha=0.3, axis="y")
    for bar, val in zip(bars, alpha_list):
        ax3.text(bar.get_x() + bar.get_width() / 2, val + (2 if val >= 0 else -4),
                 f"{val:+.0f}%", ha="center", va="bottom" if val >= 0 else "top", fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    chart_path = CHART_DIR / "equity_curves.png"
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Saved: {chart_path}")

    # --- CHART 2: Signal diagnostics ---
    fig2, axes2 = plt.subplots(2, 2, figsize=(13, 9))
    fig2.suptitle("Signal Diagnostics — Wikipedia Attention Cluster Strategy", fontsize=12, fontweight="bold")

    # 2a: Cluster weight over time (stacked area — one line per cluster, top coin)
    ax = axes2[0, 0]
    active_clusters = {k: [m for m in v if m in active_cols] for k, v in CLUSTERS.items()}
    active_clusters = {k: v for k, v in active_clusters.items() if v}
    cluster_base = 1.0 / len(active_clusters)
    # Show 14d momentum for the strongest signal coin in each cluster over time
    cluster_colors = {"old_guard": "#78909C", "L1_new": "#2196F3", "DeFi": "#4CAF50",
                      "meme": "#FF9800", "event_risk": "#F44336"}
    for cname, members in active_clusters.items():
        # Average weekly momentum across cluster members
        cluster_mom = mom14_w[members].mean(axis=1)
        ax.plot(common_plot, cluster_mom.reindex(common_plot), lw=0.9,
                label=cname, color=cluster_colors.get(cname, "gray"), alpha=0.8)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_title("14d Attention Momentum by Cluster", fontsize=9)
    ax.set_ylabel("Mean 14d pct change (clipped)", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 2b: BTC Wikipedia Z-score
    ax = axes2[0, 1]
    if "BTC" in daily_raw.columns:
        btc_weekly_att = daily_raw["BTC"].resample("W-FRI").sum().reindex(common)
        btc_rm = btc_weekly_att.rolling(52, min_periods=26).mean()
        btc_rs = btc_weekly_att.rolling(52, min_periods=26).std()
        btc_z  = (btc_weekly_att - btc_rm) / btc_rs.replace(0, np.nan)
        ax.fill_between(common, btc_z.clip(lower=0), 0, alpha=0.5, color="#2196F3", label="BTC Z (positive)")
        ax.fill_between(common, btc_z.clip(upper=0), 0, alpha=0.5, color="#F44336", label="BTC Z (negative)")
        ax.axhline(2.0, color="red", lw=0.8, linestyle="--", label="Z=2.0 threshold")
        ax.axhline(-2.0, color="blue", lw=0.8, linestyle="--")
        ax.set_title("BTC Wikipedia Attention Z-Score (52w rolling)", fontsize=9)
        ax.set_ylabel("Z-score", fontsize=8)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.2)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 2c: Rolling 52-week Sharpe
    ax = axes2[1, 0]
    roll_window = 52
    def _rolling_sharpe(r: pd.Series, w: int) -> pd.Series:
        roll_ret = r.rolling(w).apply(lambda x: (1 + x).prod() ** (52 / w) - 1)
        roll_vol = r.rolling(w).std() * np.sqrt(52)
        return roll_ret / roll_vol.replace(0, np.nan)
    rs10  = _rolling_sharpe(port10.reindex(common_plot), roll_window)
    rs_ew = _rolling_sharpe(ew_ret.reindex(common_plot), roll_window)
    ax.plot(common_plot, rs10,  color="#2196F3", lw=1.5, label="Strategy 10bps")
    ax.plot(common_plot, rs_ew, color="#FF9800", lw=1.2, label="Equal-weight")
    ax.axhline(0, color="black", lw=0.5)
    ax.axhline(1.0, color="gray", lw=0.5, linestyle=":")
    ax.set_title(f"Rolling {roll_window}-week Sharpe Ratio", fontsize=9)
    ax.set_ylabel("Sharpe", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 2d: Out-of-sample zoom (2024–2026)
    ax = axes2[1, 1]
    oos_start = pd.Timestamp("2024-01-01")
    oos_idx = common_plot[common_plot >= oos_start]
    if len(oos_idx) > 4:
        c10_oos  = _cum(port10.reindex(oos_idx)) / _cum(port10.reindex(oos_idx)).iloc[0]
        cew_oos  = _cum(ew_ret.reindex(oos_idx)) / _cum(ew_ret.reindex(oos_idx)).iloc[0]
        cbtc_oos = _cum(btc_ret.reindex(oos_idx)) / _cum(btc_ret.reindex(oos_idx)).iloc[0]
        ax.plot(oos_idx, c10_oos,  color="#2196F3", lw=2.0, label="Strategy 10bps")
        ax.plot(oos_idx, cew_oos,  color="#FF9800", lw=1.8, label="Equal-weight")
        ax.plot(oos_idx, cbtc_oos, color="#9E9E9E", lw=1.5, linestyle=":", label="BTC")
        ax.axhline(1.0, color="black", lw=0.5)
        ax.set_title("Out-of-sample: Jan 2024 – Jan 2026 (rebased to 1.0)", fontsize=9)
        ax.set_ylabel("Cumulative return", fontsize=8)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.2)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))

    plt.tight_layout()
    diag_path = CHART_DIR / "signal_diagnostics.png"
    fig2.savefig(diag_path, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    print(f"  Saved: {diag_path}")

    print(f"\n  Charts saved to {CHART_DIR}")
    print(f"\n  LOCKED CONFIG:")
    for k, v in LOCKED.items():
        print(f"    {k}: {v}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

SECTIONS = {"universe", "data", "features", "signals", "backtest", "v2",
            "collapse", "clusters", "ew_tilt",
            "auto_cluster", "cluster_tilt", "z_sweep", "daily_signal", "robustness",
            "final_signal", "stress_test", "walkforward", "execution", "regime",
            "charts"}

if __name__ == "__main__":
    args = sys.argv[1:]
    section = args[0] if args else "all"
    fetch_trends_flag = "--fetch-attention" in args

    if section not in SECTIONS | {"all"}:
        print(f"Unknown section '{section}'. Choose from: {', '.join(sorted(SECTIONS))} or all")
        print("  Add --fetch-trends to trigger new Trends API calls for uncached coins.")
        sys.exit(1)

    prices_g, trends_g = pd.DataFrame(), pd.DataFrame()

    if section in ("universe", "all"):
        section_universe()

    if section in ("data", "all"):
        # If --fetch-trends passed, fetch Trends for all universe coins
        if fetch_trends_flag:
            all_syms = [c["symbol"] for c in UNIVERSE]
            fetch_attention(all_syms)
        prices_g, trends_g = section_data()

    if section in ("features", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_features(prices_g, trends_g)

    if section in ("signals", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_signals(prices_g, trends_g)

    if section in ("backtest", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_backtest(prices_g, trends_g)

    if section in ("v2", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_v2(prices_g, trends_g)

    if section in ("collapse", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_collapse_test(prices_g, trends_g)

    if section in ("clusters", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_clusters(prices_g, trends_g)

    if section in ("ew_tilt", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_ew_tilt(prices_g, trends_g)

    if section in ("auto_cluster", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_auto_cluster(prices_g, trends_g)

    if section in ("cluster_tilt", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_cluster_tilt(prices_g, trends_g)

    if section in ("z_sweep", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_z_sweep(prices_g, trends_g)

    if section in ("daily_signal", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_daily_signal(prices_g, trends_g)

    if section in ("robustness", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_robustness(prices_g, trends_g)

    if section in ("final_signal", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_final_signal(prices_g, trends_g)

    if section in ("stress_test", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_stress_test(prices_g, trends_g)

    if section in ("walkforward", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_walkforward(prices_g, trends_g)

    if section in ("execution", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_execution(prices_g, trends_g)

    if section in ("regime", "all"):
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_regime(prices_g, trends_g)

    if section in ("charts",):   # not included in "all" — run explicitly
        if prices_g.empty:
            prices_g, trends_g = section_data()
        section_charts(prices_g, trends_g)
