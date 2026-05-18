from __future__ import annotations

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import requests

from quant_core.data.akshare_adapter import fetch_a_share_daily


FIELDS = [
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "paused",
    "is_st",
    "limit_up",
    "limit_down",
]


Fetcher = Callable[[str, str, str], list[dict]]


def _symbol_suffix(code: str) -> str:
    if code.startswith(("43", "83", "87", "88", "92")):
        return "BJ"
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "2", "3")):
        return "SZ"
    return "SH"


def _row_value(row: dict, *names: str) -> str:
    for name in names:
        if name in row:
            return str(row[name]).strip()
    return ""


def list_a_share_symbols(rows: Iterable[dict] | None = None) -> list[str]:
    """Return all A-share symbols with exchange suffixes.

    When rows are omitted, AkShare's free spot list is used.
    """
    if rows is None:
        rows = []
        for fs in ("m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "m:0+t:81+s:2048"):
            rows.extend(_fetch_eastmoney_symbols(fs))

    symbols = []
    seen = set()
    for row in rows:
        code = _row_value(row, "code", "代码", "证券代码").zfill(6)
        if not code or not code.isdigit():
            continue
        symbol = f"{code}.{_symbol_suffix(code)}"
        if symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols


def _fetch_eastmoney_symbols(fs: str) -> list[dict]:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://quote.eastmoney.com/",
        }
    )
    url = "https://push2delay.eastmoney.com/api/qt/clist/get"
    page_size = 100
    first = _request_json(
        session,
        url,
        {
            "pn": 1,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": fs,
            "fields": "f12,f14",
        },
    )
    total = int((first.get("data") or {}).get("total") or 0)
    if total == 0:
        return []
    records = []
    page_count = (total + page_size - 1) // page_size
    for page in range(1, page_count + 1):
        payload = first if page == 1 else _request_json(
            session,
            url,
            {
                "pn": page,
                "pz": page_size,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": fs,
                "fields": "f12,f14",
            },
        )
        records.extend(
            {"code": item.get("f12"), "name": item.get("f14")}
            for item in (payload.get("data") or {}).get("diff", [])
        )
    return records


def _request_json(session: requests.Session, url: str, params: dict, retries: int = 6) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, timeout=45)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"free Eastmoney symbol request failed: {last_error}")


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def _read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def download_symbols(
    workspace: str | Path,
    symbols: list[str],
    start_date: str,
    end_date: str,
    fetcher: Fetcher | None = None,
    cache_per_symbol: bool = False,
    resume: bool = True,
    workers: int = 1,
) -> dict:
    data_dir = Path(workspace) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    symbol_dir = data_dir / "symbols"
    fetch = fetcher or fetch_a_share_daily

    ok_symbols: list[str] = []
    failed_symbols: dict[str, str] = {}

    def write_status(done_count: int, row_count: int) -> None:
        status = {
            "source": "eastmoney_free_api",
            "started_at": started_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": start_date,
            "end_date": end_date,
            "requested_symbols": symbols,
            "ok_symbols": ok_symbols,
            "failed_symbols": failed_symbols,
            "rows": row_count,
            "done_symbols": done_count,
            "total_symbols": len(symbols),
            "bars_path": str(data_dir / "bars.csv"),
            "cache_per_symbol": cache_per_symbol,
            "symbol_cache_path": str(symbol_dir) if cache_per_symbol else None,
        }
        (data_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    started_at = datetime.now().isoformat(timespec="seconds")

    def load_or_fetch(symbol: str) -> tuple[str, list[dict], str | None]:
        symbol_path = symbol_dir / f"{symbol}.csv"
        try:
            if cache_per_symbol and resume and symbol_path.exists():
                symbol_rows = _read_rows(symbol_path)
            else:
                symbol_rows = fetch(symbol, start_date, end_date)
                if cache_per_symbol:
                    _write_rows(symbol_path, symbol_rows)
        except Exception as exc:  # public data endpoints can fail independently
            return symbol, [], str(exc)
        return symbol, symbol_rows, None

    rows_by_symbol: dict[str, list[dict]] = {}
    done = 0
    if workers <= 1:
        for symbol in symbols:
            symbol, symbol_rows, error = load_or_fetch(symbol)
            done += 1
            if error:
                failed_symbols[symbol] = error
            else:
                rows_by_symbol[symbol] = symbol_rows
                ok_symbols.append(symbol)
            if done % 25 == 0 or done == len(symbols):
                write_status(done, sum(len(value) for value in rows_by_symbol.values()))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(load_or_fetch, symbol): symbol for symbol in symbols}
            for future in as_completed(futures):
                symbol, symbol_rows, error = future.result()
                done += 1
                if error:
                    failed_symbols[symbol] = error
                else:
                    rows_by_symbol[symbol] = symbol_rows
                    ok_symbols.append(symbol)
                if done % 25 == 0 or done == len(symbols):
                    write_status(done, sum(len(value) for value in rows_by_symbol.values()))

    rows = []
    for symbol in symbols:
        rows.extend(rows_by_symbol.get(symbol, []))

    bars_path = data_dir / "bars.csv"
    _write_rows(bars_path, rows)

    status = {
        "source": "eastmoney_free_api",
        "started_at": started_at,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start_date,
        "end_date": end_date,
        "requested_symbols": symbols,
        "ok_symbols": ok_symbols,
        "failed_symbols": failed_symbols,
        "rows": len(rows),
        "done_symbols": len(ok_symbols) + len(failed_symbols),
        "total_symbols": len(symbols),
        "bars_path": str(bars_path),
        "cache_per_symbol": cache_per_symbol,
        "symbol_cache_path": str(symbol_dir) if cache_per_symbol else None,
    }
    (data_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Download free A-share daily bars into quant_workspace/data.")
    parser.add_argument("--workspace", default="quant_workspace")
    parser.add_argument("--symbols", help="Comma-separated symbols, e.g. 600001.SH,000001.SZ")
    parser.add_argument("--all-a-share", action="store_true", help="Download all A-share symbols from AkShare's free symbol list")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--cache-per-symbol", action="store_true", help="Write data/symbols/<symbol>.csv and resume from existing files")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    if args.all_a_share:
        symbols = list_a_share_symbols()
    elif args.symbols:
        symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
    else:
        raise SystemExit("Provide --symbols or --all-a-share")

    status = download_symbols(
        args.workspace,
        symbols,
        args.start_date,
        args.end_date,
        cache_per_symbol=args.cache_per_symbol,
        resume=not args.no_resume,
        workers=args.workers,
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
