# Quant MVP

Personal China A-share daily simulated trading MVP.

## What It Contains

- `quant_core/`: Python stock selection, simulated execution, account ledger, reports, and optional AkShare adapter.
- `quant_app/`: local dashboard for the latest report.
- `quant_workspace/`: sample workspace and generated JSON outputs.
- `plugins/`: A-share agent and skills, following the parent repository's plugin style.
- `managed-agent-cookbooks/`: headless agent template with data reader, strategy runner, and auditor.
- `tests/`: core behavior tests.

## Run Tests

```powershell
python -m unittest tests.test_quant_core -v
```

## Run One Daily Cycle

```powershell
python -m quant_core.run_daily --workspace quant_workspace --trade-date 2026-05-15 --previous-trade-date 2026-05-14
```

## View Dashboard

From the parent repository root:

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8765/quant_mvp/quant_app/index.html
```

## Data

The MVP uses `quant_workspace/data/bars.csv` first. The dashboard reads download status from `quant_workspace/data/status.json`.

AkShare is optional and free:

```powershell
pip install akshare
```

Download daily bars:

```powershell
python -m quant_core.data.downloader --workspace quant_workspace --symbols 600519.SH,000001.SZ --start-date 2025-01-01 --end-date 2026-05-14
```
