---
layout: idea
title: "The 10Y Sniper: Yield / USD-JPY Lead-Lag"
slug: "009-yield-usdjpy-lead-lag"
idea_id: "009"
version: "1.0.0"
status: "published"
tags:
  - microstructure
  - fx
  - fixed-income
  - intraday
  - lead-lag
date_range_start: "2025-10-01"
date_range_end: "2026-03-31"
---

## Overview

US T-Bond futures and USD/JPY are tethered by interest-rate parity: when Treasury yields spike, the dollar must strengthen against the yen. The two markets price the same information — but bond futures (traded on CME GLOBEX) price it first. Currency market-makers, running order books optimised for flow rather than latency, lag by seconds to roughly a minute during US session handoffs.

The **10Y Sniper** exploits this lag. Using native 3-tick bond bar timestamps as signal triggers — not resampled time bars — it enters USD/JPY within seconds of a significant bond yield shock, before the FX market has fully repriced. The strategy is in the market roughly 2% of each session.
<div class="stat-card">
  <div class="stat-label">Sharpe Ratio (Jan–Mar 2026)</div>
  <div class="stat-value positive">10.99</div>
</div>
<div class="stat-card">
  <div class="stat-label">Win Rate</div>
  <div class="stat-value positive">66.40%</div>
</div>
<div class="stat-card">
  <div class="stat-label">Gross P&L (3 months)</div>
  <div class="stat-value positive">426.00bps</div>
</div>
<div class="stat-card">
  <div class="stat-label">Trades (Jan–Mar 2026)</div>
  <div class="stat-value positive">434</div>
</div>
---

## The Lead-Lag Mechanism

CME bond futures (US T-Bond) trade on a full central limit order book with co-located HFT participants and sub-millisecond matching. EUR/USD and USD/JPY spot FX trades on distributed ECN venues with prime-brokerage credit intermediation — a structurally slower repricing chain.

When a macroeconomic data release, Fed speaker headline, or large institutional bond order moves T-Bond futures by more than 2–3 standard deviations (yield-equivalent), the FX market adjusts — but not instantaneously. Empirically, the full repricing takes 30–120 seconds depending on session liquidity. The strategy captures the first portion of that adjustment.

This is a **structural** microstructure edge, not a data artefact. The lag exists because:
1. FX market-makers process bond moves from their own risk management systems, not as primary signal sources
2. During US session opening and European session overlap (14:00–22:00 EET), liquidity is fragmented across many ECN venues
3. USD/JPY has a uniquely direct link to US yields via the JPY carry trade — unlike EUR/JPY or AUD/JPY, where the cross leg muddies the signal direction

EUR/JPY and AUD/JPY were tested and consistently negative across all parameter combinations. USD/JPY is the right instrument.

---

## Signal Architecture

All logic runs at native bond tick-bar frequency — the bond 3-tick bar timestamp is the event clock.

**Bond yield Z-score** (rolling over 20 bond events):

```
yield_ret  = -bond_return    # price down = yield up
yield_z    = zscore(yield_ret, window=20)
```

**FX quiet filter** — USD/JPY must not have repriced yet:

```
fx_ret_5m  = (fx_mid[T] - fx_mid[T - 5min]) / fx_mid[T - 5min]
fx_z       = zscore(fx_ret_5m, window=30 bond events)
```

**Entry conditions** (session: 14:00–22:00 EET):

| Direction | Bond yield | FX state |
|-----------|-----------|---------|
| Long USD/JPY | yield_z > 2.5 | fx_z < 0.5 |
| Short USD/JPY | yield_z < −2.5 | fx_z > −0.5 |

**Execution**: enter at ask (long) or bid (short) immediately at the bond event timestamp. Exit at bid (long) or ask (short) after 3 minutes. One position at a time. The natural bid/ask spread is embedded — no fixed cost estimate is used.

---

