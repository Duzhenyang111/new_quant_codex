from __future__ import annotations

import socket


def _baostock_code(symbol: str) -> str:
    code, exchange = symbol.split(".")
    return f"{exchange.lower()}.{code}"


def fetch_baostock_daily(symbol: str, start_date: str, end_date: str) -> list[dict]:
    import baostock as bs

    socket.setdefaulttimeout(30)
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_msg}")
    rows: list[dict] = []
    try:
        result = bs.query_history_k_data_plus(
            _baostock_code(symbol),
            "date,code,open,high,low,close,volume,amount,tradestatus,isST",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",
        )
        if result.error_code != "0":
            raise RuntimeError(f"baostock query failed: {result.error_msg}")
        while result.next():
            date, _code, open_, high, low, close, volume, amount, tradestatus, is_st = result.get_row_data()
            open_price = float(open_ or 0)
            close_price = float(close or 0)
            high_price = float(high or 0)
            low_price = float(low or 0)
            if not date or not open_price:
                continue
            rows.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": float(volume or 0),
                    "amount": float(amount or 0),
                    "paused": tradestatus != "1",
                    "is_st": is_st == "1",
                    "limit_up": False,
                    "limit_down": False,
                }
            )
    finally:
        bs.logout()
    return rows
