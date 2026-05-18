---
name: stock-selection-core
description: Technical A-share stock-selection engine using momentum, moving-average trend, liquidity, and low-volatility scoring.
---

# Stock Selection Core

## Filters

- Exclude ST or risk-warning stocks.
- Exclude paused stocks.
- Require at least 60 daily bars by default.
- Require minimum daily amount.

## Factors

Score eligible stocks with:

- 20-day momentum.
- 60-day momentum.
- 20-day versus 60-day moving-average trend.
- Log成交额 liquidity score.
- Negative 20-day annualized volatility as low-volatility score.

## Implementation

Use `quant_core.strategy.stock_selector.select_stocks`.

The default score weights are:

```text
0.35 * momentum_20
0.25 * momentum_60
0.20 * trend
0.10 * liquidity
0.10 * low_volatility
```

## Guardrails

- Use only data with `date <= trade_date`.
- Save factor metrics in the generated plan so every order is explainable.
- Keep the first version transparent; do not add machine-learning models until the rule-based loop is stable.
