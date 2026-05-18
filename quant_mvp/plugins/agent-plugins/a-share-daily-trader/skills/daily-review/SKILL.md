---
name: daily-review
description: Produce the daily paper-trading review and tomorrow's operation plan from the latest A-share run.
---

# Daily Review

## Contents

- Orders executed at today's open.
- Orders skipped and why.
- Updated cash and positions.
- Selected symbols for tomorrow.
- Rejected symbols and filter reasons.
- Tomorrow's operation plan.

## Implementation

Use `quant_core.reports.daily_review.build_daily_review` and the JSON files in `quant_workspace/reports/`.

## Guardrails

- Clearly label this as simulated trading.
- Do not present generated plans as investment advice.
- Highlight data gaps before discussing strategy performance.
