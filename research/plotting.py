from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


_LAYOUT = dict(
    template='plotly_dark',
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
)


def _write(fig: go.Figure, path: Path) -> None:
    path.write_text(pio.to_html(fig, full_html=False, include_plotlyjs='cdn'))


def _equity_curve_chart(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    config: dict,
) -> go.Figure:
    strat_cum = (1 + returns).cumprod() * 100
    bench_cum = (1 + benchmark_returns.reindex(returns.index).fillna(0)).cumprod() * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=strat_cum.index, y=strat_cum.values,
        name=config.get('name', 'Strategy'),
        line=dict(color='#4ecdc4', width=2),
    ))
    fig.add_trace(go.Scatter(
        x=bench_cum.index, y=bench_cum.values,
        name=config.get('benchmark', 'SPY'),
        line=dict(color='#888899', width=1.5, dash='dot'),
    ))
    fig.update_layout(
        **_LAYOUT,
        yaxis_title='Growth of $100',
        xaxis_title=None,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    )
    return fig


def _drawdown_chart(returns: pd.Series) -> go.Figure:
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=drawdown.index, y=drawdown.values,
        fill='tozeroy',
        fillcolor='rgba(255,107,107,0.3)',
        line=dict(color='#ff6b6b', width=1),
        name='Drawdown',
    ))
    fig.update_layout(
        **_LAYOUT,
        yaxis_title='Drawdown (%)',
        xaxis_title=None,
    )
    return fig


def _rolling_sharpe_chart(returns: pd.Series, window: int = 63) -> go.Figure:
    rolling = returns.rolling(window)
    rs = (rolling.mean() / rolling.std()) * np.sqrt(252)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rs.index, y=rs.values,
        line=dict(color='#4ecdc4', width=1.5),
        name=f'{window}-day Rolling Sharpe',
    ))
    fig.add_hline(y=0, line=dict(color='#888899', width=1, dash='dash'))
    fig.update_layout(
        **_LAYOUT,
        yaxis_title='Sharpe Ratio',
        xaxis_title=None,
    )
    return fig


def _returns_dist_chart(returns: pd.Series) -> go.Figure:
    from scipy.stats import norm

    mu = returns.mean()
    sigma = returns.std()
    if sigma == 0 or len(returns) < 2:
        sigma = 1e-10
    x_range = np.linspace(returns.min(), returns.max(), 200)
    normal_pdf = norm.pdf(x_range, mu, sigma)
    bin_width = (returns.max() - returns.min()) / 50 if returns.max() != returns.min() else 1e-10
    normal_scaled = normal_pdf * bin_width * len(returns)

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=returns.values,
        nbinsx=50,
        name='Daily Returns',
        marker_color='#4ecdc4',
        opacity=0.7,
    ))
    fig.add_trace(go.Scatter(
        x=x_range, y=normal_scaled,
        name='Normal',
        line=dict(color='#ff6b6b', width=2),
    ))
    fig.update_layout(
        **_LAYOUT,
        xaxis_title='Daily Return',
        yaxis_title='Count',
        bargap=0.05,
    )
    return fig


def build_all_charts(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    signals: pd.DataFrame,
    output_dir: Path,
    config: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    _write(_equity_curve_chart(returns, benchmark_returns, config), output_dir / 'equity_curve.html')
    _write(_drawdown_chart(returns), output_dir / 'drawdown.html')
    _write(_rolling_sharpe_chart(returns), output_dir / 'rolling_sharpe.html')
    _write(_returns_dist_chart(returns), output_dir / 'returns_dist.html')
