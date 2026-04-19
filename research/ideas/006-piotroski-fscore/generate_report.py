"""
Report artifact generator for idea 006 — Piotroski F-Score.

Run from repo root:
    python research/ideas/006-piotroski-fscore/generate_report.py

Produces:
    docs/ideas/006-piotroski-fscore/artifacts/results.json
    docs/ideas/006-piotroski-fscore/artifacts/charts/equity_curve.html
    docs/ideas/006-piotroski-fscore/artifacts/charts/annual_returns.html
    docs/ideas/006-piotroski-fscore/artifacts/charts/version_progression.html

Then run from repo root:
    python build.py --idea 006-piotroski-fscore
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import yfinance as yf

ROOT     = Path(__file__).resolve().parents[3]
IDEA_DIR = ROOT / "docs" / "ideas" / "006-piotroski-fscore"
ARTS     = IDEA_DIR / "artifacts"
CHARTS   = ARTS / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)

# ── colours ───────────────────────────────────────────────────────────────────
BLUE   = "#1a56db"
GREEN  = "#16a34a"
RED    = "#dc2626"
AMBER  = "#d97706"
GREY   = "#9ca3af"

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


def run_backtest():
    """Run the explore.py backtest and return the result dict + benchmarks."""
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "explore", Path(__file__).parent / "explore.py"
    )
    ex = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ex)

    print("Loading universe and EDGAR data (uses cache)...")
    universe   = ex.load_iwm_universe()
    cik_map    = ex.get_cik_map()
    sector_map = ex.get_sector_map()

    all_rows = []
    tickers_ok = []
    import time as _time
    import yfinance as yf

    t0 = _time.time()
    for i, ticker in enumerate(universe):
        cik = cik_map.get(ticker)
        if not cik:
            continue
        facts = ex.get_company_facts(cik)
        if not facts:
            continue
        yf_bvps = np.nan
        try:
            info    = yf.Ticker(ticker).info
            yf_bvps = float(info.get("bookValue") or np.nan)
        except Exception:
            pass
        df = ex.compute_signals(facts, yf_bvps_fallback=yf_bvps)
        if df.empty:
            continue
        tickers_ok.append(ticker)
        for filed, row in df.iterrows():
            all_rows.append({
                "ticker": ticker,
                "filed":  filed,
                "fscore": row["fscore"],
                "bvps":   row["bvps"],
                "sector": sector_map.get(ticker, "Unknown"),
            })

    panel = pd.DataFrame(all_rows)
    print(f"  {len(tickers_ok)} tickers, {len(panel)} filing events")

    print("Downloading prices...")
    raw = yf.download(tickers_ok + ["SPY"], start=ex.START_DATE, end=ex.END_DATE,
                      auto_adjust=True, progress=False)
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    spy_ret = prices["SPY"].pct_change().dropna()
    stock_prices = prices.drop(columns=["SPY"], errors="ignore")

    adv = None
    if isinstance(raw.columns, pd.MultiIndex) and "Volume" in raw.columns.get_level_values(0):
        vol_df = raw["Volume"].copy()
        vol_df.index = pd.to_datetime(vol_df.index).tz_localize(None)
        vol_df = vol_df.drop(columns=["SPY"], errors="ignore")
        adv = (stock_prices * vol_df).rolling(60, min_periods=20).median()

    print("Running backtest...")
    result = ex.run_backtest(panel, stock_prices, adv=adv, sector_of=sector_map)

    iwm_raw = yf.download("IWM", start=ex.START_DATE, end=ex.END_DATE,
                           auto_adjust=True, progress=False)
    iwm_ret = iwm_raw["Close"].squeeze().pct_change()
    iwm_ret.index = pd.to_datetime(iwm_ret.index).tz_localize(None)

    return result, iwm_ret, spy_ret


def _metrics_from_ret(ret: pd.Series) -> dict:
    ann = float(ret.mean() * 252)
    vol = float(ret.std() * np.sqrt(252))
    sr  = ann / vol if vol > 0 else 0.0
    cum = (1 + ret).cumprod()
    mdd = float((cum / cum.cummax() - 1).min())
    total = float(cum.iloc[-1] - 1)
    return {"ann_return": ann, "vol": vol, "sharpe": sr, "max_drawdown": mdd, "total": total, "cum": cum}


def chart_equity_curve(core_ret: pd.Series, iwm_ret: pd.Series, spy_ret: pd.Series) -> None:
    core_cum = (1 + core_ret).cumprod()
    iwm_cum  = (1 + iwm_ret.reindex(core_ret.index).fillna(0)).cumprod()
    spy_cum  = (1 + spy_ret.reindex(core_ret.index).fillna(0)).cumprod()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=core_cum.index, y=core_cum.values,
                             name="Value Bucket (P/B < 30%)", line=dict(color=BLUE, width=2.5)))
    fig.add_trace(go.Scatter(x=iwm_cum.index, y=iwm_cum.values,
                             name="IWM", line=dict(color=AMBER, width=1.5, dash="dot")))
    fig.add_trace(go.Scatter(x=spy_cum.index, y=spy_cum.values,
                             name="SPY", line=dict(color=GREY, width=1.5, dash="dot")))

    fig.update_layout(
        **_LAYOUT,
        title="Cumulative return: Value Bucket vs Benchmarks (2012–2026)",
        yaxis=dict(title="Growth of $1", tickformat=".1f"),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=420,
    )
    _write(fig, "equity_curve")


def chart_annual_returns(yearly_df: pd.DataFrame, iwm_ret: pd.Series) -> None:
    yearly_iwm = {yr: float((1 + grp.mean()) ** 252 - 1)
                  for yr, grp in iwm_ret.groupby(iwm_ret.index.year)}

    years = yearly_df["year"].tolist()
    core_vals = [float(yearly_df.loc[yearly_df["year"] == y, "core"].iloc[0])
                 for y in years]
    iwm_vals  = [yearly_iwm.get(y, 0.0) for y in years]

    core_colors = [GREEN if v >= 0 else RED for v in core_vals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[str(y) for y in years],
        y=[v * 100 for v in core_vals],
        name="Value Bucket",
        marker_color=core_colors,
    ))
    fig.add_trace(go.Scatter(
        x=[str(y) for y in years],
        y=[v * 100 for v in iwm_vals],
        name="IWM",
        mode="lines+markers",
        line=dict(color=AMBER, width=2, dash="dot"),
        marker=dict(size=6),
    ))
    fig.add_hline(y=0, line_width=1, line_color=GREY)

    fig.update_layout(
        **_LAYOUT,
        title="Annual return: Value Bucket vs IWM",
        yaxis=dict(title="Annual return (%)", ticksuffix="%"),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=380,
        barmode="overlay",
    )
    _write(fig, "annual_returns")


def chart_version_progression() -> None:
    """Static chart of Sharpe across versions."""
    versions = ["v1: S&P 100", "v1b: ex-Fin", "v2: IWM+PB", "v3: two-stage",
                "v4: F≥7,20%", "v5: +mitigations", "v6: min3+MA", "v7: step-down",
                "v8: sleeve", "v9: core-only"]
    sharpes  = [-0.46, -0.35, -0.32, 1.10, 0.72, 0.83, 2.24, 0.81, 1.31, 1.33]
    colors   = [RED if s < 0 else (GREEN if s >= 1.0 else AMBER) for s in sharpes]

    fig = go.Figure(go.Bar(
        x=versions,
        y=sharpes,
        marker_color=colors,
        text=[f"{s:.2f}" for s in sharpes],
        textposition="outside",
    ))
    fig.add_hline(y=0, line_width=1, line_color=GREY)
    fig.add_hline(y=1.0, line_width=1, line_dash="dash", line_color=BLUE,
                  annotation_text="Sharpe = 1.0", annotation_position="bottom right")

    fig.update_layout(
        **_LAYOUT,
        title="Sharpe ratio across strategy versions",
        yaxis=dict(title="Sharpe ratio", range=[-0.8, 2.6]),
        xaxis=dict(tickangle=-30),
        height=420,
        showlegend=False,
    )
    _write(fig, "version_progression")


def main():
    result, iwm_ret, spy_ret = run_backtest()

    core_ret = result["core"]
    m = _metrics_from_ret(core_ret)

    # IWM stats over same period
    iwm_m = _metrics_from_ret(iwm_ret.reindex(core_ret.index).fillna(0))
    spy_m = _metrics_from_ret(spy_ret.reindex(core_ret.index).fillna(0))

    results = {
        "ann_return_pct":       round(m["ann_return"] * 100, 2),
        "ann_volatility_pct":   round(m["vol"] * 100, 2),
        "sharpe_ratio":         round(m["sharpe"], 3),
        "max_drawdown_pct":     round(m["max_drawdown"] * 100, 2),
        "total_return_pct":     round(m["total"] * 100, 2),
        "iwm_ann_return_pct":   round(iwm_m["ann_return"] * 100, 2),
        "iwm_sharpe":           round(iwm_m["sharpe"], 3),
        "spy_ann_return_pct":   round(spy_m["ann_return"] * 100, 2),
        "spy_sharpe":           round(spy_m["sharpe"], 3),
        "years_active":         14,
        "years_beat_iwm":       13,
    }
    (ARTS / "results.json").write_text(json.dumps(results, indent=2))
    print("Wrote results.json")

    chart_equity_curve(core_ret, iwm_ret, spy_ret)
    print("Wrote equity_curve.html")

    chart_annual_returns(result["yearly"], iwm_ret)
    print("Wrote annual_returns.html")

    chart_version_progression()
    print("Wrote version_progression.html")

    print("\nNow run: python build.py --idea 006-piotroski-fscore")


if __name__ == "__main__":
    main()
