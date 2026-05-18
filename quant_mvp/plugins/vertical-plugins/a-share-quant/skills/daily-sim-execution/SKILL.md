---
name: daily-sim-execution
description: Simulate China A-share daily orders by executing yesterday's plan at today's open price. Use for paper-trading account updates.
---

# Daily Simulated Execution

## Workflow

1. Load the previous plan from `quant_workspace/plans/<previous-date>.json`.
2. Load today's bars.
3. Execute sells before buys.
4. Use today's open price only.
5. Apply A-share constraints:
   - Buy quantity rounded down to 100-share lots.
   - Skip paused symbols.
   - Skip buys at limit-up.
   - Skip sells at limit-down.
6. Write account snapshots, trades, skipped orders, and review JSON.

## Implementation

Use `quant_core.execution.simulator.execute_plan_at_open`.

## Guardrails

- This is simulated trading only.
- Do not connect to a broker or place real orders.
- Every skipped order must include a reason.
