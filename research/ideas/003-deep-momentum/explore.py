"""
Exploratory analysis for idea 003 -- Deep Momentum Strategy (UK equities).
Run from repo root: python research/ideas/003-deep-momentum/explore.py [section]

Sections:
  data      -- universe coverage, panel size, cross-section stats
  features  -- feature distributions and correlations
  baseline  -- simple momentum ranking benchmark
  model     -- walk-forward DNN accuracy and IC diagnostics
  backtest  -- full walk-forward DNN vs baseline
  all       -- run all sections (default)

Implementation of 10-step plan:
  1. Universe ~600 UK stocks (FTSE 100/250/SmallCap/AIM candidates)
  2. Unbalanced panel: 12-month lookback per date only
  3. 3-month forward return as target
  4. Cross-sectional deciles recomputed per month with full available universe
  5. 96-month training window
  6. Smaller network: 32->16->output, dropout 0.4, L2 regularisation
  7. Point-in-time size: estimated monthly from price × current market cap ratio
  8. Features: m1, m6, m12, vol_6m, size_rank (5 features, less collinear)
  9. Ensemble of 7 models with different seeds, averaged predictions
  10. Rank by expected return from predicted distribution, long top decile
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from data.fetchers.yfinance_fetcher import YFinanceFetcher

# ---------------------------------------------------------------------------
# Universe — FTSE 100 + 250 + Small Cap + AIM candidates
# Cast a wide net; fetch failures are silently dropped.
# No full-history requirement at fetch time — MIN_HISTORY enforced per date.
# ---------------------------------------------------------------------------

UNIVERSE_TICKERS = [
    # --- FTSE 100 ---
    'AZN.L','SHEL.L','HSBA.L','ULVR.L','BP.L','RIO.L','GSK.L',
    'DGE.L','LLOY.L','BATS.L','AAL.L','GLEN.L','VOD.L','NG.L',
    'PRU.L','BARC.L','NWG.L','IMB.L','REL.L','SSE.L','WPP.L',
    'TSCO.L','ABF.L','EXPN.L','HLMA.L','RKT.L','JD.L','FRES.L',
    'BRBY.L','IHG.L','CPG.L','CNA.L','LGEN.L','BA.L','STAN.L',
    'III.L','CRDA.L','SGRO.L','DPLM.L','AUTO.L','RTO.L','PSON.L',
    'INF.L','MKS.L','FLTR.L','OCDO.L','BT-A.L','LAND.L','SBRY.L',
    'CCH.L','ADM.L','ANTO.L','AHT.L','BME.L','BNZL.L','DCC.L',
    'EMG.L','ENT.L','HLN.L','HWDN.L','IGG.L','KGF.L','MNDI.L',
    'NXT.L','PSH.L','PHNX.L','SDR.L','SMT.L','SN.L','SPX.L',
    'TATE.L','UTG.L','VTY.L','WEIR.L','WG.L','WTB.L','HBR.L',
    'TLW.L','OSB.L','ITRK.L','GNS.L','SMIN.L','SRP.L','SGE.L',
    'BKG.L','PSN.L','BWY.L','TW.L','BLND.L','HMSO.L','GRI.L',
    'UU.L','SVT.L','PNN.L','CPI.L','CAPE.L','BVS.L','RS1.L',
    'PCT.L','MRO.L','RWS.L','JET2.L','FRAS.L',
    # --- FTSE 250 ---
    'IMI.L','CHG.L','PETS.L','RNK.L','ITV.L','NCC.L','XPS.L',
    'FUTR.L','KNOS.L','MONY.L','DNLM.L','DOM.L','EZJ.L','SHOE.L',
    'FEVR.L','AO.L','CARD.L','THG.L','FDM.L','AVON.L',
    'ICGT.L','HGT.L','PIN.L','BGEO.L','TCAP.L','INCH.L',
    'ATG.L','CLX.L','FNX.L','RMV.L','OXB.L','PEN.L',
    'ACSO.L','CREI.L','DLN.L','PHP.L','SHED.L','TRIG.L','SUPR.L',
    'TRN.L','FAR.L','HOC.L','JLEN.L','PMP.L','PZC.L',
    'CAML.L','GKP.L','HVO.L','COG.L','CRDL.L','XTR.L','SRES.L',
    'CTG.L','GFTU.L','MTO.L','ROR.L','VSL.L','WSP.L',
    'GAW.L','INVP.L','JUP.L','ASHM.L','ABDN.L','MNG.L',
    'MGNS.L','MSLH.L','IMI.L','ROR.L','WEIR.L',
    'BBOX.L','BCPT.L','CSH.L','LXI.L','PRSR.L','THRL.L',
    'PHP.L','SAFE.L','UKCM.L','VCT.L','NCYF.L',
    'POLR.L','CVS.L','EMIS.L','HRTX.L','NXR.L',
    'DARK.L','FOUR.L','GOCO.L','QQ.L','SYS1.L','ZPG.L',
    'EMAN.L','JEL.L','MXCT.L','SEPL.L',
    'TPX.L','VOF.L','YNGA.L','ZOO.L',
    'IGR.L','XPP.L','WSP.L','RGL.L','RNEW.L',
    'ACA.L','CEY.L','CGNR.L','EMN.L','GGP.L',
    'MPAC.L','OTB.L','PAY.L','PEAK.L',
    # --- FTSE Small Cap ---
    'ABDP.L','ACL.L','AFC.L','AGM.L','AGR.L','AJB.L','AML.L',
    'ANPG.L','AOF.L','APS.L','ARBB.L','ARDN.L','ARE.L','ARR.L',
    'ATYM.L','AUE.L','AUTG.L','AVC.L','AVV.L','AWE.L',
    'BABS.L','BAG.L','BARC.L','BBH.L','BCSA.L','BEG.L','BEW.L',
    'BHR.L','BKS.L','BLTG.L','BMY.L','BNK.L','BOC.L','BOY.L',
    'BSFA.L','BSV.L','BUR.L','BVIC.L',
    'CAM.L','CAMB.L','CCR.L','CDL.L','CEPS.L','CFX.L','CGS.L',
    'CHH.L','CKN.L','CLL.L','CLP.L','CMC.L','CMCX.L','CMS.L',
    'CMX.L','CNE.L','COPL.L','CORA.L','CPC.L','CPTN.L','CQS.L',
    'CSN.L','CTAG.L','CTR.L','CWK.L',
    'DBOX.L','DCG.L','DEED.L','DEMG.L','DGB.L','DHG.L','DIA.L',
    'DNL.L','DNLM.L','DOR.L','DOTD.L','DPH.L','DRX.L',
    'ECSC.L','EDP.L','EGL.L','EKF.L','ELM.L','EMLN.L','EMR.L',
    'ENG.L','ENOG.L','ENV.L','EPIC.L','EQN.L','ERA.L','ERM.L',
    'ETL.L','EWI.L','EXEL.L',
    'FAN.L','FBH.L','FDI.L','FEN.L','FFX.L','FGP.L','FIF.L',
    'FIPP.L','FJV.L','FKL.L','FLO.L','FLP.L','FLT.L','FLX.L',
    'FOGL.L','FORE.L','FPM.L','FRR.L','FSJ.L','FTC.L',
    'GBG.L','GCG.L','GEMD.L','GEN.L','GFC.L','GFM.L','GFT.L',
    'GHE.L','GIN.L','GKP.L','GLJ.L','GLIF.L','GLL.L','GLO.L',
    'GLP.L','GMB.L','GMVF.L','GNS.L','GOOD.L','GPOR.L','GPX.L',
    'GRG.L','GRI.L','GRL.L','GRS.L','GTI.L','GVC.L',
    'HAT.L','HBOS.L','HBR.L','HDD.L','HDIV.L','HEAR.L',
    'HEMO.L','HFG.L','HFD.L','HGM.L','HGT.L','HHI.L','HIK.L',
    'HIP.L','HMI.L','HMO.L','HOC.L','HOL.L','HPS.L','HRN.L',
    'HSD.L','HSP.L','HUMN.L','HWG.L','HYD.L',
    'IAE.L','IBST.L','ICI.L','ICM.L','IDH.L','IDOX.L','IDP.L',
    'IEM.L','IEP.L','IFM.L','IGC.L','IHC.L','IHR.L','IKA.L',
    'ILX.L','IMP.L','INFA.L','INM.L','INPP.L','INS.L',
    'IOF.L','IOM.L','IQE.L','IRM.L','IRS.L','IRV.L','ITD.L',
    'JMAT.L','JMG.L','JMI.L','JNK.L','JOG.L','JRG.L',
    'KETL.L','KHD.L','KIE.L','KING.L','KMK.L','KOD.L',
    'LAM.L','LCG.L','LEN.L','LEP.L','LGO.L','LGEN.L','LGN.L',
    'LGR.L','LIO.L','LIT.L','LIV.L','LMP.L','LMS.L','LND.L',
    'LSEG.L','LSL.L','LTG.L','LXB.L',
    'MACF.L','MAI.L','MAN.L','MARS.L','MAV.L','MCB.L','MCI.L',
    'MCLS.L','MCX.L','MDC.L','MED.L','MER.L','MFX.L','MGC.L',
    'MHN.L','MIL.L','MIRI.L','MKTX.L','MLV.L','MMH.L',
    'MMIP.L','MNB.L','MNP.L','MOG.L','MONY.L','MPA.L','MRC.L',
    'MRL.L','MRM.L','MRO.L','MRS.L','MSI.L','MSM.L','MTL.L',
    'MTR.L','MXC.L','MYI.L',
    'NAH.L','NANO.L','NCT.L','NEX.L','NFC.L','NGS.L','NHC.L',
    'NHP.L','NII.L','NINI.L','NMC.L','NOGH.L','NORI.L','NRM.L',
    'NWF.L','NWT.L',
    'OCA.L','OCN.L','OCDO.L','OCI.L','OCT.L','ODX.L','OEX.L',
    'OHL.L','OIL.L','OIR.L','OML.L','OMC.L','OML.L','OPG.L',
    'OPTI.L','ORM.L','ORR.L','OSI.L','OTB.L','OTC.L','OTP.L',
    'PARF.L','PBX.L','PCA.L','PCIP.L','PDL.L','PEB.L','PEG.L',
    'PGH.L','PGL.L','PHD.L','PHNX.L','PIC.L','PIG.L','PIP.L',
    'PKG.L','PLND.L','PLG.L','PLI.L','PLT.L','PMP.L','PNL.L',
    'POG.L','POM.L','PORK.L','PORR.L','POST.L','PPB.L','PPH.L',
    'PPN.L','PPHE.L','PRG.L','PRL.L','PRO.L','PRSR.L','PRT.L',
    'PRX.L','PSI.L','PSP.L','PTY.L','PUB.L','PUR.L',
    'QQ.L','QCCO.L','QRT.L','QTX.L',
    'RAT.L','RCH.L','RCP.L','RDI.L','RDW.L','REC.L','RED.L',
    'REL.L','RES.L','RET.L','RETO.L','RGS.L','RHM.L','RIO.L',
    'RKH.L','RKT.L','RMG.L','RMP.L','RNS.L','ROC.L','ROG.L',
    'RPT.L','RRE.L','RSA.L','RST.L','RTN.L','RUA.L','RUL.L',
    'RUR.L','RVU.L',
    'SAA.L','SAFE.L','SAG.L','SAL.L','SAR.L','SAS.L','SAT.L',
    'SCS.L','SDL.L','SDP.L','SEFI.L','SEG.L','SEPL.L','SER.L',
    'SFF.L','SFR.L','SGI.L','SGM.L','SHB.L','SHP.L','SHR.L',
    'SICT.L','SIG.L','SIM.L','SIV.L','SKS.L','SLI.L','SLL.L',
    'SLP.L','SLPE.L','SLT.L','SMD.L','SMI.L','SML.L','SMP.L',
    'SMS.L','SNN.L','SNWS.L','SOI.L','SOM.L','SOS.L','SPA.L',
    'SPE.L','SPH.L','SPI.L','SPN.L','SPT.L','SQZ.L','SRC.L',
    'SRX.L','SSE.L','SSP.L','STB.L','STO.L','STR.L','STS.L',
    'STU.L','STV.L','SUP.L','SUT.L','SVE.L','SVI.L','SWJ.L',
    'SWP.L','SXS.L','SYS1.L',
    'TALG.L','TAM.L','TAN.L','TAR.L','TBCG.L','TCC.L','TCN.L',
    'TED.L','TELF.L','TEN.L','TET.L','TGP.L','TGS.L','THL.L',
    'TIG.L','TII.L','TIME.L','TIN.L','TIR.L','TMI.L','TMP.L',
    'TMT.L','TND.L','TNI.L','TNT.L','TOF.L','TON.L','TOP.L',
    'TOPG.L','TPG.L','TPFG.L','TPI.L','TPK.L','TPN.L','TPVG.L',
    'TQL.L','TRC.L','TRI.L','TRG.L','TRM.L','TRN.L','TRS.L',
    'TSG.L','TSL.L','TST.L','TTG.L','TUI.L','TVC.L','TVS.L',
    'TXP.L','TYM.L',
    'UAI.L','UBI.L','UEM.L','UFO.L','UGO.L','UKW.L','ULS.L',
    'UMC.L','UNI.L','UPR.L','UQA.L','URA.L','URB.L','URI.L',
    'UTL.L','UTV.L',
    'VAL.L','VAR.L','VCT.L','VDP.L','VEC.L','VELA.L','VER.L',
    'VGAS.L','VGM.L','VID.L','VIP.L','VIR.L','VIS.L','VLX.L',
    'VNH.L','VOC.L','VPC.L','VRS.L','VTY.L',
    'WAG.L','WATR.L','WCW.L','WEB.L','WEIR.L','WEN.L','WEX.L',
    'WFRD.L','WHR.L','WIG.L','WIN.L','WIX.L','WJG.L','WKC.L',
    'WMH.L','WNC.L','WNS.L','WOSG.L','WPP.L','WPS.L','WPT.L',
    'WRT.L','WSG.L','WTM.L',
    'XAR.L','XAAR.L','XEL.L','XLM.L','XPD.L','XPP.L','XPS.L',
    'YELP.L','YEW.L','YOU.L','YU.L',
    'ZED.L','ZEG.L','ZIN.L','ZOO.L','ZPG.L',
    # --- AIM liquid names ---
    'ABDP.L','ABDN.L','ACG.L','ACSO.L','AEG.L','AFG.L','AGFX.L',
    'AGT.L','AHT.L','AIM.L','AIP.L','AIRT.L','AISP.L','AJG.L',
    'ALLG.L','ALS.L','ALTA.L','ALU.L','ALUR.L','AMBI.L','AMC.L',
    'AMD.L','AMO.L','AMTE.L','ANC.L','ANCR.L','AND.L','ANO.L',
    'ANPG.L','ANX.L','APC.L','APE.L','APGN.L','APH.L','API.L',
    'APLC.L','APN.L','APP.L','APQ.L','APR.L','APS.L','APSE.L',
    'ARCH.L','ARDN.L','ARE.L','ARG.L','ARIP.L','ARR.L','ARS.L',
    'ASC.L','ASCL.L','ASI.L','ASL.L','ASO.L','ASP.L','ASPL.L',
    'ASR.L','ASST.L','ATA.L','ATGN.L','ATH.L','ATM.L','ATMA.L',
    'ATO.L','ATS.L','ATT.L','ATTM.L','AUE.L','AUGA.L','AUGM.L',
    'AUG.L','AUK.L','AUL.L','AUO.L','AUP.L','AUR.L','AUS.L',
    'AUT.L','AVAC.L','AVAP.L','AVB.L','AVG.L','AVI.L','AVIN.L',
    'AVN.L','AVO.L','AVOC.L','AVON.L','AVS.L','AVT.L','AVU.L',
    'AWE.L','AWI.L','AXI.L','AXL.L','AXS.L',
    'BGEO.L','BGFD.L','BGS.L','BHY.L','BKG.L','BKI.L','BKT.L',
    'BLA.L','BLK.L','BLL.L','BLV.L','BMN.L','BMS.L','BMT.L',
    'BNA.L','BNKR.L','BNS.L','BNT.L','BNZL.L','BOA.L','BOIL.L',
    'BOL.L','BOM.L','BOR.L','BORR.L','BOT.L','BOTB.L','BOX.L',
    'BPM.L','BPS.L','BPT.L','BPW.L','BQE.L','BRA.L','BREA.L',
    'BRGE.L','BRI.L','BRIT.L','BRK.L','BRL.L','BRM.L','BRMS.L',
    'BRN.L','BRP.L','BRSA.L','BRW.L','BSL.L','BSP.L','BSX.L',
    'BTC.L','BTG.L','BTI.L','BTL.L','BTRG.L','BTRS.L',
    'BWY.L','BYG.L',
]

UNIVERSE  = sorted(set(UNIVERSE_TICKERS))

# FTSE 350 subset for liquid-universe parallel backtest
FTSE350_TICKERS = [
    # FTSE 100
    'AZN.L','SHEL.L','HSBA.L','ULVR.L','BP.L','RIO.L','GSK.L',
    'DGE.L','LLOY.L','BATS.L','AAL.L','GLEN.L','VOD.L','NG.L',
    'PRU.L','BARC.L','NWG.L','IMB.L','REL.L','SSE.L','WPP.L',
    'TSCO.L','ABF.L','EXPN.L','HLMA.L','RKT.L','JD.L','FRES.L',
    'BRBY.L','IHG.L','CPG.L','CNA.L','LGEN.L','BA.L','STAN.L',
    'III.L','CRDA.L','SGRO.L','DPLM.L','AUTO.L','RTO.L','PSON.L',
    'INF.L','MKS.L','FLTR.L','OCDO.L','BT-A.L','LAND.L','SBRY.L',
    'CCH.L','ADM.L','ANTO.L','AHT.L','BME.L','BNZL.L','DCC.L',
    'EMG.L','ENT.L','HLN.L','HWDN.L','IGG.L','KGF.L','MNDI.L',
    'NXT.L','PSH.L','PHNX.L','SDR.L','SMT.L','SN.L','SPX.L',
    'TATE.L','UTG.L','VTY.L','WEIR.L','WG.L','WTB.L','HBR.L',
    'TLW.L','OSB.L','ITRK.L','GNS.L','SMIN.L','SRP.L','SGE.L',
    'BKG.L','PSN.L','BWY.L','TW.L','BLND.L','HMSO.L','GRI.L',
    'UU.L','SVT.L','PNN.L','CPI.L','CAPE.L','BVS.L','RS1.L',
    'PCT.L','MRO.L','RWS.L','JET2.L','FRAS.L',
    # FTSE 250
    'IMI.L','CHG.L','PETS.L','RNK.L','ITV.L','NCC.L','XPS.L',
    'FUTR.L','KNOS.L','MONY.L','DNLM.L','DOM.L','EZJ.L','SHOE.L',
    'FEVR.L','AO.L','CARD.L','THG.L','FDM.L',
    'ICGT.L','HGT.L','PIN.L','BGEO.L','TCAP.L','INCH.L',
    'ATG.L','CLX.L','FNX.L','RMV.L','OXB.L','PEN.L',
    'ACSO.L','CREI.L','DLN.L','PHP.L','SHED.L','TRIG.L','SUPR.L',
    'TRN.L','HOC.L','JLEN.L','PMP.L','PZC.L',
    'CAML.L','GKP.L','COG.L','CRDL.L','XTR.L',
    'GAW.L','INVP.L','JUP.L','ASHM.L','ABDN.L','MNG.L',
    'MGNS.L','MSLH.L','MTO.L','ROR.L',
    'BBOX.L','CSH.L','LXI.L','PRSR.L',
    'CVS.L','EMIS.L','NXR.L',
    'DARK.L','FOUR.L','QQ.L',
]
FTSE350 = sorted(set(FTSE350_TICKERS))

INDEX     = '^FTSE'
START     = '2010-01-01'
END       = '2024-12-31'

# Step 2: 12-month lookback per date (not full sample)
MIN_HISTORY_MONTHS = 12    # months of data before a stock enters cross-section
# Step 3: 3-month forward returns
FWD_MONTHS         = 3
# Step 5: 96-month training window
TRAIN_MONTHS       = 96
RETRAIN_FREQ       = 12
# Base features (sector dummies added dynamically in _build_panel)
BASE_BASE_FEATURE_COLS  = ['m1', 'm6', 'm12', 'vol_6m', 'size_rank',
                      'mom_accel', 'vol_adj_mom', 'roll_sharpe']
N_DECILES          = 10
# Ensemble: 5 models, tuned hyperparams
N_ENSEMBLE         = 5
DROPOUT            = 0.3
LEARNING_RATE      = 1e-3
# TC in bps for backtest
TC_BPS             = 10.0
# Signal gate: skip if spread < this percentile of history (FTSE350 less aggressive)
SIGNAL_GATE_PCT    = 0.25
# Portfolio construction
TOP_FRAC           = 0.20   # long top 20% by predicted return
MAX_WEIGHT         = 0.05   # cap individual weight at 5%
VOL_EXCLUDE_PCT    = 0.05   # exclude top 5% most volatile stocks

# GICS sectors used for one-hot features (11 standard sectors)
SECTORS = ['Energy', 'Materials', 'Industrials', 'Consumer Discretionary',
           'Consumer Staples', 'Health Care', 'Financials',
           'Information Technology', 'Communication Services',
           'Utilities', 'Real Estate']


def _clean_series(s: pd.Series, max_daily_move: float = 0.75) -> pd.Series:
    ret    = s.pct_change(fill_method=None).fillna(0)
    capped = ret.clip(-max_daily_move, max_daily_move)
    return (1 + capped).cumprod().rename(s.name)


def fetch_all(tickers: list[str] = UNIVERSE) -> tuple[pd.DataFrame, pd.Series]:
    fetcher = YFinanceFetcher(cache_dir=Path('data/cache'))
    frames, failed = {}, []
    for t in tickers:
        try:
            df = fetcher.fetch(t, START, END)
            s  = _clean_series(df['close'].dropna())
            # Accept anything with at least MIN_HISTORY_MONTHS months of data
            if len(s) >= MIN_HISTORY_MONTHS * 21:
                frames[t] = s
        except Exception:
            failed.append(t)
    if failed:
        print(f'  Skipped (fetch failed): {len(failed)} tickers')
    idx_df = fetcher.fetch(INDEX, START, END)
    return pd.DataFrame(frames), idx_df['close']


def _monthly_prices(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.resample('ME').last()


# ---------------------------------------------------------------------------
# Step 7: Point-in-time size feature
# Estimate monthly market cap as: mc_now × (price[t] / price[t_latest])
# Then compute within-universe percentile rank as the size feature.
# ---------------------------------------------------------------------------

def _fetch_market_caps(tickers: list[str]) -> pd.Series:
    """Fetch market caps with disk cache (refreshed if >30 days old)."""
    import yfinance as yf
    import time
    cache_path = Path('data/cache/market_caps.parquet')
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        age_days = (pd.Timestamp.now() - pd.Timestamp(cache_path.stat().st_mtime, unit='s')).days
        if age_days < 30:
            return cached['marketCap'].dropna()
    caps = {}
    for i, t in enumerate(tickers):
        if (i + 1) % 50 == 0:
            print(f'    market caps: {i+1}/{len(tickers)}', flush=True)
        try:
            info = yf.Ticker(t).info
            mc   = info.get('marketCap') or info.get('market_cap')
            if mc and mc > 0:
                caps[t] = mc
        except Exception:
            pass
        time.sleep(0.05)  # avoid rate limiting
    result = pd.Series(caps, name='marketCap')
    result.to_frame().to_parquet(cache_path)
    return result


def _fetch_sectors(tickers: list[str]) -> pd.Series:
    """Fetch GICS sector for each ticker, disk-cached."""
    import yfinance as yf
    cache_path = Path('data/cache/sectors.parquet')
    if cache_path.exists():
        return pd.read_parquet(cache_path)['sector'].dropna()
    secs = {}
    for i, t in enumerate(tickers):
        if (i + 1) % 50 == 0:
            print(f'    sectors: {i+1}/{len(tickers)}', flush=True)
        try:
            info = yf.Ticker(t).info
            s    = info.get('sector') or info.get('sectorKey', '').title()
            if s:
                secs[t] = s
        except Exception:
            pass
    result = pd.Series(secs, name='sector')
    result.to_frame().to_parquet(cache_path)
    return result


def _sector_dummies(tickers: list[str], sectors: pd.Series) -> pd.DataFrame:
    """One-hot encode sector for each ticker. Unknown → all zeros."""
    cols = [f'sec_{s.lower().replace(" ", "_")[:12]}' for s in SECTORS]
    df   = pd.DataFrame(0.0, index=tickers, columns=cols)
    for t in tickers:
        s = sectors.get(t)
        if s in SECTORS:
            col = f'sec_{s.lower().replace(" ", "_")[:12]}'
            df.loc[t, col] = 1.0
    return df


def _pointintime_size(monthly: pd.DataFrame, mc_now: pd.Series) -> pd.DataFrame:
    """
    Estimate historical market cap at each month-end:
        mc[t] = mc_now × (price[t] / price[t_last])
    Then compute cross-sectional percentile rank within available stocks.
    Returns DataFrame(dates × tickers) of size rank [0,1].
    """
    last_price = monthly.ffill().iloc[-1]
    common     = mc_now.index.intersection(monthly.columns)
    mc_aligned = mc_now.reindex(common)
    price_last = last_price.reindex(common)

    size_rank = pd.DataFrame(np.nan, index=monthly.index, columns=monthly.columns)
    for date in monthly.index:
        px_row = monthly.loc[date].reindex(common)
        avail  = px_row.notna() & price_last.notna() & mc_aligned.notna()
        if avail.sum() < 5:
            continue
        mc_est  = mc_aligned[avail] * (px_row[avail] / price_last[avail])
        mc_est  = mc_est.replace([np.inf, -np.inf], np.nan).dropna()
        if len(mc_est) < 5:
            continue
        size_rank.loc[date, mc_est.index] = mc_est.rank(pct=True).values
    return size_rank


# ---------------------------------------------------------------------------
# Step 8: Feature computation — m1, m6, m12, vol_6m, size_rank
# ---------------------------------------------------------------------------

def _compute_features(monthly: pd.DataFrame,
                      size_rank: pd.DataFrame) -> dict[str, pd.DataFrame]:
    m1  = monthly.shift(1) / monthly.shift(2)  - 1   # skip last month
    m6  = monthly.shift(1) / monthly.shift(7)  - 1
    m12 = monthly.shift(1) / monthly.shift(13) - 1

    monthly_ret = monthly.pct_change(fill_method=None)
    # 6-month realised volatility (annualised)
    vol_6m = monthly_ret.rolling(6).std() * np.sqrt(12)

    # Step 3 new features: orthogonal signals
    # Momentum acceleration: recent minus long-run (positive = momentum building)
    mom_accel = m1 - m12

    # Volatility-adjusted momentum: m1 scaled by vol (unit-risk momentum)
    vol_6m_safe = vol_6m.replace(0, np.nan)
    vol_adj_mom = m1 / vol_6m_safe

    # Rolling Sharpe: mean monthly return / std over last 6 months (annualised)
    roll_mean = monthly_ret.rolling(6).mean()
    roll_std  = monthly_ret.rolling(6).std().replace(0, np.nan)
    roll_sharpe = roll_mean / roll_std * np.sqrt(12)

    return {'m1': m1, 'm6': m6, 'm12': m12, 'vol_6m': vol_6m,
            'size_rank': size_rank, 'mom_accel': mom_accel,
            'vol_adj_mom': vol_adj_mom, 'roll_sharpe': roll_sharpe}


def _cross_section_standardise(df: pd.DataFrame) -> pd.DataFrame:
    mu    = df.mean(axis=1)
    sigma = df.std(axis=1).replace(0, np.nan)
    return df.sub(mu, axis=0).div(sigma, axis=0)


# ---------------------------------------------------------------------------
# Step 4: Build unbalanced panel with per-date cross-sectional deciles
# Step 3: 3-month forward return as target
# ---------------------------------------------------------------------------

def _build_panel(prices: pd.DataFrame, mc_now: pd.Series,
                 sectors: pd.Series | None = None
                 ) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """
    Build flat panel of (date, ticker) observations.
    Target = cross-sectionally standardised 3-month forward log-return (regression).
    Features = BASE_BASE_FEATURE_COLS + sector one-hot dummies (if sectors provided).
    """
    monthly    = _monthly_prices(prices)
    size_rank  = _pointintime_size(monthly, mc_now)
    raw_feats  = _compute_features(monthly, size_rank)

    no_std = {'size_rank'}
    std_feats = {k: (_cross_section_standardise(v) if k not in no_std else v)
                 for k, v in raw_feats.items()}

    # Sector one-hot (static per ticker, broadcasted to all dates)
    sec_dummies: pd.DataFrame | None = None
    sec_cols: list[str] = []
    if sectors is not None and len(sectors) > 0:
        sd = _sector_dummies(prices.columns.tolist(), sectors)
        # Only keep sector columns that have at least one positive entry
        sd = sd.loc[:, sd.sum() > 0]
        if len(sd.columns) > 0:
            sec_dummies = sd
            sec_cols = sd.columns.tolist()

    feature_cols = BASE_BASE_FEATURE_COLS + sec_cols

    monthly_log = monthly.apply(np.log)
    fwd_log     = monthly_log.shift(-FWD_MONTHS) - monthly_log
    fwd_raw     = monthly.shift(-FWD_MONTHS) / monthly - 1

    records = []
    for date in monthly.index[13:]:
        fwd_row = fwd_log.loc[date].dropna()
        if len(fwd_row) < 20:
            continue

        fwd_mu  = fwd_row.mean()
        fwd_std = fwd_row.std()
        if fwd_std == 0 or np.isnan(fwd_std):
            continue
        fwd_std_row = (fwd_row - fwd_mu) / fwd_std

        decile = pd.qcut(fwd_row, q=N_DECILES, labels=False, duplicates='drop')

        for ticker in fwd_row.index:
            n_months = monthly.loc[:date, ticker].notna().sum()
            if n_months < MIN_HISTORY_MONTHS:
                continue

            row_feats: dict = {}
            valid = True
            for fname in BASE_BASE_FEATURE_COLS:
                fdf = std_feats[fname]
                val = fdf.loc[date, ticker] if ticker in fdf.columns else np.nan
                if np.isnan(val) or np.isinf(val):
                    valid = False
                    break
                row_feats[fname] = val
            if not valid:
                continue

            # Add sector dummies
            if sec_dummies is not None and ticker in sec_dummies.index:
                for sc in sec_cols:
                    row_feats[sc] = float(sec_dummies.loc[ticker, sc])
            elif sec_cols:
                for sc in sec_cols:
                    row_feats[sc] = 0.0   # unknown sector → all zeros

            row_feats['_date']    = date
            row_feats['_ticker']  = ticker
            row_feats['_target']  = float(fwd_std_row[ticker])
            row_feats['_decile']  = int(decile[ticker]) if not pd.isna(decile.get(ticker)) else -1
            row_feats['_fwd_raw'] = float(fwd_raw.loc[date, ticker]) if ticker in fwd_raw.columns else np.nan
            records.append(row_feats)

    panel   = pd.DataFrame(records).set_index(['_date', '_ticker'])
    X       = panel[feature_cols]
    y       = panel['_target']
    fwd_y   = panel['_fwd_raw']
    deciles = panel['_decile']
    return X, y, fwd_y, deciles


# ---------------------------------------------------------------------------
# Step 6: Smaller network with L2 regularisation
# ---------------------------------------------------------------------------

def _build_model(input_dim: int = 8, l2: float = 1e-4) -> 'torch.nn.Module':
    """Regression network: outputs a single predicted return score."""
    import torch.nn as nn

    class RegressionNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, 32), nn.ReLU(), nn.Dropout(DROPOUT),
                nn.Linear(32, 16),        nn.ReLU(), nn.Dropout(DROPOUT),
                nn.Linear(16, 1),
            )
            self._l2 = l2

        def forward(self, x):
            return self.net(x).squeeze(-1)

        def l2_loss(self):
            l2 = 0.0
            for p in self.parameters():
                l2 = l2 + p.pow(2).sum()
            return self._l2 * l2

    return RegressionNet()


def _train_model(X_train: np.ndarray, y_train: np.ndarray,
                 epochs: int = 80, batch_size: int = 128,
                 lr: float = LEARNING_RATE, seed: int = 42) -> 'torch.nn.Module':
    """Train regression model with Huber loss (robust to return outliers)."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    torch.manual_seed(seed)
    model   = _build_model(X_train.shape[1])
    opt     = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.HuberLoss(delta=1.0)

    Xt = torch.FloatTensor(X_train)
    yt = torch.FloatTensor(y_train)   # float targets for regression
    loader = DataLoader(TensorDataset(Xt, yt), batch_size=batch_size, shuffle=True)

    model.train()
    for _ in range(epochs):
        for xb, yb in loader:
            opt.zero_grad()
            loss   = loss_fn(model(xb), yb) + model.l2_loss()
            loss.backward()
            opt.step()
    model.eval()
    return model


