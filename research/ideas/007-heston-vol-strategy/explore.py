"""
Heston Vol Strategy — Idea 007 (v5: Cross-sectional VRP)
=========================================================
Hypothesis: the Volatility Risk Premium (VRP = implied_vol - realised_vol)
is the direct market expression of the Heston variance deviation signal.
When implied vol exceeds realised vol, the market is pricing in more variance
than has been observed — via the leverage effect (rho < 0) this implies a
positive expected return on the underlying index.

Applied cross-sectionally: allocate proportionally to max(VRP_i, 0) across
all pairs where the leverage effect is confirmed (rho < 0). The portfolio is
almost always invested (VRP is structurally positive for equity indices),
solving the time-dilution problem of the binary signal approach.

No CIR fitting required — VRP is measured directly from market prices.
No entry/exit thresholds — weights vary continuously with the signal.
Only design parameters: realised-vol lookback, rho lookback, rebalance frequency.

Pairs:
  SPY / ^VIX   (S&P 500)
  QQQ / ^VXN   (Nasdaq 100)
  GLD / ^GVZ   (Gold — rho filter excludes when leverage effect absent)

Signal per pair:
  vrp_t     = vol_index_t - realised_vol_t   (both annualised %)
  rho_t     = rolling Corr(r_t, delta_vol_t) (leverage effect check)
  score_t   = max(vrp_t, 0)  if rho_t < RHO_THRESHOLD  else 0
  weight_t  = score_t / sum(scores_t)        (proportional allocation)

Sharpe measured vs 3-month T-bill (^IRX).

Sections:
  signal  -- full backtest with diagnostics
  sweep   -- grid over RV_WINDOW x REBAL_STEP
"""

import sys
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config — intentionally minimal; no thresholds to overfit
# ---------------------------------------------------------------------------
PAIRS = [
    ("SPY", "^VIX"),   # S&P 500
    ("QQQ", "^VXN"),   # Nasdaq 100
    ("GLD", "^GVZ"),   # Gold (rho filter expected to exclude risk-off episodes)
]
RF_TICKER     = "^IRX"
PERIOD        = "max"
INTERVAL      = "1d"

RV_WINDOW     = 20    # days for rolling realised vol (industry standard)
RHO_WINDOW    = 60    # days for rolling leverage-effect correlation
RHO_THRESHOLD = -0.1  # require confirmed negative rho to allocate

REBAL_STEP    = 21    # days between rebalances (~monthly)
TC_BPS        = 2.0   # one-way bps per unit of weight change

_ANN = np.sqrt(252)


# ---------------------------------------------------------------------------
# 1. Data
# ---------------------------------------------------------------------------
def fetch_data() -> tuple[dict[str, pd.DataFrame], pd.Series]:
    all_etfs = [p[0] for p in PAIRS]
    all_vols = [p[1] for p in PAIRS]

    print(f"Fetching ETFs + vol indices ({PERIOD} daily)...")
    etf_raw = yf.download(all_etfs, period=PERIOD, interval=INTERVAL,
                          progress=False, auto_adjust=True)
    etf_close = etf_raw["Close"] if isinstance(etf_raw.columns, pd.MultiIndex) else etf_raw
    etf_close.index = pd.to_datetime(etf_close.index, utc=True)

    vol_raw = yf.download(all_vols, period=PERIOD, interval=INTERVAL,
                          progress=False, auto_adjust=True)
    vol_close = vol_raw["Close"] if isinstance(vol_raw.columns, pd.MultiIndex) else vol_raw
    vol_close.index = pd.to_datetime(vol_close.index, utc=True)

    rf_raw = yf.download(RF_TICKER, period=PERIOD, interval=INTERVAL,
                         progress=False, auto_adjust=True)
    if isinstance(rf_raw.columns, pd.MultiIndex):
        rf_raw.columns = rf_raw.columns.droplevel(1)
    rf_s = (rf_raw["Close"] / 100 / 252).rename("rf_daily")
    rf_s.index = pd.to_datetime(rf_s.index, utc=True)

    pairs_data: dict[str, pd.DataFrame] = {}
    for etf, vol_ticker in PAIRS:
        if etf not in etf_close.columns or vol_ticker not in vol_close.columns:
            print(f"  SKIP {etf}/{vol_ticker}: not available")
            continue
        df = pd.DataFrame({
            "close": etf_close[etf],
            "vol":   vol_close[vol_ticker],
        }).dropna()
        if len(df) < RV_WINDOW + RHO_WINDOW + 50:
            print(f"  SKIP {etf}/{vol_ticker}: insufficient data")
            continue
        df.index = pd.to_datetime(df.index, utc=True)
        df["rf_daily"]   = rf_s.reindex(df.index, method="ffill").fillna(0)
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        df["excess_ret"] = df["log_return"] - df["rf_daily"]

        # Realised vol: rolling std of log returns, annualised to match vol index (%)
        df["rv"] = df["log_return"].rolling(RV_WINDOW).std() * _ANN * 100

        # VRP: implied minus realised (positive = implied > realised = buy signal)
        df["vrp"] = df["vol"] - df["rv"]

        # 200-day MA regime filter: Heston fast-reversion only holds in uptrends.
        # In secular bear markets, elevated VRP persists without price recovery.
        # 200d MA is an industry-standard non-optimised regime indicator.
        df["ma200"] = df["close"].rolling(200).mean()
        df["above_ma200"] = df["close"] > df["ma200"]

        # Leverage effect: rolling Corr(r_t, delta_vol_t)
        df["delta_vol"] = df["vol"].diff()
        df["rho"] = df["log_return"].rolling(RHO_WINDOW).corr(df["delta_vol"])

        df = df.dropna(subset=["rv", "vrp", "rho"])  # keep rows once rv+rho are valid
        pairs_data[etf] = df
        print(f"  {etf}/{vol_ticker}: {len(df):,} bars  "
              f"{df.index[0].date()} to {df.index[-1].date()}  "
              f"mean VRP={df['vrp'].mean():.1f}  mean rho={df['rho'].mean():.3f}")

    return pairs_data, rf_s


