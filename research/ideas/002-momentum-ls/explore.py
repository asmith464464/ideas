"""
Exploratory analysis for idea 002 -- multi-timeframe momentum long/short (FTSE 100).
Run from repo root: python research/ideas/002-momentum-ls/explore.py [section]

Sections:
  data        -- data availability and coverage
  signals     -- momentum score distributions and component correlations
  regime      -- regime frequency, duration, transitions
  packets     -- portfolio composition and packet-boundary behaviour over time
  turnover    -- monthly rebalance turnover and TC sensitivity
  baseline    -- simple walk-forward backtest of composite signal
  universe    -- expanded universe coverage and survivorship bias assessment
  turnover_grid  -- compare turnover/alpha across rebalance freq, packet width, buffer rules
  all         -- run all sections (default)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from data.fetchers.yfinance_fetcher import YFinanceFetcher

# -----------------------------------------------------------------------
# Universe definition — FTSE 100 (large cap)
#
# Current constituents + historical members with surviving yfinance tickers.
# Uses return-based cleaning (cap daily moves at ±75%) to handle yfinance
# corporate action data errors. At each rebalance, only stocks with
# MIN_HISTORY days of data up to that date are included (point-in-time
# approximation for stocks that listed mid-backtest).
#
# FTSE 250 expansion was tested but degraded Sharpe significantly — yfinance
# data quality for mid-caps is poor and momentum signal is weaker. Retained
# FTSE 100 only. See notes.md for details.
#
# Residual survivorship bias: M&A targets (GKN, Shire, BG Group, etc.) with
# no surviving ticker cannot be included. Cannot be eliminated without a
# commercial constituent history feed.
# -----------------------------------------------------------------------

UNIVERSE_TICKERS = [
    # FTSE 100 — current constituents + historical members with surviving tickers
    # (Tested FTSE 250 expansion: see notes.md — degraded performance due to
    #  data quality issues and weaker momentum signal in mid-caps via yfinance)
    'AZN.L',  'SHEL.L', 'HSBA.L', 'ULVR.L', 'BP.L',   'RIO.L',  'GSK.L',
    'DGE.L',  'LLOY.L', 'BATS.L', 'AAL.L',  'GLEN.L', 'VOD.L',  'NG.L',
    'PRU.L',  'BARC.L', 'NWG.L',  'IMB.L',  'REL.L',  'SSE.L',  'WPP.L',
    'TSCO.L', 'ABF.L',  'EXPN.L', 'HLMA.L', 'RKT.L',  'JD.L',   'FRES.L',
    'BRBY.L', 'IHG.L',  'CPG.L',  'CNA.L',  'LGEN.L', 'BA.L',   'STAN.L',
    'III.L',  'CRDA.L', 'SGRO.L', 'DPLM.L', 'AUTO.L', 'RTO.L',  'PSON.L',
    'INF.L',  'MKS.L',  'FLTR.L', 'OCDO.L', 'BT-A.L', 'LAND.L', 'SBRY.L',
    'CCH.L',  'ADM.L',  'ANTO.L', 'AHT.L',  'BME.L',  'BNZL.L', 'DCC.L',
    'EMG.L',  'ENT.L',  'HLN.L',  'HWDN.L', 'IGG.L',  'KGF.L',  'MNDI.L',
    'NXT.L',  'PSH.L',  'PHNX.L', 'SDR.L',  'SMT.L',  'SN.L',   'SPX.L',
    'TATE.L', 'UTG.L',  'VTY.L',  'WEIR.L', 'WG.L',   'WTB.L',  'HBR.L',
    'TLW.L',  'OSB.L',  'ITRK.L', 'GNS.L',  'SMIN.L', 'SRP.L',  'SGE.L',
    'BKG.L',  'PSN.L',  'BWY.L',  'TW.L',   'BLND.L', 'HMSO.L', 'GRI.L',
    'UU.L',   'SVT.L',  'PNN.L',  'CPI.L',  'CAPE.L', 'BVS.L',  'RS1.L',
    'PCT.L',  'MRO.L',  'MRW.L',  'RWS.L',  'JET2.L', 'FRAS.L', 'WDS.L',
]

UNIVERSE = sorted(set(UNIVERSE_TICKERS))

INDEX     = '^FTSE'
START     = '2010-01-01'
END       = '2024-12-31'

# Signal constants (trading days)
W1_LO, W1_HI = 21,  63    # 1-3m
W2_LO, W2_HI = 126, 252   # 6-12m
W3_LO, W3_HI = 252, 378   # 12-18m
MIN_HISTORY  = W3_HI + 63  # 441 days to compute all signals


def _clean_series(s: pd.Series, max_daily_move: float = 0.75) -> pd.Series:
    """
    Return-based cleaning: cap each daily return at ±max_daily_move and
    reconstruct a clean price index from those capped returns.

    This is robust to all types of yfinance data corruption:
      - single-day spikes (unadjusted splits, corporate actions)
      - multi-day blocks at the wrong price scale (e.g. two securities merged)
    The original price LEVEL is irrelevant; only relative returns are used
    downstream in momentum signals and the backtest, so reconstructing a
    return-based index (starting at 1.0) is equivalent.

    max_daily_move=0.75 caps at ±75% per day. Real large moves (e.g. -50%
    COVID crash) are preserved; +10,000% artifacts become +75%.
    """
    ret = s.pct_change(fill_method=None).fillna(0)
    capped = ret.clip(-max_daily_move, max_daily_move)
    return (1 + capped).cumprod().rename(s.name)


def fetch_all(tickers: list[str] = UNIVERSE) -> tuple[pd.DataFrame, pd.Series]:
    fetcher = YFinanceFetcher(cache_dir=Path('data/cache'))
    frames, failed = {}, []
    for t in tickers:
        try:
            df = fetcher.fetch(t, START, END)
            s = _clean_series(df['close'].dropna())
            # Accept any stock with at least 63 days of data.
            # MIN_HISTORY enforcement happens per-rebalance-date inside _backtest
            # so mid-backtest listings are included rather than dropped entirely.
            if len(s) >= 63:
                frames[t] = s
        except Exception:
            failed.append(t)
    if failed:
        print(f'  Skipped (fetch failed): {len(failed)} tickers')
    idx_df   = fetcher.fetch(INDEX, START, END)
    prices   = pd.DataFrame(frames)
    return prices, idx_df['close']


# ---------------------------------------------------------------------------
# Signal helpers
# ---------------------------------------------------------------------------

def _vol_window(prices: pd.DataFrame, lo: int, hi: int) -> pd.DataFrame:
    daily = prices.pct_change(fill_method=None)
    out   = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    arr   = daily.to_numpy()
    for i in range(hi, len(prices)):
        window = arr[i - hi:i - lo]
        out.iloc[i] = np.nanstd(window, axis=0) * np.sqrt(252)
    return out


def _momentum_signals(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    r1 = prices.shift(W1_LO) / prices.shift(W1_HI) - 1
    r2 = prices.shift(W2_LO) / prices.shift(W2_HI) - 1
    r3 = prices.shift(W3_LO) / prices.shift(W3_HI) - 1
    v1 = _vol_window(prices, W1_LO, W1_HI)
    v2 = _vol_window(prices, W2_LO, W2_HI)
    v3 = _vol_window(prices, W3_LO, W3_HI)
    s1 = r1 / v1.replace(0, np.nan)
    s2 = r2 / v2.replace(0, np.nan)
    s3 = r3 / v3.replace(0, np.nan)
    return 0.20 * s1 + 0.50 * s2 + 0.30 * s3, s1, s2, s3


def _residual_momentum_signals(prices: pd.DataFrame, index_px: pd.Series) -> pd.DataFrame:
    """
    Momentum signal with market beta removed before ranking.
    For each stock and each horizon, compute:
        residual_return = stock_return - beta_i * index_return
    where beta_i is the rolling 252-day regression beta.
    Ranking on residual return isolates stock-specific momentum from
    market-wide trends, reducing noise from broad market swings.
    """
    daily     = prices.pct_change(fill_method=None)
    idx_daily = index_px.pct_change(fill_method=None)

    rolling_var = idx_daily.rolling(252).var()
    beta        = daily.apply(lambda col: col.rolling(252).cov(idx_daily)).div(
                      rolling_var, axis=0)

    r1 = prices.shift(W1_LO) / prices.shift(W1_HI) - 1
    r2 = prices.shift(W2_LO) / prices.shift(W2_HI) - 1
    r3 = prices.shift(W3_LO) / prices.shift(W3_HI) - 1

    idx_r1 = (index_px.shift(W1_LO) / index_px.shift(W1_HI) - 1)
    idx_r2 = (index_px.shift(W2_LO) / index_px.shift(W2_HI) - 1)
    idx_r3 = (index_px.shift(W3_LO) / index_px.shift(W3_HI) - 1)

    res1 = r1.sub(beta.mul(idx_r1, axis=0))
    res2 = r2.sub(beta.mul(idx_r2, axis=0))
    res3 = r3.sub(beta.mul(idx_r3, axis=0))

    v1 = _vol_window(prices, W1_LO, W1_HI)
    v2 = _vol_window(prices, W2_LO, W2_HI)
    v3 = _vol_window(prices, W3_LO, W3_HI)

    s1 = res1 / v1.replace(0, np.nan)
    s2 = res2 / v2.replace(0, np.nan)
    s3 = res3 / v3.replace(0, np.nan)
    return 0.20 * s1 + 0.50 * s2 + 0.30 * s3


def _xsz_momentum_signals(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Multi-horizon momentum using cross-sectional z-scores of each component.
    Rather than dividing by each stock's own volatility (time-series scaling),
    z-score each component cross-sectionally at each date so all three
    horizons contribute equally in standardised units.
    Lower turnover than raw returns — z-scoring smooths extreme rank jumps.
    """
    r1 = prices.shift(W1_LO) / prices.shift(W1_HI) - 1
    r2 = prices.shift(W2_LO) / prices.shift(W2_HI) - 1
    r3 = prices.shift(W3_LO) / prices.shift(W3_HI) - 1

    def csz(df: pd.DataFrame) -> pd.DataFrame:
        mu    = df.mean(axis=1)
        sigma = df.std(axis=1).replace(0, np.nan)
        return df.sub(mu, axis=0).div(sigma, axis=0)

    return 0.20 * csz(r1) + 0.50 * csz(r2) + 0.30 * csz(r3)


