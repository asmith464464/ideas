from pathlib import Path

import pandas as pd
import yfinance as yf

from data.fetchers.base_fetcher import BaseFetcher


class YFinanceFetcher(BaseFetcher):

    def __init__(self, cache_dir: Path, no_cache: bool = False):
        super().__init__(cache_dir)
        self.no_cache = no_cache

    def fetch(self, ticker: str, start: str, end: str, interval: str = '1d') -> pd.DataFrame:
        cache_path = self._cache_path(ticker, start, end, interval)

        if not self.no_cache and cache_path.exists():
            return pd.read_parquet(cache_path)

        raw = yf.download(
            ticker,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )

        if raw.empty:
            raise ValueError(f"No data returned for {ticker} ({start} to {end})")

        df = raw.copy()
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
        df.index.name = 'date'
        df['ticker'] = ticker

        df = df[['open', 'high', 'low', 'close', 'volume', 'ticker']]

        df.to_parquet(cache_path)
        return df