# ---------------------------------------------------------------------------
# 2. Signal: VRP-proportional weights, rebalanced monthly
# ---------------------------------------------------------------------------
def compute_weights(pairs_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    At each rebalance date, compute allocation weights for all pairs.
    Uses the intersection of pair indices (all three pairs must have data).

    Signal: raw VRP — weight_i = max(vrp_i, 0) / sum(max(vrp_j, 0))
             only when rho_i < RHO_THRESHOLD (leverage effect confirmed)
    """
    # Intersection: all pairs must have data; start date = latest pair warmup
    common = None
    for df in pairs_data.values():
        common = df.index if common is None else common.intersection(df.index)

    rebal_dates = common[::REBAL_STEP]

    rows = []
    for t in rebal_dates:
        scores = {}
        for etf, df in pairs_data.items():
            if t not in df.index:
                continue
            row = df.loc[t]
            # Require: negative rho (leverage effect) AND positive raw VRP
            if row["rho"] >= RHO_THRESHOLD or row["vrp"] <= 0:
                continue
            scores[etf] = max(row["vrp"], 0.0)

        total = sum(scores.values())
        weights = {etf: (s / total if total > 1e-8 else 0.0)
                   for etf, s in scores.items()}
        weights["timestamp"] = t
        rows.append(weights)

    wdf = pd.DataFrame(rows).set_index("timestamp")
    wdf = wdf.reindex(columns=list(pairs_data.keys()), fill_value=0.0)
    return wdf


# ---------------------------------------------------------------------------
# 3. Backtest
# ---------------------------------------------------------------------------
def run_backtest(pairs_data: dict[str, pd.DataFrame],
                 weights: pd.DataFrame) -> pd.DataFrame:
    # Intersection: aligned common period for all pairs
    common = None
    for df in pairs_data.values():
        common = df.index if common is None else common.intersection(df.index)

    ret_df = pd.DataFrame(
        {etf: df.reindex(common)["log_return"] for etf, df in pairs_data.items()}
    )
    rf_s = pd.DataFrame(
        {etf: df.reindex(common)["rf_daily"] for etf, df in pairs_data.items()}
    ).mean(axis=1)

    # Forward-fill weights from rebalance dates to daily bars
    w_daily = weights.reindex(common, method="ffill").fillna(0.0)

    port_gross = (ret_df * w_daily).sum(axis=1)

    TC = TC_BPS / 10_000
    w_prev     = w_daily.shift(1, fill_value=0.0)
    delta_w    = (w_daily - w_prev).abs().sum(axis=1)
    rebal_mask = delta_w > 1e-8
    tc_series  = rebal_mask.astype(float) * delta_w * TC

    port_net  = port_gross - tc_series
    invested  = w_daily.sum(axis=1)
    total_ret = port_net + rf_s * (1 - invested).clip(lower=0)

    return pd.DataFrame({
        "port_gross": port_gross,
        "port_net":   port_net,
        "total_ret":  total_ret,
        "rf_daily":   rf_s,
        "invested":   invested,
    }, index=common)


# ---------------------------------------------------------------------------
# 4. Stats
# ---------------------------------------------------------------------------
def _print_stats(result: pd.DataFrame,
                 pairs_data: dict[str, pd.DataFrame],
                 weights: pd.DataFrame,
                 label: str = "") -> float:
    if label:
        print(f"\n--- {label} ---")

    port_excess = result["total_ret"] - result["rf_daily"]
    sr_strat = (port_excess.mean() / port_excess.std() * _ANN
                if port_excess.std() > 0 else 0.0)

    # EW B&H benchmark
    bh_rets   = pd.DataFrame({e: df.reindex(result.index)["log_return"]
                              for e, df in pairs_data.items()}).mean(axis=1)
    bh_excess = bh_rets - result["rf_daily"]
    sr_bh     = (bh_excess.mean() / bh_excess.std() * _ANN
                 if bh_excess.std() > 0 else 0.0)

    ann_ret = result["total_ret"].mean() * 252 * 100
    ann_bh  = bh_rets.mean() * 252 * 100

    cumr_s = result["total_ret"].cumsum()
    cumr_b = bh_rets.fillna(0).cumsum()
    dd_s   = (cumr_s - cumr_s.cummax()).min() * 100
    dd_b   = (cumr_b - cumr_b.cummax()).min() * 100

    avg_inv  = result["invested"].mean() * 100
    tc_drag  = (result["port_gross"] - result["port_net"]).mean() * 252 * 100
    mean_rf  = result["rf_daily"].mean() * 252 * 100

    print(f"\n{'':25} {'Ann Ret':>10} {'Sharpe(xrf)':>12} {'Max DD':>8}")
    print(f"  {'Strategy (net TC)':<25} {ann_ret:>9.2f}% {sr_strat:>11.3f} {dd_s:>7.2f}%")
    print(f"  {'EW B&H':<25} {ann_bh:>9.2f}% {sr_bh:>11.3f} {dd_b:>7.2f}%")
    print(f"  Mean rf (ann): {mean_rf:.2f}%")
    print(f"\n  Avg weight invested: {avg_inv:.1f}%  TC drag: {tc_drag:.2f}% ann")

    # Per-pair allocation and VRP stats
    w_daily = weights.reindex(result.index, method="ffill").fillna(0.0)
    print(f"\n  {'Pair':<6} {'avg wt%':>8} {'avg VRP':>9} "
          f"{'avg rho':>9} {'rho<thr%':>10} {'start':>12}")
    for etf, df in pairs_data.items():
        df_al   = df.reindex(result.index)
        avg_w   = w_daily[etf].mean() * 100 if etf in w_daily.columns else 0.0
        avg_vrp = df_al["vrp"].mean()
        avg_rho = df_al["rho"].mean()
        rho_pct = (df_al["rho"] < RHO_THRESHOLD).mean() * 100
        start   = str(df.index[0].date())
        print(f"  {etf:<6} {avg_w:>7.1f}%  {avg_vrp:>8.1f}  "
              f"{avg_rho:>8.3f}  {rho_pct:>9.1f}%  {start:>12}")

    return sr_strat


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def section_signal():
    pairs_data, rf_s = fetch_data()
    if not pairs_data:
        print("No valid pairs.")
        return

    print("\nComputing VRP weights...")
    weights = compute_weights(pairs_data)

    print("Running backtest...")
    result = run_backtest(pairs_data, weights)

    print("\n=== RESULTS ===")
    _print_stats(result, pairs_data, weights)


def section_sweep():
    global RV_WINDOW, REBAL_STEP
    pairs_data, _ = fetch_data()
    print("\n=== SWEEP: RV_WINDOW x REBAL_STEP ===")
    print(f"{'RV_win':>7} {'Rebal':>7} {'SR(xrf)':>9} {'Ann Ret':>9} {'DD%':>8}")
    print("-" * 48)
    orig_rv, orig_rs = RV_WINDOW, REBAL_STEP
    best = (-999, None)

    # Recompute RV and VRP for each RV_WINDOW setting
    for rv_win in [10, 20, 40]:
        # Recompute rv/vrp for this window
        local_data = {}
        for etf, df_orig in pairs_data.items():
            df = df_orig.copy()
            df["rv"]  = df["log_return"].rolling(rv_win).std() * _ANN * 100
            df["vrp"] = df["vol"] - df["rv"]
            df = df.dropna()
            local_data[etf] = df

        for rs in [5, 10, 21]:
            RV_WINDOW  = rv_win
            REBAL_STEP = rs
            weights = compute_weights(local_data)
            result  = run_backtest(local_data, weights)
            port_excess = result["total_ret"] - result["rf_daily"]
            sr = (port_excess.mean() / port_excess.std() * _ANN
                  if port_excess.std() > 0 else 0.0)
            ann_ret = result["total_ret"].mean() * 252 * 100
            cumr    = result["total_ret"].cumsum()
            dd      = (cumr - cumr.cummax()).min() * 100
            flag    = " <--" if sr > best[0] else ""
            if sr > best[0]:
                best = (sr, (rv_win, rs))
            print(f"  {rv_win:>6}  {rs:>6}   {sr:>7.3f}  {ann_ret:>8.2f}%  {dd:>7.2f}%{flag}")

    RV_WINDOW, REBAL_STEP = orig_rv, orig_rs
    if best[1]:
        print(f"\n  Best: RV_WINDOW={best[1][0]}, REBAL_STEP={best[1][1]}, SR={best[0]:.3f}")


SECTIONS = {
    "signal": section_signal,
    "sweep":  section_sweep,
}

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "signal"
    if arg in SECTIONS:
        SECTIONS[arg]()
    else:
        print(f"Unknown section: {arg}. Choose: {list(SECTIONS.keys())}")
        sys.exit(1)