def _regime(index_px: pd.Series, vol_window: int = 20) -> pd.Series:
    rv   = index_px.pct_change(fill_method=None).rolling(vol_window).std() * np.sqrt(252)
    pct  = rv.expanding().rank(pct=True)
    reg  = pd.Series('normal', index=index_px.index)
    reg[pct < 0.15] = 'low'
    reg[pct > 0.85] = 'high'
    return reg


def _rebalance_dates(score: pd.DataFrame, freq: str = 'ME') -> list:
    trading = score.dropna(how='all').index
    first   = trading[MIN_HISTORY]
    cal     = pd.date_range(first, trading[-1], freq=freq)
    return [trading[trading <= d][-1] for d in cal if len(trading[trading <= d]) > 0]


def _packet_weights(scores_row: pd.Series, fade_lo: float = 0.10,
                    fade_hi: float = 0.20,
                    sector_map: dict | None = None,
                    abs_ret_row: pd.Series | None = None) -> pd.Series:
    """
    Packet weighting with optional enhancements:
      sector_map:   {ticker: sector} — if provided, ranking is done within sector
                    before combining into a single book
      abs_ret_row:  12m absolute returns — if provided, shorts are suppressed
                    for any stock with a positive absolute 12m return
    """
    valid = scores_row.dropna()
    if len(valid) < 10:
        return pd.Series(0.0, index=scores_row.index)

    if sector_map is not None:
        # Rank within each sector, then combine
        sector_scores = {}
        for ticker, score in valid.items():
            sec = sector_map.get(ticker, 'Unknown')
            sector_scores.setdefault(sec, {})[ticker] = score

        w = pd.Series(0.0, index=valid.index)
        for sec, sec_tickers in sector_scores.items():
            if len(sec_tickers) < 3:
                continue
            sec_s = pd.Series(sec_tickers)
            ranks = sec_s.rank(pct=True)
            for ticker, r in ranks.items():
                if r >= (1.0 - fade_lo):
                    w[ticker] = 1.0
                elif r >= (1.0 - fade_hi):
                    w[ticker] = (r - (1.0 - fade_hi)) / (fade_hi - fade_lo)
                elif r <= fade_lo:
                    w[ticker] = -1.0
                elif r <= fade_hi:
                    w[ticker] = -((fade_hi - r) / (fade_hi - fade_lo))
    else:
        ranks = valid.rank(pct=True)
        w     = pd.Series(0.0, index=valid.index)
        for ticker, r in ranks.items():
            if r >= (1.0 - fade_lo):
                w[ticker] = 1.0
            elif r >= (1.0 - fade_hi):
                w[ticker] = (r - (1.0 - fade_hi)) / (fade_hi - fade_lo)
            elif r <= fade_lo:
                w[ticker] = -1.0
            elif r <= fade_hi:
                w[ticker] = -((fade_hi - r) / (fade_hi - fade_lo))

    # Absolute momentum filter: suppress shorts for stocks with positive 12m return
    if abs_ret_row is not None:
        for ticker in w.index:
            if w.get(ticker, 0) < 0:
                ar = abs_ret_row.get(ticker, np.nan)
                if pd.notna(ar) and ar > 0:
                    w[ticker] = 0.0

    long_sum  = w[w > 0].sum()
    short_sum = w[w < 0].sum()
    if long_sum  > 0: w[w > 0] /= long_sum
    if short_sum < 0: w[w < 0] /= abs(short_sum)

    result = pd.Series(0.0, index=scores_row.index)
    result.update(w)
    return result


def _continuous_packet_weights(scores_row: pd.Series,
                               abs_ret_row: pd.Series | None = None) -> pd.Series:
    """
    Continuous weight allocation proportional to cross-sectional rank.
    Weight_i = 2 * (rank_pct_i - 0.5), giving linear range [-1, +1].
    The top-ranked stock gets +1, the median gets 0, the bottom gets -1.
    Longs and shorts are normalised separately to unit gross exposure.
    Lower turnover than discrete packets because small rank changes
    cause small weight changes rather than crossing a bucket boundary.
    """
    valid = scores_row.dropna()
    if len(valid) < 10:
        return pd.Series(0.0, index=scores_row.index)

    ranks = valid.rank(pct=True)
    w     = (ranks - 0.5) * 2

    if abs_ret_row is not None:
        for ticker in w.index:
            if w.get(ticker, 0) < 0:
                ar = abs_ret_row.get(ticker, np.nan)
                if pd.notna(ar) and ar > 0:
                    w[ticker] = 0.0

    long_sum  = w[w > 0].sum()
    short_sum = w[w < 0].sum()
    if long_sum  > 0: w[w > 0] /= long_sum
    if short_sum < 0: w[w < 0] /= abs(short_sum)

    result = pd.Series(0.0, index=scores_row.index)
    result.update(w)
    return result


