import numpy as np
import pandas as pd
from pathlib import Path
from itertools import product

# ── Config ────────────────────────────────────────────────────────────────────
DATA_FILE  = Path(__file__).parent.parent / "ie_data.xls"
START_DATE = "1900-01-01"

# Best params (v3 sweep — ECY + inflation filter, Sharpe 1.127)
BEST = dict(
    ecy_window       = 240,
    mom_months       = 6,
    rate_window      = 12,
    cheap_thresh     = 0.33,
    expensive_thresh = 0.67,
    w_cheap_up       = 1.00,
    w_cheap_dn       = 0.20,
    w_fair_up        = 0.80,
    w_fair_dn        = 0.40,
    w_exp_up         = 0.30,
    w_exp_dn         = 0.00,
    use_rate_filter  = False,  # rate filter hurts — routing to cash misses bond yield income
    use_infl_filter  = True,
    infl_thresh      = 0.04,
    infl_eq_cap      = 0.50,
)


# ── Data Loading ──────────────────────────────────────────────────────────────
def load_shiller(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Data", header=None, skiprows=7)
    raw.columns = [
        "Date", "SP500", "Dividend", "Earnings", "CPI", "Date_Frac",
        "LongRate", "RealPrice", "RealDiv", "RealTR", "RealEarnings",
        "RealScaledEarnings", "CAPE", "_c13", "TRCAPE", "_c15",
        "ExcessCAPEYield", "BondRetFactor", "RealBondReturn",
        "RealStock10Y", "RealBonds10Y", "RealExcess10Y",
    ]
    df = raw[raw["Date"].notna() & (raw["Date"] != "Date")].copy()
    df["Date"] = df["Date"].astype(float)

    year  = df["Date"].astype(int)
    month = ((df["Date"] - year) * 100).round().astype(int).clip(1, 12)
    df["date"] = pd.to_datetime({"year": year, "month": month, "day": 1})
    df = df.set_index("date").sort_index()

    df["eq_ret"]   = df["RealTR"].pct_change()
    df["bond_ret"] = df["BondRetFactor"] - 1

    return df[["SP500", "RealTR", "CAPE", "LongRate", "CPI",
               "ExcessCAPEYield", "eq_ret", "bond_ret"]]


# ── Signal Computation ────────────────────────────────────────────────────────
def compute_signals(df: pd.DataFrame, ecy_window: int, mom_months: int,
                    rate_window: int) -> pd.DataFrame:
    df = df.copy()

    # ECY percentile: high = equities cheap relative to bonds → bullish
    df["ecy_pct"] = (
        df["ExcessCAPEYield"]
        .rolling(ecy_window, min_periods=60)
        .apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    )

    # 6-month total-return momentum
    df["momentum"] = df["RealTR"].pct_change(mom_months)

    # Rate trend: positive = rates rising = bond prices falling
    df["rates_rising"] = df["LongRate"].diff(rate_window) > 0

    # YoY inflation
    df["cpi_yoy"] = df["CPI"].pct_change(12)

    return df


# ── Vectorised Backtest ───────────────────────────────────────────────────────
def run_backtest(df: pd.DataFrame, params: dict) -> pd.Series:
    d = df.dropna(subset=["ecy_pct", "momentum", "rates_rising",
                           "cpi_yoy", "eq_ret", "bond_ret"]).copy()
    d = d[d.index >= START_DATE]

    ct = params["cheap_thresh"]
    et = params["expensive_thresh"]

    # All signals lag one period — no lookahead
    ecy_prev    = d["ecy_pct"].shift(1)
    mom_prev    = d["momentum"].shift(1)
    rates_prev  = d["rates_rising"].shift(1)
    infl_prev   = d["cpi_yoy"].shift(1)

    # ECY regime: high ECY pct = equities cheap relative to bonds
    cheap     = ecy_prev > (1 - ct)     # top third of ECY → cheap equities
    expensive = ecy_prev < (1 - et)     # bottom third of ECY → expensive equities
    fair      = ~cheap & ~expensive
    mom_up    = mom_prev > 0

    eq_w = np.select(
        [cheap & mom_up,
         cheap & ~mom_up,
         fair  & mom_up,
         fair  & ~mom_up,
         expensive & mom_up,
         expensive & ~mom_up],
        [params["w_cheap_up"],
         params["w_cheap_dn"],
         params["w_fair_up"],
         params["w_fair_dn"],
         params["w_exp_up"],
         params["w_exp_dn"]],
        default=0.60,
    )

    # Inflation cap: in high-inflation regimes, cap equity allocation
    if params.get("use_infl_filter", False):
        high_infl = infl_prev > params["infl_thresh"]
        eq_w = np.where(high_infl, np.minimum(eq_w, params["infl_eq_cap"]), eq_w)

    bond_w = 1.0 - eq_w

    # Rate filter: when rates rising, rotate defensive allocation to cash (0%)
    if params.get("use_rate_filter", False):
        eff_bond_ret = np.where(rates_prev, 0.0, d["bond_ret"].values)
    else:
        eff_bond_ret = d["bond_ret"].values

    strat = pd.Series(
        eq_w * d["eq_ret"].values + bond_w * eff_bond_ret,
        index=d.index,
    ).dropna()
    return strat


# ── Metrics ───────────────────────────────────────────────────────────────────
def compute_metrics(returns: pd.Series) -> dict:
    ann_ret  = (1 + returns).prod() ** (12 / len(returns)) - 1
    ann_vol  = returns.std() * np.sqrt(12)
    sharpe   = ann_ret / ann_vol if ann_vol > 0 else 0.0
    cum      = (1 + returns).cumprod()
    max_dd   = ((cum - cum.cummax()) / cum.cummax()).min()
    total_ret = cum.iloc[-1] - 1
    return dict(ann_ret=ann_ret, ann_vol=ann_vol, sharpe=sharpe,
                max_dd=max_dd, total_ret=total_ret, n=len(returns))


def annual_returns(returns: pd.Series) -> pd.Series:
    return returns.groupby(returns.index.year).apply(lambda r: (1 + r).prod() - 1)


# ── Grid Search ───────────────────────────────────────────────────────────────
def grid_search(base_df: pd.DataFrame) -> pd.DataFrame:
    combos = list(product(
        [180, 240],                           # ecy_window
        [3, 6],                               # mom_months
        [12],                                 # rate_window (fixed)
        [(0.25, 0.75), (0.33, 0.67)],         # thresholds
        [1.00],                               # w_cheap_up
        [0.20, 0.40],                         # w_cheap_dn
        [(0.70, 0.50), (0.80, 0.40)],         # (w_fair_up, w_fair_dn)
        [0.30, 0.40, 0.50],                   # w_exp_up
        [0.00, 0.10],                         # w_exp_dn
        [True, False],                        # use_rate_filter
        [True, False],                        # use_infl_filter
    ))
    print(f"Grid search: {len(combos)} combinations...")

    cache = {}
    rows  = []
    for (ew, mm, rw, (ct, et), wcu, wcd, (wfu, wfd), weu, wed,
         use_rate, use_infl) in combos:
        key = (ew, mm, rw)
        if key not in cache:
            cache[key] = compute_signals(base_df, ew, mm, rw)

        params = dict(
            ecy_window=ew, mom_months=mm, rate_window=rw,
            cheap_thresh=ct, expensive_thresh=et,
            w_cheap_up=wcu, w_cheap_dn=wcd,
            w_fair_up=wfu, w_fair_dn=wfd,
            w_exp_up=weu, w_exp_dn=wed,
            use_rate_filter=use_rate, use_infl_filter=use_infl,
            infl_thresh=0.04, infl_eq_cap=0.50,
        )
        ret = run_backtest(cache[key], params)
        m   = compute_metrics(ret)
        rows.append({**params, **m})

    return pd.DataFrame(rows).sort_values("sharpe", ascending=False)


# ── Main ──────────────────────────────────────────────────────────────────────
def run(sweep: bool = False):
    print("Loading Shiller data...")
    base_df = load_shiller(DATA_FILE)

    if sweep:
        grid = grid_search(base_df)
        disp_cols = [
            "ecy_window", "mom_months", "cheap_thresh", "expensive_thresh",
            "w_cheap_up", "w_cheap_dn", "w_fair_up", "w_fair_dn",
            "w_exp_up", "w_exp_dn", "use_rate_filter", "use_infl_filter",
            "ann_ret", "ann_vol", "sharpe", "max_dd",
        ]
        print("\nTop 15 by Sharpe:")
        print(grid[disp_cols].head(15).to_string(index=False))
        print("\nBest params:")
        best = grid.iloc[0]
        for k in ["ecy_window","mom_months","cheap_thresh","expensive_thresh",
                  "w_cheap_up","w_cheap_dn","w_fair_up","w_fair_dn",
                  "w_exp_up","w_exp_dn","use_rate_filter","use_infl_filter"]:
            print(f"  {k} = {best[k]}")

        # Also show contribution of each filter in isolation
        print("\nFilter contribution (best base params, filters toggled):")
        for rf, inf in [(False, False), (True, False), (False, True), (True, True)]:
            sub = grid[(grid["use_rate_filter"] == rf) & (grid["use_infl_filter"] == inf)]
            if len(sub):
                r = sub.iloc[0]
                print(f"  rate={str(rf):<5} infl={str(inf):<5}  "
                      f"sharpe={r['sharpe']:.3f}  ret={r['ann_ret']:.2%}  dd={r['max_dd']:.2%}")
        return grid

    # ── Run with BEST params ───────────────────────────────────────────────────
    print("Computing signals...")
    df = compute_signals(base_df, BEST["ecy_window"], BEST["mom_months"],
                         BEST["rate_window"])

    print("Running backtest...")
    strat_ret = run_backtest(df, BEST)

    d = df.dropna(subset=["ecy_pct", "momentum", "rates_rising",
                           "cpi_yoy", "eq_ret", "bond_ret"])
    d = d[d.index >= START_DATE]
    bench_6040 = (0.60 * d["eq_ret"] + 0.40 * d["bond_ret"]).dropna()
    bench_eq   = d["eq_ret"].dropna()

    m_s = compute_metrics(strat_ret)
    m_6 = compute_metrics(bench_6040)
    m_e = compute_metrics(bench_eq)

    print(f"\n{'Metric':<24} {'Strategy':>14} {'60/40':>12} {'Equity':>12}")
    print("-" * 64)
    for name, key, fmt in [
        ("Ann. Return",     "ann_ret",   ".2%"),
        ("Ann. Volatility", "ann_vol",   ".2%"),
        ("Sharpe (rf=0%)",  "sharpe",    ".3f"),
        ("Max Drawdown",    "max_dd",    ".2%"),
        ("Total Return",    "total_ret", ".0%"),
    ]:
        print(f"{name:<24} {format(m_s[key], fmt):>14} "
              f"{format(m_6[key], fmt):>12} {format(m_e[key], fmt):>12}")

    print(f"\nPeriod: {strat_ret.index[0].date()} to {strat_ret.index[-1].date()} "
          f"({m_s['n']} months)")
    print("Signals: ECY percentile (20yr window) + 6M momentum + rate trend + inflation cap")

    # Regime breakdown
    ecy_prev = d["ecy_pct"].shift(1)
    cheap     = ecy_prev > (1 - BEST["cheap_thresh"])
    expensive = ecy_prev < (1 - BEST["expensive_thresh"])
    regime    = pd.Series("fair", index=d.index)
    regime[cheap]     = "cheap"
    regime[expensive] = "expensive"
    high_infl = d["cpi_yoy"].shift(1) > BEST["infl_thresh"]
    rates_up  = d["rates_rising"].shift(1)

    print("\nRegime distribution (ECY-based):")
    for r in ["cheap", "fair", "expensive"]:
        n = (regime == r).sum()
        print(f"  {r:<12} {n:4d} months  ({n / len(regime) * 100:.1f}%)")

    print(f"\nHigh inflation months: {high_infl.sum()} ({high_infl.mean()*100:.1f}%)")
    print(f"Rates rising months:   {rates_up.sum()} ({rates_up.mean()*100:.1f}%)")

    yr_s = annual_returns(strat_ret)
    yr_6 = annual_returns(bench_6040)
    yr_e = annual_returns(bench_eq)
    beat_6040 = (yr_s > yr_6).sum()
    beat_eq   = (yr_s > yr_e).sum()
    n_yrs     = len(yr_s)
    print(f"\nYears beat 60/40: {beat_6040}/{n_yrs} ({beat_6040/n_yrs*100:.1f}%)")
    print(f"Years beat equity: {beat_eq}/{n_yrs} ({beat_eq/n_yrs*100:.1f}%)")

    return strat_ret, bench_6040, bench_eq, yr_s, yr_6, yr_e


if __name__ == "__main__":
    import sys
    if "--sweep" in sys.argv:
        run(sweep=True)
    else:
        run(sweep=False)
