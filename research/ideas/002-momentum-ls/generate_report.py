"""
One-time report artifact generator for idea 002 — multi-timeframe momentum L/S.

Run from repo root:
    python research/ideas/002-momentum-ls/generate_report.py

Produces:
    docs/ideas/002-momentum-ls/artifacts/results.json
    docs/ideas/002-momentum-ls/artifacts/charts/equity_curve.html
    docs/ideas/002-momentum-ls/artifacts/charts/drawdown.html
    docs/ideas/002-momentum-ls/artifacts/charts/annual_returns.html
    docs/ideas/002-momentum-ls/artifacts/charts/sharpe_journey.html
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from research.metrics import compute_all_metrics

# Import strategy helpers from explore.py via importlib
import importlib.util
_spec = importlib.util.spec_from_file_location(
    'explore', Path(__file__).parent / 'explore.py')
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)

fetch_all          = _m.fetch_all
_backtest          = _m._backtest
_momentum_signals  = _m._momentum_signals
_rebalance_dates   = _m._rebalance_dates
MIN_HISTORY        = _m.MIN_HISTORY

ARTIFACTS = Path(__file__).resolve().parents[3] / 'docs/ideas/002-momentum-ls/artifacts'
CHARTS    = ARTIFACTS / 'charts'
CHARTS.mkdir(parents=True, exist_ok=True)

BLUE    = '#1a56db'
GREY    = '#9ca3af'
RED     = '#dc2626'
GREEN   = '#16a34a'
AMBER   = '#d97706'
PURPLE  = '#7c3aed'

_LAYOUT = dict(
    template='plotly_white',
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(color='#1a1a2e'),
)


def _write(fig: go.Figure, name: str) -> None:
    (CHARTS / f'{name}.html').write_text(
        pio.to_html(fig, full_html=False, include_plotlyjs='cdn'))


def _calibrate_gate(prices: pd.DataFrame) -> float:
    score, _, _, _ = _momentum_signals(prices)
    reb = _rebalance_dates(score, 'ME')
    spreads = []
    for d in reb:
        eligible = [c for c in prices.columns
                    if prices[c].loc[:d].dropna().shape[0] >= MIN_HISTORY]
        row = score.loc[d, eligible].dropna()
        if len(row) >= 10:
            spreads.append(row.quantile(0.9) - row.quantile(0.1))
    return float(pd.Series(spreads).quantile(0.40))


def _run_journeys(prices, idx):
    """Run each milestone config and return dict of label -> daily returns."""
    gate = _calibrate_gate(prices)

    configs = {
        'Baseline\n(no TC)': dict(freq='ME', fade_lo=0.10, fade_hi=0.20,
                                  buffer=0.0, tc_bps=0.0),
        'Baseline\n(10bps TC,\n5% buffer)': dict(freq='ME', fade_lo=0.10, fade_hi=0.20,
                                                  buffer=0.05, tc_bps=10.0),
        '+ Vol target\n& abs filter': dict(freq='ME', fade_lo=0.05, fade_hi=0.15,
                                           buffer=0.05, tc_bps=10.0,
                                           vol_target=0.10, abs_momentum_filter=True),
        '+ Signal gate\n(skip-40%)': dict(freq='ME', fade_lo=0.10, fade_hi=0.20,
                                          buffer=0.05, tc_bps=10.0,
                                          vol_target=0.10, abs_momentum_filter=True,
                                          signal_gate=gate),
        'Final config': dict(freq='ME', fade_lo=0.10, fade_hi=0.20,
                             buffer=0.05, tc_bps=10.0,
                             vol_target=0.12, vol_target_lb=15,
                             signal_gate=gate,
                             abs_long_min=0.01, abs_short_max=-0.01),
    }

    # Flat 2% p.a. risk-free rate (approximation of BoE base rate avg 2013-2024).
    # True average was ~1% during 2013-2021 ZIRP and ~4% during 2022-2024 hiking
    # cycle. A time-varying series would require an external data feed.
    RISK_FREE_RATE = 0.02

    idx_ret = idx.pct_change(fill_method=None)
    results = {}
    for label, kw in configs.items():
        ret = _backtest(prices, idx, **kw)
        m   = compute_all_metrics(ret, idx_ret.reindex(ret.index).fillna(0),
                                  risk_free_rate=RISK_FREE_RATE)
        results[label] = {'ret': ret, 'metrics': m}
    return results, idx_ret


def chart_sharpe_journey(journey: dict) -> None:
    labels  = list(journey.keys())
    sharpes = [journey[l]['metrics']['sharpe_ratio'] for l in labels]
    colors  = [BLUE if s == max(sharpes) else GREY for s in sharpes]
    colors[-1] = BLUE

    fig = go.Figure(go.Bar(
        x=labels, y=sharpes,
        marker_color=colors,
        text=[f'{s:.2f}' for s in sharpes],
        textposition='outside',
    ))
    fig.update_layout(
        **_LAYOUT,
        title='Sharpe ratio at each development stage',
        yaxis=dict(title='Sharpe ratio', range=[min(0, min(sharpes)) - 0.05,
                                                max(sharpes) + 0.15]),
        xaxis=dict(tickfont=dict(size=11)),
        showlegend=False,
        height=400,
    )
    fig.add_hline(y=0, line_color=RED, line_dash='dash', line_width=1)
    _write(fig, 'sharpe_journey')


def chart_equity_curve(final_ret: pd.Series, idx: pd.Series) -> None:
    idx_ret   = idx.pct_change(fill_method=None).reindex(final_ret.index).fillna(0)
    strat_cum = (1 + final_ret).cumprod() * 100
    bench_cum = (1 + idx_ret).cumprod() * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=strat_cum.index, y=strat_cum.values,
        name='Strategy', line=dict(color=BLUE, width=2)))
    fig.add_trace(go.Scatter(
        x=bench_cum.index, y=bench_cum.values,
        name='FTSE 100', line=dict(color=GREY, width=1.5, dash='dot')))
    fig.update_layout(
        **_LAYOUT,
        title='Cumulative return — final config vs FTSE 100 (indexed to 100)',
        yaxis=dict(title='Value (rebased to 100)'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        height=400,
    )
    _write(fig, 'equity_curve')


def chart_drawdown(final_ret: pd.Series) -> None:
    cum = (1 + final_ret).cumprod()
    dd  = (cum / cum.cummax() - 1) * 100

    fig = go.Figure(go.Scatter(
        x=dd.index, y=dd.values,
        fill='tozeroy',
        fillcolor='rgba(220,38,38,0.15)',
        line=dict(color=RED, width=1),
        name='Drawdown',
    ))
    fig.update_layout(
        **_LAYOUT,
        title='Drawdown from peak — final config',
        yaxis=dict(title='Drawdown (%)'),
        height=350,
        showlegend=False,
    )
    _write(fig, 'drawdown')


def chart_annual_returns(final_ret: pd.Series) -> None:
    ann = {}
    for yr, grp in final_ret.groupby(final_ret.index.year):
        ann[yr] = float((1 + grp).prod() - 1) * 100

    years  = list(ann.keys())
    values = list(ann.values())
    colors = [GREEN if v >= 0 else RED for v in values]

    fig = go.Figure(go.Bar(
        x=years, y=values,
        marker_color=colors,
        text=[f'{v:+.1f}%' for v in values],
        textposition='outside',
    ))
    fig.update_layout(
        **_LAYOUT,
        title='Annual returns — final config',
        yaxis=dict(title='Return (%)'),
        height=380,
        showlegend=False,
    )
    fig.add_hline(y=0, line_color='#1a1a2e', line_width=0.5)
    _write(fig, 'annual_returns')


def chart_equity_journey(journey: dict, idx: pd.Series) -> None:
    """Overlay equity curves for each milestone on one chart."""
    idx_ret = idx.pct_change(fill_method=None)

    palette = [GREY, '#94a3b8', AMBER, PURPLE, BLUE]
    widths  = [1, 1, 1.5, 1.5, 2.5]
    dashes  = ['dot', 'dash', 'dash', 'dot', 'solid']

    fig = go.Figure()
    for (label, data), color, width, dash in zip(
            journey.items(), palette, widths, dashes):
        ret = data['ret']
        cum = (1 + ret).cumprod() * 100
        clean_label = label.replace('\n', ' ')
        fig.add_trace(go.Scatter(
            x=cum.index, y=cum.values,
            name=clean_label,
            line=dict(color=color, width=width, dash=dash),
        ))

    # FTSE 100 benchmark aligned to final config start
    final_ret   = list(journey.values())[-1]['ret']
    bench_start = final_ret.index[0]
    bench       = (1 + idx_ret.loc[bench_start:]).cumprod() * 100
    fig.add_trace(go.Scatter(
        x=bench.index, y=bench.values,
        name='FTSE 100',
        line=dict(color='#e5e7eb', width=1, dash='dot'),
    ))

    fig.update_layout(
        **_LAYOUT,
        title='Cumulative return — strategy evolution',
        yaxis=dict(title='Value (rebased to 100)'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0,
                    font=dict(size=10)),
        height=430,
    )
    _write(fig, 'equity_journey')


def save_results(final_metrics: dict) -> None:
    out = {k: float(v) if isinstance(v, (int, float, np.floating)) else v
           for k, v in final_metrics.items()}
    (ARTIFACTS / 'results.json').write_text(json.dumps(out, indent=2))


def main():
    print('Fetching price data...')
    prices, idx = fetch_all()
    idx_ret = idx.pct_change(fill_method=None)

    print('Running milestone backtests...')
    journey, idx_ret = _run_journeys(prices, idx)

    final_ret = journey['Final config']['ret']
    final_m   = journey['Final config']['metrics']

    print('Generating charts...')
    chart_sharpe_journey(journey)
    chart_equity_journey(journey, idx)
    chart_equity_curve(final_ret, idx)
    chart_drawdown(final_ret)
    chart_annual_returns(final_ret)

    print('Saving results.json...')
    save_results(final_m)

    print()
    print('Final config metrics:')
    for k in ['annualised_return_pct', 'sharpe_ratio', 'max_drawdown_pct',
              'sortino_ratio', 'annualised_volatility_pct']:
        print(f'  {k}: {final_m[k]:.2f}')
    print()
    print(f'Artifacts written to {ARTIFACTS}')


if __name__ == '__main__':
    main()