# Step 9: ensemble training with different seeds
def _train_ensemble(X_train: np.ndarray, y_train: np.ndarray,
                    n: int = N_ENSEMBLE) -> list:
    models = []
    for i in range(n):
        print(f'    training model {i+1}/{n}...', flush=True)
        models.append(_train_model(X_train, y_train, seed=42 + i * 17))
    return models


def _predict_ensemble(models: list, X: np.ndarray) -> np.ndarray:
    """Average regression predictions across ensemble. Returns 1-D array."""
    import torch
    preds = []
    with torch.no_grad():
        for model in models:
            p = model(torch.FloatTensor(X)).numpy()
            preds.append(p)
    return np.mean(preds, axis=0)


def _rescale_predictions(preds: np.ndarray) -> np.ndarray:
    """
    Step 4: Post-process predictions to expand cross-sectional spread.
    Standardise to zero mean, unit std — keeps IC intact but widens spread
    so top/bottom decile cuts are more decisive.
    """
    mu  = preds.mean()
    std = preds.std()
    if std < 1e-8:
        return preds
    return (preds - mu) / std


def _weighted_portfolio_return(pred_s: pd.Series, fr: pd.Series,
                               vol_row: pd.Series | None = None) -> float:
    """
    Long top TOP_FRAC by predicted score, return-weighted, capped at MAX_WEIGHT.
    Optional vol_row: exclude stocks in top VOL_EXCLUDE_PCT volatility before picking.
    """
    candidates = pred_s
    # Light quality filter: exclude highest-vol stocks (top 5%)
    if vol_row is not None and len(vol_row) > 10:
        vol_thr = vol_row.quantile(1.0 - VOL_EXCLUDE_PCT)
        safe    = vol_row[vol_row <= vol_thr].index
        candidates = candidates.reindex(safe).dropna()

    if len(candidates) < 5:
        candidates = pred_s   # fallback to full set

    # Top TOP_FRAC by predicted score
    thr   = candidates.quantile(1.0 - TOP_FRAC)
    longs = candidates[candidates >= thr]

    if len(longs) == 0:
        return np.nan

    # Weights proportional to predicted score (shift to all-positive, then normalise)
    w = longs - longs.min() + 1e-6
    w = w / w.sum()
    # Cap individual weight
    w = w.clip(upper=MAX_WEIGHT)
    w = w / w.sum()

    ret_vals = fr.reindex(w.index).dropna()
    w = w.reindex(ret_vals.index).dropna()
    if len(w) == 0:
        return np.nan
    w = w / w.sum()
    return float((ret_vals * w).sum())


