import json
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from research.metrics import compute_all_metrics
from research.plotting import build_all_charts


class BaseStrategy(ABC):

    def __init__(self, idea_dir: Path, config: dict):
        self.idea_dir  = idea_dir
        self.config    = config
        self.name      = config['name']
        self.slug      = config['slug']
        self.version   = config.get('version', '0.1.0')
        self.artifacts = idea_dir / 'artifacts'
        self.artifacts.mkdir(exist_ok=True)
        (self.artifacts / 'charts').mkdir(exist_ok=True)

    @abstractmethod
    def fetch_data(self) -> pd.DataFrame:
        ...

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        ...

    @abstractmethod
    def backtest(self, signals: pd.DataFrame) -> dict:
        ...

    def run(self) -> None:
        data        = self.fetch_data()
        signals     = self.generate_signals(data)
        result      = self.backtest(signals)
        returns     = result['returns']
        signal_rows = result['signal_rows']
        benchmark   = self._fetch_benchmark()

        metrics = compute_all_metrics(
            returns=returns,
            benchmark_returns=benchmark,
            risk_free_rate=self.config.get('risk_free_rate', 0.0),
        )

        self._write_json(self.artifacts / 'results.json', metrics)
        self._write_json(
            self.artifacts / 'signal_table.json',
            signal_rows.reset_index().to_dict(orient='records'),
        )

        build_all_charts(
            returns=returns,
            benchmark_returns=benchmark,
            signals=signals,
            output_dir=self.artifacts / 'charts',
            config=self.config,
        )

        print(f"  [{self.slug}] artifacts written to {self.artifacts}")

    def generate_extra_charts(self, returns, signals, output_dir):
        pass

    def _fetch_benchmark(self) -> pd.Series:
        from data.fetchers.yfinance_fetcher import YFinanceFetcher
        fetcher = YFinanceFetcher(cache_dir=Path('data/cache'))
        df = fetcher.fetch(
            self.config.get('benchmark', 'SPY'),
            self.config['date_range']['start'],
            self.config['date_range']['end'],
        )
        return df['close'].pct_change().dropna()

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.write_text(json.dumps(data, indent=2, default=str))
