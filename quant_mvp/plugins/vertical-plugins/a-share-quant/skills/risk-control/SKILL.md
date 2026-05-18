---
name: risk-control
description: Apply simple risk limits to A-share simulated trading plans and account state.
---

# Risk Control

## First-Version Limits

- Maximum total equity exposure: 95%.
- Maximum single position weight: 20%.
- Cash buffer: 5%.
- Skip paused symbols.
- Skip buys at limit-up and sells at limit-down.
- Do not trade if today's open price is missing.

## Review

Every daily report should show skipped orders, current positions, cash, and selected symbols so the user can inspect risk manually.
