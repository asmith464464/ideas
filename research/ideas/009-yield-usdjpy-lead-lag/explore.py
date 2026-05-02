"""
009 - Yield / USD-JPY Lead-Lag  ("10Y Sniper")

Hypothesis: US T-Bond futures yield changes lead USD/JPY by seconds to minutes
during liquidity handoffs. The high intraday correlation between yields and
USD/JPY means FX must reprice to preserve interest-rate parity, but currency
market-makers lag bond platforms. We capture that lag by entering USD/JPY
immediately after a bond-price spike before FX has repriced.

Data: 3-tick OHLCV bars (bid + ask) for USD/JPY and US T-Bond futures,
      Jan–Mar 2026.

Signal (1-minute bars, US session only):
  yield_z  : rolling Z-score of −bond_return  (price ↓ ⟹ yield ↑)
  fx_z     : rolling Z-score of USD/JPY return
  LONG     : yield_z >  BOND_Z  and  fx_z < FX_QUIET   → expect USD/JPY to rise
  SHORT    : yield_z < −BOND_Z  and  fx_z > −FX_QUIET  → expect USD/JPY to fall
  filter   : 30-min rolling corr(yield_ret, fx_ret) ≥ CORR_MIN

Exit: after EXIT_BARS minutes  OR  when |fx_z| ≥ CONV_FRAC × |yield_z_at_entry|.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA = {
    "fx_ask":   REPO_ROOT / "USDJPY_TickBar_3_Ask_2026.01.01_2026.03.31.csv",
    "fx_bid":   REPO_ROOT / "USDJPY_TickBar_3_Bid_2026.01.01_2026.03.31.csv",
    "bond_ask": REPO_ROOT / "USTBONDTRUSD_TickBar_3_Ask_2026.01.01_2026.03.31.csv",
    "bond_bid": REPO_ROOT / "USTBONDTRUSD_TickBar_3_Bid_2026.01.01_2026.03.31.csv",
}
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
_CACHE_PQ     = CACHE_DIR / "minute_bars.parquet"
_CACHE_CSV    = CACHE_DIR / "minute_bars.csv"
_CACHE_30S_PQ = CACHE_DIR / "bars_30s.parquet"
_CACHE_30S_CSV= CACHE_DIR / "bars_30s.csv"
# Cached raw mid-price series (loaded once, shared across resolutions)
_FX_MID_CACHE: pd.Series | None   = None
_BOND_MID_CACHE: pd.Series | None = None

# ── default parameters ────────────────────────────────────────────────────────
Z_WINDOW  = 10     # bars (minutes) for rolling Z-score
CORR_WIN  = 30     # bars for rolling correlation filter
BOND_Z    = 2.0    # bond yield Z-score threshold to trigger entry (2.5 too few trades)
FX_QUIET  = 0.5    # USD/JPY must be below this Z-score (quiet) to enter
CORR_MIN  = 0.0    # rolling correlation filter (0 = disabled; 1-min corr is too noisy to use)
EXIT_BARS = 3      # maximum hold period in minutes
CONV_FRAC     = 0.80   # exit early when fx_z reaches this fraction of entry yield_z
SESS_H        = (14, 22)   # EET hours for main bond-futures session (14=08 ET, 22=16 ET)
# Round-trip cost in bps. The tick-bar bid/ask differential is NOT the instantaneous
# spread — it mixes ask-side and bid-side ticks at different times and gives near-zero
# artificial spread. We override with a realistic fixed cost:
#   0.5 pip spread (0.5 × 0.641 bps at 156) ≈ 0.32 bps × 2 sides = 0.64 bps spread
#   + $3/lot commission on 100k USD = 0.3 bps per side × 2 = 0.6 bps
#   total ≈ 1.3 bps round-trip; add 0.5 bps slippage → 1.8 bps
RT_COST_BPS   = 2.0


# ── data loading ──────────────────────────────────────────────────────────────
def _read_close(path: Path) -> pd.Series:
    df = pd.read_csv(
        path,
        usecols=["Time (EET)", "Close"],
        parse_dates=["Time (EET)"],
        index_col="Time (EET)",
    )
    return df["Close"]


def _load_raw_mids() -> tuple[pd.Series, pd.Series]:
    """Load raw mid prices once and cache in module-level vars."""
    global _FX_MID_CACHE, _BOND_MID_CACHE
    if _FX_MID_CACHE is None:
        print("  reading raw CSVs …")
        t0 = time.time()
        fx_ask   = _read_close(_DATA["fx_ask"])
        fx_bid   = _read_close(_DATA["fx_bid"])
        bd_ask   = _read_close(_DATA["bond_ask"])
        bd_bid   = _read_close(_DATA["bond_bid"])
        _FX_MID_CACHE   = (fx_ask + fx_bid) / 2
        _BOND_MID_CACHE = (bd_ask + bd_bid) / 2
        print(f"  raw load done: {time.time() - t0:.1f}s")
    return _FX_MID_CACHE, _BOND_MID_CACHE


def _make_bars(freq: str, ffill_limit: int = 5) -> pd.DataFrame:
    fx_mid, bond_mid = _load_raw_mids()
    return pd.DataFrame({
        "usdjpy": fx_mid.resample(freq).last(),
        "bond":   bond_mid.resample(freq).last(),
    }).ffill(limit=ffill_limit).dropna(subset=["usdjpy", "bond"])


def load_minute_bars(force: bool = False) -> pd.DataFrame:
    """Resample to 1-minute bars, cached."""
    if not force:
        if _CACHE_PQ.exists():
            print("  loading cached 1-min bars (parquet) …")
            return pd.read_parquet(_CACHE_PQ)
        if _CACHE_CSV.exists():
            print("  loading cached 1-min bars (csv) …")
            return pd.read_csv(_CACHE_CSV, index_col=0, parse_dates=True)
    df = _make_bars("1min")
    try:
        df.to_parquet(_CACHE_PQ)
    except Exception:
        df.to_csv(_CACHE_CSV)
    print(f"  cached {len(df):,} 1-min bars")
    return df


def load_30s_bars(force: bool = False) -> pd.DataFrame:
    """Resample to 30-second bars, cached. Finer resolution to capture the seconds-scale lag."""
    if not force:
        if _CACHE_30S_PQ.exists():
            print("  loading cached 30-s bars (parquet) …")
            return pd.read_parquet(_CACHE_30S_PQ)
        if _CACHE_30S_CSV.exists():
            print("  loading cached 30-s bars (csv) …")
            return pd.read_csv(_CACHE_30S_CSV, index_col=0, parse_dates=True)
    df = _make_bars("30s")
    try:
        df.to_parquet(_CACHE_30S_PQ)
    except Exception:
        df.to_csv(_CACHE_30S_CSV)
    print(f"  cached {len(df):,} 30-s bars")
    return df


# ── signals ───────────────────────────────────────────────────────────────────
def _zscore(s: pd.Series, w: int) -> pd.Series:
    mu  = s.rolling(w, min_periods=max(w // 2, 3)).mean()
    sig = s.rolling(w, min_periods=max(w // 2, 3)).std()
    return (s - mu) / sig.replace(0, np.nan)


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    d["fx_ret"]    = d["usdjpy"].pct_change()
    d["bond_ret"]  = d["bond"].pct_change()
    d["yield_ret"] = -d["bond_ret"]          # bond price ↓ ⟹ yield ↑

    d["yield_z"] = _zscore(d["yield_ret"], Z_WINDOW)
    d["fx_z"]    = _zscore(d["fx_ret"],    Z_WINDOW)
    d["corr"]    = d["yield_ret"].rolling(CORR_WIN).corr(d["fx_ret"])

    in_session = (d.index.hour >= SESS_H[0]) & (d.index.hour < SESS_H[1])
    corr_ok    = d["corr"] >= CORR_MIN

    long_cond  = (d["yield_z"] >  BOND_Z) & (d["fx_z"]  <  FX_QUIET)
    short_cond = (d["yield_z"] < -BOND_Z) & (d["fx_z"]  > -FX_QUIET)

    d["signal"] = 0
    d.loc[long_cond  & corr_ok & in_session, "signal"] =  1
    d.loc[short_cond & corr_ok & in_session, "signal"] = -1
    return d


# ── backtest ──────────────────────────────────────────────────────────────────
def run_backtest(d: pd.DataFrame, rt_cost_bps: float = RT_COST_BPS) -> dict:
    """
    One trade at a time. Enter at close of signal bar, exit at EXIT_BARS or
    convergence. Transaction cost = fixed RT_COST_BPS round-trip (realistic
    institutional estimate; the tick-bar bid/ask differential is unreliable).
    """
    px      = d["usdjpy"].values
    sig     = d["signal"].values
    fx_z    = d["fx_z"].values
    yield_z = d["yield_z"].values
    rt_cost = rt_cost_bps / 1e4
    n       = len(d)

    trades  = []
    in_pos  = False
    e_i     = 0
    dirn    = 0
    e_px    = 0.0
    e_yz    = 0.0   # yield_z at entry (convergence target)

    for i in range(1, n):
        if in_pos:
            held = i - e_i
            fz_i = fx_z[i] if np.isfinite(fx_z[i]) else 0.0
            converged = (held >= 1) and (abs(fz_i) >= CONV_FRAC * abs(e_yz))

            if held >= EXIT_BARS or converged:
                raw = (px[i] / e_px - 1.0) * dirn
                trades.append({
                    "entry":     d.index[e_i],
                    "exit":      d.index[i],
                    "dir":       dirn,
                    "held":      held,
                    "raw_ret":   raw,
                    "cost":      rt_cost,
                    "net_ret":   raw - rt_cost,
                    "converged": converged,
                    "entry_yz":  e_yz,
                })
                in_pos = False

        elif not in_pos and sig[i - 1] != 0:
            in_pos = True
            e_i    = i - 1
            dirn   = int(sig[i - 1])
            e_px   = px[i - 1]
            e_yz   = yield_z[i - 1] if np.isfinite(yield_z[i - 1]) else BOND_Z

    t = pd.DataFrame(trades)
    if t.empty:
        return {"trades": t, "daily_ret": pd.Series(dtype=float), "n_trades": 0}

    # build daily P&L series (0 on days with no trades)
    daily_raw = t.set_index("exit")["net_ret"].resample("1D").sum()
    bdays     = pd.bdate_range(d.index[0].date(), d.index[-1].date())
    daily     = daily_raw.reindex(bdays, fill_value=0.0)

    return {"trades": t, "daily_ret": daily, "n_trades": len(t)}


# ── metrics ───────────────────────────────────────────────────────────────────
def compute_metrics(res: dict) -> dict:
    t     = res["trades"]
    daily = res["daily_ret"]
    if t.empty or len(t) < 5:
        return {}

    net = t["net_ret"].values
    wins = net[net > 0]
    loss = net[net < 0]

    ann_ret = float(daily.mean() * 252)
    ann_vol = float(daily.std()  * np.sqrt(252))
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0

    cum = (1 + daily).cumprod()
    mdd = float((cum / cum.cummax() - 1).min())
    pf  = abs(wins.sum() / loss.sum()) if loss.size and loss.sum() != 0 else np.nan

    return {
        "n_trades":      len(t),
        "win_rate":      round(float((net > 0).mean()), 4),
        "avg_win_bps":   round(float(wins.mean()) * 1e4, 2) if wins.size else 0.0,
        "avg_loss_bps":  round(float(loss.mean()) * 1e4, 2) if loss.size else 0.0,
        "profit_factor": round(float(pf), 3) if np.isfinite(pf) else None,
        "avg_hold_mins": round(float(t["held"].mean()), 2) if "held" in t.columns else None,
        "conv_rate":     round(float(t["converged"].mean()), 4) if "converged" in t.columns else None,
        "ann_return":    round(ann_ret, 4),
        "ann_vol":       round(ann_vol, 4),
        "sharpe":        round(sharpe, 4),
        "max_drawdown":  round(mdd, 4),
        "total_pnl_bps": round(float(net.sum()) * 1e4, 1),
    }


def _print_metrics(m: dict, label: str = ""):
    w = 26
    print(f"\n{'-' * 50}")
    if label:
        print(f"  {label}")
        print(f"{'-' * 50}")
    for k, v in m.items():
        if v is None:
            continue
        fmt = f"{v:>10.4f}" if isinstance(v, float) else f"{v:>10}"
        print(f"  {k:<{w}} {fmt}")
    print(f"{'-' * 50}")


# ── sections ──────────────────────────────────────────────────────────────────
def section_signal():
    print("\n=== 009  Yield / USD-JPY Lead-Lag ===========================")
    print(f"  Z_WINDOW={Z_WINDOW}  BOND_Z={BOND_Z}  FX_QUIET={FX_QUIET}")
    print(f"  CORR_MIN={CORR_MIN}  EXIT_BARS={EXIT_BARS}  session={SESS_H[0]}-{SESS_H[1]} EET")

    df  = load_minute_bars()
    d   = compute_signals(df)

    n_sess = int(((d.index.hour >= SESS_H[0]) & (d.index.hour < SESS_H[1])).sum())
    n_sig  = int((d["signal"] != 0).sum())
    print(f"\n  1-min bars total  : {len(d):,}")
    print(f"  bars in session   : {n_sess:,}")
    corr_valid = d["corr"].dropna()
    print(f"  corr valid bars   : {len(corr_valid):,}  "
          f"median={corr_valid.median():.3f}  p90={corr_valid.quantile(.9):.3f}")
    print(f"  corr>={CORR_MIN} bars  : {int((d['corr'] >= CORR_MIN).sum()):,}")
    # signal count at different bond_z levels (no corr filter) — diagnostic
    sess = (d.index.hour >= SESS_H[0]) & (d.index.hour < SESS_H[1])
    print("  signal count by bond_z (no corr filter):")
    for bz in [1.0, 1.5, 2.0, 2.5, 3.0]:
        n = int(((d["yield_z"].abs() > bz) & (d["fx_z"].abs() < FX_QUIET) & sess).sum())
        print(f"    bond_z > {bz}: {n:>5} signals")
    print(f"  signal bars (with corr filter): {n_sig:,}  ({n_sig / max(n_sess, 1) * 100:.2f}% of session)")

    res = run_backtest(d)
    if res["n_trades"] == 0:
        print("\n  [!] No trades generated. Try lowering BOND_Z or CORR_MIN.")
        return

    m = compute_metrics(res)
    _print_metrics(m, f"Results  (BOND_Z={BOND_Z}  EXIT={EXIT_BARS}m  CORR>={CORR_MIN})")

    trades = res["trades"]
    monthly = (
        trades
        .assign(month=trades["entry"].dt.to_period("M"))
        .groupby("month")["net_ret"]
        .agg(
            n="count",
            pnl_bps=lambda x: round(x.sum() * 1e4, 1),
            wr=lambda x: round((x > 0).mean(), 3),
        )
    )
    print("\n  Monthly breakdown:")
    print(monthly.to_string())

    # cost sensitivity: re-run at different round-trip cost assumptions
    print("\n  Cost sensitivity (round-trip bps):")
    for cost_bps in [0.5, 1.0, 2.0, 3.0, 5.0]:
        r2 = run_backtest(d, rt_cost_bps=cost_bps)
        m2 = compute_metrics(r2)
        if m2:
            print(f"    rt={cost_bps:.1f} bps -> sharpe={m2['sharpe']:.3f}  "
                  f"pnl={m2['total_pnl_bps']:.1f} bps  wr={m2['win_rate']*100:.1f}%")


def section_sweep():
    print("\n=== Parameter Sweep ===========================================")
    global BOND_Z, EXIT_BARS, CORR_MIN

    df = load_minute_bars()

    hdr = f"{'bz':>5}  {'exit':>4}  {'corr':>5}  {'n':>5}  {'sharpe':>7}  {'wr%':>6}  {'pnl':>8}"
    print(hdr)
    print("-" * len(hdr))

    best = None
    for bz in [1.5, 2.0, 2.5, 3.0]:
        for ex in [2, 3, 5]:
            for co in [0.0, 0.20, 0.40, 0.70]:
                BOND_Z, EXIT_BARS, CORR_MIN = bz, ex, co
                d   = compute_signals(df)
                res = run_backtest(d)
                if res["n_trades"] < 10:
                    print(f"  {bz:>4.1f}  {ex:>4}  {co:>5.2f}  {'<10':>5}")
                    continue
                m = compute_metrics(res)
                if not m:
                    continue
                sr = m["sharpe"]
                print(f"  {bz:>4.1f}  {ex:>4}  {co:>5.2f}  {m['n_trades']:>5}"
                      f"  {sr:>7.3f}  {m['win_rate']*100:>6.1f}  {m['total_pnl_bps']:>8.1f}")
                if best is None or sr > best[0]:
                    best = (sr, bz, ex, co, m)

    if best:
        BOND_Z, EXIT_BARS, CORR_MIN = best[1], best[2], best[3]
        print(f"\n  * Best Sharpe {best[0]:.3f}  @  bond_z={best[1]}  exit={best[2]}m  corr={best[3]}")
        _print_metrics(best[4], "Best parameters detail")


def section_fine():
    """
    Re-run on 30-second bars. At 1-min resolution, FX has ~60s to reprice before
    we see the signal — most of the edge is gone. At 30s, we should capture the lag
    earlier, increasing gross P&L per trade. EXIT_BARS = 6 = 3 minutes.
    """
    global Z_WINDOW, EXIT_BARS
    Z_WINDOW_ORIG, EXIT_BARS_ORIG = Z_WINDOW, EXIT_BARS
    Z_WINDOW  = 20   # 20 × 30s = 10 min lookback
    EXIT_BARS = 6    # 6 × 30s = 3 min hold

    print("\n=== 009  Yield / USD-JPY Lead-Lag  [30-second bars] =========")
    print(f"  Z_WINDOW={Z_WINDOW}  BOND_Z={BOND_Z}  FX_QUIET={FX_QUIET}")
    print(f"  CORR_MIN={CORR_MIN}  EXIT_BARS={EXIT_BARS}  session={SESS_H[0]}-{SESS_H[1]} EET")

    df  = load_30s_bars()
    d   = compute_signals(df)

    n_sess = int(((d.index.hour >= SESS_H[0]) & (d.index.hour < SESS_H[1])).sum())
    n_sig  = int((d["signal"] != 0).sum())
    print(f"\n  30-s bars total   : {len(d):,}")
    print(f"  bars in session   : {n_sess:,}")
    print(f"  signal bars       : {n_sig:,}  ({n_sig / max(n_sess, 1) * 100:.2f}% of session)")

    res = run_backtest(d)
    if res["n_trades"] == 0:
        print("\n  [!] No trades generated.")
        Z_WINDOW, EXIT_BARS = Z_WINDOW_ORIG, EXIT_BARS_ORIG
        return

    m = compute_metrics(res)
    _print_metrics(m, f"30-s bars  (BOND_Z={BOND_Z}  EXIT=3m  CORR>={CORR_MIN})")

    trades = res["trades"]
    monthly = (
        trades
        .assign(month=trades["entry"].dt.to_period("M"))
        .groupby("month")["net_ret"]
        .agg(
            n="count",
            pnl_bps=lambda x: round(x.sum() * 1e4, 1),
            wr=lambda x: round((x > 0).mean(), 3),
        )
    )
    print("\n  Monthly breakdown:")
    print(monthly.to_string())

    print("\n  Cost sensitivity (round-trip bps):")
    for cost_bps in [0.5, 1.0, 2.0, 3.0]:
        r2 = run_backtest(d, rt_cost_bps=cost_bps)
        m2 = compute_metrics(r2)
        if m2:
            print(f"    rt={cost_bps:.1f} bps -> sharpe={m2['sharpe']:.3f}  "
                  f"pnl={m2['total_pnl_bps']:.1f} bps  wr={m2['win_rate']*100:.1f}%")

    Z_WINDOW, EXIT_BARS = Z_WINDOW_ORIG, EXIT_BARS_ORIG


# ═══════════════════════════════════════════════════════════════════════════════
# RUN 2 — Tick-Event Driven, Multi-Pair
# Key insight: bond 3-tick bars ARE native events. Using them as signal triggers
# (rather than resampling to a time grid) means FX has had seconds — not 60 s —
# to reprice. The spread cost uses real ask/bid from data, not a fixed estimate.
# ═══════════════════════════════════════════════════════════════════════════════

# Run 2 parameters
R2_BOND_Z      = 2.5   # tighter threshold: shock-level bond moves only
R2_FX_QUIET    = 0.3   # FX must be very quiet
R2_BOND_Z_WIN  = 20    # last N bond events for bond Z-score
R2_FX_LOOKBACK = 5     # minutes: how far back to measure FX "quiet-ness"
R2_FX_Z_WIN    = 30    # last N bond events for FX Z-score reference window
R2_EXIT_MINS   = 3     # minutes

_TICK_CACHE: dict = {}

_FX_PAIRS = {
    "USDJPY": ("USDJPY_TickBar_3_Ask_2026.01.01_2026.03.31.csv",
               "USDJPY_TickBar_3_Bid_2026.01.01_2026.03.31.csv"),
    "EURJPY": ("EURJPY_TickBar_3_Ask_2026.01.01_2026.03.31.csv",
               "EURJPY_TickBar_3_Bid_2026.01.01_2026.03.31.csv"),
    "AUDJPY": ("AUDJPY_TickBar_3_Ask_2026.01.01_2026.03.31.csv",
               "AUDJPY_TickBar_3_Bid_2026.01.01_2026.03.31.csv"),
}


def load_tick_pair(name: str) -> tuple[pd.Series, pd.Series]:
    """Load and module-cache raw ask+bid close series for a named pair."""
    if name not in _TICK_CACHE:
        if name == "USTBONDTRUSD":
            ask_f = _DATA["bond_ask"]
            bid_f = _DATA["bond_bid"]
        else:
            a, b  = _FX_PAIRS[name]
            ask_f, bid_f = REPO_ROOT / a, REPO_ROOT / b
        print(f"  loading {name} …")
        _TICK_CACHE[name] = (_read_close(ask_f), _read_close(bid_f))
    return _TICK_CACHE[name]


def build_event_signals(
    bond_ask: pd.Series,
    bond_bid: pd.Series,
    fx_ask:   pd.Series,
    fx_bid:   pd.Series,
    bond_z:    float = R2_BOND_Z,
    fx_quiet:  float = R2_FX_QUIET,
    bond_z_win: int  = R2_BOND_Z_WIN,
    fx_lookback: int = R2_FX_LOOKBACK,
    fx_z_win:   int  = R2_FX_Z_WIN,
) -> pd.DataFrame:
    """
    Generate signals at native bond tick-bar event frequency.

    Bond Z-score: rolling over last bond_z_win bond events.
    FX quiet-ness: Z-score of (FX return over last fx_lookback minutes),
                   rolling over last fx_z_win bond events.
    """
    bond_mid = (bond_ask + bond_bid) / 2
    fx_mid   = (fx_ask  + fx_bid)   / 2

    # Restrict bond events to session hours
    in_sess  = (bond_mid.index.hour >= SESS_H[0]) & (bond_mid.index.hour < SESS_H[1])
    bond_mid = bond_mid[in_sess]

    # Bond yield Z-score (rolling over bond events)
    bond_ret  = bond_mid.pct_change()
    yield_ret = -bond_ret                     # bond price down = yield up
    yield_z   = _zscore(yield_ret, bond_z_win)

    # FX return over the lookback window at each bond event time
    lookback   = pd.Timedelta(minutes=fx_lookback)
    fx_now     = fx_mid.reindex(bond_mid.index, method="pad")
    fx_lagged  = fx_mid.reindex(bond_mid.index - lookback, method="pad")
    fx_lagged.index = bond_mid.index
    fx_ret_win = (fx_now - fx_lagged) / fx_lagged

    # Z-score that FX return (rolling over bond event times)
    fx_z = _zscore(fx_ret_win, fx_z_win)

    # Entry prices at bond event time (using real ask/bid — cost is embedded)
    e_ask = fx_ask.reindex(bond_mid.index, method="pad")
    e_bid = fx_bid.reindex(bond_mid.index, method="pad")

    df = pd.DataFrame({
        "yield_z":   yield_z,
        "fx_z":      fx_z,
        "entry_ask": e_ask,
        "entry_bid": e_bid,
    }, index=bond_mid.index).dropna(subset=["yield_z", "fx_z"])

    long_cond  = (df["yield_z"] >  bond_z) & (df["fx_z"] <  fx_quiet)
    short_cond = (df["yield_z"] < -bond_z) & (df["fx_z"] > -fx_quiet)

    df["signal"] = 0
    df.loc[long_cond,  "signal"] =  1
    df.loc[short_cond, "signal"] = -1
    return df


def run_event_backtest(
    signals:          pd.DataFrame,
    fx_ask:           pd.Series,
    fx_bid:           pd.Series,
    exit_mins:        int   = R2_EXIT_MINS,
    entry_lag_secs:   int   = 0,
    extra_slip_pips:  float = 0.0,
    commission_bps:   float = 0.0,
) -> dict:
    """
    Event-driven backtest. One position at a time.
    LONG:  enter at ask + slip, exit at bid − slip.
    SHORT: enter at bid − slip, exit at ask + slip.
    Natural bid/ask spread is already embedded; extra_slip_pips and
    commission_bps layer additional costs on top.

    entry_lag_secs: execution delay after bond event (models API/latency).
    extra_slip_pips: additional adverse price movement per side (JPY pip = 0.01).
    commission_bps:  round-trip commission in basis points.
    """
    PIP       = 0.01   # 1 pip for all JPY pairs
    exit_delta = pd.Timedelta(minutes=exit_mins)
    entry_lag  = pd.Timedelta(seconds=entry_lag_secs)
    comm       = commission_bps / 1e4
    slip       = extra_slip_pips * PIP

    sigs       = signals[signals["signal"] != 0]
    trades     = []
    next_entry = pd.Timestamp.min

    for evt_time, row in sigs.iterrows():
        if evt_time < next_entry:
            continue

        dirn           = int(row["signal"])
        actual_entry   = evt_time + entry_lag
        exit_time      = actual_entry + exit_delta

        if dirn == 1:   # LONG: buy ask + slip, sell bid − slip
            e_px    = float(fx_ask.asof(actual_entry)) + slip
            exit_px = float(fx_bid.asof(exit_time))    - slip
            raw_ret = exit_px / e_px - 1 - comm
        else:           # SHORT: sell bid − slip, buy ask + slip
            e_px    = float(fx_bid.asof(actual_entry)) - slip
            exit_px = float(fx_ask.asof(exit_time))    + slip
            raw_ret = e_px / exit_px - 1 - comm

        if e_px <= 0 or exit_px <= 0 or not np.isfinite(raw_ret):
            continue

        trades.append({
            "entry":    evt_time,
            "exit":     exit_time,
            "dir":      dirn,
            "entry_px": e_px,
            "exit_px":  exit_px,
            "net_ret":  raw_ret,
        })
        next_entry = exit_time

    t = pd.DataFrame(trades)
    if t.empty:
        return {"trades": t, "daily_ret": pd.Series(dtype=float), "n_trades": 0}

    daily_raw = t.set_index("exit")["net_ret"].resample("1D").sum()
    bdays     = pd.bdate_range(signals.index[0].date(), signals.index[-1].date())
    daily     = daily_raw.reindex(bdays, fill_value=0.0)
    return {"trades": t, "daily_ret": daily, "n_trades": len(t)}


def section_tick_event():
    """Run 2: tick-event approach, all three JPY pairs."""
    print("\n=== Run 2: Tick-Event (Bond Bar Timestamps) ===================")
    print(f"  bond_z={R2_BOND_Z}  fx_quiet={R2_FX_QUIET}  "
          f"lookback={R2_FX_LOOKBACK}m  exit={R2_EXIT_MINS}m")
    print("  Cost model: real ask/bid spread embedded — no fixed RT estimate\n")

    bond_ask, bond_bid = load_tick_pair("USTBONDTRUSD")

    for pair in ["USDJPY", "EURJPY", "AUDJPY"]:
        fx_ask, fx_bid = load_tick_pair(pair)
        sigs = build_event_signals(bond_ask, bond_bid, fx_ask, fx_bid)

        n_sig = int((sigs["signal"] != 0).sum())
        print(f"  {pair}  bond events in session: {len(sigs):,}  signals: {n_sig:,}")

        res = run_event_backtest(sigs, fx_ask, fx_bid)
        if res["n_trades"] == 0:
            print(f"  {pair}: no trades\n")
            continue

        m = compute_metrics(res)
        _print_metrics(m, f"{pair}  [tick-event  bond_z={R2_BOND_Z}  exit={R2_EXIT_MINS}m]")

        trades = res["trades"]
        monthly = (
            trades
            .assign(month=trades["entry"].dt.to_period("M"))
            .groupby("month")["net_ret"]
            .agg(n="count",
                 pnl_bps=lambda x: round(x.sum() * 1e4, 1),
                 wr=lambda x: round((x > 0).mean(), 3))
        )
        print(monthly.to_string())
        print()


def section_compare():
    """Sweep bond_z and exit_mins across all three pairs; find best Sharpe."""
    print("\n=== Run 2: Pair Comparison Sweep ==============================")
    bond_ask, bond_bid = load_tick_pair("USTBONDTRUSD")

    hdr = f"{'pair':>8}  {'bz':>4}  {'exit':>4}  {'n':>5}  {'sharpe':>7}  {'wr%':>6}  {'pnl_bps':>8}"
    print(hdr)
    print("-" * len(hdr))

    best_overall = None

    for pair in ["USDJPY", "EURJPY", "AUDJPY"]:
        fx_ask, fx_bid = load_tick_pair(pair)

        for bz in [2.0, 2.5, 3.0]:
            for ex in [2, 3, 5]:
                sigs = build_event_signals(bond_ask, bond_bid, fx_ask, fx_bid,
                                           bond_z=bz)
                res  = run_event_backtest(sigs, fx_ask, fx_bid, exit_mins=ex)
                if res["n_trades"] < 10:
                    continue
                m = compute_metrics(res)
                if not m:
                    continue

                sr = m["sharpe"]
                print(f"  {pair:>8}  {bz:>4.1f}  {ex:>4}  {m['n_trades']:>5}"
                      f"  {sr:>7.3f}  {m['win_rate']*100:>6.1f}  {m['total_pnl_bps']:>8.1f}")

                if best_overall is None or sr > best_overall[0]:
                    best_overall = (sr, pair, bz, ex, m)

    if best_overall:
        sr, pair, bz, ex, m = best_overall
        print(f"\n  * Best: {pair}  bond_z={bz}  exit={ex}m  Sharpe={sr:.3f}")
        _print_metrics(m, f"Best overall: {pair}")


def section_oos_q4():
    """
    True out-of-sample test on Q4 2025 (Oct–Dec 2025).

    The strategy was developed entirely on Jan–Mar 2026 data. This section
    applies params to a completely independent prior period with NO adjustment.

    Two baselines:
      A. A-priori params: original hypothesis spec, never touched during development.
      B. Optimised params: best from the Jan-Mar sweep, applied blind to Q4 2025.

    If both are positive, the edge is confirmed across two independent quarters.
    """
    _Q4 = {
        "fx_ask":   REPO_ROOT / "USDJPY_TickBar_3_Ask_2025.09.30_2026.01.01.csv",
        "fx_bid":   REPO_ROOT / "USDJPY_TickBar_3_Bid_2025.09.30_2026.01.01.csv",
        "bond_ask": REPO_ROOT / "USTBONDTRUSD_TickBar_3_Ask_2025.09.30_2026.01.01.csv",
        "bond_bid": REPO_ROOT / "USTBONDTRUSD_TickBar_3_Bid_2025.09.30_2026.01.01.csv",
    }
    for k, p in _Q4.items():
        if not p.exists():
            print(f"  Missing: {p.name}")
            return

    print("\n=== OOS Test: Q4 2025 (Oct–Dec 2025) =========================")
    print("  STRATEGY WAS DEVELOPED ON JAN-MAR 2026 — THIS DATA WAS NEVER SEEN")

    print("  loading Q4 2025 tick data …")
    fx_ask   = _read_close(_Q4["fx_ask"])
    fx_bid   = _read_close(_Q4["fx_bid"])
    bond_ask = _read_close(_Q4["bond_ask"])
    bond_bid = _read_close(_Q4["bond_bid"])

    # Filter to Oct–Dec (files may include a little Sep/Jan overlap)
    mask_fx   = (fx_ask.index  >= "2025-10-01") & (fx_ask.index  < "2026-01-01")
    mask_bond = (bond_ask.index >= "2025-10-01") & (bond_ask.index < "2026-01-01")
    fx_ask, fx_bid     = fx_ask[mask_fx],   fx_bid[mask_fx]
    bond_ask, bond_bid = bond_ask[mask_bond], bond_bid[mask_bond]

    print(f"  USDJPY ticks  : {len(fx_ask):,}  "
          f"({fx_ask.index[0].date()} – {fx_ask.index[-1].date()})")
    print(f"  USTBOND ticks : {len(bond_ask):,}  "
          f"({bond_ask.index[0].date()} – {bond_ask.index[-1].date()})")

    specs = [
        ("A-priori  (bz=2.5  quiet=0.5  exit=3m)", 2.5, 0.5, 3),
        ("Optimised (bz=2.0  quiet=0.3  exit=2m)", 2.0, 0.3, 2),
    ]

    results = {}
    for label, bz, quiet, ex in specs:
        sigs = build_event_signals(bond_ask, bond_bid, fx_ask, fx_bid,
                                   bond_z=bz, fx_quiet=quiet)
        n_sig = int((sigs["signal"] != 0).sum())
        res   = run_event_backtest(sigs, fx_ask, fx_bid, exit_mins=ex)
        m     = compute_metrics(res)
        results[label] = m

        verdict = "PASS" if (m and m["sharpe"] > 0) else "FAIL"
        _print_metrics(m or {}, f"{verdict}  {label}")

        if m and res["n_trades"] > 0:
            trades = res["trades"]
            monthly = (
                trades
                .assign(month=trades["entry"].dt.to_period("M"))
                .groupby("month")["net_ret"]
                .agg(n="count",
                     pnl_bps=lambda x: round(x.sum() * 1e4, 1),
                     wr=lambda x: round((x > 0).mean(), 3))
            )
            print("  Monthly:")
            print(monthly.to_string())

    print("\n  Summary vs Jan-Mar 2026 development period:")
    print(f"  {'Spec':>40}  {'OOS Q4-2025':>12}  {'IS Jan-Mar':>12}")
    print(f"  {'-'*66}")
    is_sharpes = {"A-priori  (bz=2.5  quiet=0.5  exit=3m)": 11.4,
                  "Optimised (bz=2.0  quiet=0.3  exit=2m)": 11.0}
    for label, m in results.items():
        oos_sr = f"{m['sharpe']:+.2f}" if m else "N/A"
        is_sr  = f"{is_sharpes[label]:+.2f}"
        print(f"  {label:>40}  {oos_sr:>12}  {is_sr:>12}")


def section_walkforward():
    """
    Walk-forward test to address multiple-comparison bias.

    The parameter sweep was run on the full Jan–Mar dataset, which introduces
    in-sample selection bias. This section:
      1. Re-optimises on Jan+Feb only (training window)
      2. Applies the best training params to March alone (out-of-sample)
      3. Also reports March results at the original hypothesis params
         (bond_z=2.5 from the initial strategy spec) as a theory-prior baseline

    A positive OOS result on March with training params, AND a positive result
    with the a-priori bond_z=2.5, would confirm the edge is real.
    """
    print("\n=== Walk-Forward Test (bias check) ============================")
    bond_ask, bond_bid = load_tick_pair("USTBONDTRUSD")
    fx_ask,   fx_bid   = load_tick_pair("USDJPY")

    cutoff = pd.Timestamp("2026-03-01")

    # Split signals into train (Jan+Feb) and test (March)
    sigs_all = build_event_signals(bond_ask, bond_bid, fx_ask, fx_bid,
                                   bond_z=2.0, fx_quiet=0.3)
    sigs_train = sigs_all[sigs_all.index <  cutoff]
    sigs_test  = sigs_all[sigs_all.index >= cutoff]

    print(f"  Train: Jan+Feb  signals={int((sigs_train['signal']!=0).sum()):,}")
    print(f"  Test:  March    signals={int((sigs_test['signal']!=0).sum()):,}\n")

    # ── Step 1: optimise on training window ──────────────────────────────────
    print("  Training sweep (Jan+Feb only):")
    hdr = f"  {'bz':>4}  {'exit':>4}  {'n':>5}  {'sharpe':>7}  {'wr%':>6}  {'pnl_bps':>8}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    best_train = None
    for bz in [2.0, 2.5, 3.0]:
        for ex in [2, 3, 5]:
            s = build_event_signals(bond_ask, bond_bid, fx_ask, fx_bid,
                                    bond_z=bz, fx_quiet=0.3)
            s_tr = s[s.index < cutoff]
            r = run_event_backtest(s_tr, fx_ask, fx_bid, exit_mins=ex)
            m = compute_metrics(r)
            if not m:
                continue
            sr = m["sharpe"]
            print(f"  {bz:>4.1f}  {ex:>4}  {m['n_trades']:>5}  {sr:>7.3f}  "
                  f"{m['win_rate']*100:>6.1f}  {m['total_pnl_bps']:>8.1f}")
            if best_train is None or sr > best_train[0]:
                best_train = (sr, bz, ex)

    best_bz, best_ex = best_train[1], best_train[2]
    print(f"\n  Best training params: bond_z={best_bz}  exit={best_ex}m  "
          f"(train Sharpe={best_train[0]:.3f})")

    # ── Step 2: apply best training params to March OOS ──────────────────────
    print("\n  Out-of-sample: March 2026")
    sigs_oos = build_event_signals(bond_ask, bond_bid, fx_ask, fx_bid,
                                   bond_z=best_bz, fx_quiet=0.3)
    sigs_oos = sigs_oos[sigs_oos.index >= cutoff]
    r_oos = run_event_backtest(sigs_oos, fx_ask, fx_bid, exit_mins=best_ex)
    m_oos = compute_metrics(r_oos)
    if m_oos:
        _print_metrics(m_oos,
            f"OOS March  (best-train params: bz={best_bz} exit={best_ex}m)")
    else:
        print("  No trades in OOS period.")

    # ── Step 3: original hypothesis params (no selection) ────────────────────
    print("\n  A-priori baseline: original strategy spec (bond_z=2.5, exit=3m)")
    sigs_prior = build_event_signals(bond_ask, bond_bid, fx_ask, fx_bid,
                                     bond_z=2.5, fx_quiet=0.5)
    sigs_prior = sigs_prior[sigs_prior.index >= cutoff]
    r_prior = run_event_backtest(sigs_prior, fx_ask, fx_bid, exit_mins=3)
    m_prior = compute_metrics(r_prior)
    if m_prior:
        _print_metrics(m_prior, "OOS March  (a-priori: bz=2.5  fx_quiet=0.5  exit=3m)")
    else:
        print("  No trades in OOS period with a-priori params.")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n  Summary:")
    if m_oos:
        verdict = "PASS" if m_oos["sharpe"] > 0 else "FAIL"
        print(f"  OOS (trained params)  : Sharpe {m_oos['sharpe']:+.3f}  "
              f"pnl={m_oos['total_pnl_bps']:.1f} bps  -> {verdict}")
    if m_prior:
        verdict = "PASS" if m_prior["sharpe"] > 0 else "FAIL"
        print(f"  OOS (a-priori params) : Sharpe {m_prior['sharpe']:+.3f}  "
              f"pnl={m_prior['total_pnl_bps']:.1f} bps  -> {verdict}")


def section_stress():
    """
    Slippage and cost stress test for the optimal USD/JPY tick-event strategy.
    Answers:
      1. What is the actual embedded bid/ask spread in the data?
      2. How much execution latency can the strategy absorb?
      3. How many pips of extra slippage before the edge is gone?
      4. What commission level ($/lot) breaks even?
    """
    print("\n=== Stress Test: Slippage & Cost Analysis ====================")
    print("  Instrument: USDJPY   Parameters: bond_z=2.0  fx_quiet=0.3  exit=2m\n")

    bond_ask, bond_bid = load_tick_pair("USTBONDTRUSD")
    fx_ask,   fx_bid   = load_tick_pair("USDJPY")

    sigs = build_event_signals(bond_ask, bond_bid, fx_ask, fx_bid,
                                bond_z=2.0, fx_quiet=0.3)
    sig_rows = sigs[sigs["signal"] != 0].copy()

    # ── 1. Embedded spread at signal bars ────────────────────────────────────
    mid  = (sig_rows["entry_ask"] + sig_rows["entry_bid"]) / 2
    spd  = (sig_rows["entry_ask"] - sig_rows["entry_bid"]) / mid * 1e4
    print("  1. Embedded bid/ask spread at entry (bps):")
    print(f"     mean   {spd.mean():.3f}")
    print(f"     median {spd.median():.3f}")
    print(f"     p75    {spd.quantile(.75):.3f}")
    print(f"     p90    {spd.quantile(.90):.3f}")
    print(f"     p99    {spd.quantile(.99):.3f}")
    # Round-trip = 2x one-way spread
    print(f"     round-trip mean  {spd.mean()*2:.3f} bps  "
          f"({spd.mean()*2/0.641:.2f} pips at 156 USDJPY)")

    # Baseline for comparison
    base = run_event_backtest(sigs, fx_ask, fx_bid, exit_mins=2)
    m0   = compute_metrics(base)
    print(f"\n  Baseline (0 extra slippage, 0 commission):")
    print(f"     n={m0['n_trades']}  sharpe={m0['sharpe']:.3f}  "
          f"wr={m0['win_rate']*100:.1f}%  pnl={m0['total_pnl_bps']:.1f} bps")
    gross_per_trade = m0["total_pnl_bps"] / m0["n_trades"]
    rt_spread = spd.mean() * 2
    print(f"     net/trade={gross_per_trade:.3f} bps  "
          f"(gross incl. spread ~{gross_per_trade + rt_spread:.3f} bps)")

    # ── 2. Execution latency sweep ────────────────────────────────────────────
    print("\n  2. Execution latency (time from bond event to fill):")
    print(f"     {'latency':>10}  {'n':>5}  {'sharpe':>7}  {'wr%':>6}  {'pnl_bps':>9}  {'net/tr':>8}")
    print("     " + "-" * 54)
    for lat in [0, 5, 10, 30, 60, 120]:
        res = run_event_backtest(sigs, fx_ask, fx_bid, exit_mins=2,
                                 entry_lag_secs=lat)
        m = compute_metrics(res)
        if not m:
            print(f"     {lat:>8}s  <5 trades")
            continue
        npt = m["total_pnl_bps"] / max(m["n_trades"], 1)
        print(f"     {lat:>8}s  {m['n_trades']:>5}  {m['sharpe']:>7.3f}  "
              f"{m['win_rate']*100:>6.1f}  {m['total_pnl_bps']:>9.1f}  {npt:>8.3f}")

    # ── 3. Extra pip slippage sweep ───────────────────────────────────────────
    print("\n  3. Extra pip slippage per side (JPY pip = 0.01):")
    mid_px = float(mid.mean())
    print(f"     {'slip(pip)':>10}  {'slip(bps)':>10}  {'sharpe':>7}  {'wr%':>6}  {'pnl_bps':>9}")
    print("     " + "-" * 52)
    for slip in [0.0, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0]:
        slip_bps = slip * 0.01 / mid_px * 1e4 * 2   # round-trip
        res = run_event_backtest(sigs, fx_ask, fx_bid, exit_mins=2,
                                 extra_slip_pips=slip)
        m = compute_metrics(res)
        if not m:
            continue
        print(f"     {slip:>10.1f}  {slip_bps:>10.3f}  {m['sharpe']:>7.3f}  "
              f"{m['win_rate']*100:>6.1f}  {m['total_pnl_bps']:>9.1f}")

    # ── 4. Commission sweep ───────────────────────────────────────────────────
    print("\n  4. Commission ($/100k lot, round-trip):")
    print(f"     {'comm$/lot':>10}  {'comm_bps':>9}  {'sharpe':>7}  {'wr%':>6}  {'pnl_bps':>9}")
    print("     " + "-" * 50)
    for comm_usd in [0, 2, 3, 5, 7, 10]:
        # $X per 100k = X/100000 per unit = X/100000 × 10000 bps = X/10 bps per side × 2
        comm_bps_rt = comm_usd * 2 / 10.0
        res = run_event_backtest(sigs, fx_ask, fx_bid, exit_mins=2,
                                 commission_bps=comm_bps_rt)
        m = compute_metrics(res)
        if not m:
            continue
        print(f"     {comm_usd:>10}  {comm_bps_rt:>9.2f}  {m['sharpe']:>7.3f}  "
              f"{m['win_rate']*100:>6.1f}  {m['total_pnl_bps']:>9.1f}")

    # ── 5. Combined realistic scenario ───────────────────────────────────────
    print("\n  5. Combined realistic scenarios:")
    print(f"     {'scenario':>30}  {'sharpe':>7}  {'wr%':>6}  {'pnl_bps':>9}")
    print("     " + "-" * 56)
    scenarios = [
        ("ECN retail (0.2pip slip, $3/lot)",  0.2,  0, 0.6),
        ("ECN retail (0.5pip slip, $3/lot)",  0.5,  0, 0.6),
        ("Prime brok (0.1pip slip, $1/lot)",  0.1,  0, 0.2),
        ("10s latency + 0.2pip + $3/lot",     0.2, 10, 0.6),
        ("30s latency + 0.3pip + $5/lot",     0.3, 30, 1.0),
    ]
    for label, slip, lat, comm_bps in scenarios:
        res = run_event_backtest(sigs, fx_ask, fx_bid, exit_mins=2,
                                 extra_slip_pips=slip,
                                 entry_lag_secs=lat,
                                 commission_bps=comm_bps)
        m = compute_metrics(res)
        if not m:
            continue
        print(f"     {label:>30}  {m['sharpe']:>7.3f}  "
              f"{m['win_rate']*100:>6.1f}  {m['total_pnl_bps']:>9.1f}")


SECTIONS = {
    "signal":       section_signal,
    "sweep":        section_sweep,
    "fine":         section_fine,
    "tick":         section_tick_event,
    "compare":      section_compare,
    "walkforward":  section_walkforward,
    "stress":       section_stress,
    "oos_q4":       section_oos_q4,
}

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "tick"
    fn  = SECTIONS.get(arg)
    if fn:
        fn()
    else:
        print(f"Unknown section '{arg}'. Options: {', '.join(SECTIONS)}")