# GICS-style sector map for the universe
# Approximate — based on primary business activity
SECTOR_MAP = {
    'AZN.L':  'Healthcare', 'GSK.L':   'Healthcare', 'HLN.L':  'Healthcare',
    'SHP.L':  'Healthcare', 'BTG.L':   'Healthcare',
    'SHEL.L': 'Energy',     'BP.L':    'Energy',     'TLW.L':  'Energy',
    'HBR.L':  'Energy',
    'HSBA.L': 'Financials', 'BARC.L':  'Financials', 'LLOY.L': 'Financials',
    'NWG.L':  'Financials', 'STAN.L':  'Financials', 'LGEN.L': 'Financials',
    'PRU.L':  'Financials', 'III.L':   'Financials', 'OSB.L':  'Financials',
    'PSH.L':  'Financials', 'PHNX.L':  'Financials', 'SDR.L':  'Financials',
    'IGG.L':  'Financials', 'ITRK.L':  'Industrials',
    'RIO.L':  'Materials',  'AAL.L':   'Materials',  'GLEN.L': 'Materials',
    'FRES.L': 'Materials',  'ANTO.L':  'Materials',  'MNDI.L': 'Materials',
    'WEIR.L': 'Industrials','CRDA.L':  'Materials',
    'ULVR.L': 'ConsumerStaples','DGE.L':'ConsumerStaples','BATS.L':'ConsumerStaples',
    'IMB.L':  'ConsumerStaples','ABF.L':'ConsumerStaples','TSCO.L':'ConsumerStaples',
    'SBRY.L': 'ConsumerStaples','MKS.L':'ConsumerDiscretionary','RKT.L':'ConsumerStaples',
    'CCH.L':  'ConsumerStaples','TATE.L':'ConsumerStaples',
    'VOD.L':  'Telecom',    'BT-A.L':  'Telecom',
    'NG.L':   'Utilities',  'SSE.L':   'Utilities',  'UU.L':   'Utilities',
    'SVT.L':  'Utilities',  'PNN.L':   'Utilities',  'CPI.L':  'Utilities',
    'REL.L':  'Technology', 'EXPN.L':  'Technology', 'SGRO.L': 'RealEstate',
    'LAND.L': 'RealEstate', 'BLND.L':  'RealEstate', 'HMSO.L': 'RealEstate',
    'BKG.L':  'RealEstate', 'PSN.L':   'RealEstate', 'BWY.L':  'RealEstate',
    'TW.L':   'RealEstate', 'GRI.L':   'RealEstate',
    'WPP.L':  'ConsumerDiscretionary','BRBY.L':'ConsumerDiscretionary',
    'IHG.L':  'ConsumerDiscretionary','AUTO.L':'ConsumerDiscretionary',
    'JD.L':   'ConsumerDiscretionary','CPG.L': 'ConsumerDiscretionary',
    'MRW.L':  'ConsumerStaples',
    'BA.L':   'Industrials', 'HLMA.L':  'Industrials','RTO.L':  'Industrials',
    'DPLM.L': 'Industrials', 'INF.L':   'Industrials','ADM.L':  'Industrials',
    'AHT.L':  'Industrials', 'BNZL.L':  'Industrials','WG.L':   'Industrials',
    'HWDN.L': 'Industrials', 'CAPE.L':  'Industrials','SRP.L':  'Industrials',
    'SN.L':   'Industrials', 'SMIN.L':  'Industrials','BVS.L':  'Industrials',
    'RS1.L':  'Industrials', 'MELR.L':  'Industrials','SPX.L':  'Industrials',
    'FLTR.L': 'ConsumerDiscretionary','OCDO.L':'ConsumerDiscretionary',
    'NXT.L':  'ConsumerDiscretionary','KGF.L': 'ConsumerDiscretionary',
    'WTB.L':  'ConsumerDiscretionary','FRAS.L':'ConsumerDiscretionary',
    'ENT.L':  'ConsumerDiscretionary','TPK.L': 'ConsumerDiscretionary',
    'JET2.L': 'ConsumerDiscretionary',
    'PSON.L': 'Technology',  'SGE.L':   'Technology', 'SMT.L':  'Technology',
    'RWS.L':  'Technology',  'DARK.L':  'Technology', 'DCC.L':  'Technology',
    'BME.L':  'Healthcare',  'EMG.L':   'Financials', 'GNS.L':  'Healthcare',
    'CNA.L':  'Industrials', 'UTG.L':   'Utilities',  'VTY.L':  'RealEstate',
    'WDS.L':  'Energy',      'CLLN.L':  'Industrials','PCT.L':  'Technology',
    'BOO.L':  'ConsumerDiscretionary', 'FLTRF.L':'ConsumerDiscretionary',
}


