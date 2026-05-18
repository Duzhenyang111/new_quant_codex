# Quant MVP Storage Optimization Plan

## Goal

Upgrade Quant MVP from CSV-first runtime reads to a faster local analytics layout that can support full A-share daily history, daily stock selection, simulated execution, and frontend status reporting.

This plan is documentation only. No storage migration or runtime behavior changes are included in this step.

## Current State

The system currently stores downloaded market data as per-symbol CSV files:

```text
quant_workspace/data/symbols/<symbol>.csv
```

The downloader can resume from these files and eventually merge them into:

```text
quant_workspace/data/bars.csv
```

At the time this plan was written, the partial download cache had:

```text
symbol files: 2648
cache size: ~144 MB
date range: 2023-05-15 to 2026-05-14
```

This is acceptable as a raw download cache, but not ideal as the main runtime data store. Daily selection would repeatedly scan large CSV files, which will become slower as data grows.

## Recommended Architecture

Use a three-layer local data layout:

```text
quant_workspace/
  data/
    raw/
      symbols/
        600519.SH.csv
        000001.SZ.csv

    warehouse/
      bars.parquet
      factors.parquet

    quant.duckdb
    status.json
```

### Layer 1: Raw CSV Cache

Purpose:

- Preserve original downloaded data.
- Support interrupted downloads and resume.
- Keep a simple inspectable source.

Files:

```text
data/raw/symbols/<symbol>.csv
```

Notes:

- CSV remains useful for download recovery.
- The strategy runtime should not depend on scanning all raw CSVs.

### Layer 2: Parquet Warehouse

Purpose:

- Store clean normalized market data in a compressed columnar format.
- Speed up date-range and symbol-range scans.
- Reduce memory usage versus loading CSV into Python lists.

Files:

```text
data/warehouse/bars.parquet
data/warehouse/factors.parquet
```

`bars.parquet` schema:

```text
date              string or date
symbol            string
open              double
high              double
low               double
close             double
volume            double
amount            double
paused            boolean
is_st             boolean
limit_up          boolean
limit_down        boolean
```

Future `factors.parquet` schema:

```text
date              string or date
symbol            string
momentum_20       double
momentum_60       double
trend             double
liquidity         double
low_volatility    double
score             double
```

### Layer 3: DuckDB Query Engine

Purpose:

- Query Parquet directly with SQL.
- Avoid running a database service.
- Let the strategy load only the required rows.

File:

```text
data/quant.duckdb
```

Recommended objects:

```sql
create view bars as
select * from read_parquet('warehouse/bars.parquet');
```

Later, if needed:

```sql
create table factors as
select * from read_parquet('warehouse/factors.parquet');
```

## Why DuckDB + Parquet

| Option | Fit |
|---|---|
| Single CSV | Simple, but slow for full-market repeated reads |
| Per-symbol CSV only | Good for resume, weak for cross-sectional selection |
| SQLite | Easy, but less ideal for columnar analytical scans |
| Postgres / TimescaleDB | Powerful, but too heavy for this local MVP |
| Parquet only | Fast storage, but query ergonomics are weaker without an engine |
| DuckDB + Parquet | Best balance for local quant research and daily batch runs |

## Runtime Query Pattern

Daily selection usually needs:

1. Today's full-market cross section.
2. Each candidate's last 60 to 120 trading days.
3. Current account and previous plan.

Instead of reading all rows from `bars.csv`, the runtime should query:

```sql
select *
from bars
where date <= ?
qualify row_number() over (
  partition by symbol
  order by date desc
) <= 120;
```

For execution:

```sql
select *
from bars
where date = ?;
```

For frontend status:

```sql
select
  count(*) as rows,
  count(distinct symbol) as symbols,
  min(date) as start_date,
  max(date) as end_date
from bars;
```

## Migration Steps

### Step 1: Add Storage Dependencies

Use one of these options:

```powershell
pip install duckdb pyarrow
```

or, if pandas Parquet support is already available through another engine, still prefer `duckdb` explicitly.