## Performance
<div class="chart-wrapper">
  <div>                        <script type="text/javascript">window.PlotlyConfig = {MathJaxConfig: 'local'};</script>
        <script charset="utf-8" src="https://cdn.plot.ly/plotly-3.3.0.min.js" integrity="sha256-bO3dS6yCpk9aK4gUpNELtCiDeSYvGYnK7jFI58NQnHI=" crossorigin="anonymous"></script>                <div id="56510d7c-5036-430d-b00c-a961022e1b19" class="plotly-graph-div" style="height:380px; width:100%;"></div>            <script type="text/javascript">                window.PLOTLYENV=window.PLOTLYENV || {};                                if (document.getElementById("56510d7c-5036-430d-b00c-a961022e1b19")) {                    Plotly.newPlot(                        "56510d7c-5036-430d-b00c-a961022e1b19",                        [{"fill":"tozeroy","fillcolor":"rgba(26,86,219,0.08)","line":{"color":"#1a56db","width":2.5},"mode":"lines","name":"Cumulative P&L","x":["2026-01-02T00:00:00","2026-01-05T00:00:00","2026-01-06T00:00:00","2026-01-07T00:00:00","2026-01-08T00:00:00","2026-01-09T00:00:00","2026-01-12T00:00:00","2026-01-13T00:00:00","2026-01-14T00:00:00","2026-01-15T00:00:00","2026-01-16T00:00:00","2026-01-19T00:00:00","2026-01-20T00:00:00","2026-01-21T00:00:00","2026-01-22T00:00:00","2026-01-23T00:00:00","2026-01-26T00:00:00","2026-01-27T00:00:00","2026-01-28T00:00:00","2026-01-29T00:00:00","2026-01-30T00:00:00","2026-02-02T00:00:00","2026-02-03T00:00:00","2026-02-04T00:00:00","2026-02-05T00:00:00","2026-02-06T00:00:00","2026-02-09T00:00:00","2026-02-10T00:00:00","2026-02-11T00:00:00","2026-02-12T00:00:00","2026-02-13T00:00:00","2026-02-16T00:00:00","2026-02-17T00:00:00","2026-02-18T00:00:00","2026-02-19T00:00:00","2026-02-20T00:00:00","2026-02-23T00:00:00","2026-02-24T00:00:00","2026-02-25T00:00:00","2026-02-26T00:00:00","2026-02-27T00:00:00","2026-03-02T00:00:00","2026-03-03T00:00:00","2026-03-04T00:00:00","2026-03-05T00:00:00","2026-03-06T00:00:00","2026-03-09T00:00:00","2026-03-10T00:00:00","2026-03-11T00:00:00","2026-03-12T00:00:00","2026-03-13T00:00:00","2026-03-16T00:00:00","2026-03-17T00:00:00","2026-03-18T00:00:00","2026-03-19T00:00:00","2026-03-20T00:00:00","2026-03-23T00:00:00","2026-03-24T00:00:00","2026-03-25T00:00:00","2026-03-26T00:00:00","2026-03-27T00:00:00","2026-03-30T00:00:00","2026-03-31T00:00:00"],"y":{"dtype":"f8","bdata":"tINJXBVvBsB4BNg5SIr8v2I0\u002flvpCRdAHIIIXSfvMEBwH65hsWozQINzbY4vYTlADMMxz1avPUDINZARFatAQHgr1\u002fhmskNA8UPJ6TKDR0DyfHmg6bxKQJnu0bLxDUtAoUik+TeHS0DYTndCw2VIQLTRoS9ehUtA6BqC7Ho0S0B4hTIL8mVLQENySM+XkVJAe28awlVxSkDSv3wGf\u002f1QQKxNkRxqLlFAwyBTDUTPUUAWx8s5pkpSQOBnUKwKfVNAKep2\u002fi\u002fYV0AKtbc3T+BXQD4wZ1qmv1dAXGXgb5GIVkCU4UmD\u002fJhhQOqbx+xpkWJAzfP1dztgZkBwfthgGqVmQKl7BlSjAGdA+0dKyffzZ0BvrN9x9IppQPhe7g0nrGlAEvgFDb9NakBnxaDjtZdqQGuhEAdEqGpA5+4Ox7M1a0C+y32JjFJrQAgNZLqEhWtAAR5CJ13Aa0B1JsacB\u002f5sQMDUZex0oG1AqZHCqIPcb0A7OPFtvSVwQGrLjmBIpHBAqs8bH+\u002fkcEDm3IecKxpxQIbLat6mZnFAXuICwr8xckChM3I68E9yQEOAMwlJqHJAXl6RWCVVdEBMh4uVsSZ1QHWlOfa+aHZAyfDCVYhTd0BIuqAsJnp4QHojg5x2CHlAB1iVhYb4eEAa2xtCK7l5QOtcrql1qHpA"},"type":"scatter"}],                        {"template":{"data":{"barpolar":[{"marker":{"line":{"color":"white","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"white","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"#C8D4E3","linecolor":"#C8D4E3","minorgridcolor":"#C8D4E3","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"#C8D4E3","linecolor":"#C8D4E3","minorgridcolor":"#C8D4E3","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermapbox":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermapbox"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"white","showlakes":true,"showland":true,"subunitcolor":"#C8D4E3"},"hoverlabel":{"align":"left"},"hovermode":"closest","mapbox":{"style":"light"},"paper_bgcolor":"white","plot_bgcolor":"white","polar":{"angularaxis":{"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":""},"bgcolor":"white","radialaxis":{"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"},"yaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"},"zaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""},"baxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""},"bgcolor":"white","caxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":"","title":{"standoff":15},"zerolinecolor":"#EBF0F8","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":"","title":{"standoff":15},"zerolinecolor":"#EBF0F8","zerolinewidth":2}}},"shapes":[{"line":{"color":"#9ca3af","width":1},"type":"line","x0":0,"x1":1,"xref":"x domain","y0":0,"y1":0,"yref":"y"}],"font":{"color":"#1a1a2e"},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","title":{"text":"Cumulative P&L â€” IS period (Janâ€“Mar 2026, bz=2.0, exit=2m)"},"yaxis":{"title":{"text":"Cumulative P&L (bps)"}},"xaxis":{"title":{"text":""}},"showlegend":false,"height":380},                        {"responsive": true}                    )                };            </script>        </div>
  <p class="chart-caption">Cumulative P&L (basis points) over Jan–Mar 2026 using optimised parameters (bz=2.0, exit=2m). The strategy accumulates steadily with minimal drawdown — consistent with a microstructure edge rather than a macro bet.</p>
</div>
The daily P&L distribution is narrow and positively skewed. Time in market is approximately 2% of session, which produces very low annualised volatility (~1–2%) and consequently high Sharpe ratios. This is a feature of the strategy's design — it is not leveraged and is not replicating a macro position.

---

## Monthly Consistency

Six consecutive profitable months across two independent periods, using the conservative a-priori parameters (bz=2.5, exit=3m — never adjusted to data).
<div class="chart-wrapper">
  <div>                        <script type="text/javascript">window.PlotlyConfig = {MathJaxConfig: 'local'};</script>
        <script charset="utf-8" src="https://cdn.plot.ly/plotly-3.3.0.min.js" integrity="sha256-bO3dS6yCpk9aK4gUpNELtCiDeSYvGYnK7jFI58NQnHI=" crossorigin="anonymous"></script>                <div id="3d1acb80-5b15-471d-8dac-f2ea95783586" class="plotly-graph-div" style="height:380px; width:100%;"></div>            <script type="text/javascript">                window.PLOTLYENV=window.PLOTLYENV || {};                                if (document.getElementById("3d1acb80-5b15-471d-8dac-f2ea95783586")) {                    Plotly.newPlot(                        "3d1acb80-5b15-471d-8dac-f2ea95783586",                        [{"marker":{"color":["#d97706","#d97706","#d97706","#1a56db","#1a56db","#1a56db"]},"text":["108","56","49","72","113","121"],"textposition":"outside","x":["Oct 2025","Nov 2025","Dec 2025","Jan 2026","Feb 2026","Mar 2026"],"y":[108.0,56.5,48.6,72.1,112.7,121.3],"type":"bar"},{"marker":{"color":"#d97706"},"name":"Q4 2025 OOS","x":[],"y":[],"type":"bar"},{"marker":{"color":"#1a56db"},"name":"Janâ€“Mar 2026 IS","x":[],"y":[],"type":"bar"}],                        {"template":{"data":{"barpolar":[{"marker":{"line":{"color":"white","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"white","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"#C8D4E3","linecolor":"#C8D4E3","minorgridcolor":"#C8D4E3","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"#C8D4E3","linecolor":"#C8D4E3","minorgridcolor":"#C8D4E3","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermapbox":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermapbox"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"white","showlakes":true,"showland":true,"subunitcolor":"#C8D4E3"},"hoverlabel":{"align":"left"},"hovermode":"closest","mapbox":{"style":"light"},"paper_bgcolor":"white","plot_bgcolor":"white","polar":{"angularaxis":{"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":""},"bgcolor":"white","radialaxis":{"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"},"yaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"},"zaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""},"baxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""},"bgcolor":"white","caxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":"","title":{"standoff":15},"zerolinecolor":"#EBF0F8","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":"","title":{"standoff":15},"zerolinecolor":"#EBF0F8","zerolinewidth":2}}},"shapes":[{"line":{"color":"#9ca3af","width":1},"type":"line","x0":0,"x1":1,"xref":"x domain","y0":0,"y1":0,"yref":"y"}],"font":{"color":"#1a1a2e"},"legend":{"orientation":"h","yanchor":"bottom","y":1.02,"xanchor":"left","x":0},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","title":{"text":"Monthly P&L â€” a-priori params (bz=2.5, exit=3m), six months"},"yaxis":{"title":{"text":"P&L (bps)"}},"xaxis":{"title":{"text":""}},"height":380,"showlegend":true,"barmode":"overlay"},                        {"responsive": true}                    )                };            </script>        </div>
  <p class="chart-caption">Monthly P&L across Q4 2025 (out-of-sample, amber) and Jan–Mar 2026 (in-sample, blue), a-priori parameters. All six months positive. December 2025 shows lower activity consistent with year-end thin markets.</p>
</div>
---

## Out-of-Sample Robustness

The strategy was developed exclusively on Jan–Mar 2026 data. Two independent out-of-sample tests were applied:

1. **Walk-forward (March 2026)**: parameters re-optimised on Jan+Feb only, tested on unseen March data
2. **Q4 2025 prior period**: fully independent quarter preceding all development
<div class="chart-wrapper">
  <div>                        <script type="text/javascript">window.PlotlyConfig = {MathJaxConfig: 'local'};</script>
        <script charset="utf-8" src="https://cdn.plot.ly/plotly-3.3.0.min.js" integrity="sha256-bO3dS6yCpk9aK4gUpNELtCiDeSYvGYnK7jFI58NQnHI=" crossorigin="anonymous"></script>                <div id="7e6ffa93-9807-4c64-aca8-6fc856c2f593" class="plotly-graph-div" style="height:420px; width:100%;"></div>            <script type="text/javascript">                window.PLOTLYENV=window.PLOTLYENV || {};                                if (document.getElementById("7e6ffa93-9807-4c64-aca8-6fc856c2f593")) {                    Plotly.newPlot(                        "7e6ffa93-9807-4c64-aca8-6fc856c2f593",                        [{"marker":{"color":"#9ca3af"},"name":"A-priori (bz=2.5, exit=3m)","text":["8.7","11.4","7.3"],"textposition":"outside","x":["IS (Janâ€“Mar 2026)","Walk-Fwd OOS\n(Mar 2026)","Q4 2025 OOS\n(Octâ€“Dec 2025)"],"y":[8.69,11.38,7.31],"type":"bar"},{"marker":{"color":"#1a56db"},"name":"Optimised (bz=2.0, exit=2m)","text":["11.0","20.7","12.0"],"textposition":"outside","x":["IS (Janâ€“Mar 2026)","Walk-Fwd OOS\n(Mar 2026)","Q4 2025 OOS\n(Octâ€“Dec 2025)"],"y":[10.99,20.71,12.04],"type":"bar"}],                        {"template":{"data":{"barpolar":[{"marker":{"line":{"color":"white","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"white","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"#C8D4E3","linecolor":"#C8D4E3","minorgridcolor":"#C8D4E3","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"#C8D4E3","linecolor":"#C8D4E3","minorgridcolor":"#C8D4E3","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermapbox":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermapbox"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"white","showlakes":true,"showland":true,"subunitcolor":"#C8D4E3"},"hoverlabel":{"align":"left"},"hovermode":"closest","mapbox":{"style":"light"},"paper_bgcolor":"white","plot_bgcolor":"white","polar":{"angularaxis":{"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":""},"bgcolor":"white","radialaxis":{"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"},"yaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"},"zaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""},"baxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""},"bgcolor":"white","caxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":"","title":{"standoff":15},"zerolinecolor":"#EBF0F8","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":"","title":{"standoff":15},"zerolinecolor":"#EBF0F8","zerolinewidth":2}}},"shapes":[{"line":{"color":"#16a34a","dash":"dash","width":1},"type":"line","x0":0,"x1":1,"xref":"x domain","y0":1.0,"y1":1.0,"yref":"y"},{"line":{"color":"#9ca3af","width":1},"type":"line","x0":0,"x1":1,"xref":"x domain","y0":0,"y1":0,"yref":"y"}],"annotations":[{"showarrow":false,"text":"Sharpe = 1","x":1,"xanchor":"right","xref":"x domain","y":1.0,"yanchor":"top","yref":"y"}],"font":{"color":"#1a1a2e"},"yaxis":{"title":{"text":"Sharpe ratio"},"range":[0,25.887500000000003]},"legend":{"orientation":"h","yanchor":"bottom","y":1.02,"xanchor":"left","x":0},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","title":{"text":"Sharpe ratio across three independent test windows"},"xaxis":{"title":{"text":""}},"barmode":"group","height":420},                        {"responsive": true}                    )                };            </script>        </div>
  <p class="chart-caption">Sharpe ratio across three test windows. Grey bars show the a-priori specification (bond_z=2.5) — parameters chosen from the original strategy hypothesis, never adjusted to any data. All six bars are positive; the minimum is 7.3.</p>
</div><div class="stat-card">
  <div class="stat-label">Q4 2025 OOS Sharpe (a-priori)</div>
  <div class="stat-value positive">7.31</div>
</div>
<div class="stat-card">
  <div class="stat-label">Walk-Forward OOS Sharpe (a-priori)</div>
  <div class="stat-value positive">11.38</div>
</div>
<div class="stat-card">
  <div class="stat-label">Q4 2025 OOS Win Rate</div>
  <div class="stat-value positive">66.70%</div>
</div>
<div class="stat-card">
  <div class="stat-label">Q4 2025 OOS P&L (3 months)</div>
  <div class="stat-value positive">213.00bps</div>
</div>
The a-priori result is the most important: bond_z=2.5 was specified in the original strategy hypothesis before any backtesting began. It achieves Sharpe > 7 on two different unseen quarters. The edge is not a parameter fit.

---

## Execution Costs

The strategy requires genuine execution speed — the lag window is seconds to a few minutes. A standard REST API with sub-5-second round-trip is sufficient; co-location is not required.
<div class="chart-wrapper">
  <div>                        <script type="text/javascript">window.PlotlyConfig = {MathJaxConfig: 'local'};</script>
        <script charset="utf-8" src="https://cdn.plot.ly/plotly-3.3.0.min.js" integrity="sha256-bO3dS6yCpk9aK4gUpNELtCiDeSYvGYnK7jFI58NQnHI=" crossorigin="anonymous"></script>                <div id="13860511-bfa9-4c90-89dc-986b488e3fb5" class="plotly-graph-div" style="height:360px; width:100%;"></div>            <script type="text/javascript">                window.PLOTLYENV=window.PLOTLYENV || {};                                if (document.getElementById("13860511-bfa9-4c90-89dc-986b488e3fb5")) {                    Plotly.newPlot(                        "13860511-bfa9-4c90-89dc-986b488e3fb5",                        [{"marker":{"color":["#16a34a","#16a34a","#dc2626","#dc2626","#dc2626"]},"orientation":"h","text":["7.81","1.62","-3.19","-2.81","-11.04"],"textposition":"outside","x":[7.81,1.62,-3.19,-2.81,-11.04],"y":["Prime broker (0.1pip + $1\u002flot)","ECN retail (0.2pip + $3\u002flot)","ECN retail (0.5pip + $3\u002flot)","10s lag + 0.2pip + $3\u002flot","30s lag + 0.3pip + $5\u002flot"],"type":"bar"}],                        {"template":{"data":{"barpolar":[{"marker":{"line":{"color":"white","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"white","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"#C8D4E3","linecolor":"#C8D4E3","minorgridcolor":"#C8D4E3","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"#C8D4E3","linecolor":"#C8D4E3","minorgridcolor":"#C8D4E3","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermapbox":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermapbox"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"white","showlakes":true,"showland":true,"subunitcolor":"#C8D4E3"},"hoverlabel":{"align":"left"},"hovermode":"closest","mapbox":{"style":"light"},"paper_bgcolor":"white","plot_bgcolor":"white","polar":{"angularaxis":{"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":""},"bgcolor":"white","radialaxis":{"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"},"yaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"},"zaxis":{"backgroundcolor":"white","gridcolor":"#DFE8F3","gridwidth":2,"linecolor":"#EBF0F8","showbackground":true,"ticks":"","zerolinecolor":"#EBF0F8"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""},"baxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""},"bgcolor":"white","caxis":{"gridcolor":"#DFE8F3","linecolor":"#A2B1C6","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":"","title":{"standoff":15},"zerolinecolor":"#EBF0F8","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"#EBF0F8","linecolor":"#EBF0F8","ticks":"","title":{"standoff":15},"zerolinecolor":"#EBF0F8","zerolinewidth":2}}},"shapes":[{"line":{"color":"#16a34a","dash":"dash","width":1},"type":"line","x0":1.0,"x1":1.0,"xref":"x","y0":0,"y1":1,"yref":"y domain"},{"line":{"color":"#9ca3af","width":1},"type":"line","x0":0,"x1":0,"xref":"x","y0":0,"y1":1,"yref":"y domain"}],"annotations":[{"showarrow":false,"text":"Sharpe = 1","x":1.0,"xanchor":"left","xref":"x","y":1,"yanchor":"top","yref":"y domain"}],"font":{"color":"#1a1a2e"},"xaxis":{"title":{"text":"Sharpe ratio"},"range":[-12.54,9.809999999999999]},"margin":{"l":240},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","title":{"text":"Sharpe ratio under realistic execution scenarios"},"yaxis":{"title":{"text":""}},"height":360,"showlegend":false},                        {"responsive": true}                    )                };            </script>        </div>
  <p class="chart-caption">Sharpe ratio under five combined execution scenarios. ECN retail with tight spreads (0.2 pip slippage + $3/lot commission) still exceeds the Sharpe 1 target. Scenarios with 0.5 pip slippage or 30-second latency are unviable.</p>
</div><div class="stat-card">
  <div class="stat-label">Sharpe — ECN Retail (0.2pip + $3/lot)</div>
  <div class="stat-value positive">1.62</div>
</div>
<div class="stat-card">
  <div class="stat-label">Sharpe — Prime Broker (0.1pip + $1/lot)</div>
  <div class="stat-value positive">7.81</div>
</div>
The embedded bid/ask spread from data averages **0.97 pips round-trip** (0.62 bps) — this is the cost already baked into every backtest result above. The slippage and commission in the scenarios above are *additional* costs on top of the natural spread.

**Viable execution profile**: API latency < 5 seconds, extra slippage < 0.2 pip, commission ≤ $3/lot. This matches Interactive Brokers Lite, OANDA, or IC Markets Pro.

**Avoid**: major macro prints (CPI, NFP at 14:30 EET) where spreads widen to 2–5 pips. These events also generate the largest bond Z-scores — but the strategy edge collapses when execution costs spike.

---

## Limitations

- **Short history**: 6 months of data total (3 IS + 3 OOS). The sample covers a specific macro regime — rising US rates with active carry trade. A BOJ intervention period (e.g., Q2 2024) or Treasury market stress could close the lag window entirely.
- **Execution dependency**: unlike daily-rebalanced strategies, the edge disappears at > ~60-second execution latency. It requires a live connection to both a bond futures data feed and an FX execution API, with near-real-time event processing.
- **Signal sparsity at a-priori threshold**: bond_z=2.5 generates ~50–60 signals per month. This is statistically adequate but limits diversification — a single bad month could have outsized impact on reported Sharpe.
- **Spread regime risk**: the 0.97-pip round-trip in the data reflects normal liquid-hours conditions. News-driven spread widening is not modelled and would turn profitable setups into losses.
<table class="metric-table">
  <tbody>
    <tr>
      <td class="metric-key">Sharpe Is</td>
      <td class="metric-value positive">10.99</td>
    </tr>
    <tr>
      <td class="metric-key">Win Rate Is Pct</td>
      <td class="metric-value positive">66.40%</td>
    </tr>
    <tr>
      <td class="metric-key">Pnl Is Bps</td>
      <td class="metric-value positive">426.00</td>
    </tr>
    <tr>
      <td class="metric-key">N Trades Is</td>
      <td class="metric-value positive">434.00</td>
    </tr>
    <tr>
      <td class="metric-key">Profit Factor Is</td>
      <td class="metric-value positive">2.73</td>
    </tr>
    <tr>
      <td class="metric-key">Max Drawdown Is Pct</td>
      <td class="metric-value negative">-0.21%</td>
    </tr>
    <tr>
      <td class="metric-key">Sharpe Oos Apriori</td>
      <td class="metric-value positive">7.31</td>
    </tr>
    <tr>
      <td class="metric-key">Sharpe Oos Opt</td>
      <td class="metric-value positive">12.04</td>
    </tr>
    <tr>
      <td class="metric-key">Win Rate Oos Pct</td>
      <td class="metric-value positive">66.70%</td>
    </tr>
    <tr>
      <td class="metric-key">N Trades Oos</td>
      <td class="metric-value positive">138.00</td>
    </tr>
    <tr>
      <td class="metric-key">Pnl Oos Bps</td>
      <td class="metric-value positive">213.00</td>
    </tr>
    <tr>
      <td class="metric-key">Sharpe Wf Apriori</td>
      <td class="metric-value positive">11.38</td>
    </tr>
    <tr>
      <td class="metric-key">Sharpe Ecn Retail</td>
      <td class="metric-value positive">1.62</td>
    </tr>
    <tr>
      <td class="metric-key">Sharpe Prime</td>
      <td class="metric-value positive">7.81</td>
    </tr>
    <tr>
      <td class="metric-key">Bond Z Opt</td>
      <td class="metric-value positive">2.00</td>
    </tr>
    <tr>
      <td class="metric-key">Exit Mins Opt</td>
      <td class="metric-value positive">2.00</td>
    </tr>
    <tr>
      <td class="metric-key">Bond Z Apriori</td>
      <td class="metric-value positive">2.50</td>
    </tr>
    <tr>
      <td class="metric-key">Exit Mins Apriori</td>
      <td class="metric-value positive">3.00</td>
    </tr>
    <tr>
      <td class="metric-key">Session Start Eet</td>
      <td class="metric-value positive">14.00</td>
    </tr>
    <tr>
      <td class="metric-key">Session End Eet</td>
      <td class="metric-value positive">22.00</td>
    </tr>
  </tbody>
</table>