"""
Wikipedia daily pageviews fetcher.

Uses the Wikimedia Pageviews API — free, no API key, daily granularity back
to 2015, generous rate limits (~200 req/s).  A strong proxy for retail
attention: Wikipedia page traffic spikes sharply during market mania and
collapses (FTX: 44k peak views on collapse day; Dogecoin: 361k during
Elon spike).

Usage:
    fetcher = WikipediaFetcher(cache_dir=Path("data/cache"))
    df = fetcher.fetch_all(WIKI_ARTICLES, "2020-01-01", "2025-12-31")
    # Returns DataFrame: date x symbol, values = daily pageviews
"""

import time
from pathlib import Path

import pandas as pd
import requests

PAGEVIEWS_BASE = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
    "/en.wikipedia/all-access/all-agents"
)
HEADERS = {"User-Agent": "crypto-attention-research/1.0"}
SLEEP   = 0.3   # seconds between calls — well within free-tier limits


class WikipediaFetcher:

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir) / "004_wiki"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, symbol: str) -> Path:
        return self.cache_dir / f"{symbol}.parquet"

    def fetch_coin(
        self,
        symbol: str,
        article: str,
        start: str,
        end: str,
        force_refresh: bool = False,
    ) -> pd.Series:
        """
        Return daily Wikipedia pageviews for `article` as a Series indexed by date.
        Cached per symbol.
        """
        cache = self._cache_path(symbol)
        if not force_refresh and cache.exists():
            s = pd.read_parquet(cache).squeeze()
            s.index = pd.to_datetime(s.index)
            return s.rename(symbol)

        start_fmt = pd.Timestamp(start).strftime("%Y%m%d") + "00"
        end_fmt   = pd.Timestamp(end).strftime("%Y%m%d")   + "00"
        url = f"{PAGEVIEWS_BASE}/{article}/daily/{start_fmt}/{end_fmt}"

        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            time.sleep(SLEEP)
        except Exception as e:
            print(f"  [WARN] Wikipedia fetch failed for {symbol} ({article}): {e}")
            return pd.Series(dtype=float, name=symbol)

        if r.status_code != 200:
            print(f"  [WARN] Wikipedia {symbol}: HTTP {r.status_code} for '{article}'")
            return pd.Series(dtype=float, name=symbol)

        items = r.json().get("items", [])
        if not items:
            return pd.Series(dtype=float, name=symbol)

        s = pd.Series(
            {pd.Timestamp(i["timestamp"][:8]): i["views"] for i in items},
            name=symbol,
            dtype=float,
        )
        pd.DataFrame(s).to_parquet(cache)
        return s

    def fetch_all(
        self,
        articles: dict[str, str],   # {symbol: wikipedia_article_name}
        start: str,
        end: str,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Fetch pageviews for all symbols in `articles`.
        Returns DataFrame (date x symbol).  Missing coins return NaN column.
        """
        cached  = [s for s in articles if self._cache_path(s).exists() and not force_refresh]
        to_fetch = [s for s in articles if s not in cached]

        if cached:
            print(f"  Loading {len(cached)} coins from Wikipedia cache ...")
        if to_fetch:
            print(f"  Fetching {len(to_fetch)} coins from Wikimedia API ...")

        series_list = []
        for sym in list(articles):
            article = articles[sym]
            s = self.fetch_coin(sym, article, start, end, force_refresh=force_refresh)
            if not s.empty:
                series_list.append(s)

        if not series_list:
            return pd.DataFrame()

        df = pd.concat(series_list, axis=1).sort_index()
        df.index = pd.to_datetime(df.index)
        return df

    def weekly(self, daily: pd.DataFrame) -> pd.DataFrame:
        """Resample daily pageviews to weekly (Friday sum)."""
        return daily.resample("W-FRI").sum()