# ---------------------------------------------------------------------------
# Metrics (monthly returns)
# ---------------------------------------------------------------------------

def _monthly_metrics(ret: pd.Series, rf_annual: float = 0.02) -> dict:
    n       = len(ret)
    years   = n / 12
    rf_m    = rf_annual / 12
    total   = (1 + ret).prod()
    cagr    = total ** (1 / years) - 1 if years > 0 else 0.0
    vol_ann = ret.std() * np.sqrt(12)
    excess  = ret - rf_m
    sharpe  = (excess.mean() / ret.std() * np.sqrt(12) if ret.std() > 0 else 0.0)
    down    = ret[ret < rf_m]
    sortino = (excess.mean() / down.std() * np.sqrt(12)
               if len(down) > 1 and down.std() > 0 else 0.0)
    cum     = (1 + ret).cumprod()
    dd      = (cum / cum.cummax() - 1).min() * 100
    return {
        'annualised_return_pct':    cagr * 100,
        'annualised_volatility_pct': vol_ann * 100,
        'sharpe_ratio':             sharpe,
        'sortino_ratio':            sortino,
        'max_drawdown_pct':         dd,
    }


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def section_data(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print('\n=== DATA OVERVIEW ===')
    print(f'Tickers fetched: {len(prices.columns)}')
    print(f'Date range: {prices.index[0].date()} to {prices.index[-1].date()}')

    by_year: dict[int, int] = {}
    for col in prices.columns:
        yr = prices[col].dropna().index[0].year
        by_year[yr] = by_year.get(yr, 0) + 1
    print('\nStart year distribution:')
    for yr in sorted(by_year):
        print(f'  {yr}: {by_year[yr]:3d} tickers')

    monthly = _monthly_prices(prices)
    # cross-section per month: stocks with >= MIN_HISTORY_MONTHS data up to that date
    xs = []
    for date in monthly.index[MIN_HISTORY_MONTHS:]:
        n = (monthly.loc[:date].notna().sum() >= MIN_HISTORY_MONTHS).sum()
        xs.append(n)
    xs = pd.Series(xs)
    print(f'\nMonthly cross-section (stocks with >= {MIN_HISTORY_MONTHS}m history):')
    print(f'  Mean: {xs.mean():.0f}   Min: {xs.min()}   Max: {xs.max()}')

    # panel size estimate
    monthly_m = _monthly_prices(prices)
    fwd   = monthly_m.shift(-FWD_MONTHS) / monthly_m - 1
    total = 0
    for date in monthly_m.index[13:]:
        avail = (monthly_m.loc[:date].notna().sum() >= MIN_HISTORY_MONTHS)
        fr    = fwd.loc[date].dropna()
        total += len(fr.index.intersection(avail[avail].index))
    print(f'\nEstimated panel observations: ~{total:,}')
    print(f'  Training window: {TRAIN_MONTHS} months  '
          f'Retrain every: {RETRAIN_FREQ} months')
    print(f'  Target: {FWD_MONTHS}-month forward return decile')
    print(f'  Features: {BASE_FEATURE_COLS}  Ensemble: {N_ENSEMBLE} models')


def section_features(prices: pd.DataFrame, index_px: pd.Series,
                     mc_now: pd.Series | None = None) -> None:
    print('\n=== FEATURE ANALYSIS ===')
    monthly   = _monthly_prices(prices)
    if mc_now is None:
        mc_now = pd.Series(dtype=float)
    size_rank = _pointintime_size(monthly, mc_now)
    feats     = _compute_features(monthly, size_rank)
    std_feats = {k: (_cross_section_standardise(v) if k != 'size_rank' else v)
                 for k, v in feats.items()}
    fwd       = monthly.shift(-FWD_MONTHS) / monthly - 1

    cutoff = monthly.index[-1] - pd.DateOffset(years=3)
    print(f'Distributions (last 3yr, cross-sectionally standardised where applicable):')
    print(f'  {"Feature":<10} {"Mean":>7} {"Std":>7} {"Skew":>7} {"p5":>7} {"p95":>7}')
    print('  ' + '-' * 52)
    for fname in BASE_FEATURE_COLS:
        s = std_feats[fname][std_feats[fname].index >= cutoff].stack().dropna()
        s = s.replace([np.inf, -np.inf], np.nan).dropna()
        print(f'  {fname:<10} {s.mean():>7.3f} {s.std():>7.3f} '
              f'{s.skew():>7.3f} {s.quantile(0.05):>7.3f} {s.quantile(0.95):>7.3f}')

    print('\nFeature correlations (Spearman rank, time-averaged, last 36m):')
    from scipy import stats
    keys = BASE_FEATURE_COLS
    corr_sums = {(a, b): [] for i, a in enumerate(keys) for b in keys[i+1:]}
    for date in monthly.index[-36:]:
        vals = {}
        for k in keys:
            col_data = std_feats[k].loc[date] if date in std_feats[k].index else pd.Series()
            vals[k]  = col_data.replace([np.inf, -np.inf], np.nan).dropna()
        common = vals[keys[0]].index
        for k in keys[1:]:
            common = common.intersection(vals[k].index)
        if len(common) < 20:
            continue
        for i, a in enumerate(keys):
            for b in keys[i+1:]:
                r, _ = stats.spearmanr(vals[a].reindex(common), vals[b].reindex(common))
                corr_sums[(a, b)].append(r)
    print(f'  {"Pair":<18} {"Mean corr":>10}')
    print('  ' + '-' * 30)
    for pair, vals in corr_sums.items():
        if vals:
            print(f'  {"-".join(pair):<18} {np.mean(vals):>10.3f}')

    print(f'\n{FWD_MONTHS}-month forward return by decile:')
    decile_rets: dict[int, list] = {d: [] for d in range(N_DECILES)}
    for date in monthly.index[13:]:
        fr = fwd.loc[date].dropna()
        if len(fr) < 20:
            continue
        dc = pd.qcut(fr, q=N_DECILES, labels=False, duplicates='drop')
        for d in range(N_DECILES):
            mask = dc == d
            if mask.sum() > 0:
                decile_rets[d].extend(fr[mask].tolist())
    print(f'  {"Decile":<8} {"Median%":>9} {"Mean%":>9} {"Std%":>9}')
    print('  ' + '-' * 38)
    for d in range(N_DECILES):
        s = pd.Series(decile_rets[d]) * 100
        print(f'  {d:<8} {s.median():>9.2f} {s.mean():>9.2f} {s.std():>9.2f}')


def section_baseline(prices: pd.DataFrame, index_px: pd.Series) -> None:
    print(f'\n=== BASELINE: SIMPLE 12M MOMENTUM ({FWD_MONTHS}m forward return) ===')
    monthly = _monthly_prices(prices)
    m12     = monthly.shift(1) / monthly.shift(13) - 1
    fwd     = monthly.shift(-FWD_MONTHS) / monthly - 1

    port_rets, dates = [], []
    for date in monthly.index[13:]:
        fr  = fwd.loc[date].dropna()
        sig = m12.loc[date].dropna()
        # Only stocks with >= MIN_HISTORY_MONTHS months of data
        avail = [c for c in sig.index
                 if monthly.loc[:date, c].notna().sum() >= MIN_HISTORY_MONTHS]
        sig = sig.reindex(avail).dropna()
        if len(sig) < 20:
            continue
        ranks  = sig.rank(pct=True)
        longs  = ranks[ranks >= 0.90].index
        shorts = ranks[ranks <= 0.10].index
        lr     = fr.reindex(longs).dropna().mean()
        sr     = fr.reindex(shorts).dropna().mean()
        if pd.isna(lr) or pd.isna(sr):
            continue
        port_rets.append(lr - sr)
        dates.append(date)

    ret = pd.Series(port_rets, index=dates)
    m   = _monthly_metrics(ret)
    print(f'  {"Metric":<28} {"Value"}')
    print('  ' + '-' * 40)
    for k in ['annualised_return_pct', 'sharpe_ratio', 'max_drawdown_pct', 'sortino_ratio']:
        print(f'  {k:<28} {m[k]:.2f}')

    print('\n  Annual returns:')
    for yr, grp in ret.groupby(ret.index.year):
        ann = (1 + grp).prod() - 1
        sgn = '+' if ann >= 0 else '-'
        print(f'    {yr}: {sgn}{abs(ann)*100:5.1f}%  {"#" * int(abs(ann)*100)}')


def section_model(prices: pd.DataFrame, index_px: pd.Series,
                  mc_now: pd.Series | None = None) -> None:
    print('\n=== DNN MODEL: WALK-FORWARD IC DIAGNOSTICS ===', flush=True)
    if mc_now is None:
        print('  Fetching market cap snapshot...', flush=True)
        mc_now = _fetch_market_caps(prices.columns.tolist())
        print(f'  Market cap available for {mc_now.notna().sum()}/{len(prices.columns)} tickers', flush=True)

    print('  Building panel...', flush=True)
    sectors = _fetch_sectors(prices.columns.tolist())
    X, y, fwd_y, deciles = _build_panel(prices, mc_now, sectors=sectors)
    feature_cols = X.columns.tolist()
    dates = sorted(X.index.get_level_values(0).unique())
    print(f'  Panel: {len(X):,} obs  {len(dates)} months  '
          f'{len(X.index.get_level_values(1).unique())} tickers', flush=True)
    print(f'  Model: regression (Huber loss)  Features: {len(feature_cols)}', flush=True)

    if len(dates) < TRAIN_MONTHS + 6:
        print(f'  Need {TRAIN_MONTHS + 6} months, have {len(dates)}. Skipping.', flush=True)
        return

    print(f'\n  Walk-forward: {TRAIN_MONTHS}m train, retrain every {RETRAIN_FREQ}m, '
          f'{N_ENSEMBLE}-model ensemble', flush=True)

    all_dec, all_pred, all_dates = [], [], []
    ensemble = None

    for t_idx in range(TRAIN_MONTHS, len(dates)):
        train_dates = dates[:t_idx]
        test_date   = dates[t_idx]

        if (t_idx - TRAIN_MONTHS) % RETRAIN_FREQ == 0:
            train_mask = X.index.get_level_values(0).isin(train_dates)
            Xtr  = X[train_mask][feature_cols].values.astype(np.float32)
            ytr  = y[train_mask].values.astype(np.float32)
            valid = ~(np.isnan(Xtr).any(axis=1) | np.isinf(Xtr).any(axis=1))
            Xtr, ytr = Xtr[valid], ytr[valid]
            if len(Xtr) < 500:
                continue
            ensemble = _train_ensemble(Xtr, ytr)
            print(f'  Ensemble trained: {len(Xtr):,} obs through '
                  f'{train_dates[-1].date()}', flush=True)

        if ensemble is None:
            continue

        test_mask = X.index.get_level_values(0) == test_date
        tickers   = X[test_mask].index.get_level_values(1)
        Xte       = X[test_mask][feature_cols].values.astype(np.float32)
        dec_te    = deciles[test_mask].values
        valid     = (~(np.isnan(Xte).any(axis=1) | np.isinf(Xte).any(axis=1))
                     & (dec_te >= 0))
        if valid.sum() < 5:
            continue

        preds = _predict_ensemble(ensemble, Xte[valid])
        preds = _rescale_predictions(preds)

        all_dec.extend(dec_te[valid].tolist())
        all_pred.extend(preds.tolist())
        all_dates.extend([test_date] * valid.sum())

    if not all_dec:
        print('  No predictions generated.')
        return

    all_dec  = np.array(all_dec)
    all_pred = np.array(all_pred)

    from scipy import stats
    ic, pval = stats.spearmanr(all_pred, all_dec)
    print(f'\n  Rank IC (Spearman, predicted score vs actual decile): '
          f'{ic:.4f}  (p={pval:.4f})')

    # Monthly IC time series (step 8 monitoring)
    monthly_ics, pred_spreads = [], []
    for date in sorted(set(all_dates)):
        mask = np.array(all_dates) == date
        if mask.sum() < 10:
            continue
        r, _ = stats.spearmanr(all_pred[mask], all_dec[mask])
        monthly_ics.append(r)
        pred_spreads.append(all_pred[mask].max() - all_pred[mask].min())
    ics = pd.Series(monthly_ics)
    t_stat = ics.mean() / (ics.std() / np.sqrt(len(ics))) if ics.std() > 0 else 0
    print(f'  Monthly IC: mean={ics.mean():.4f}  std={ics.std():.4f}  '
          f't-stat={t_stat:.2f}  pct_positive={(ics > 0).mean():.1%}')
    print(f'  Predicted score spread (top-bottom, monthly avg): '
          f'{np.mean(pred_spreads):.3f}')

    # Step 9: decile calibration table
    print('\n  Mean predicted score by actual decile:')
    print(f'  {"Decile":<8} {"Mean pred":>10}  {"Count":>8}')
    print('  ' + '-' * 32)
    for d in range(N_DECILES):
        mask = all_dec == d
        if mask.sum() > 0:
            print(f'  {d:<8} {all_pred[mask].mean():>10.4f}  {mask.sum():>8}')


def _run_backtest(prices: pd.DataFrame, mc_now: pd.Series,
                  sectors: pd.Series, label: str) -> None:
    """
    Run three long-only configs:
      1. Momentum baseline: equal-weight top 10% by 12m momentum
      2. DNN: return-weighted top 20%, max weight 5%, vol filter
      3. Blended: 0.5×momentum rank + 0.5×DNN rank, return-weighted top 20%

    All: 10bps TC on turnover, signal gate (skip bottom-25% spread months).
    """
    print(f'\n--- Universe: {label} ({len(prices.columns)} tickers) ---', flush=True)
    X, y, fwd_y, deciles = _build_panel(prices, mc_now, sectors=sectors)
    feature_cols = X.columns.tolist()
    dates = sorted(X.index.get_level_values(0).unique())
    if len(dates) < TRAIN_MONTHS + 6:
        print('  Insufficient data, skipping.')
        return

    monthly = _monthly_prices(prices)
    fwd     = monthly.shift(-FWD_MONTHS) / monthly - 1
    m12     = monthly.shift(1) / monthly.shift(13) - 1
    vol6m   = monthly.pct_change(fill_method=None).rolling(6).std() * np.sqrt(12)
    tc      = TC_BPS / 10000

    spread_hist: list[float] = []
    r_dnn, r_mom, r_blend = [], [], []
    prev_dnn: set   = set()
    prev_mom: set   = set()
    prev_blend: set = set()
    test_dates: list = []
    ensemble = None

    for t_idx in range(TRAIN_MONTHS, len(dates)):
        train_dates = dates[:t_idx]
        test_date   = dates[t_idx]

        if (t_idx - TRAIN_MONTHS) % RETRAIN_FREQ == 0:
            train_mask = X.index.get_level_values(0).isin(train_dates)
            Xtr  = X[train_mask][feature_cols].values.astype(np.float32)
            ytr  = y[train_mask].values.astype(np.float32)
            valid = ~(np.isnan(Xtr).any(axis=1) | np.isinf(Xtr).any(axis=1))
            Xtr, ytr = Xtr[valid], ytr[valid]
            if len(Xtr) < 500:
                continue
            ensemble = _train_ensemble(Xtr, ytr)
            print(f'  Retrained: {len(Xtr):,} obs  {len(feature_cols)} features  '
                  f'window ends {train_dates[-1].date()}', flush=True)

        if ensemble is None:
            continue

        test_mask = X.index.get_level_values(0) == test_date
        tickers   = X[test_mask].index.get_level_values(1)
        Xte       = X[test_mask][feature_cols].values.astype(np.float32)
        valid_fe  = ~(np.isnan(Xte).any(axis=1) | np.isinf(Xte).any(axis=1))
        if valid_fe.sum() < 10:
            continue

        ticks_v = tickers[valid_fe]
        preds   = _predict_ensemble(ensemble, Xte[valid_fe])
        preds   = _rescale_predictions(preds)
        pred_s  = pd.Series(preds, index=ticks_v)
        fr      = fwd.loc[test_date]
        vol_row = vol6m.loc[test_date].reindex(ticks_v).dropna()

        # Signal gate on DNN spread
        spread = pred_s.quantile(0.9) - pred_s.quantile(0.1)
        spread_hist.append(spread)
        gate_thr = (pd.Series(spread_hist).expanding().quantile(SIGNAL_GATE_PCT).iloc[-1]
                    if len(spread_hist) > 12 else 0.0)
        if spread < gate_thr:
            continue

        # Available stocks
        avail = [c for c in m12.columns
                 if not pd.isna(m12.loc[test_date, c])
                 and monthly.loc[:test_date, c].notna().sum() >= MIN_HISTORY_MONTHS]
        sig = m12.loc[test_date].reindex(avail).dropna()
        if len(sig) < 20:
            continue

        mom_rank_pct = sig.rank(pct=True)
        dnn_rank_pct = pred_s.rank(pct=True)

        # --- Config 1: Momentum equal-weight top 10% ---
        mom_longs = set(mom_rank_pct[mom_rank_pct >= 0.90].index)
        mlr  = fr.reindex(list(mom_longs)).dropna().mean()
        m_tc = len(mom_longs - prev_mom) / max(len(mom_longs), 1) * tc
        r_mom.append(mlr - m_tc if not pd.isna(mlr) else np.nan)

        # --- Config 2: DNN return-weighted top 20%, vol filter, 5% cap ---
        dlr  = _weighted_portfolio_return(pred_s, fr, vol_row=vol_row)
        # Approximate turnover: stocks in top 20% this vs last month
        dnn_top = set(dnn_rank_pct[dnn_rank_pct >= 0.80].index)
        d_tc = len(dnn_top - prev_dnn) / max(len(dnn_top), 1) * tc
        r_dnn.append(dlr - d_tc if not pd.isna(dlr) else np.nan)

        # --- Config 3: Blended rank (0.5 mom + 0.5 DNN), return-weighted top 20% ---
        common = mom_rank_pct.index.intersection(dnn_rank_pct.index)
        if len(common) >= 10:
            blend = 0.5 * mom_rank_pct.reindex(common) + 0.5 * dnn_rank_pct.reindex(common)
            blend = _rescale_predictions(blend.values)
            blend_s = pd.Series(blend, index=common)
            blend_vol = vol6m.loc[test_date].reindex(common).dropna()
            blr = _weighted_portfolio_return(blend_s, fr, vol_row=blend_vol)
            blend_top = set(pd.Series(blend, index=common).rank(pct=True).pipe(
                lambda s: s[s >= 0.80]).index)
            bl_tc = len(blend_top - prev_blend) / max(len(blend_top), 1) * tc
            r_blend.append(blr - bl_tc if not pd.isna(blr) else np.nan)
            prev_blend = blend_top
        else:
            r_blend.append(np.nan)

        test_dates.append(test_date)
        prev_dnn = dnn_top
        prev_mom = mom_longs

    if not test_dates:
        print('  No results.')
        return

    idx = pd.Index(test_dates)
    ret_mom   = pd.Series(r_mom,   index=idx).dropna()
    ret_dnn   = pd.Series(r_dnn,   index=idx).dropna()
    ret_blend = pd.Series(r_blend, index=idx).dropna()

    skipped = len(dates) - TRAIN_MONTHS - len(test_dates)
    print(f'  Rebalances: {len(test_dates)} executed, {skipped} skipped by gate', flush=True)
    print(f'  {"Config":<44} {"Ann%":>6} {"Sharpe":>7} {"MaxDD%":>8} {"Sortino":>8}')
    print('  ' + '-' * 78)
    configs = [
        ('Momentum top-10% equal-weight',         ret_mom),
        ('DNN top-20% return-weighted + vol cap',  ret_dnn),
        ('Blended 0.5×mom + 0.5×DNN top-20%',     ret_blend),
    ]
    for lbl, ret in configs:
        if len(ret) < 6:
            print(f'  {lbl:<44}  (insufficient data)')
            continue
        m = _monthly_metrics(ret)
        print(f'  {lbl:<44} {m["annualised_return_pct"]:>6.1f} '
              f'{m["sharpe_ratio"]:>7.2f} {m["max_drawdown_pct"]:>8.1f}% '
              f'{m["sortino_ratio"]:>8.2f}')

    print('\n  Year-by-year (Momentum | DNN | Blended):')
    print(f'  {"Year":<6} {"Mom":>8} {"DNN":>8} {"Blend":>8}')
    print('  ' + '-' * 38)
    for yr in sorted(set(idx.year)):
        def _ann(r):
            g = r[r.index.year == yr]
            return (1+g).prod()-1 if len(g) > 0 else float('nan')
        print(f'  {yr:<6} {_ann(ret_mom)*100:>7.1f}% '
              f'{_ann(ret_dnn)*100:>7.1f}% {_ann(ret_blend)*100:>7.1f}%')


def section_backtest(prices: pd.DataFrame, index_px: pd.Series,
                     mc_now: pd.Series | None = None) -> None:
    print('\n=== BACKTEST: DNN vs MOMENTUM vs BLENDED (long-only, 10bps TC) ===',
          flush=True)
    if mc_now is None:
        print('  Fetching market cap snapshot...', flush=True)
        mc_now = _fetch_market_caps(prices.columns.tolist())

    print('  Fetching sector data...', flush=True)
    sectors = _fetch_sectors(prices.columns.tolist())
    print(f'  Sectors: {sectors.nunique()} unique  {sectors.notna().sum()}/{len(prices.columns)} tickers',
          flush=True)

    # FTSE 350 — primary focus
    ftse350_cols = [c for c in prices.columns if c in set(FTSE350)]
    if len(ftse350_cols) >= 50:
        prices_350 = prices[ftse350_cols]
        mc_350     = mc_now.reindex(ftse350_cols).dropna()
        sec_350    = sectors.reindex(ftse350_cols).dropna()
        _run_backtest(prices_350, mc_350, sec_350, label='FTSE 350')

    # Full universe — for comparison
    _run_backtest(prices, mc_now, sectors, label='Full universe')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SECTIONS = {
    'data':     section_data,
    'features': section_features,
    'baseline': section_baseline,
    'model':    section_model,
    'backtest': section_backtest,
}


def main() -> None:
    arg    = sys.argv[1] if len(sys.argv) > 1 else 'all'
    to_run = list(SECTIONS.keys()) if arg == 'all' else [arg]
    if any(s not in SECTIONS for s in to_run):
        print(f'Unknown section. Available: {", ".join(SECTIONS)}, all')
        sys.exit(1)
    print('Fetching price data...', flush=True)
    prices, index_px = fetch_all()

    # Fetch market cap once and share across sections that need it
    mc_now = None
    if any(s in to_run for s in ['features', 'model', 'backtest']):
        print('Fetching market cap snapshot...', flush=True)
        mc_now = _fetch_market_caps(prices.columns.tolist())
        print(f'  Market cap available: {mc_now.notna().sum()}/{len(prices.columns)}', flush=True)

    for section in to_run:
        fn   = SECTIONS[section]
        import inspect
        sig  = inspect.signature(fn)
        if 'mc_now' in sig.parameters:
            fn(prices, index_px, mc_now=mc_now)
        else:
            fn(prices, index_px)
    print('\nDone.')


if __name__ == '__main__':
    main()
