from __future__ import annotations

import csv
from pathlib import Path


BOOL_FIELDS = {"paused", "is_st", "limit_up", "limit_down"}
FLOAT_FIELDS = {"open", "high", "low", "close", "volume", "amount"}


def _coerce(value: str, field: str):
    if field in BOOL_FIELDS:
        return str(value).strip().lower() in {"1", "true", "yes", "y"}
    if field in FLOAT_FIELDS:
        return float(value)
    return value


def load_bars_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {field: _coerce(value, field) for field, value in row.items()}
            for row in reader
        ]


def group_history(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row["symbol"]), []).append(row)
    for values in grouped.values():
        values.sort(key=lambda item: item["date"])
    return grouped


def bars_for_date(rows: list[dict], trade_date: str) -> dict[str, dict]:
    return {str(row["symbol"]): row for row in rows if row["date"] == trade_date}