### Step 2: Move Raw Symbol Cache

Current:

```text
quant_workspace/data/symbols/*.csv
```

Target:

```text
quant_workspace/data/raw/symbols/*.csv
```

The downloader should write new files to the target path.

### Step 3: Build Warehouse Writer

Create a module:

```text
quant_core/data/warehouse.py
```

Responsibilities:

- Read all `data/raw/symbols/*.csv`.
- Normalize types.
- Drop duplicate `(date, symbol)` rows.
- Sort by `symbol, date`.
- Write `data/warehouse/bars.parquet`.
- Update `data/status.json`.

### Step 4: Add DuckDB Access Layer

Create a module:

```text
quant_core/data/store.py
```

Responsibilities:

- Open `data/quant.duckdb`.
- Register or create the `bars` view.
- Query today's bars.
- Query trailing history for a trade date.
- Query warehouse summary.

Suggested interface:

```python
class MarketDataStore:
    def bars_for_date(self, trade_date: str) -> dict[str, dict]:
        ...

    def trailing_history(self, trade_date: str, lookback_days: int) -> dict[str, list[dict]]:
        ...

    def summary(self) -> dict:
        ...
```

### Step 5: Update Daily Runtime

Modify:

```text
quant_core/run_daily.py
```

Current behavior:

- Loads all rows from `data/bars.csv`.

Target behavior:

- Prefer DuckDB/Parquet if available.
- Fallback to CSV loader if warehouse is missing.

This keeps the MVP usable even before migration is complete.

### Step 6: Update Downloader Status

Modify:

```text
quant_core/data/downloader.py
```

Status should include:

```json
{
  "downloaded_symbols": 5704,
  "failed_symbols": 0,
  "raw_rows": 4200000,
  "warehouse_rows": 4200000,
  "warehouse_path": "quant_workspace/data/warehouse/bars.parquet",
  "duckdb_path": "quant_workspace/data/quant.duckdb",
  "start_date": "2023-05-15",
  "end_date": "2026-05-14"
}
```

### Step 7: Update Frontend Status Panel

Modify:

```text
quant_app/app.js
quant_app/index.html
```

Display:

- Download progress.
- Raw cache count.
- Warehouse row count.
- Start date and end date.
- Parquet file size.
- DuckDB availability.
- Last warehouse build time.

### Step 8: Update Tests

Add tests for:

- Building `bars.parquet` from symbol CSVs.
- Querying `bars_for_date`.
- Querying trailing history.
- Falling back to CSV if warehouse is missing.
- Status summary fields.

## Implementation Order

Recommended order:

1. Add tests for warehouse build.
2. Implement `warehouse.py`.
3. Add tests for DuckDB query layer.
4. Implement `store.py`.
5. Modify `run_daily.py` to use store with CSV fallback.
6. Update frontend status fields.
7. Convert current partial raw cache into Parquet.
8. Continue/resume full three-year download.
9. Build final warehouse.
10. Run daily cycle from the warehouse.

## Validation Criteria

The migration is complete when:

- `python -m unittest tests.test_quant_core -v` passes.
- `data/warehouse/bars.parquet` exists.
- `data/quant.duckdb` exists or can create the `bars` view on demand.
- The daily run no longer scans full `bars.csv` when Parquet is available.
- Frontend shows real warehouse status.
- A daily plan can be generated from the downloaded three-year history.

## Risks

- Free data endpoints may fail or throttle.
- Some symbols may have no three-year history due to recent listings.
- Beijing Stock Exchange symbol handling may need refinement.
- ST status and limit-up/limit-down flags are currently conservative defaults unless enhanced with richer data.
- Full-market factor computation should stay simple until data quality is verified.

## Recommendation

Proceed with DuckDB + Parquet, while keeping raw per-symbol CSV files as the durable download cache.

This gives the MVP a clean path:

```text
free download -> raw CSV cache -> Parquet warehouse -> DuckDB queries -> daily strategy -> frontend
```
