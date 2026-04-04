from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class BaseFetcher(ABC):

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def fetch(self, ticker: str, start: str, end: str, interval: str = '1d') -> pd.DataFrame:
        ...

    def fetch_many(
        self,
        tickers: list[str],
        start: str,
        end: str,
        interval: str = '1d',
    ) -> dict[str, pd.DataFrame]:
        return {t: self.fetch(t, start, end, interval) for t in tickers}

    def _cache_path(self, ticker: str, start: str, end: str, interval: str) -> Path:
        key = f"{ticker}_{start}_{end}_{interval}.parquet"
        return self.cache_dir / key