def _backtest(prices: pd.DataFrame, index_px: pd.Series,
              freq: str = 'ME',
              fade_lo: float = 0.10, fade_hi: float = 0.20,
              buffer: float = 0.0,
              tc_bps: float = 0.0,
              regime_scale: bool = False,
              sector_neutral: bool = False,
              vol_target: float | None = None,
              vol_target_lb: int = 20,
              adaptive_vol_lb: bool = False,
              abs_momentum_filter: bool = False,
              abs_long_min: float = 0.0,
              abs_short_max: float = 0.0,
              signal_gate: float | None = None,
              adaptive_gate: bool = False,
              adaptive_gate_low: float = 0.20,
              adaptive_gate_normal: float = 0.40,
              adaptive_gate_high: float = 0.60,
              residual_momentum: bool = False,
              xsz_signal: bool = False,
              continuous_weights: bool = False) -> pd.Series:
    """
    Full backtest.

    Signal gate flags:
      signal_gate:          fixed threshold (p90-p10 spread); skip if below
      adaptive_gate:        vary gate percentile by vol regime:
                            low → gate_low, normal → gate_normal, high → gate_high
                            Each percentile is calibrated expanding over the run.

    Vol target flags:
      vol_target:           annualised target (e.g. 0.10)
      vol_target_lb:        lookback days for realised vol (default 20)
      adaptive_vol_lb:      shorten lookback in high-vol regimes:
                            low→40d, normal→20d, high→10d

    Abs momentum filter flags:
      abs_momentum_filter:  suppress positions below threshold (legacy: thresholds = 0)
      abs_long_min:         suppress long if 12m abs return < this (e.g. 0.02)
      abs_short_max:        suppress short if 12m abs return > this (e.g. -0.02)
    """
    if residual_momentum:
        score = _residual_momentum_signals(prices, index_px)
    elif xsz_signal:
        score = _xsz_momentum_signals(prices)
    else:
        score, _, _, _ = _momentum_signals(prices)
    reg            = _regime(index_px)
    reb_dates      = set(_rebalance_dates(score, freq))
    daily_ret      = prices.pct_change(fill_method=None)
    port_ret       = pd.Series(0.0, index=daily_ret.index)
    cur_w          = pd.Series(dtype=float)
    tc             = tc_bps / 10_000
    scale_map      = {'low': 1.2, 'normal': 1.0, 'high': 0.6}

    # Pre-compute absolute 12m return
    abs_12m = prices.shift(21) / prices.shift(252) - 1

    # Expanding spread history for adaptive gate (maps regime → sorted spread list)
    spread_hist: list[float] = []

    port_vol_hist: list[float] = []

    smap = SECTOR_MAP if sector_neutral else None

    for i, date in enumerate(daily_ret.index):
        if date in reb_dates:
            eligible = [
                col for col in prices.columns
                if prices[col].loc[:date].dropna().shape[0] >= MIN_HISTORY
            ]
            row      = score.loc[date, eligible]
            valid_row = row.dropna()

            # --- Signal gate decision ---
            if len(valid_row) >= 10:
                spread = float(valid_row.quantile(0.9) - valid_row.quantile(0.1))

                if adaptive_gate:
                    # Determine threshold as expanding percentile, adjusted per regime
                    r       = reg.get(date, 'normal')
                    pct_map = {'low': adaptive_gate_low,
                               'normal': adaptive_gate_normal,
                               'high': adaptive_gate_high}
                    pct     = pct_map[r]
                    if len(spread_hist) >= 10:
                        threshold = float(pd.Series(spread_hist).quantile(pct))
                        if spread < threshold:
                            spread_hist.append(spread)
                            continue
                    spread_hist.append(spread)
                elif signal_gate is not None:
                    if spread < signal_gate:
                        continue

            # --- Build abs-momentum-aware filter ---
            abs_r = None
            if abs_momentum_filter or abs_long_min != 0.0 or abs_short_max != 0.0:
                abs_r = abs_12m.loc[date, eligible]

            if continuous_weights:
                new_w = _continuous_packet_weights(row, abs_ret_row=abs_r)
            else:
                new_w = _packet_weights(row, fade_lo=fade_lo, fade_hi=fade_hi,
                                        sector_map=smap, abs_ret_row=abs_r)

            # Conviction thresholds: stricter than the legacy "> 0 / < 0" filter
            if abs_r is not None and (abs_long_min != 0.0 or abs_short_max != 0.0):
                for ticker in list(new_w.index):
                    w_val = new_w.get(ticker, 0.0)
                    ar    = abs_r.get(ticker, np.nan)
                    if pd.isna(ar):
                        continue
                    if w_val > 0 and ar < abs_long_min:
                        new_w[ticker] = 0.0
                    elif w_val < 0 and ar > abs_short_max:
                        new_w[ticker] = 0.0
                # Re-normalise after any zeroing
                long_sum  = new_w[new_w > 0].sum()
                short_sum = new_w[new_w < 0].sum()
                if long_sum  > 0: new_w[new_w > 0] /= long_sum
                if short_sum < 0: new_w[new_w < 0] /= abs(short_sum)

            if regime_scale and vol_target is None:
                scale = scale_map.get(reg.get(date, 'normal'), 1.0)
                new_w = new_w * scale

            if buffer > 0 and len(cur_w) > 0:
                all_t       = cur_w.index.union(new_w.index)
                diff        = (new_w.reindex(all_t).fillna(0) -
                               cur_w.reindex(all_t).fillna(0)).abs()
                update_mask = diff > buffer
                merged      = cur_w.reindex(all_t).fillna(0).copy()
                merged[update_mask] = new_w.reindex(all_t).fillna(0)[update_mask]
                new_w = merged

            if len(cur_w) > 0 and tc > 0:
                all_t    = cur_w.index.union(new_w.index)
                turnover = (new_w.reindex(all_t).fillna(0) -
                            cur_w.reindex(all_t).fillna(0)).abs().sum()
                port_ret[date] -= turnover * tc
            cur_w = new_w

        if len(cur_w) > 0:
            dr      = daily_ret.loc[date]
            aligned = cur_w.reindex(dr.index).fillna(0)
            day_ret = float((aligned * dr.fillna(0)).sum())

            if vol_target is not None:
                if adaptive_vol_lb:
                    r  = reg.get(date, 'normal')
                    lb = {'low': 40, 'normal': 20, 'high': 10}[r]
                else:
                    lb = vol_target_lb
                if len(port_vol_hist) >= lb:
                    realised_vol = float(np.std(port_vol_hist[-lb:]) * np.sqrt(252))
                    if realised_vol > 0:
                        scale = min(max(vol_target / realised_vol, 0.5), 1.5)
                        day_ret *= scale

            port_ret[date] += day_ret
            port_vol_hist.append(day_ret)

    first_reb = min(reb_dates)
    return port_ret[port_ret.index >= first_reb]


def _summary(ret: pd.Series, idx_ret: pd.Series, label: str) -> dict:
    from research.metrics import compute_all_metrics
    m = compute_all_metrics(ret, idx_ret.reindex(ret.index).fillna(0))
    print(f'  {label:<52} ann={m["annualised_return_pct"]:>5.1f}%  '
          f'sharpe={m["sharpe_ratio"]:>5.2f}  dd={m["max_drawdown_pct"]:>6.1f}%')
    return m


# ---------------------------------------------------------------------------
# Section: data / universe
# ---------------------------------------------------------------------------

