import numpy as np
import pandas as pd
import yfinance as yf
import logging
import warnings
from itertools import combinations

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
warnings.filterwarnings("ignore")

# CURATED UNIVERSES: Removed Banks/Financials to avoid credit-shock bias
UNIVERSES = {
    "UK_MEGA": {
        "RESOURCES": ["RIO.L", "AAL.L", "GLEN.L", "BP.L", "SHEL.L", "ANTO.L"],
        "HOUSEBUILDERS": ["PSN.L", "TW.L", "VTY.L", "CRST.L", "BWY.L", "GLE.L"],
        "REITS": ["BLND.L", "LAND.L", "SGRO.L", "UTG.L", "HMSO.L", "GPE.L"],
        "UTILITIES": ["NG.L", "SSE.L", "UU.L", "SVT.L", "CNA.L"]
    },
    "AU_MEGA": {
        "MINING": ["BHP.AX", "RIO.AX", "FMG.AX", "S32.AX", "NST.AX", "EVN.AX"],
        "ENERGY": ["WDS.AX", "STO.AX", "ORG.AX", "SOL.AX", "WHC.AX"],
        "REITS": ["GMG.AX", "SCG.AX", "DXS.AX", "VCX.AX", "GPT.AX", "MGR.AX"],
        "UTIL_INFRA": ["APA.AX", "TCL.AX", "ALX.AX", "AZJ.AX", "TLS.AX"]
    },
    "CA_MEGA": {
        "ENERGY_PIPE": ["ENB.TO", "TRP.TO", "PPL.TO", "KEY.TO", "ALA.TO"],
        "ENERGY_PROD": ["CNQ.TO", "SU.TO", "IMO.TO", "CVE.TO", "TOU.TO"],
        "RETAIL_UTIL": ["ATD.TO", "L.TO", "WN.TO", "EMP-A.TO", "DOL.TO", "FTS.TO", "H.TO"]
    }
}

class CuratedAlphaEngine:
    def __init__(self, entry_z=2.5, rf_rate=0.02, end_date=None):
        self.entry_z = entry_z
        self.exit_z = 0.2
        self.rf_rate = rf_rate
        self.t_cost = 0.0005
        self.ann_factor = np.sqrt(252 * 8.5)
        self.end_date = end_date  # "YYYY-MM-DD" to lock the data window

    def get_hurst(self, series):
        lags = range(2, 20)
        tau = [np.sqrt(np.std(np.subtract(series[lag:], series[:-lag]))) for lag in lags]
        return np.polyfit(np.log(lags), np.log(tau), 1)[0] * 2.0

    def run(self, verbose=True):
        master_pair_stats = []
        region_summaries = []

        for region, sector_map in UNIVERSES.items():
            if verbose:
                logging.info(f"AUDIT: Analyzing curated {region} at {self.entry_z} sigma...")
            tickers = list(set([t for s in sector_map.values() for t in s]))
            data = yf.download(tickers, period="730d", interval="1h", progress=False)["Close"].ffill().dropna(axis=1)
            if self.end_date:
                cutoff = pd.Timestamp(self.end_date, tz="UTC") + pd.Timedelta(days=1)
                data = data[data.index < cutoff]
            
            train, test = data.iloc[:500], data.iloc[500:]
            test_rets = test.pct_change()
            region_pnls = []

            for sector, members in sector_map.items():
                valid = [t for t in members if t in train.columns]
                for s1, s2 in combinations(valid, 2):
                    if train[s1].corr(train[s2]) > 0.85:
                        h = self.get_hurst((train[s1] / train[s2]).values)
                        if h < 0.44:
                            ratio = test[s1] / test[s2]
                            z = (ratio - ratio.rolling(150).mean()) / ratio.rolling(150).std()
                            
                            curr, signals = 0, []
                            for val in z:
                                if curr == 0:
                                    if val < -self.entry_z: curr = 1
                                    elif val > self.entry_z: curr = -1
                                elif (curr == 1 and val >= -self.exit_z) or (curr == -1 and val <= self.exit_z):
                                    curr = 0
                                signals.append(curr)
                            
                            sig = pd.Series(signals, index=test.index)
                            if sig.abs().sum() == 0: continue

                            spread_ret = test_rets[s1] - test_rets[s2]
                            vol = spread_ret.rolling(100).std().ffill().replace(0, 0.01)
                            pnl = (sig.shift(1) * spread_ret * (0.01/vol).shift(1)) - (sig.diff().abs() * self.t_cost)
                            
                            pair_ret = (1 + pnl).prod() - 1
                            pair_sharpe = ( (pnl.mean() - (self.rf_rate/(252*8.5))) / pnl.std() ) * self.ann_factor
                            
                            master_pair_stats.append({
                                "Region": region,
                                "Sector": sector,
                                "Pair": f"{s1}/{s2}",
                                "Hurst": round(h, 4),
                                "Trades": int(sig.diff().abs().sum() / 2),
                                "NetReturn": pair_ret,
                                "Sharpe": round(pair_sharpe, 2)
                            })
                            region_pnls.append(pnl)

            if region_pnls:
                r_pnl = pd.concat(region_pnls, axis=1).mean(axis=1)
                r_sharpe = ( (r_pnl.mean() - (self.rf_rate/(252*8.5))) / r_pnl.std() ) * self.ann_factor
                r_ret = (1 + r_pnl).prod() - 1
                region_summaries.append({"Region": region, "Sharpe": r_sharpe, "Return": r_ret})

        pair_df = pd.DataFrame(master_pair_stats).sort_values("Sharpe", ascending=False)
        region_df = pd.DataFrame(region_summaries)

        if verbose:
            print("\n" + "="*85)
            print(f"DETAILED PAIR ATTRIBUTION (CURATED - {self.entry_z} SIGMA)")
            print("="*85)
            display = pair_df.copy()
            display["NetReturn"] = display["NetReturn"].map("{:.2%}".format)
            print(display.to_string(index=False))

            print("\n" + "="*85)
            print("REGION SUMMARY (RF: 2%)")
            print("="*85)
            print(region_df.to_string(index=False))

        return pair_df, region_df

if __name__ == "__main__":
    CuratedAlphaEngine().run()