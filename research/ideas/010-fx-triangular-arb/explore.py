"""
Idea 010 -- FX Triangular Lead-Lag: EUR/USD + USD/ZAR -> EUR/ZAR

Hypothesis: At each EUR/ZAR tick update, the direct quote catches up to
the synthetic (EUR/USD x USD/ZAR). If true, the synthetic move during a
EUR/ZAR gap predicts the next EUR/ZAR tick direction -- and size.

Core analysis (tick-centric):
  For each EUR/ZAR tick at time t:
    gap        = t - t_prev  (seconds since last direct tick)
    synth_prev = EURUSD(t_prev) x USDZAR(t_prev)
    synth_now  = EURUSD(t)  x USDZAR(t)
    synth_move = synth_now - synth_prev           (what synthetic did in gap)
    direct_move= EURZAR(t)  - EURZAR(t_prev)      (what direct did in gap)

  Key questions:
    1. Does direct_move track synth_move? (R^2, beta)
    2. After a large synth_move, does the direct update lag or keep up?
    3. Is there a tradeable window between synth moving and direct updating?
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR         = Path(".")
TRADING_HR_START = 7    # UTC hour, weekday filter
TRADING_HR_END   = 21
SYNTH_MOVE_THRESH = 100  # EUR/ZAR pips synth move to flag as "event"
EURUSD_PIP       = 0.0001
EURZAR_PIP       = 0.0001
MAX_GAP_S        = 60    # exclude gaps longer than this (overnight stale)

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_pair(name: str, side: str) -> pd.DataFrame:
    path = next(DATA_DIR.glob(f"{name}_TickBar_3_{side}_*.csv"))
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df["ts"] = pd.to_datetime(df["EndTime"], format="%Y.%m.%d %H:%M:%S.%f")
    return df[["ts", "Close"]].rename(columns={"Close": side.lower()}).set_index("ts")


def build_mid(name: str) -> pd.DataFrame:
    ask = load_pair(name, "Ask")
    bid = load_pair(name, "Bid")
    c = ask.join(bid, how="outer").sort_index().ffill()
    c["mid"] = (c["ask"] + c["bid"]) / 2
    return c


# ---------------------------------------------------------------------------
# Load raw tick series (not gridded -- we want actual tick timestamps)
# ---------------------------------------------------------------------------
print("Loading raw tick series...")
eurusd = build_mid("EURUSD")
usdzar = build_mid("USDZAR")
eurzar = build_mid("EURZAR")

# Filter to weekday trading hours (UTC)
def trading_hours(df):
    mask = (
        (df.index.dayofweek < 5) &
        (df.index.hour >= TRADING_HR_START) &
        (df.index.hour < TRADING_HR_END)
    )
    return df[mask]

eurzar_t = trading_hours(eurzar)
print(f"  EUR/ZAR ticks in trading hours: {len(eurzar_t):,}")

# ---------------------------------------------------------------------------
# Tick-centric analysis: at each EUR/ZAR tick, look back to previous tick
# ---------------------------------------------------------------------------
print("\nBuilding tick-centric dataset...")

records = []
ez_times = eurzar_t.index.tolist()

for i in range(1, len(ez_times)):
    t_now  = ez_times[i]
    t_prev = ez_times[i - 1]
    gap_s  = (t_now - t_prev).total_seconds()

    if gap_s > MAX_GAP_S or gap_s < 0.1:
        continue

    # EUR/USD and USD/ZAR mid at t_prev and t_now (ffill -- last known quote)
    eu_prev = eurusd["mid"].asof(t_prev)
    uz_prev = usdzar["mid"].asof(t_prev)
    eu_now  = eurusd["mid"].asof(t_now)
    uz_now  = usdzar["mid"].asof(t_now)

    ez_prev = eurzar_t["mid"].iloc[i - 1]
    ez_now  = eurzar_t["mid"].iloc[i]
    ez_ask  = eurzar_t["ask"].iloc[i]
    ez_bid  = eurzar_t["bid"].iloc[i]
    ez_spread = (ez_ask - ez_bid) / EURZAR_PIP

    synth_prev = eu_prev * uz_prev
    synth_now  = eu_now  * uz_now
    synth_move = (synth_now - synth_prev) / EURZAR_PIP   # in EUR/ZAR pips
    direct_move = (ez_now - ez_prev) / EURZAR_PIP

    # Dislocation at t_prev: how far was synthetic from direct before this tick
    disloc_prev = (synth_prev - ez_prev) / EURZAR_PIP

    records.append({
        "t":            t_now,
        "gap_s":        gap_s,
        "synth_move":   synth_move,
        "direct_move":  direct_move,
        "disloc_prev":  disloc_prev,
        "ez_spread":    ez_spread,
        "eu_move_pips": (eu_now - eu_prev) / EURUSD_PIP,
    })

df = pd.DataFrame(records)
print(f"  Valid tick intervals: {len(df):,}")
print(f"  Date range: {df['t'].min()} to {df['t'].max()}")

# ---------------------------------------------------------------------------
# Q1: Does direct_move track synth_move?
# ---------------------------------------------------------------------------
print("\n=== Q1: Regression -- direct_move ~ synth_move ===")

from numpy.polynomial import polynomial as P
mask = df["synth_move"].abs() < 500   # exclude extreme outliers
d = df[mask]

# Simple OLS
x = d["synth_move"].values
y = d["direct_move"].values
n = len(x)
beta = np.cov(x, y)[0, 1] / np.var(x)
alpha = y.mean() - beta * x.mean()
y_hat = alpha + beta * x
ss_res = np.sum((y - y_hat) ** 2)
ss_tot = np.sum((y - y.mean()) ** 2)
r2 = 1 - ss_res / ss_tot

print(f"  N = {n:,}")
print(f"  beta  = {beta:.4f}  (1.0 = direct fully tracks synthetic)")
print(f"  alpha = {alpha:.4f} pips")
print(f"  R^2   = {r2:.4f}")
print(f"  Residual std = {np.std(y - y_hat):.2f} pips")

# ---------------------------------------------------------------------------
# Q2: Gap distribution and synth move during gap
# ---------------------------------------------------------------------------
print("\n=== Q2: Gap and synthetic move analysis ===")
print(f"  Gap seconds:   mean={df['gap_s'].mean():.1f}  median={df['gap_s'].median():.1f}  p90={df['gap_s'].quantile(0.9):.1f}")
print(f"  Synth move (pips):  mean={df['synth_move'].mean():.2f}  std={df['synth_move'].std():.2f}  p99={df['synth_move'].abs().quantile(0.99):.1f}")
print(f"  Direct move (pips): mean={df['direct_move'].mean():.2f}  std={df['direct_move'].std():.2f}")
print(f"  EUR/ZAR spread:     mean={df['ez_spread'].mean():.1f}  median={df['ez_spread'].median():.1f}")

# ---------------------------------------------------------------------------
# Q3: Event detection -- large synth moves during a gap
# ---------------------------------------------------------------------------
print(f"\n=== Q3: Events where |synth_move| > {SYNTH_MOVE_THRESH} pips in gap ===")
events = df[df["synth_move"].abs() > SYNTH_MOVE_THRESH].copy()
print(f"  Events: {len(events):,}")

if len(events) > 0:
    # Does the direct tick move in the same direction as the synth move?
    events["same_dir"] = np.sign(events["synth_move"]) == np.sign(events["direct_move"])
    events["direct_covers"] = events["direct_move"].abs() >= events["synth_move"].abs() * 0.5

    print(f"  Same direction: {events['same_dir'].sum()} / {len(events)} ({100*events['same_dir'].mean():.1f}%)")
    print(f"  Direct covers >=50% of synth move: {events['direct_covers'].sum()} ({100*events['direct_covers'].mean():.1f}%)")
    print(f"  Avg synth_move: {events['synth_move'].mean():.1f} pips")
    print(f"  Avg direct_move: {events['direct_move'].mean():.1f} pips")
    print(f"  Avg gap: {events['gap_s'].mean():.1f}s")

# ---------------------------------------------------------------------------
# Q4: Dislocation at t_prev predicts direct_move direction at next tick
# ---------------------------------------------------------------------------
print("\n=== Q4: Does pre-tick dislocation predict next direct tick direction? ===")
# When synthetic is above direct (disloc_prev > 0), does direct tick upward?
d2 = df[df["disloc_prev"].abs() > 50]  # at least 50 pip dislocation entering the tick
print(f"  Ticks with |pre-dislocation| > 50 pips: {len(d2):,}")
if len(d2) > 0:
    correct = (np.sign(d2["disloc_prev"]) == np.sign(d2["direct_move"])).mean()
    print(f"  Direction accuracy: {100*correct:.1f}%  (50% = random)")
    print(f"  Avg pre-disloc:  {d2['disloc_prev'].mean():.1f} pips")
    print(f"  Avg direct move: {d2['direct_move'].mean():.1f} pips")

# ---------------------------------------------------------------------------
# Q5: Tradeable edge -- can we enter before direct catches up?
# ---------------------------------------------------------------------------
print("\n=== Q5: P&L estimate for 'buy direct when synth > direct + spread' ===")
# Signal: disloc_prev > ez_spread (synthetic more than 1 spread above direct)
# Trade: buy EUR/ZAR at ask immediately after previous direct tick
# Exit: sell at next direct bid (we capture the direct tick move)
# Profit = direct_move - spread
df["entry_signal"] = df["disloc_prev"] > df["ez_spread"]
df["exit_signal"]  = df["disloc_prev"] < -df["ez_spread"]

for label, sig_col in [("BUY (synth > direct + spread)", "entry_signal"),
                        ("SELL (synth < direct - spread)", "exit_signal")]:
    trades = df[df[sig_col]]
    if len(trades) == 0:
        print(f"  {label}: 0 trades")
        continue
    pnl = trades["direct_move"] * np.sign(trades["disloc_prev"]) - trades["ez_spread"]
    print(f"  {label}:")
    print(f"    Trades: {len(trades):,}")
    print(f"    PnL per trade: mean={pnl.mean():.1f}  median={pnl.median():.1f}  std={pnl.std():.1f} pips")
    print(f"    Win rate: {(pnl > 0).mean()*100:.1f}%")
    print(f"    Total PnL: {pnl.sum():.0f} pips over {(df['t'].max()-df['t'].min()).days} days")

# ---------------------------------------------------------------------------
# Summary verdict
# ---------------------------------------------------------------------------
print("\n=== Summary ===")
print(f"Tick gap (median): {df['gap_s'].median():.1f}s -- time available to act before direct updates")
print(f"Synth move p99: {df['synth_move'].abs().quantile(0.99):.0f} EUR/ZAR pips per gap")
print(f"EUR/ZAR spread (median): {df['ez_spread'].median():.0f} pips -- the hurdle")
hurdle_pct = (df["synth_move"].abs() > df["ez_spread"]).mean() * 100
print(f"Gaps where |synth_move| exceeds spread: {hurdle_pct:.2f}% of ticks")
print()
print("Next step: if R^2 > 0.5 and direction accuracy > 60%, the lag is real.")
print("If spread is the blocker, find same triangle with tighter direct cross.")
