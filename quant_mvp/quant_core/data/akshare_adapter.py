from __future__ import annotations

import time
from typing import Iterable

import requests


def _value(row: dict, *names: str, default=0):
    for name in names:
        if name in row:
            return row[name]
    return default


def normalize_daily_rows(symbol: str, rows: Iterable[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        normalized.append(
            {
                "date": str(_value(row, "\u65e5\u671f", "date")),
                "symbol": symbol,
                "open": float(_value(row, "\u5f00\u76d8", "open")),
                "high": float(_value(row, "\u6700\u9ad8", "high")),
                "low": float(_value(row, "\u6700\u4f4e", "low")),
                "close": float(_value(row, "\u6536\u76d8", "close")),
                "volume": float(_value(row, "\u6210\u4ea4\u91cf", "volume")),
                "amount": float(_value(row, "\u6210\u4ea4\u989d", "amount")),
                "paused": False,
                "is_st": False,
                "limit_up": False,
                "limit_down": False,
            }
        )
    return normalized


def _market_id(symbol: str) -> str:
    return "1" if symbol.endswith(".SH") else "0"


def _request_json(url: str, params: dict, retries: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            session = requests.Session()
            session.trust_env = False
            session.headers.update(
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://quote.eastmoney.com/",
                }
            )
            response = session.get(url, params=params, timeout=20)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"free Eastmoney request failed: {last_error}")


def fetch_eastmoney_daily(symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> list[dict]:
    fqt_map = {"": "0", "qfq": "1", "hfq": "2"}
    plain_symbol = symbol.split(".")[0]
    payload = _request_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        {
            "secid": f"{_market_id(symbol)}.{plain_symbol}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": fqt_map.get(adjust, "1"),
            "beg": start_date.replace("-", ""),
            "end": end_date.replace("-", ""),
        },
    )
    data = payload.get("data") or {}
    klines = data.get("klines") or []
    rows = []
    for line in klines:
        date, open_, close, high, low, volume, amount, *_ = line.split(",")
        rows.append(
            {
                "date": date,
                "symbol": symbol,
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
                "amount": float(amount),
                "paused": False,
                "is_st": False,
                "limit_up": False,
                "limit_down": False,
            }
        )
    return rows


def fetch_a_share_daily(symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> list[dict]:
    """Fetch free A-share daily bars without MCP or paid market-data tokens."""
    return fetch_eastmoney_daily(symbol, start_date, end_date, adjust)
