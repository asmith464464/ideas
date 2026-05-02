"""
Report artifact generator for idea 007 — Heston Vol / VRP Strategy.

Run from repo root:
    python research/ideas/007-heston-vol-strategy/generate_report.py

Produces:
    docs/ideas/007-heston-vol-strategy/artifacts/results.json
    docs/ideas/007-heston-vol-strategy/artifacts/charts/equity_curve.html
    docs/ideas/007-heston-vol-strategy/artifacts/charts/vrp_signal.html
    docs/ideas/007-heston-vol-strategy/artifacts/charts/allocation.html

Then run from repo root:
    python build.py --idea 007-heston-vol-strategy
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

ROOT     = Path(__file__).resolve().parents[3]
IDEA_DIR = ROOT / "docs" / "ideas" / "007-heston-vol-strategy"
ARTS     = IDEA_DIR / "artifacts"
CHARTS   = ARTS / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)

BLUE  = "#1a56db"
GREEN = "#16a34a"
RED   = "#dc2626"
AMBER = "#d97706"
GREY  = "#9ca3af"

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


def run_all(ex):
    pairs_data, rf_s = ex.fetch_data()
    weights  = ex.compute_weights(pairs_data)
    result   = ex.run_backtest(pairs_data, weights)
    return pairs_data, weights, result


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def chart_equity_curve(result: pd.DataFrame, pairs_data: dict) -> None:
    cum_strat = result["total_ret"].cumsum()

    bh_rets = pd.DataFrame(
        {e: df.reindex(result.index)["log_return"] for e, df in pairs_data.items()}
    ).mean(axis=1)
    cum_bh = bh_rets.fillna(0).cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cum_strat.index, y=cum_strat.values * 100,
        name="VRP Strategy", line=dict(color=BLUE, width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=cum_bh.index, y=cum_bh.values * 100,
        name="EW Buy & Hold", line=dict(color=GREY, width=1.8, dash="dot"),
    ))

    fig.update_layout(
        **_LAYOUT,
        title="Cumulative log-return: VRP Strategy vs Equal-Weight Buy & Hold",
        yaxis=dict(title="Cumulative log-return (%)"),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=420,
    )
    _write(fig, "equity_curve")


def chart_vrp_signal(pairs_data: dict, result: pd.DataFrame) -> None:
    """Rolling VRP per pair over the backtest period."""
    fig = go.Figure()
    colours = {"SPY": BLUE, "QQQ": GREEN, "GLD": AMBER}

    for etf, df in pairs_data.items():
        s = df.reindex(result.index)["vrp"].dropna()
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            name=f"{etf} VRP", line=dict(color=colours.get(etf, GREY), width=1.5),
        ))

    fig.add_hline(y=0, line_width=1, line_color=RED, line_dash="dash",
                  annotation_text="VRP = 0", annotation_position="bottom right")

    fig.update_layout(
        **_LAYOUT,
        title="Volatility Risk Premium per pair (implied vol − realised vol, annualised %)",
        yaxis=dict(title="VRP (vol points)"),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=380,
    )
    _write(fig, "vrp_signal")


def chart_allocation(weights: pd.DataFrame, result: pd.DataFrame) -> None:
    """Stacked area chart of daily allocated weights over time."""
    w_daily = weights.reindex(result.index, method="ffill").fillna(0.0)
    colours  = {"SPY": BLUE, "QQQ": GREEN, "GLD": AMBER}

    fig = go.Figure()
    for etf in w_daily.columns:
        fig.add_trace(go.Scatter(
            x=w_daily.index,
            y=(w_daily[etf] * 100).values,
            name=etf,
            stackgroup="one",
            line=dict(width=0.5, color=colours.get(etf, GREY)),
            fillcolor=colours.get(etf, GREY),
            mode="lines",
        ))

    fig.update_layout(
        **_LAYOUT,
        title="Daily portfolio allocation (rebalanced monthly)",
        yaxis=dict(title="Weight (%)", range=[0, 105]),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=360,
    )
    _write(fig, "allocation")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading explore.py backtest...")
    ex = load_explore()

    print("Fetching data & running backtest...")
    pairs_data, weights, result = run_all(ex)

    _ANN = np.sqrt(252)
    port_excess = result["total_ret"] - result["rf_daily"]
    sr_strat    = port_excess.mean() / port_excess.std() * _ANN

    bh_rets = pd.DataFrame(
        {e: df.reindex(result.index)["log_return"] for e, df in pairs_data.items()}
    ).mean(axis=1)
    bh_excess = bh_rets - result["rf_daily"]
    sr_bh     = bh_excess.mean() / bh_excess.std() * _ANN

    ann_ret = result["total_ret"].mean() * 252 * 100
    ann_bh  = bh_rets.mean() * 252 * 100

    cumr_s  = result["total_ret"].cumsum()
    cumr_b  = bh_rets.fillna(0).cumsum()
    dd_s    = (cumr_s - cumr_s.cummax()).min() * 100
    dd_b    = (cumr_b - cumr_b.cummax()).min() * 100

    ann_vol  = port_excess.std() * _ANN * 100
    avg_inv  = result["invested"].mean() * 100
    tc_drag  = (result["port_gross"] - result["port_net"]).mean() * 252 * 100

    start_date = str(result.index[0].date())
    end_date   = str(result.index[-1].date())

    results = {
        "ann_return_pct":       round(ann_ret, 2),
        "ann_volatility_pct":   round(ann_vol, 2),
        "sharpe_ratio":         round(float(sr_strat), 3),
        "max_drawdown_pct":     round(dd_s, 2),
        "bh_ann_return_pct":    round(ann_bh, 2),
        "bh_sharpe_ratio":      round(float(sr_bh), 3),
        "bh_max_drawdown_pct":  round(dd_b, 2),
        "avg_weight_invested_pct": round(avg_inv, 1),
        "tc_drag_ann_pct":      round(tc_drag, 3),
        "n_pairs":              len(pairs_data),
        "rv_window_days":       ex.RV_WINDOW,
        "rho_window_days":      ex.RHO_WINDOW,
        "rebal_step_days":      ex.REBAL_STEP,
        "start_date":           start_date,
        "end_date":             end_date,
    }

    (ARTS / "results.json").write_text(json.dumps(results, indent=2))
    print("Wrote results.json")

    chart_equity_curve(result, pairs_data)
    print("Wrote equity_curve.html")

    chart_vrp_signal(pairs_data, result)
    print("Wrote vrp_signal.html")

    chart_allocation(weights, result)
    print("Wrote allocation.html")

    print(f"\nKey metrics:")
    print(f"  SR(xrf):   {sr_strat:.3f}")
    print(f"  Ann Ret:   {ann_ret:.2f}%")
    print(f"  Max DD:    {dd_s:.2f}%")
    print(f"  Period:    {start_date} to {end_date}")
    print(f"\nNow run: python build.py --idea 007-heston-vol-strategy")


if __name__ == "__main__":
    main()
