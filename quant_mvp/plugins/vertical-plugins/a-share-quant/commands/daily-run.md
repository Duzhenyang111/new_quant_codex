---
description: Run the A-share daily simulated trading cycle
argument-hint: "[trade date YYYY-MM-DD]"
---

# A-Share Daily Run

Run the daily batch after market close:

1. Load yesterday's plan.
2. Execute it at today's open price.
3. Update the simulated account.
4. Load today's close data.
5. Generate today's review.
6. Generate tomorrow's plan from data available through today.

Use local `quant_workspace/data/bars.csv` first. If the user has AkShare installed, the data adapter in `quant_core.data.akshare_adapter` can fetch free public A-share daily bars.
