from pathlib import Path

import pandas as pd

from data.fetchers.yfinance_fetcher import YFinanceFetcher
from research.base_strategy import BaseStrategy


class TimeSeriesMomentum(BaseStrategy):

    def fetch_data(self) -> pd.DataFrame:
        fetcher = YFinanceFetcher(cache_dir=Path('data/cache'))
        universe = self.config['universe']
        frames = fetcher.fetch_many(
            universe,
            self.config['date_range']['start'],
            self.config['date_range']['end'],
        )
        combined = pd.concat(
            {ticker: df['close'] for ticker, df in frames.items()},
            axis=1,
        )
        combined.columns.name = None
        return combined

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        lookback = self.config['lookback_days']
        skip     = self.config['skip_days']
        signals  = pd.DataFrame(index=data.index, columns=data.columns, dtype=float)

        for col in data.columns:
            price = data[col].dropna()
            sig   = pd.Series(0.0, index=price.index)
            for i in range(lookback, len(price)):
                past_price    = price.iloc[i - lookback]
                lookback_return = (price.iloc[i - skip] / past_price) - 1
                sig.iloc[i] = 1.0 if lookback_return > 0 else -1.0
            signals[col] = sig

        return signals

    def backtest(self, signals: pd.DataFrame) -> dict:
        fetcher = YFinanceFetcher(cache_dir=Path('data/cache'))
        universe = self.config['universe']
        frames = fetcher.fetch_many(
            universe,
            self.config['date_range']['start'],
            self.config['date_range']['end'],
        )
        prices = pd.concat(
            {ticker: df['close'] for ticker, df in frames.items()},
            axis=1,
        )
        prices.columns.name = None

        daily_returns = prices.pct_change()

        rebalance_dates = self._monthly_rebalance_dates(signals.index)

        tc_bps       = self.config.get('transaction_cost_bps', 5)
        tc_per_trade = tc_bps / 10_000

        portfolio_returns = pd.Series(0.0, index=daily_returns.index)
        prev_weights      = pd.Series(0.0, index=signals.columns)

        active_weights = pd.Series(0.0, index=signals.columns)

        for date in daily_returns.index:
            if date in rebalance_dates:
                sig = signals.loc[date]
                long_tickers  = sig[sig == 1].index.tolist()
                short_tickers = sig[sig == -1].index.tolist()

                new_weights = pd.Series(0.0, index=signals.columns)
                if long_tickers:
                    new_weights[long_tickers] = 1.0 / len(long_tickers)
                if short_tickers:
                    new_weights[short_tickers] = -1.0 / len(short_tickers)

                turnover = (new_weights - prev_weights).abs().sum()
                tc_drag  = turnover * tc_per_trade

                active_weights = new_weights
                prev_weights   = new_weights.copy()
            else:
                tc_drag = 0.0

            if date in daily_returns.index:
                day_ret = (active_weights * daily_returns.loc[date].fillna(0)).sum()
                portfolio_returns[date] = day_ret - tc_drag

        valid_start = signals[signals.abs().sum(axis=1) > 0].index
        if len(valid_start):
            portfolio_returns = portfolio_returns.loc[valid_start[0]:]

        signal_rows = signals.loc[portfolio_returns.index].tail(50).copy()
        signal_rows['date'] = signal_rows.index
        long_count  = (signals == 1).sum(axis=1)
        short_count = (signals == -1).sum(axis=1)
        signal_summary = pd.DataFrame({
            'long_count':  long_count,
            'short_count': short_count,
        }, index=signals.index).tail(50)

        return {
            'returns':     portfolio_returns,
            'signal_rows': signal_summary,
        }

    def _monthly_rebalance_dates(self, index: pd.DatetimeIndex) -> set:
        s = pd.Series(index, index=index)
        return set(s.resample('ME').last().dropna().values)
