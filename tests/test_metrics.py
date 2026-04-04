import math
import numpy as np
import pandas as pd
import pytest

from research.metrics import compute_all_metrics

REQUIRED_KEYS = {
    'total_return_pct',
    'annualised_return_pct',
    'annualised_volatility_pct',
    'sharpe_ratio',
    'sortino_ratio',
    'max_drawdown_pct',
    'calmar_ratio',
    'win_rate_pct',
    'avg_trade_return_pct',
    'num_trades',
    'benchmark_return_pct',
    'information_ratio',
}

dates = pd.date_range('2020-01-01', periods=252, freq='B')
benchmark = pd.Series([0.0005] * 252, index=dates)


def test_zero_returns_all_finite():
    returns = pd.Series([0.0] * 252, index=dates)
    metrics = compute_all_metrics(returns, benchmark)
    assert set(metrics.keys()) == REQUIRED_KEYS
    for key, val in metrics.items():
        assert math.isfinite(val), f"{key} is not finite: {val}"


def test_constant_positive_return():
    returns = pd.Series([0.001] * 252, index=dates)
    metrics = compute_all_metrics(returns, benchmark)
    assert metrics['sharpe_ratio'] > 0
    assert metrics['max_drawdown_pct'] == 0.0
    assert metrics['total_return_pct'] > 0


def test_alternating_returns_win_rate():
    values = [0.01, -0.01] * 126
    returns = pd.Series(values, index=dates)
    metrics = compute_all_metrics(returns, benchmark)
    assert abs(metrics['win_rate_pct'] - 50.0) < 1.0
    expected_vol = 0.01 * np.sqrt(252) * 100
    assert abs(metrics['annualised_volatility_pct'] - expected_vol) < 0.5


def test_single_large_drawdown():
    values = [0.01] * 100 + [-0.5] + [0.0] * 151
    returns = pd.Series(values, index=dates)
    metrics = compute_all_metrics(returns, benchmark)
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    expected_mdd = float(((cumulative - rolling_max) / rolling_max).min() * 100)
    assert abs(metrics['max_drawdown_pct'] - expected_mdd) < 0.01


def test_all_required_keys_present():
    returns = pd.Series([0.001] * 252, index=dates)
    metrics = compute_all_metrics(returns, benchmark)
    assert set(metrics.keys()) == REQUIRED_KEYS
