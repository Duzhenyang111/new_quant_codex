# A-Share Daily Trader

Daily simulated trading template for personal China A-share research.

## Security Tier

Paper trading only. This agent must not connect to broker APIs or place real orders.

## Data

Use `quant_workspace/data/bars.csv` first. AkShare is optional for free public daily bars and requires local installation with `pip install akshare`.

## Handoffs

- `data-reader`: read-only data inspection.
- `strategy-runner`: only worker with write access to generated outputs.
- `auditor`: read-only run audit.
