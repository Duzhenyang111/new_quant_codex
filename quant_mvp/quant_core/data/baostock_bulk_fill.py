from __future__ import annotations

import argparse
import csv
import json
import socket
from datetime import datetime
from pathlib import Path

from quant_core.data.downloader import FIELDS, list_a_share_symbols
from quant_core.data.sqlite_store import count_bars, latest_bar_date_by_symbol, upsert_bars


def _baostock_code(symbol: str) -> str:
    code, exchange = symbol.split(".")
    return f"{exchange.lower()}.{code}"


def _write_symbol_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def _fetch_rows(bs, symbol: str, start_date: str, end_date: str) -> list[dict]:
    result = bs.query_history_k_data_plus(
        _baostock_code(symbol),
        "date,code,open,high,low,close,volume,amount,tradestatus,isST",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2",
    )
    if result.error_code != "0":
        raise RuntimeError(result.error_msg)
    rows = []
    while result.next():
        date, _code, open_, high, low, close, volume, amount, tradestatus, is_st = result.get_row_data()
        if not date or not open_:
            continue
        rows.append(
            {
                "date": date,
                "symbol": symbol,
                "open": float(open_ or 0),
                "high": float(high or 0),
                "low": float(low or 0),
                "close": float(close or 0),
                "volume": float(volume or 0),
                "amount": float(amount or 0),
                "paused": tradestatus != "1",
                "is_st": is_st == "1",
                "limit_up": False,
                "limit_down": False,
            }
        )
    return rows


def _refresh_manifest(symbol_dir: Path, output_path: Path) -> None:
    symbols = []
    for path in sorted(symbol_dir.glob("*.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if rows:
            symbols.append({"symbol": path.stem, "rows": len(rows), "start_date": rows[0]["date"], "end_date": rows[-1]["date"]})
    output_path.write_text(json.dumps({"symbols": symbols}, ensure_ascii=False, indent=2), encoding="utf-8")


def bulk_fill(workspace: str | Path, start_date: str, end_date: str) -> dict:
    import baostock as bs

    socket.setdefaulttimeout(30)
    root = Path(workspace)
    data_dir = root / "data"
    symbol_dir = data_dir / "symbols"
    db_path = data_dir / "market_data.sqlite"
    status_path = data_dir / "baostock_bulk_status.json"
    all_symbols = list_a_share_symbols()
    latest = latest_bar_date_by_symbol(db_path)
    pending = [symbol for symbol in all_symbols if latest.get(symbol, "") < end_date]
    completed: list[str] = []
    failed: dict[str, str] = {}
    started_at = datetime.now().isoformat(timespec="seconds")
    bars_rows = count_bars(db_path)

    def write_status(done: int) -> None:
        status = {
            "source": "baostock_bulk_to_sqlite",
            "started_at": started_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": start_date,
            "end_date": end_date,
            "all_symbols": len(all_symbols),
            "initial_sqlite_symbols": len(latest),
            "pending_symbols": len(pending),
            "done_symbols": done,
            "completed_symbols": completed,
            "failed_symbols": failed,
            "bars_rows": bars_rows,
            "database_path": str(db_path),
        }
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_msg}")
    try:
        write_status(0)
        for index, symbol in enumerate(pending, start=1):
            try:
                rows = _fetch_rows(bs, symbol, start_date, end_date)
                if not rows:
                    failed[symbol] = "empty response"
                else:
                    _write_symbol_csv(symbol_dir / f"{symbol}.csv", rows)
                    inserted = upsert_bars(db_path, rows)
                    bars_rows += inserted
                    completed.append(symbol)
            except Exception as exc:
                failed[symbol] = str(exc)
            if index % 20 == 0 or index == len(pending):
                write_status(index)
    finally:
        bs.logout()
    _refresh_manifest(symbol_dir, data_dir / "symbol_manifest.json")
    write_status(len(pending))
    return json.loads(status_path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Stable single-session Baostock fill into SQLite.")
    parser.add_argument("--workspace", default="quant_workspace")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    args = parser.parse_args()
    print(json.dumps(bulk_fill(args.workspace, args.start_date, args.end_date), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
