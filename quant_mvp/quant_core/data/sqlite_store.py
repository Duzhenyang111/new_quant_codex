from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable


BAR_FIELDS = [
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

INDEX_FIELDS = ["date", "symbol", "name", "open", "high", "low", "close", "volume", "daily_return"]


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS bars (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL DEFAULT 0,
                amount REAL NOT NULL DEFAULT 0,
                paused INTEGER NOT NULL DEFAULT 0,
                is_st INTEGER NOT NULL DEFAULT 0,
                limit_up INTEGER NOT NULL DEFAULT 0,
                limit_down INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (symbol, date)
            );

            CREATE INDEX IF NOT EXISTS idx_bars_date ON bars(date);
            CREATE INDEX IF NOT EXISTS idx_bars_symbol_date ON bars(symbol, date);

            CREATE TABLE IF NOT EXISTS indices (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL DEFAULT 0,
                daily_return REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (symbol, date)
            );

            CREATE INDEX IF NOT EXISTS idx_indices_date ON indices(date);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _to_float(row: dict, field: str) -> float:
    return float(row.get(field) or 0)


def _to_int_bool(row: dict, field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool):
        return int(value)
    return 1 if str(value).lower() in {"1", "true", "yes"} else 0


def upsert_bars(db_path: str | Path, rows: Iterable[dict]) -> int:
    init_database(db_path)
    payload = [
        (
            str(row.get("date", "")),
            str(row.get("symbol", "")),
            _to_float(row, "open"),
            _to_float(row, "high"),
            _to_float(row, "low"),
            _to_float(row, "close"),
            _to_float(row, "volume"),
            _to_float(row, "amount"),
            _to_int_bool(row, "paused"),
            _to_int_bool(row, "is_st"),
            _to_int_bool(row, "limit_up"),
            _to_int_bool(row, "limit_down"),
        )
        for row in rows
        if row.get("date") and row.get("symbol")
    ]
    if not payload:
        return 0
    conn = connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO bars (
                date, symbol, open, high, low, close, volume, amount, paused, is_st, limit_up, limit_down
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                amount=excluded.amount,
                paused=excluded.paused,
                is_st=excluded.is_st,
                limit_up=excluded.limit_up,
                limit_down=excluded.limit_down
            """,
            payload,
        )
        conn.commit()
    finally:
        conn.close()
    return len(payload)


def upsert_indices(db_path: str | Path, rows: Iterable[dict]) -> int:
    init_database(db_path)
    payload = [
        (
            str(row.get("date", "")),
            str(row.get("symbol", "")),
            str(row.get("name", "")),
            _to_float(row, "open"),
            _to_float(row, "high"),
            _to_float(row, "low"),
            _to_float(row, "close"),
            _to_float(row, "volume"),
            _to_float(row, "daily_return"),
        )
        for row in rows
        if row.get("date") and row.get("symbol")
    ]
    if not payload:
        return 0
    conn = connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO indices (date, symbol, name, open, high, low, close, volume, daily_return)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
                name=excluded.name,
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                daily_return=excluded.daily_return
            """,
            payload,
        )
        conn.commit()
    finally:
        conn.close()
    return len(payload)


def count_bars(db_path: str | Path) -> int:
    init_database(db_path)
    conn = connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0])
    finally:
        conn.close()


def count_indices(db_path: str | Path) -> int:
    init_database(db_path)
    conn = connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM indices").fetchone()[0])
    finally:
        conn.close()


def latest_bar_date_by_symbol(db_path: str | Path) -> dict[str, str]:
    init_database(db_path)
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT symbol, MAX(date) AS latest_date FROM bars GROUP BY symbol").fetchall()
    finally:
        conn.close()
    return {row["symbol"]: row["latest_date"] for row in rows}


def _bar_payload(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["paused"] = bool(payload.get("paused"))
    payload["is_st"] = bool(payload.get("is_st"))
    payload["limit_up"] = bool(payload.get("limit_up"))
    payload["limit_down"] = bool(payload.get("limit_down"))
    return payload


def bars_for_trade_date(db_path: str | Path, trade_date: str) -> dict[str, dict]:
    init_database(db_path)
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM bars WHERE date = ?", (trade_date,)).fetchall()
    finally:
        conn.close()
    return {row["symbol"]: _bar_payload(row) for row in rows}


def history_until_trade_date(db_path: str | Path, trade_date: str, rows_per_symbol: int = 90) -> dict[str, list[dict]]:
    init_database(db_path)
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT b.*, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                FROM bars b
                WHERE b.date <= ?
            )
            WHERE rn <= ?
            ORDER BY symbol, date
            """,
            (trade_date, rows_per_symbol),
        ).fetchall()
    finally:
        conn.close()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        payload = _bar_payload(row)
        grouped.setdefault(payload["symbol"], []).append(payload)
    return grouped


def index_for_trade_date(db_path: str | Path, trade_date: str, symbol: str = "000001.SH") -> dict | None:
    init_database(db_path)
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM indices WHERE date = ? AND symbol = ?",
            (trade_date, symbol),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def import_bars_csv(csv_path: str | Path, db_path: str | Path, batch_size: int = 5000) -> int:
    imported = 0
    with Path(csv_path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        batch: list[dict] = []
        for row in reader:
            batch.append(row)
            if len(batch) >= batch_size:
                imported += upsert_bars(db_path, batch)
                batch = []
        if batch:
            imported += upsert_bars(db_path, batch)
    return imported


def import_symbol_csv_dir(symbol_dir: str | Path, db_path: str | Path, batch_size: int = 5000) -> int:
    imported = 0
    batch: list[dict] = []
    for csv_path in sorted(Path(symbol_dir).glob("*.csv")):
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                batch.append(row)
                if len(batch) >= batch_size:
                    imported += upsert_bars(db_path, batch)
                    batch = []
    if batch:
        imported += upsert_bars(db_path, batch)
    return imported


def import_indices_csv(csv_path: str | Path, db_path: str | Path, batch_size: int = 5000) -> int:
    imported = 0
    if not Path(csv_path).exists():
        return 0
    with Path(csv_path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        batch: list[dict] = []
        for row in reader:
            batch.append(row)
            if len(batch) >= batch_size:
                imported += upsert_indices(db_path, batch)
                batch = []
        if batch:
            imported += upsert_indices(db_path, batch)
    return imported
