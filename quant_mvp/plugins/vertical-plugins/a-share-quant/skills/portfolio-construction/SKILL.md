---
name: portfolio-construction
description: Turn ranked A-share picks into target-weight orders for daily simulated trading.
---

# Portfolio Construction

## Default Rules

- Select top N ranked stocks.
- Keep total equity exposure at or below 95%.
- Cap each position at 20%.
- Preserve a 5% cash buffer.
- Generate target-weight orders, not market orders.

## Output

Write a JSON plan under `quant_workspace/plans/<trade-date>.json` with:

- `trade_date`
- `execute_date`
- `execute_price: next_open`
- `orders`
- `risk_limits`

Each order must include `symbol`, `action`, `target_weight`, `reason`, and factor metrics when available.
