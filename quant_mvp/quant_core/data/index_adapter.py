from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


DEFAULT_MARKET_INDICES = [
    {"symbol": "000001.SH", "ak_symbol": "sh000001", "name": "上证指数"},
    {"symbol": "399001.SZ", "ak_symbol": "sz399001", "name": "深证成指"},
    {"symbol": "000300.SH", "ak_symbol": "sh000300", "name": "沪深300"},
]

INDEX_FIELDS = ["date", "symbol", "name", "open", "high", "low", "close", "volume", "daily_return"]


def normalize_index_rows(symbol: str, name: str, rows: Iterable[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        open_price = float(row.get("open", row.get("开盘", 0)) or 0)
        close_price = float(row.get("close", row.get("收盘", 0)) or 0)
        normalized.append(
            {
                "date": str(row.get("date", row.get("日期", ""))),
                "symbol": symbol,
                "name": name,
                "open": open_price,
                "high": float(row.get("high", row.get("最高", 0)) or 0),
                "low": float(row.get("low", row.get("最低", 0)) or 0),
                "close": close_price,
                "volume": float(row.get("volume", row.get("成交量", 0)) or 0),
                "daily_return": close_price / open_price - 1 if open_price else 0.0,
            }
        )
    return normalized


def fetch_akshare_index_daily(ak_symbol: str, symbol: str, name: str, start_date: str, end_date: str) -> list[dict]:
    import akshare as ak

    frame = ak.stock_zh_index_daily(symbol=ak_symbol)
    rows = frame.to_dict("records")
    normalized = normalize_index_rows(symbol, name, rows)
    return [row for row in normalized if start_date <= row["date"] <= end_date]


def write_index_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in INDEX_FIELDS})


def read_index_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def index_for_date(rows: list[dict], trade_date: str, preferred_symbol: str = "000001.SH") -> dict | None:
    for row in rows:
        if row.get("date") == trade_date and row.get("symbol") == preferred_symbol:
            return _numeric_row(row)
    for row in rows:
        if row.get("date") == trade_date:
            return _numeric_row(row)
    return None


def _numeric_row(row: dict) -> dict:
    copied = dict(row)
    for field in ("open", "high", "low", "close", "volume", "daily_return"):
        copied[field] = float(copied.get(field) or 0)
    return copied


def download_market_indices(workspace: str | Path, start_date: str, end_date: str) -> dict:
    root = Path(workspace)
    index_dir = root / "data" / "indices"
    all_rows: list[dict] = []
    status = {
        "source": "akshare_free_index_daily",
        "start_date": start_date,
        "end_date": end_date,
        "indices": [],
        "rows": 0,
    }
    for config in DEFAULT_MARKET_INDICES:
        rows = fetch_akshare_index_daily(
            config["ak_symbol"],
            config["symbol"],
            config["name"],
            start_date,
            end_date,
        )
        write_index_rows(index_dir / f"{config['symbol']}.csv", rows)
        all_rows.extend(rows)
        status["indices"].append({"symbol": config["symbol"], "name": config["name"], "rows": len(rows)})
    write_index_rows(root / "data" / "indices.csv", all_rows)
    status["rows"] = len(all_rows)
    return status
