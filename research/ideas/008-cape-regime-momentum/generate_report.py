"""
Report artifact generator for idea 008 — CAPE Regime + Momentum.

Run from repo root:
    python research/ideas/008-cape-regime-momentum/generate_report.py

Produces:
    docs/ideas/008-cape-regime-momentum/artifacts/results.json
    docs/ideas/008-cape-regime-momentum/artifacts/charts/equity_curve.html
    docs/ideas/008-cape-regime-momentum/artifacts/charts/annual_returns.html
    docs/ideas/008-cape-regime-momentum/artifacts/charts/equity_allocation.html

Then run:
    python build.py --idea 008-cape-regime-momentum
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

ROOT     = Path(__file__).resolve().parents[3]
IDEA_DIR = ROOT / "docs" / "ideas" / "008-cape-regime-momentum"
ARTS     = IDEA_DIR / "artifacts"
CHARTS   = ARTS / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)

BLUE  = "#1a56db"
GREEN = "#16a34a"
RED   = "#dc2626"
AMBER = "#d97706"
GREY  = "#9ca3af"
TEAL  = "#0891b2"

_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1a1a2e"),
)


def _write(fig: go.Figure, name: str) -> None:
    (CHARTS / f"{name}.html").write_text(
        pio.to_html(fig, full_html=False, include_plotlyjs="cdn"), encoding="utf-8"
    )


def load_explore():
    spec = importlib.util.spec_from_file_location(
        "explore", Path(__file__).parent / "explore.py"
    )
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)
    return ex


def build_full_df(ex):
    """Return DataFrame with all signals + allocation weights for charting."""
    base_df = ex.load_shiller(ex.DATA_FILE)
    df = ex.compute_signals(base_df, ex.BEST["ecy_window"],
                            ex.BEST["mom_months"], ex.BEST["rate_window"])
    df = df.dropna(subset=["ecy_pct", "momentum", "rates_rising",
                            "eq_ret", "bond_ret"])
    df["cpi_yoy"] = df["CPI"].pct_change(12)
    df = df.dropna(subset=["cpi_yoy"])
    df = df[df.index >= ex.START_DATE].copy()

    p = ex.BEST
    ecy_prev   = df["ecy_pct"].shift(1)
    mom_prev   = df["momentum"].shift(1)
    infl_prev  = df["cpi_yoy"].shift(1)

    cheap     = ecy_prev > (1 - p["cheap_thresh"])
    expensive = ecy_prev < (1 - p["expensive_thresh"])
    fair      = ~cheap & ~expensive
    mom_up    = mom_prev > 0

    eq_w = np.select(
        [cheap & mom_up, cheap & ~mom_up,
         fair  & mom_up, fair  & ~mom_up,
         expensive & mom_up, expensive & ~mom_up],
        [p["w_cheap_up"], p["w_cheap_dn"],
         p["w_fair_up"],  p["w_fair_dn"],
         p["w_exp_up"],   p["w_exp_dn"]],
        default=0.60,
    )
    if p.get("use_infl_filter"):
        eq_w = np.where(infl_prev > p["infl_thresh"],
                        np.minimum(eq_w, p["infl_eq_cap"]), eq_w)

    df["eq_weight"]   = eq_w
    df["regime"]      = "fair"
    df.loc[cheap,     "regime"] = "cheap"
    df.loc[expensive, "regime"] = "expensive"
    df["high_infl"]   = infl_prev > p["infl_thresh"]

    strat = eq_w * df["eq_ret"] + (1 - eq_w) * df["bond_ret"]
    df["strat_ret"]  = strat
    df["bench_6040"] = 0.60 * df["eq_ret"] + 0.40 * df["bond_ret"]
    df["bench_eq"]   = df["eq_ret"]

    return df.dropna(subset=["strat_ret"])


def metrics(returns: pd.Series) -> dict:
    ann_ret  = (1 + returns).prod() ** (12 / len(returns)) - 1
    ann_vol  = returns.std() * np.sqrt(12)
    sharpe   = ann_ret / ann_vol if ann_vol > 0 else 0.0
    cum      = (1 + returns).cumprod()
    max_dd   = ((cum - cum.cummax()) / cum.cummax()).min()
    total    = cum.iloc[-1] - 1
    return dict(ann_ret=ann_ret, ann_vol=ann_vol, sharpe=sharpe,
                max_dd=max_dd, total=total)


# ── Chart 1: Equity curve (log scale) ────────────────────────────────────────
def chart_equity_curve(df: pd.DataFrame) -> None:
    strat_cum = (1 + df["strat_ret"]).cumprod()
    b6040_cum = (1 + df["bench_6040"]).cumprod()
    eq_cum    = (1 + df["bench_eq"]).cumprod()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=strat_cum.index, y=strat_cum.values,
        name="Strategy", line=dict(color=BLUE, width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=b6040_cum.index, y=b6040_cum.values,
        name="60/40", line=dict(color=AMBER, width=1.5, dash="dot"),
    ))
    fig.add_trace(go.Scatter(
        x=eq_cum.index, y=eq_cum.values,
        name="100% Equity", line=dict(color=GREY, width=1.5, dash="dot"),
    ))
    fig.update_layout(
        **_LAYOUT,
        title="Cumulative real total return (log scale, 1900-2026)",
        yaxis=dict(title="Growth of $1 (real)", type="log",
                   tickformat=".0f"),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0),
        height=440,
    )
    _write(fig, "equity_curve")


# ── Chart 2: Annual returns vs 60/40 (1950–present) ──────────────────────────
def chart_annual_returns(df: pd.DataFrame) -> None:
    df_post = df[df.index.year >= 1950]
    yr_strat = df_post["strat_ret"].groupby(df_post.index.year).apply(
        lambda r: (1 + r).prod() - 1)
    yr_6040  = df_post["bench_6040"].groupby(df_post.index.year).apply(
        lambda r: (1 + r).prod() - 1)

    years   = [str(y) for y in yr_strat.index]
    s_vals  = (yr_strat * 100).tolist()
    b_vals  = (yr_6040  * 100).tolist()
    colors  = [GREEN if v >= b else RED
               for v, b in zip(s_vals, b_vals)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=years, y=s_vals, name="Strategy",
        marker_color=colors, opacity=0.85,
    ))
    fig.add_trace(go.Scatter(
        x=years, y=b_vals, name="60/40",
        mode="lines", line=dict(color=AMBER, width=2, dash="dot"),
    ))
    fig.add_hline(y=0, line_width=1, line_color=GREY)
    fig.update_layout(
        **_LAYOUT,
        title="Annual real return: Strategy vs 60/40 (1950-2026)",
        yaxis=dict(title="Annual return (%)", ticksuffix="%"),
        xaxis=dict(title="", tickangle=-45),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0),
        height=420,
    )
    _write(fig, "annual_returns")


# ── Chart 3: Equity allocation over time ─────────────────────────────────────
def chart_equity_allocation(df: pd.DataFrame) -> None:
    fig = go.Figure()

    # Shade high-inflation periods
    hi = df[df["high_infl"] == True]
    in_block = False
    x0 = None
    for date, row in df.iterrows():
        if row["high_infl"] and not in_block:
            x0 = date
            in_block = True
        elif not row["high_infl"] and in_block:
            fig.add_vrect(x0=x0, x1=date, fillcolor=RED,
                          opacity=0.07, line_width=0,
                          annotation_text="", layer="below")
            in_block = False
    if in_block:
        fig.add_vrect(x0=x0, x1=df.index[-1], fillcolor=RED,
                      opacity=0.07, line_width=0, layer="below")

    # Equity allocation line
    fig.add_trace(go.Scatter(
        x=df.index, y=(df["eq_weight"] * 100).values,
        name="Equity allocation",
        fill="tozeroy", fillcolor=f"rgba(26,86,219,0.12)",
        line=dict(color=BLUE, width=1.5),
    ))

    # Reference lines
    for level, label in [(60, "60% (neutral)"), (100, "100%"), (0, "0%")]:
        fig.add_hline(y=level, line_width=1, line_dash="dash",
                      line_color=GREY,
                      annotation_text=label if level == 60 else "",
                      annotation_position="right")

    fig.update_layout(
        **_LAYOUT,
        title="Equity allocation over time (red shading = CPI > 4%)",
        yaxis=dict(title="Equity weight (%)", ticksuffix="%",
                   range=[-5, 110]),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0),
        height=380,
        showlegend=False,
    )
    _write(fig, "equity_allocation")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("Loading explore module...")
    ex = load_explore()

    print("Building results...")
    df = build_full_df(ex)

    m_s = metrics(df["strat_ret"])
    m_6 = metrics(df["bench_6040"])
    m_e = metrics(df["bench_eq"])

    yr_strat = df["strat_ret"].groupby(df.index.year).apply(lambda r: (1+r).prod()-1)
    yr_6040  = df["bench_6040"].groupby(df.index.year).apply(lambda r: (1+r).prod()-1)
    yr_eq    = df["bench_eq"].groupby(df.index.year).apply(lambda r: (1+r).prod()-1)
    beat_6040 = int((yr_strat > yr_6040).sum())
    beat_eq   = int((yr_strat > yr_eq).sum())
    n_years   = int(len(yr_strat))
    high_infl_pct = float(df["high_infl"].mean() * 100)

    results = {
        "ann_return_pct":          round(m_s["ann_ret"] * 100, 2),
        "ann_volatility_pct":      round(m_s["ann_vol"] * 100, 2),
        "sharpe_ratio":            round(m_s["sharpe"], 3),
        "max_drawdown_pct":        round(m_s["max_dd"] * 100, 2),
        "bench_6040_ann_return_pct": round(m_6["ann_ret"] * 100, 2),
        "bench_6040_sharpe":       round(m_6["sharpe"], 3),
        "bench_6040_max_dd_pct":   round(m_6["max_dd"] * 100, 2),
        "bench_eq_ann_return_pct": round(m_e["ann_ret"] * 100, 2),
        "bench_eq_sharpe":         round(m_e["sharpe"], 3),
        "bench_eq_max_dd_pct":     round(m_e["max_dd"] * 100, 2),
        "years_active":            n_years,
        "years_beat_6040":         beat_6040,
        "high_inflation_pct":      round(high_infl_pct, 1),
    }
    (ARTS / "results.json").write_text(json.dumps(results, indent=2))
    print("Wrote results.json")

    chart_equity_curve(df)
    print("Wrote equity_curve.html")

    chart_annual_returns(df)
    print("Wrote annual_returns.html")

    chart_equity_allocation(df)
    print("Wrote equity_allocation.html")

    print("\nNow run: python build.py --idea 008-cape-regime-momentum")


if __name__ == "__main__":
    main()
