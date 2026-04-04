# Time-Series Momentum

## Introduction

Momentum is one of the oldest and most persistent anomalies in financial markets. The basic observation — that assets which have performed well recently tend to continue performing well — has been documented across equities, bonds, commodities, and currencies, in samples spanning centuries and out-of-sample across geographies where the original researchers had no data.

Time-series momentum, formalised by Moskowitz, Ooi & Pedersen (2012), is a clean version of this idea. Unlike cross-sectional momentum, which ranks assets against each other, TSMOM asks a simpler question: has this asset gone up or down over the past year? If up, go long. If down, go short. The signal is the asset's own past return — no ranking, no relative comparison.

The behavioural story is underreaction. Investors update their beliefs too slowly in response to persistent fundamental trends. Prices drift in the direction of the shock as more participants gradually incorporate the information. Eventually the trend exhausts itself and often reverses sharply — the momentum crash — but the intermediate drift is real and tradeable.

There is also a risk premia interpretation. Trend-following strategies are effectively long volatility: they tend to make money during prolonged bear markets by being short, providing a form of crisis insurance. Whether the returns are compensation for bearing this risk or a pure anomaly remains contested.

## Signal construction

The signal at each rebalance date is the 12-month return of each asset, skipping the most recent month:

```
signal_return = price[t - 21 days] / price[t - 252 days] - 1
signal = +1 if signal_return > 0, else -1
```

The skip — excluding the most recent month — exists because short-horizon returns exhibit mean reversion, not momentum. The 1-month reversal effect is well-documented and would contaminate the signal if included. By starting the lookback window 21 trading days before the rebalance date, we get the 12-1 month return that isolates the intermediate-horizon momentum.

The universe spans eight liquid ETFs covering equities across market caps and geographies, plus fixed income and gold: SPY, QQQ, IWM, EFA, EEM, GLD, TLT, LQD. This diversification across asset classes is intentional. The momentum effect is not unique to equities, and holding uncorrelated assets reduces left-tail risk compared to a pure equity momentum strategy.

Positions are rebalanced on the last trading day of each calendar month, with equal weight within each leg. Transaction costs of 5 basis points per side are applied to changed positions at each rebalance.

## Equity curve

The equity curve below shows the cumulative growth of $100 invested in the strategy versus a buy-and-hold investment in SPY over the same period.

{{ chart: equity_curve | caption="Cumulative return indexed to 100, 2010–2024" }}

## Headline metrics

{{ metric: sharpe_ratio }}
{{ metric: annualised_return_pct }}
{{ metric: max_drawdown_pct | positive_is_good=false }}

## Drawdown analysis

Momentum strategies are prone to sharp drawdowns when trends reverse quickly. The worst episodes tend to cluster around macro regime changes — central bank pivots, sudden risk-off events, coordinated recoveries following a market crash. The 2020 COVID crash and the subsequent rapid recovery in risk assets was particularly hostile for trend-following.

{{ chart: drawdown | caption="Rolling drawdown from equity peak" }}

## Return distribution

{{ chart: returns_dist | caption="Daily return distribution vs fitted normal" }}

## Rolling Sharpe

The rolling 63-day Sharpe ratio shows how the strategy's risk-adjusted performance varies across market regimes. Extended periods above zero indicate sustained trend-following alpha; dips below zero often correspond to choppy, mean-reverting markets where the signal fires on noise.

{{ chart: rolling_sharpe | caption="63-day rolling Sharpe ratio" }}

## Full performance summary

{{ metric_table }}

## Recent signals

{{ signal_table | rows=15 }}

## Observations

The results over 2010–2024 show a strategy that struggles to keep up with a simple buy-and-hold in SPY during an extended bull market with unusually low dispersion across asset classes. When equity momentum is strong and correlated, the short leg — typically allocated to underperforming fixed income or defensive assets — acts as a drag.

The strategy performs better during periods of genuine cross-asset dispersion: when equities fall while bonds or gold rise, the signal correctly allocates short equity exposure and long defensive assets, generating meaningful positive returns. The 2022 period (rate hikes, equity selloff, bond crash) is a stress case because both equity and bond legs were down simultaneously, straining the diversification thesis.

Known weaknesses:
- Equal weighting of long and short legs means the strategy is not market-neutral in gross exposure terms
- No volatility scaling: a vol-targeted version would reduce the whipsaw from high-volatility periods
- Transaction costs at 5bps per side are conservative for institutional execution but optimistic for retail

## Next steps

1. Add volatility scaling (position size inversely proportional to asset volatility) as per the original Moskowitz et al. specification
2. Test cross-sectional momentum as an overlay to rank the long and short legs
3. Extend the universe to include commodities via GLD alternatives and energy ETFs
4. Examine the impact of the skip period: 0, 5, 10, 21, and 63 days
5. Walk-forward optimisation of the lookback window to test parameter sensitivity
