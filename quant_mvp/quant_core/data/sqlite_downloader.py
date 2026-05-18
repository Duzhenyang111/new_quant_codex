from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable

from quant_core.data.baostock_adapter import fetch_baostock_daily
from quant_core.data.downloader import FIELDS, list_a_share_symbols
from quant_core.data.sqlite_store import count_bars, latest_bar_date_by_symbol, upsert_bars

Fetcher = Callable[[str, str, str], list[dict]]


def _write_symbol_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def _manifest_from_symbol_cache(symbol_dir: Path) -> dict:
    symbols = []
    for path in sorted(symbol_dir.glob("*.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        symbols.append(
            {
                "symbol": path.stem,
                "rows": len(rows),
                "start_date": rows[0].get("date"),
                "end_date": rows[-1].get("date"),
            }
        )
    return {"symbols": symbols}


def refresh_symbol_manifest(workspace: str | Path) -> dict:
    root = Path(workspace)
    manifest = _manifest_from_symbol_cache(root / "data" / "symbols")
    (root / "data" / "symbol_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def fetch_daily_with_fallback(symbol: str, start_date: str, end_date: str) -> list[dict]:
    return fetch_baostock_daily(symbol, start_date, end_date)


def download_remaining_to_sqlite(
    workspace: str | Path,
    start_date: str,
    end_date: str,
    workers: int = 8,
    fetcher: Fetcher | None = None,
) -> dict:
    root = Path(workspace)
    data_dir = root / "data"
    symbol_dir = data_dir / "symbols"
    db_path = data_dir / "market_data.sqlite"
    status_path = data_dir / "sqlite_download_status.json"
    fetch = fetcher or fetch_daily_with_fallback

    all_symbols = list_a_share_symbols()
    latest = latest_bar_date_by_symbol(db_path)
    pending = [symbol for symbol in all_symbols if latest.get(symbol, "") < end_date]
    completed: list[str] = []
    failed: dict[str, str] = {}
    started_at = datetime.now().isoformat(timespec="seconds")
    row_count = count_bars(db_path)

    def write_status(done: int) -> None:
        status = {
            "source": "eastmoney_free_api_to_sqlite",
            "started_at": started_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": start_date,
            "end_date": end_date,
            "all_symbols": len(all_symbols),
            "initial_sqlite_symbols": len(latest),
            "pending_symbols": len(pending),
            "completed_symbols": completed,
            "failed_symbols": failed,
            "done_symbols": done,
            "bars_rows": row_count,
            "database_path": str(db_path),
        }
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_symbol(symbol: str) -> tuple[str, int, str | None]:
        try:
            rows = fetch(symbol, start_date, end_date)
            if not rows:
                return symbol, 0, "empty response"
            _write_symbol_csv(symbol_dir / f"{symbol}.csv", rows)
            inserted = upsert_bars(db_path, rows)
            return symbol, inserted, None
        except Exception as exc:
            time.sleep(0.2)
            return symbol, 0, str(exc)

    if not pending:
        write_status(0)
        refresh_symbol_manifest(root)
        return json.loads(status_path.read_text(encoding="utf-8"))

    done = 0
    write_status(done)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(load_symbol, symbol): symbol for symbol in pending}
        for future in as_completed(futures):
            symbol, inserted, error = future.result()
            done += 1
            if error:
                failed[symbol] = error
            else:
                completed.append(symbol)
                row_count += inserted
            if done % 10 == 0 or done == len(pending):
                write_status(done)

    refresh_symbol_manifest(root)
    write_status(done)
    return json.loads(status_path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Download missing A-share daily bars into SQLite and per-symbol CSV cache.")
    parser.add_argument("--workspace", default="quant_workspace")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    status = download_remaining_to_sqlite(args.workspace, args.start_date, args.end_date, args.workers)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
