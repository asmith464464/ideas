import numpy as np
import pandas as pd


TRADING_DAYS = 252


def total_return_pct(returns: pd.Series) -> float:
    return float(((1 + returns).prod() - 1) * 100)


def annualised_return_pct(returns: pd.Series) -> float:
    n = len(returns)
    if n == 0:
        return 0.0
    compounded = (1 + returns).prod()
    if compounded <= 0:
        return float('-inf')
    return float((compounded ** (TRADING_DAYS / n) - 1) * 100)


def annualised_volatility_pct(returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    return float(returns.std() * np.sqrt(TRADING_DAYS) * 100)


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    daily_rf = risk_free_rate / TRADING_DAYS
    excess = returns - daily_rf
    std = excess.std()
    if std == 0:
        return 0.0
    return float((excess.mean() / std) * np.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    daily_rf = risk_free_rate / TRADING_DAYS
    excess = returns - daily_rf
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float('inf') if excess.mean() > 0 else 0.0
    downside_std = np.sqrt((downside ** 2).mean()) * np.sqrt(TRADING_DAYS)
    if downside_std == 0:
        return 0.0
    return float((excess.mean() * TRADING_DAYS) / downside_std)


def max_drawdown_pct(returns: pd.Series) -> float:
    if len(returns) == 0:
        return 0.0
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    return float(drawdown.min() * 100)


def calmar_ratio(returns: pd.Series) -> float:
    ann_ret = annualised_return_pct(returns)
    mdd = abs(max_drawdown_pct(returns))
    if mdd == 0:
        return float('inf') if ann_ret > 0 else 0.0
    return float(ann_ret / mdd)


def win_rate_pct(returns: pd.Series) -> float:
    if len(returns) == 0:
        return 0.0
    return float((returns > 0).mean() * 100)


def _detect_trades(returns: pd.Series) -> list[pd.Series]:
    nonzero = returns[returns != 0]
    if len(nonzero) == 0:
        return []
    trades = []
    current_trade: list = []
    for i, (idx, val) in enumerate(nonzero.items()):
        if not current_trade:
            current_trade.append((idx, val))
        else:
            current_trade.append((idx, val))
    if current_trade:
        trades.append(pd.Series(dict(current_trade)))
    return trades


def avg_trade_return_pct(returns: pd.Series) -> float:
    nonzero = returns[returns != 0]
    if len(nonzero) == 0:
        return 0.0
    return float(nonzero.mean() * 100)


def num_trades(returns: pd.Series) -> int:
    signal_changes = returns != 0
    blocks = (signal_changes != signal_changes.shift()).cumsum()
    trade_blocks = blocks[signal_changes]
    return int(trade_blocks.nunique())


def benchmark_return_pct(benchmark_returns: pd.Series) -> float:
    return float(((1 + benchmark_returns).prod() - 1) * 100)


def information_ratio(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    aligned_strategy, aligned_bench = returns.align(benchmark_returns, join='inner')
    active = aligned_strategy - aligned_bench
    tracking_error = active.std() * np.sqrt(TRADING_DAYS)
    if tracking_error == 0:
        return 0.0
    active_return = (
        annualised_return_pct(aligned_strategy) - annualised_return_pct(aligned_bench)
    )
    return float(active_return / (tracking_error * 100))


def compute_all_metrics(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
) -> dict:
    return {
        'total_return_pct':          total_return_pct(returns),
        'annualised_return_pct':     annualised_return_pct(returns),
        'annualised_volatility_pct': annualised_volatility_pct(returns),
        'sharpe_ratio':              sharpe_ratio(returns, risk_free_rate),
        'sortino_ratio':             sortino_ratio(returns, risk_free_rate),
        'max_drawdown_pct':          max_drawdown_pct(returns),
        'calmar_ratio':              calmar_ratio(returns),
        'win_rate_pct':              win_rate_pct(returns),
        'avg_trade_return_pct':      avg_trade_return_pct(returns),
        'num_trades':                num_trades(returns),
        'benchmark_return_pct':      benchmark_return_pct(benchmark_returns),
        'information_ratio':         information_ratio(returns, benchmark_returns),
    }
