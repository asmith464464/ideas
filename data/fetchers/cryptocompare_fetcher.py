"""
CryptoCompare daily OHLCV fetcher.

Used for idea 004 because CryptoCompare retains historical data for delisted
coins (LUNA, FTT, etc.) that yfinance no longer serves.

Free tier: no API key required for most historical data; rate limit ~50 req/min.
Max 2000 daily bars per call; paginates automatically for longer histories.

Usage:
    fetcher = CryptoCompareFetcher(cache_dir=Path("data/cache"))
    df = fetcher.fetch("BTC", "2020-01-01", "2025-12-31")
    # Returns DataFrame with columns: open, high, low, close, volume (USD)
"""

import time
from pathlib import Path

import pandas as pd
import requests

CC_BASE = "https://min-api.cryptocompare.com/data/v2"
SLEEP = 1.2   # seconds between calls


class CryptoCompareFetcher:

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, symbol: str, start: str, end: str) -> Path:
        return self.cache_dir / f"cc_{symbol}_{start}_{end}.parquet"

    def fetch(
        self,
        symbol: str,
        start: str,
        end: str,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Return daily OHLCV for `symbol` (e.g. "BTC", "LUNA") from start to end.
        Prices are in USD.  Returns empty DataFrame if no data available.
        """
        cache = self._cache_path(symbol, start, end)
        if not force_refresh and cache.exists():
            df = pd.read_parquet(cache)
            df.index = pd.to_datetime(df.index)
            return df

        start_ts = int(pd.Timestamp(start).timestamp())
        end_ts   = int(pd.Timestamp(end).timestamp())

        all_bars: list[dict] = []
        to_ts = end_ts

        while True:
            limit = min(2000, (to_ts - start_ts) // 86400 + 1)
            if limit <= 0:
                break

            try:
                r = requests.get(
                    f"{CC_BASE}/histoday",
                    params={
                        "fsym": symbol.upper(),
                        "tsym": "USD",
                        "limit": min(limit, 2000),
                        "toTs": to_ts,
                    },
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
                time.sleep(SLEEP)
            except Exception as e:
                print(f"  [WARN] CryptoCompare fetch failed for {symbol}: {e}")
                break

            if data.get("Response") != "Success":
                break

            bars = data["Data"]["Data"]
            if not bars:
                break

            # Filter to requested range
            bars = [b for b in bars if start_ts <= b["time"] <= end_ts]
            if not bars:
                break

            all_bars = bars + all_bars  # prepend older data

            earliest = bars[0]["time"]
            if earliest <= start_ts:
                break

            # Step back for next page
            to_ts = earliest - 86400

        if not all_bars:
            return pd.DataFrame()

        df = pd.DataFrame(all_bars)
        df["date"] = pd.to_datetime(df["time"], unit="s").dt.normalize()
        df = df.set_index("date")[["open", "high", "low", "close", "volumeto"]]
        df = df.rename(columns={"volumeto": "volume"})
        df = df[df["close"] > 0].sort_index()
        df = df[~df.index.duplicated(keep="last")]

        if not df.empty:
            df.to_parquet(cache)

        return df

    def fetch_weekly_close(self, symbol: str, start: str, end: str) -> pd.Series:
        """Return weekly (Friday) close prices as a Series."""
        df = self.fetch(symbol, start, end)
        if df.empty:
            return pd.Series(dtype=float, name=symbol)
        return df["close"].resample("W-FRI").last().rename(symbol)
