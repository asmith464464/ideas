# Heston Volatility Risk Premium

## Hypothesis

The Heston stochastic volatility model couples price and variance through a correlation parameter ρ (rho). When ρ < 0 — the *leverage effect* — rising variance is associated with falling prices and vice versa. This coupling creates a directional price implication when variance deviates from its long-run mean.

Rather than fitting a full Heston calibration (which breaks down on daily data), this strategy exploits the same signal via the **Volatility Risk Premium (VRP)**: the gap between implied volatility and realised volatility. When implied vol exceeds realised vol, the market is pricing in more future variance than has been observed — and via ρ < 0 this structurally implies a positive expected return on the underlying.

**VRP is structurally positive for equity indices** — market makers consistently price in a risk premium above realised vol, and investors pay it for the insurance. This allows the strategy to be almost always invested, avoiding the Sharpe dilution that plagues binary threshold strategies.

## Mathematical Framework

The Heston model couples price and variance:

$$dS_t = \mu S_t \, dt + \sqrt{\nu_t} \, S_t \, dW_t^1$$

$$d\nu_t = \kappa(\theta - \nu_t) \, dt + \sigma \sqrt{\nu_t} \, dW_t^2, \quad dW_t^1 \, dW_t^2 = \rho \, dt$$

When **ρ < 0** (confirmed leverage effect) and **ν_t > θ** (variance above long-run mean), the model predicts variance will revert downward — and the negative ρ means falling variance accompanies rising price. The VRP is the market's direct expression of this deviation: implied vol (a forward-looking estimate of √ν) above realised vol signals the market has priced in elevated variance.

## Signal Logic

For each pair (index ETF / vol index):

1. **Realised vol**: `RV_t = std(log returns, 20d) × √252 × 100` — annualised %
2. **VRP**: `VRP_t = implied_vol_t − RV_t` — positive when market prices in more vol than observed
3. **Leverage effect check**: `ρ_t = Corr(returns_t, Δimplied_vol_t, 60d)` — must be negative
4. **Score**: `score_i = max(VRP_i, 0)` if `ρ_i < −0.1`, else 0
5. **Weight**: `w_i = score_i / Σscores` — proportional allocation, rebalanced monthly

The rho filter gates GLD/GVZ during safe-haven demand episodes (when gold vol rises with gold prices — positive ρ), correctly excluding those periods.

## Universe

| Pair | Vol Index | Coverage |
|------|-----------|----------|
| SPY (S&P 500) | ^VIX | 1993–present |
| QQQ (Nasdaq 100) | ^VXN | 2001–present |
| GLD (Gold) | ^GVZ | 2008–present |

The backtest runs from the intersection date (~2008) when all three pairs have data.

## Results

{{ metric:sharpe_ratio | label=Sharpe Ratio (vs T-bill) }}
{{ metric:ann_return_pct | label=Annual Return | suffix=% }}
{{ metric:max_drawdown_pct | label=Max Drawdown | suffix=% }}
{{ metric:avg_weight_invested_pct | label=Average Weight Invested | suffix=% }}

{{ chart:equity_curve | caption=Cumulative log-return: VRP Strategy vs Equal-Weight Buy & Hold (2008–2026) }}

{{ chart:vrp_signal | caption=Rolling Volatility Risk Premium per pair — positive VRP drives allocation }}

{{ chart:allocation | caption=Monthly portfolio allocation by pair — weight proportional to VRP strength }}

## Benchmark Comparison

| Metric | Strategy | EW Buy & Hold |
|--------|----------|---------------|
| Annual Return | {{ metric:ann_return_pct }}% | {{ metric:bh_ann_return_pct }}% |
| Sharpe (vs T-bill) | {{ metric:sharpe_ratio }} | {{ metric:bh_sharpe_ratio }} |
| Max Drawdown | {{ metric:max_drawdown_pct }}% | {{ metric:bh_max_drawdown_pct }}% |

The strategy improves on buy & hold on both risk-adjusted return and drawdown. The drawdown reduction comes from natural de-risking: when VRP turns negative during crashes (implied vol spikes faster than realised vol adjusts), the strategy reduces exposure to the affected index.

## Design Choices

**Why VRP instead of CIR calibration?** Fitting κ, θ, σ from GARCH-estimated variance paths produces near-zero mean-reversion speeds on daily data (half-lives of months rather than days). VRP measured directly from liquid vol indices is more reliable and avoids estimation error.

**Why proportional weighting instead of binary signals?** Binary threshold signals only fire ~12% of the time (at VIX extremes), causing severe Sharpe dilution via the `SR ≈ √(invested%) × SR(active)` relationship. Proportional VRP weighting keeps the portfolio invested ~88% of the time while still tilting toward the highest VRP pairs.

**Why the rho filter?** The Heston edge is conditional on a negative price-vol correlation. GLD periodically acts as a safe haven (positive ρ); allocating during those episodes would invert the signal. The rolling 60-day ρ filter gates these periods out automatically.

**Why not add leverage or more pairs?** The natural ceiling for this strategy type is SR ≈ 0.75–0.80 with long-only equity exposure. Adding leverage would scale return and risk proportionally without improving Sharpe, and would not change the structural story.