def section_universe(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print('\n=== UNIVERSE COVERAGE ===')
    n = len(prices.columns)
    sufficient = (prices.count() >= MIN_HISTORY).sum()
    print(f'Tickers fetched (any data): {n}')
    print(f'Tickers with full MIN_HISTORY ({MIN_HISTORY}d, ~1.75yr): {sufficient}')
    print(f'Mid-backtest listings (added dynamically as they reach MIN_HISTORY): {n - sufficient}')
    print()

    # History by start year
    by_year = {}
    for col in prices.columns:
        yr = prices[col].dropna().index[0].year
        by_year.setdefault(yr, []).append(col)
    print('Start year distribution:')
    for yr in sorted(by_year):
        print(f'  {yr}: {len(by_year[yr]):3d} tickers  {", ".join(by_year[yr][:6])}'
              f'{"..." if len(by_year[yr]) > 6 else ""}')

    # Survivorship bias note
    print()
    print('Survivorship bias assessment:')
    print('  Included: current FTSE 100 + historical members with surviving yfinance tickers')
    print('  Excluded (no surviving ticker): acquired/delisted names (GKN, Shire, BG Group,')
    print('    Cadbury, ARM pre-2023, WMH/William Hill post-acquisition, GFS/G4S, MGGT/Meggitt)')
    print('  Residual bias: survivorship bias from excluded names is present but reduced')
    print('  vs a current-constituents-only approach. Cannot be fully eliminated with')
    print('  free data — would require a commercial constituent history feed.')


def section_data(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print('\n=== DATA OVERVIEW ===')
    s = index_px.dropna()
    print(f'Index (^FTSE): {s.index[0].date()} to {s.index[-1].date()}  ({len(s)} days)')
    print(f'Universe: {len(prices.columns)} tickers with sufficient history')
    print()
    print(f'{"Ticker":<10} {"First date":<14} {"Days":>6}')
    print('-' * 34)
    for col in sorted(prices.columns, key=lambda c: prices[c].dropna().index[0]):
        s2 = prices[col].dropna()
        print(f'{col:<10} {str(s2.index[0].date()):<14} {len(s2):>6}')


def section_signals(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print('\n=== SIGNAL DISTRIBUTIONS ===')
    score, s1, s2, s3 = _momentum_signals(prices)
    cutoff = score.index[-1] - pd.DateOffset(years=3)
    recent = score[score.index >= cutoff].stack().dropna()
    print(f'Universe: {len(prices.columns)} stocks')
    print(f'Composite score (last 3yr, all stocks):')
    print(f'  Mean: {recent.mean():.3f}   Std: {recent.std():.3f}')
    print(f'  p5:   {recent.quantile(0.05):.3f}   p95: {recent.quantile(0.95):.3f}')
    print(f'  Skew: {recent.skew():.3f}   Kurt: {recent.kurtosis():.3f}')
    print()
    valid_dates = score.dropna(how='all').index[-252:]
    corr_12, corr_13, corr_23 = [], [], []
    for date in valid_dates:
        r1 = s1.loc[date].dropna(); r2 = s2.loc[date].dropna(); r3 = s3.loc[date].dropna()
        if len(r1.index.intersection(r2.index)) > 5:
            corr_12.append(r1.reindex(r1.index.intersection(r2.index)).corr(
                           r2.reindex(r1.index.intersection(r2.index))))
        if len(r1.index.intersection(r3.index)) > 5:
            corr_13.append(r1.reindex(r1.index.intersection(r3.index)).corr(
                           r3.reindex(r1.index.intersection(r3.index))))
        if len(r2.index.intersection(r3.index)) > 5:
            corr_23.append(r2.reindex(r2.index.intersection(r3.index)).corr(
                           r3.reindex(r2.index.intersection(r3.index))))
    print(f'Cross-sectional component correlations (avg last 1yr):')
    print(f'  1-3m vs 6-12m:   {np.nanmean(corr_12):.3f}')
    print(f'  1-3m vs 12-18m:  {np.nanmean(corr_13):.3f}')
    print(f'  6-12m vs 12-18m: {np.nanmean(corr_23):.3f}')


def section_regime(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print('\n=== REGIME ANALYSIS ===')
    reg   = _regime(index_px).loc[START:]
    total = len(reg.dropna())
    print(f'{"Regime":<10} {"Days":>7} {"Pct":>7}  {"Scale"}')
    print('-' * 38)
    for r, scale in [('low', '120%'), ('normal', '100%'), ('high', '60%')]:
        n = (reg == r).sum()
        print(f'{r:<10} {n:>7} {n/total*100:>6.1f}%  {scale}')
    print()
    for r in ['low', 'high']:
        runs, in_run, length = [], False, 0
        for val in reg.dropna():
            if val == r:
                in_run = True; length += 1
            elif in_run:
                runs.append(length); in_run = False; length = 0
        if in_run: runs.append(length)
        if runs:
            s = pd.Series(runs)
            print(f'{r.capitalize()} vol regime: count={len(s)}  mean={s.mean():.1f}d  '
                  f'median={s.median():.0f}d  max={s.max()}d')
    print()
    print('High-vol days by year:')
    for yr, grp in reg.groupby(reg.index.year):
        pct = (grp == 'high').mean() * 100
        print(f'  {yr}: {pct:5.1f}%  {"#" * int(pct / 2)}')


def section_packets(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print('\n=== PACKET ANALYSIS ===')
    score, _, _, _ = _momentum_signals(prices)
    reb  = _rebalance_dates(score)
    n    = len(prices.columns)
    rows = []
    for date in reb:
        row   = score.loc[date].dropna()
        if len(row) < 10: continue
        ranks = row.rank(pct=True)
        rows.append({'full_long':  (ranks >= 0.90).sum(),
                     'fade_long':  ((ranks >= 0.80) & (ranks < 0.90)).sum(),
                     'fade_short': ((ranks > 0.10) & (ranks <= 0.20)).sum(),
                     'full_short': (ranks <= 0.10).sum()})
    df = pd.DataFrame(rows)
    print(f'Universe: {n} stocks   Rebalances: {len(df)}')
    print()
    print(f'{"Packet":<22} {"Mean":>6} {"Std":>5} {"Min":>5} {"Max":>5}')
    print('-' * 48)
    for col, label in [('full_long','Full long (90-100%)'), ('fade_long','Fade long (80-90%)'),
                       ('fade_short','Fade short (10-20%)'), ('full_short','Full short (0-10%)')]:
        print(f'{label:<22} {df[col].mean():>6.1f} {df[col].std():>5.1f} '
              f'{df[col].min():>5} {df[col].max():>5}')


def section_turnover(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print('\n=== TURNOVER ANALYSIS (baseline: monthly, 10/20 packets, no buffer) ===')
    score, _, _, _ = _momentum_signals(prices)
    reb   = _rebalance_dates(score, 'ME')
    prev  = None
    tvs   = []
    for date in reb:
        row = score.loc[date]
        if row.dropna().shape[0] < 10: continue
        w = _packet_weights(row)
        if prev is not None:
            all_t = prev.index.union(w.index)
            tvs.append((w.reindex(all_t).fillna(0) - prev.reindex(all_t).fillna(0)).abs().sum())
        prev = w
    tv = pd.Series(tvs)
    print(f'Monthly one-way turnover: mean={tv.mean()*100:.1f}%  '
          f'median={tv.median()*100:.1f}%  p90={tv.quantile(0.9)*100:.1f}%')
    for bps in [5, 10, 20]:
        print(f'  At {bps:2d}bps/side: ~{tv.mean()*12*bps:.0f}bps/yr')


def section_baseline(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print('\n=== BASELINE BACKTEST (monthly, no TC, no regime) ===')
    idx_ret = index_px.pct_change(fill_method=None)
    ret = _backtest(prices, index_px, freq='ME', tc_bps=0, regime_scale=False)
    _summary(ret, idx_ret, 'Monthly / no TC / no regime')

    from research.metrics import compute_all_metrics
    m = compute_all_metrics(ret, idx_ret.reindex(ret.index).fillna(0))
    reg = _regime(index_px)
    print()
    print('Returns by regime:')
    for r, scale in [('low','120%'), ('normal','100%'), ('high','60%')]:
        mask = reg.reindex(ret.index).fillna('normal') == r
        sub  = ret[mask]
        if len(sub) < 20: continue
        ann  = sub.mean() * 252 * 100
        sh   = sub.mean() / sub.std() * np.sqrt(252) if sub.std() > 0 else 0
        print(f'  {r:<8} (scale {scale}): ann={ann:>6.1f}%  sharpe={sh:>5.2f}  n={len(sub)}d')
    print()
    print('Annual returns:')
    for yr, grp in ret.groupby(ret.index.year):
        ann = (1 + grp).prod() - 1
        sgn = '+' if ann >= 0 else '-'
        print(f'  {yr}: {sgn}{abs(ann)*100:5.1f}%  {"#" * int(abs(ann)*200)}')


def section_turnover_grid(prices: pd.DataFrame, index_px: pd.Series) -> None:
    """
    Systematic grid across:
      - Rebalance frequency: monthly, 6-weekly, quarterly
      - Packet fade width: narrow (5/15), base (10/20), wide (15/30)
      - Buffer rule: none, 2%, 5%
    Each cell shows TC-adjusted Sharpe at 10bps, and raw turnover.
    """
    print('\n=== TURNOVER / ALPHA GRID (10bps TC, no regime scaling) ===')
    idx_ret = index_px.pct_change(fill_method=None)

    freqs   = [('Monthly',   'ME'),
               ('6-weekly',  '6W'),
               ('Quarterly', 'QE')]
    packets = [('Narrow (5/15)',  0.05, 0.15),
               ('Base (10/20)',   0.10, 0.20),
               ('Wide (15/30)',   0.15, 0.30)]
    buffers = [('No buffer', 0.0),
               ('2% buffer', 0.02),
               ('5% buffer', 0.05)]

    print(f'\n{"Config":<48} {"AnnRet%":>8} {"Sharpe":>7} {"MaxDD%":>7} {"TC drag est."}')
    print('-' * 90)

    from research.metrics import compute_all_metrics

    # First measure turnover for each config (gross, then derive TC drag)
    for freq_label, freq in freqs:
        for pkt_label, fade_lo, fade_hi in packets:
            for buf_label, buf in buffers:
                label = f'{freq_label} / {pkt_label} / {buf_label}'
                ret   = _backtest(prices, index_px, freq=freq,
                                  fade_lo=fade_lo, fade_hi=fade_hi,
                                  buffer=buf, tc_bps=10.0,
                                  regime_scale=False)
                m = compute_all_metrics(ret, idx_ret.reindex(ret.index).fillna(0))
                print(f'  {label:<46} {m["annualised_return_pct"]:>8.1f} '
                      f'{m["sharpe_ratio"]:>7.2f} {m["max_drawdown_pct"]:>7.1f}%')

    # Best configs with regime scaling
    print(f'\n--- With regime scaling ---')
    for freq_label, freq in freqs[:2]:
        for pkt_label, fade_lo, fade_hi in packets[1:]:
            for buf_label, buf in [(buffers[1])]:
                label = f'{freq_label} / {pkt_label} / {buf_label} / regime'
                ret   = _backtest(prices, index_px, freq=freq,
                                  fade_lo=fade_lo, fade_hi=fade_hi,
                                  buffer=buf, tc_bps=10.0,
                                  regime_scale=True)
                m = compute_all_metrics(ret, idx_ret.reindex(ret.index).fillna(0))
                print(f'  {label:<46} {m["annualised_return_pct"]:>8.1f} '
                      f'{m["sharpe_ratio"]:>7.2f} {m["max_drawdown_pct"]:>7.1f}%')


# ---------------------------------------------------------------------------
# Section: improvements comparison
# ---------------------------------------------------------------------------

def section_improvements(prices: pd.DataFrame, index_px: pd.Series) -> None:
    """
    Isolate and combine the three enhancements against a fixed baseline.
    Baseline: monthly, narrow (5/15), 5% buffer, 10bps TC — the best config
    from the previous grid.
    """
    print('\n=== IMPROVEMENTS COMPARISON (monthly, narrow 5/15, 5% buffer, 10bps TC) ===')
    idx_ret = index_px.pct_change(fill_method=None)

    base_kw = dict(freq='ME', fade_lo=0.05, fade_hi=0.15,
                   buffer=0.05, tc_bps=10.0)

    configs = [
        ('Baseline (best prior config)',
         dict(**base_kw)),
        # --- individual enhancements ---
        ('+ Sector neutral',
         dict(**base_kw, sector_neutral=True)),
        ('+ Vol target 10%',
         dict(**base_kw, vol_target=0.10)),
        ('+ Abs momentum filter',
         dict(**base_kw, abs_momentum_filter=True)),
        # --- pairs ---
        ('+ Sector neutral + Vol target',
         dict(**base_kw, sector_neutral=True, vol_target=0.10)),
        ('+ Sector neutral + Abs filter',
         dict(**base_kw, sector_neutral=True, abs_momentum_filter=True)),
        ('+ Vol target + Abs filter',
         dict(**base_kw, vol_target=0.10, abs_momentum_filter=True)),
        # --- all three ---
        ('+ All three',
         dict(**base_kw, sector_neutral=True, vol_target=0.10,
              abs_momentum_filter=True)),
    ]

    from research.metrics import compute_all_metrics

    print(f'\n  {"Config":<44} {"Ann%":>6} {"Sharpe":>7} {"MaxDD%":>7} {"Sortino":>8}')
    print('  ' + '-' * 78)

    results = {}
    for label, kw in configs:
        ret = _backtest(prices, index_px, **kw)
        m   = compute_all_metrics(ret, idx_ret.reindex(ret.index).fillna(0))
        results[label] = m
        print(f'  {label:<44} {m["annualised_return_pct"]:>6.1f} '
              f'{m["sharpe_ratio"]:>7.2f} {m["max_drawdown_pct"]:>7.1f}% '
              f'{m["sortino_ratio"]:>8.2f}')

    # Year-by-year for baseline vs best combined
    print('\n  Year-by-year: Baseline vs best combined')
    baseline_ret = _backtest(prices, index_px, **base_kw)
    best_ret     = _backtest(prices, index_px, **base_kw,
                             sector_neutral=True, vol_target=0.10,
                             abs_momentum_filter=True)

    print(f'\n  {"Year":<6} {"Baseline":>10} {"All three":>10} {"Diff":>8}')
    print('  ' + '-' * 38)
    for yr in sorted(set(baseline_ret.index.year)):
        b = baseline_ret[baseline_ret.index.year == yr]
        c = best_ret[best_ret.index.year == yr]
        b_ann = (1 + b).prod() - 1
        c_ann = (1 + c).prod() - 1
        diff  = c_ann - b_ann
        flag  = ' <--' if abs(diff) > 0.05 else ''
        print(f'  {yr:<6} {b_ann*100:>9.1f}% {c_ann*100:>9.1f}% {diff*100:>+7.1f}%{flag}')

    # Regime breakdown for all-three vs baseline
    reg = _regime(index_px)
    print('\n  Returns by regime: Baseline vs All three')
    print(f'  {"Regime":<10} {"B ann%":>8} {"B sharpe":>9} {"C ann%":>8} {"C sharpe":>9}')
    print('  ' + '-' * 50)
    for r, scale in [('low', '120%'), ('normal', '100%'), ('high', '60%')]:
        mask = reg.reindex(baseline_ret.index).fillna('normal') == r
        bsub = baseline_ret[mask]
        csub = best_ret[best_ret.index.isin(bsub.index)]
        if len(bsub) < 20:
            continue
        b_ann = bsub.mean() * 252 * 100
        b_sh  = bsub.mean() / bsub.std() * np.sqrt(252) if bsub.std() > 0 else 0
        c_ann = csub.mean() * 252 * 100 if len(csub) > 0 else float('nan')
        c_sh  = csub.mean() / csub.std() * np.sqrt(252) if len(csub) > 1 and csub.std() > 0 else 0
        print(f'  {r:<10} {b_ann:>8.1f}% {b_sh:>9.2f} {c_ann:>8.1f}% {c_sh:>9.2f}')


# ---------------------------------------------------------------------------
# Section: signal improvements (round 2)
# ---------------------------------------------------------------------------

def section_sharpe2(prices: pd.DataFrame, index_px: pd.Series) -> None:
    """
    Test five signal-level improvements against the current best config.
    Prior best: vol target 10% + abs momentum filter → Sharpe 0.37.

    1. Signal gate       — skip rebalance when cross-sectional spread is weak
    2. Residual momentum — remove market beta before ranking
    3. XSZ signal        — cross-sectional z-score per horizon (vs time-series vol)
    4. Abs filter        — already in prior best; kept as anchor
    5. Continuous weights— linear rank weights replacing discrete packet buckets
    """
    print('\n=== SIGNAL IMPROVEMENTS ROUND 2 (monthly, narrow 5/15, 5% buffer, 10bps TC) ===')
    idx_ret = index_px.pct_change(fill_method=None)
    from research.metrics import compute_all_metrics

    best_kw = dict(freq='ME', fade_lo=0.05, fade_hi=0.15, buffer=0.05, tc_bps=10.0,
                   vol_target=0.10, abs_momentum_filter=True)

    # Calibrate signal gate thresholds from historical rebalance spread distribution
    print('  Calibrating signal gate...')
    score_ref, _, _, _ = _momentum_signals(prices)
    reb_ref = _rebalance_dates(score_ref, 'ME')
    spreads = []
    for d in reb_ref:
        eligible = [c for c in prices.columns
                    if prices[c].loc[:d].dropna().shape[0] >= MIN_HISTORY]
        row = score_ref.loc[d, eligible].dropna()
        if len(row) >= 10:
            spreads.append(row.quantile(0.9) - row.quantile(0.1))
    sp       = pd.Series(spreads)
    gate_p25 = float(sp.quantile(0.25))
    gate_p50 = float(sp.quantile(0.50))
    print(f'  Spread p25={gate_p25:.2f}  p50={gate_p50:.2f}  p75={sp.quantile(0.75):.2f}  '
          f'(gate_p25 skips ~25% of rebalances, gate_p50 skips ~50%)')

    # Gate thresholds
    gate_p33 = float(sp.quantile(0.33))
    gate_p40 = float(sp.quantile(0.40))

    # Base packets (10/20) outperform narrow (5/15) with signal gate — tested separately
    base_10_20_kw = dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05,
                         tc_bps=10.0, vol_target=0.10, abs_momentum_filter=True)

    configs = [
        # anchor
        ('Prior best: narrow 5/15, vol target, abs filter',
         dict(**best_kw)),
        # 1. signal gating — several thresholds, both packet widths
        ('1. Gate skip-25%, narrow 5/15',
         dict(**best_kw, signal_gate=gate_p25)),
        ('1. Gate skip-33%, narrow 5/15',
         dict(**best_kw, signal_gate=gate_p33)),
        ('1. Gate skip-40%, narrow 5/15',
         dict(**best_kw, signal_gate=gate_p40)),
        ('1. Gate skip-50%, narrow 5/15',
         dict(**best_kw, signal_gate=gate_p50)),
        ('1. Gate skip-33%, base 10/20',
         dict(**base_10_20_kw, signal_gate=gate_p33)),
        ('1. Gate skip-40%, base 10/20  ***',
         dict(**base_10_20_kw, signal_gate=gate_p40)),
        ('1. Gate skip-50%, base 10/20',
         dict(**base_10_20_kw, signal_gate=gate_p50)),
        # 2. residual momentum
        ('2. Residual momentum (beta-adjusted)',
         dict(**best_kw, residual_momentum=True)),
        ('2. Residual + gate skip-40%, base 10/20',
         dict(**base_10_20_kw, residual_momentum=True, signal_gate=gate_p40)),
        # 3. cross-sectional z-score signal
        ('3. XSZ signal',
         dict(**best_kw, xsz_signal=True)),
        # 5. continuous weights
        ('5. Continuous weights',
         dict(**best_kw, continuous_weights=True)),
        ('5. Continuous + gate skip-40%, base 10/20',
         dict(**base_10_20_kw, continuous_weights=True, signal_gate=gate_p40)),
    ]

    print(f'\n  {"Config":<46} {"Ann%":>6} {"Sharpe":>7} {"MaxDD%":>7} {"Sortino":>8}')
    print('  ' + '-' * 80)

    results = {}
    rets    = {}
    for label, kw in configs:
        ret = _backtest(prices, index_px, **kw)
        m   = compute_all_metrics(ret, idx_ret.reindex(ret.index).fillna(0))
        results[label] = m
        rets[label]    = ret
        print(f'  {label:<46} {m["annualised_return_pct"]:>6.1f} '
              f'{m["sharpe_ratio"]:>7.2f} {m["max_drawdown_pct"]:>7.1f}% '
              f'{m["sortino_ratio"]:>8.2f}')

    # Year-by-year: prior best vs best new (gate skip-40% base 10/20)
    prior_label   = configs[0][0]
    best_new      = '1. Gate skip-40%, base 10/20  ***'
    prior_ret     = rets[prior_label]
    best_new_ret  = rets[best_new]
    best_new_sh   = results[best_new]['sharpe_ratio']

    print(f'\n  Year-by-year: Prior best vs "{best_new}" (Sharpe {best_new_sh:.2f})')
    print(f'\n  {"Year":<6} {"Prior":>10} {"Best new":>10} {"Diff":>8}')
    print('  ' + '-' * 38)
    for yr in sorted(set(prior_ret.index.year)):
        b     = prior_ret[prior_ret.index.year == yr]
        c     = best_new_ret[best_new_ret.index.year == yr]
        b_ann = (1 + b).prod() - 1
        c_ann = (1 + c).prod() - 1 if len(c) > 0 else float('nan')
        diff  = c_ann - b_ann if not np.isnan(c_ann) else float('nan')
        flag  = ' <--' if not np.isnan(diff) and abs(diff) > 0.05 else ''
        print(f'  {yr:<6} {b_ann*100:>9.1f}% {c_ann*100:>9.1f}% {diff*100:>+7.1f}%{flag}')

    # Regime breakdown
    reg = _regime(index_px)
    print(f'\n  Regime breakdown: Prior best vs best new')
    print(f'  {"Regime":<10} {"Prior ann%":>11} {"Prior sh":>9} '
          f'{"New ann%":>10} {"New sh":>8}')
    print('  ' + '-' * 54)
    for r in ['low', 'normal', 'high']:
        mask  = reg.reindex(prior_ret.index).fillna('normal') == r
        bsub  = prior_ret[mask]
        csub  = best_new_ret[best_new_ret.index.isin(bsub.index)]
        if len(bsub) < 20:
            continue
        b_ann = bsub.mean() * 252 * 100
        b_sh  = bsub.mean() / bsub.std() * np.sqrt(252) if bsub.std() > 0 else 0
        c_ann = csub.mean() * 252 * 100 if len(csub) > 0 else float('nan')
        c_sh  = (csub.mean() / csub.std() * np.sqrt(252)
                 if len(csub) > 1 and csub.std() > 0 else 0)
        print(f'  {r:<10} {b_ann:>10.1f}% {b_sh:>9.2f} {c_ann:>9.1f}% {c_sh:>8.2f}')


# ---------------------------------------------------------------------------
# Section: signal improvements (round 3)
# ---------------------------------------------------------------------------

def section_sharpe3(prices: pd.DataFrame, index_px: pd.Series) -> None:
    """
    Test three focused improvements against the current best config.
    Prior best: gate skip-40% + base 10/20 + vol target 10% + abs filter → Sharpe 0.63

    1. Adaptive signal gate — vary gate percentile by vol regime
    2. Adaptive vol-target lookback — shorter in high-vol (10d), longer in low-vol (40d)
    3. Conviction thresholds on abs filter — require >2% for longs, <-2% for shorts
    """
    print('\n=== SIGNAL IMPROVEMENTS ROUND 3 (base 10/20, 5% buffer, 10bps TC) ===')
    idx_ret = index_px.pct_change(fill_method=None)
    from research.metrics import compute_all_metrics

    # Calibrate fixed gate for anchor
    score_ref, _, _, _ = _momentum_signals(prices)
    reb_ref = _rebalance_dates(score_ref, 'ME')
    spreads = []
    for d in reb_ref:
        eligible = [c for c in prices.columns
                    if prices[c].loc[:d].dropna().shape[0] >= MIN_HISTORY]
        row = score_ref.loc[d, eligible].dropna()
        if len(row) >= 10:
            spreads.append(row.quantile(0.9) - row.quantile(0.1))
    sp       = pd.Series(spreads)
    gate_p40 = float(sp.quantile(0.40))

    anchor_kw = dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05,
                     tc_bps=10.0, vol_target=0.10, abs_momentum_filter=True,
                     signal_gate=gate_p40)

    configs = [
        ('Prior best: fixed gate-40%, base 10/20, vt10, abs',
         dict(**anchor_kw)),

        # 1. Adaptive gate — vary strictness by regime
        ('1. Adaptive gate (low=0.10, norm=0.40, high=0.60)',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, abs_momentum_filter=True,
              adaptive_gate=True,
              adaptive_gate_low=0.10, adaptive_gate_normal=0.40,
              adaptive_gate_high=0.60)),
        ('1. Adaptive gate (low=0.20, norm=0.40, high=0.60)',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, abs_momentum_filter=True,
              adaptive_gate=True,
              adaptive_gate_low=0.20, adaptive_gate_normal=0.40,
              adaptive_gate_high=0.60)),
        ('1. Adaptive gate (low=0.20, norm=0.40, high=0.70)',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, abs_momentum_filter=True,
              adaptive_gate=True,
              adaptive_gate_low=0.20, adaptive_gate_normal=0.40,
              adaptive_gate_high=0.70)),
        ('1. Adaptive gate (low=0.10, norm=0.35, high=0.55)',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, abs_momentum_filter=True,
              adaptive_gate=True,
              adaptive_gate_low=0.10, adaptive_gate_normal=0.35,
              adaptive_gate_high=0.55)),

        # 2. Adaptive vol lookback
        ('2. Adaptive vol lb (low=40d, norm=20d, high=10d)',
         dict(**anchor_kw, adaptive_vol_lb=True)),
        ('2. Fixed vol lb 10d',
         dict(**anchor_kw, vol_target_lb=10)),
        ('2. Fixed vol lb 40d',
         dict(**anchor_kw, vol_target_lb=40)),

        # 3. Conviction threshold on abs filter
        ('3. Abs thresh long>1%, short<-1%',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, signal_gate=gate_p40,
              abs_long_min=0.01, abs_short_max=-0.01)),
        ('3. Abs thresh long>2%, short<-2%',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, signal_gate=gate_p40,
              abs_long_min=0.02, abs_short_max=-0.02)),
        ('3. Abs thresh long>3%, short<-3%',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, signal_gate=gate_p40,
              abs_long_min=0.03, abs_short_max=-0.03)),
        ('3. Abs thresh long>2%, short<-2% (legacy 0% too)',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, signal_gate=gate_p40,
              abs_momentum_filter=True,
              abs_long_min=0.02, abs_short_max=-0.02)),

        # Combinations of the best from each category
        ('Adaptive gate + adaptive vol lb',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10, abs_momentum_filter=True,
              adaptive_gate=True,
              adaptive_gate_low=0.20, adaptive_gate_normal=0.40,
              adaptive_gate_high=0.60,
              adaptive_vol_lb=True)),
        ('Adaptive gate + abs thresh 2%',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10,
              adaptive_gate=True,
              adaptive_gate_low=0.20, adaptive_gate_normal=0.40,
              adaptive_gate_high=0.60,
              abs_long_min=0.02, abs_short_max=-0.02)),
        ('All three combined',
         dict(freq='ME', fade_lo=0.10, fade_hi=0.20, buffer=0.05, tc_bps=10.0,
              vol_target=0.10,
              adaptive_gate=True,
              adaptive_gate_low=0.20, adaptive_gate_normal=0.40,
              adaptive_gate_high=0.60,
              adaptive_vol_lb=True,
              abs_long_min=0.02, abs_short_max=-0.02)),
    ]

    print(f'\n  {"Config":<52} {"Ann%":>6} {"Sharpe":>7} {"MaxDD%":>7} {"Sortino":>8}')
    print('  ' + '-' * 88)

    results, rets = {}, {}
    for label, kw in configs:
        ret = _backtest(prices, index_px, **kw)
        m   = compute_all_metrics(ret, idx_ret.reindex(ret.index).fillna(0))
        results[label] = m
        rets[label]    = ret
        marker = '  ***' if m['sharpe_ratio'] > results[configs[0][0]]['sharpe_ratio'] else ''
        print(f'  {label:<52} {m["annualised_return_pct"]:>6.1f} '
              f'{m["sharpe_ratio"]:>7.2f} {m["max_drawdown_pct"]:>7.1f}% '
              f'{m["sortino_ratio"]:>8.2f}{marker}')

    best_label = max(results, key=lambda l: results[l]['sharpe_ratio'])
    best_sh    = results[best_label]['sharpe_ratio']
    prior_ret  = rets[configs[0][0]]
    best_ret   = rets[best_label]

    print(f'\n  Year-by-year: Prior best vs "{best_label}" (Sharpe {best_sh:.2f})')
    print(f'\n  {"Year":<6} {"Prior":>10} {"Best":>10} {"Diff":>8}')
    print('  ' + '-' * 38)
    for yr in sorted(set(prior_ret.index.year)):
        b     = prior_ret[prior_ret.index.year == yr]
        c     = best_ret[best_ret.index.year == yr]
        b_ann = (1 + b).prod() - 1
        c_ann = (1 + c).prod() - 1 if len(c) > 0 else float('nan')
        diff  = c_ann - b_ann if not np.isnan(c_ann) else float('nan')
        flag  = ' <--' if not np.isnan(diff) and abs(diff) > 0.05 else ''
        print(f'  {yr:<6} {b_ann*100:>9.1f}% {c_ann*100:>9.1f}% {diff*100:>+7.1f}%{flag}')

    reg = _regime(index_px)
    print(f'\n  Regime breakdown: Prior best vs best new')
    print(f'  {"Regime":<10} {"Prior ann%":>11} {"Prior sh":>9} '
          f'{"Best ann%":>10} {"Best sh":>8}')
    print('  ' + '-' * 54)
    for r in ['low', 'normal', 'high']:
        mask  = reg.reindex(prior_ret.index).fillna('normal') == r
        bsub  = prior_ret[mask]
        csub  = best_ret[best_ret.index.isin(bsub.index)]
        if len(bsub) < 20:
            continue
        b_ann = bsub.mean() * 252 * 100
        b_sh  = bsub.mean() / bsub.std() * np.sqrt(252) if bsub.std() > 0 else 0
        c_ann = csub.mean() * 252 * 100 if len(csub) > 0 else float('nan')
        c_sh  = (csub.mean() / csub.std() * np.sqrt(252)
                 if len(csub) > 1 and csub.std() > 0 else 0)
        print(f'  {r:<10} {b_ann:>10.1f}% {b_sh:>9.2f} {c_ann:>9.1f}% {c_sh:>8.2f}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SECTIONS = {
    'data':          section_data,
    'universe':      section_universe,
    'signals':       section_signals,
    'regime':        section_regime,
    'packets':       section_packets,
    'turnover':      section_turnover,
    'baseline':      section_baseline,
    'turnover_grid':  section_turnover_grid,
    'improvements':   section_improvements,
    'sharpe2':        section_sharpe2,
    'sharpe3':        section_sharpe3,
}


def main() -> None:
    arg    = sys.argv[1] if len(sys.argv) > 1 else 'all'
    to_run = list(SECTIONS.keys()) if arg == 'all' else [arg]
    if any(s not in SECTIONS for s in to_run):
        print(f'Unknown section. Available: {", ".join(SECTIONS)} all')
        sys.exit(1)
    print('Fetching data...')
    prices, index_px = fetch_all()
    for section in to_run:
        SECTIONS[section](prices, index_px)
    print('\nDone.')


if __name__ == '__main__':
    main()
