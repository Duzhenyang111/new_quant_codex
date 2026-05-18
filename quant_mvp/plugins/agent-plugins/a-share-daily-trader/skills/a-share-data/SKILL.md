---
name: a-share-data
description: Load and normalize free China A-share daily market data for the personal quant system. Use when the user needs OHLCV data without MCP or paid providers.
---

# A-Share Data

## Purpose

Provide free, auditable A-share daily bars to the trading workflow.

## Source Priority

1. `quant_workspace/data/bars.csv` local file, using the internal schema.
2. AkShare via `quant_core.data.akshare_adapter` if installed.
3. User-provided CSV exports from another free source, normalized before use.

## Required Schema

`date,symbol,open,high,low,close,volume,amount,paused,is_st,limit_up,limit_down`

Symbols should use suffixes such as `600001.SH` or `000001.SZ`.

## Guardrails

- Never use future data when generating a plan.
- Treat public data endpoints as unreliable; cache or persist the data used for every run.
- If a bar is missing, paused, or malformed, skip the related trade rather than fabricating a price.
