from __future__ import annotations

import argparse
import bisect
import json
import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from quant_core.account.ledger import Account
from quant_core.data.sqlite_store import connect
from quant_core.execution.simulator import execute_plan_at_open
from quant_core.reports.daily_review import build_daily_review
from quant_core.run_daily import _reason_from_metrics
from quant_core.strategy.stock_selector import select_stocks


def _rows_for_date(conn: sqlite3.Connection, trade_date: str) -> dict[str, dict]:
    rows = conn.execute("SELECT * FROM bars WHERE date = ?", (trade_date,)).fetchall()
    return {row["symbol"]: dict(row) for row in rows}


def _history(conn: sqlite3.Connection, trade_date: str, lookback_days: int = 220) -> dict[str, list[dict]]:
    start = (date.fromisoformat(trade_date) - timedelta(days=lookback_days)).isoformat()
    rows = conn.execute(
        """
        SELECT * FROM (
            SELECT b.*, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM bars b
            WHERE b.date <= ? AND b.date >= ?
        )
        WHERE rn <= 90
        ORDER BY symbol, date
        """,
        (trade_date, start),
    ).fetchall()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        payload = dict(row)
        payload["paused"] = bool(payload.get("paused"))
        payload["is_st"] = bool(payload.get("is_st"))
        payload["limit_up"] = bool(payload.get("limit_up"))
        payload["limit_down"] = bool(payload.get("limit_down"))
        grouped[payload["symbol"]].append(payload)
    return dict(grouped)


def _index_for_date(conn: sqlite3.Connection, trade_date: str, symbol: str = "000001.SH") -> dict | None:
    row = conn.execute("SELECT * FROM indices WHERE date = ? AND symbol = ?", (trade_date, symbol)).fetchone()
    return dict(row) if row else None


def _trading_dates(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT date FROM bars WHERE date >= ? AND date <= ? ORDER BY date",
        (start_date, end_date),
    ).fetchall()
    return [row["date"] for row in rows]


def _load_backtest_bars(conn: sqlite3.Connection, start_date: str, end_date: str, lookback_days: int = 220):
    warmup_start = (date.fromisoformat(start_date) - timedelta(days=lookback_days)).isoformat()
    rows = conn.execute(
        "SELECT * FROM bars WHERE date >= ? AND date <= ? ORDER BY symbol, date",
        (warmup_start, end_date),
    ).fetchall()
    history_by_symbol: dict[str, list[dict]] = defaultdict(list)
    bars_by_date: dict[str, dict[str, dict]] = defaultdict(dict)
    dates_by_symbol: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        payload = dict(row)
        payload["paused"] = bool(payload.get("paused"))
        payload["is_st"] = bool(payload.get("is_st"))
        payload["limit_up"] = bool(payload.get("limit_up"))
        payload["limit_down"] = bool(payload.get("limit_down"))
        symbol = payload["symbol"]
        history_by_symbol[symbol].append(payload)
        dates_by_symbol[symbol].append(payload["date"])
        if start_date <= payload["date"] <= end_date:
            bars_by_date[payload["date"]][symbol] = payload
    return dict(history_by_symbol), dict(dates_by_symbol), dict(bars_by_date)


def _history_slice(history_by_symbol: dict[str, list[dict]], dates_by_symbol: dict[str, list[str]], trade_date: str) -> dict[str, list[dict]]:
    sliced = {}
    for symbol, rows in history_by_symbol.items():
        end = bisect.bisect_right(dates_by_symbol[symbol], trade_date)
        if end:
            sliced[symbol] = rows[max(0, end - 90) : end]
    return sliced


def _load_indices(conn: sqlite3.Connection, start_date: str, end_date: str, symbol: str = "000001.SH") -> dict[str, dict]:
    rows = conn.execute(
        "SELECT * FROM indices WHERE symbol = ? AND date >= ? AND date <= ?",
        (symbol, start_date, end_date),
    ).fetchall()
    return {row["date"]: dict(row) for row in rows}


def _plan_from_selection(trade_date: str, selection, current_symbols: set[str]) -> dict:
    pick_symbols = {pick.symbol for pick in selection.picks}
    sell_orders = [
        {"symbol": symbol, "action": "sell", "target_weight": 0.0, "reason": "不在下一交易日动量候选池，调出组合"}
        for symbol in sorted(current_symbols - pick_symbols)
    ]
    buy_orders = [
        {
            "symbol": pick.symbol,
            "action": "buy",
            "target_weight": pick.target_weight,
            "reason": _reason_from_metrics(pick.metrics),
            "score": pick.score,
            "metrics": pick.metrics,
        }
        for pick in selection.picks
    ]
    return {
        "trade_date": trade_date,
        "execute_date": "next_open",
        "execute_price": "next_open",
        "orders": sell_orders + buy_orders,
    }


def _max_drawdown(values: list[float]) -> float:
    peak = -math.inf
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1)
    return max_dd


def run_year_backtest(workspace: str | Path, start_date: str, end_date: str, initial_cash: float = 100000.0) -> dict:
    root = Path(workspace)
    db_path = root / "data" / "market_data.sqlite"
    output_dir = root / "backtests"
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        trading_dates = _trading_dates(conn, start_date, end_date)
        if len(trading_dates) < 2:
            raise RuntimeError("not enough trading dates for backtest")
        history_by_symbol, dates_by_symbol, bars_by_date = _load_backtest_bars(conn, start_date, end_date)
        index_by_date = _load_indices(conn, start_date, end_date)

        account = Account(cash=initial_cash, positions={})
        reports = []
        equity_curve = []

        first_history = _history_slice(history_by_symbol, dates_by_symbol, trading_dates[0])
        first_selection = select_stocks(first_history, trading_dates[0])
        previous_plan = _plan_from_selection(trading_dates[0], first_selection, set())

        for trade_date in trading_dates[1:]:
            today_bars = bars_by_date.get(trade_date, {})
            execution = execute_plan_at_open(account, previous_plan, today_bars)
            account = execution.account
            history = _history_slice(history_by_symbol, dates_by_symbol, trade_date)
            selection = select_stocks(history, trade_date)
            review = build_daily_review(
                trade_date,
                account,
                execution,
                selection,
                today_bars,
                market_index=index_by_date.get(trade_date),
            )
            previous_plan = _plan_from_selection(trade_date, selection, set(account.positions.keys()))
            reports.append({"review": review, "next_plan": previous_plan})
            equity_curve.append({"date": trade_date, "total_assets": review["total_assets"], "market": review["market"]})

        assets = [point["total_assets"] for point in equity_curve]
        returns = [assets[index] / assets[index - 1] - 1 for index in range(1, len(assets)) if assets[index - 1]]
        win_rate = sum(1 for value in returns if value > 0) / len(returns) if returns else 0.0
        summary = {
            "start_date": trading_dates[1],
            "end_date": trading_dates[-1],
            "trading_days": len(trading_dates) - 1,
            "initial_cash": initial_cash,
            "final_assets": round(assets[-1], 4) if assets else initial_cash,
            "total_return": round((assets[-1] / initial_cash - 1) if assets else 0.0, 6),
            "max_drawdown": round(_max_drawdown(assets), 6),
            "win_rate": round(win_rate, 6),
            "final_cash": round(account.cash, 4),
            "final_positions": account.to_dict()["positions"],
            "reports_path": str(output_dir / f"year_backtest_{trading_dates[1]}_{trading_dates[-1]}.json"),
        }
        payload = {"summary": summary, "equity_curve": equity_curve, "reports": reports}
        output_path = output_dir / f"year_backtest_{trading_dates[1]}_{trading_dates[-1]}.json"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "latest_year_backtest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a one-year daily simulated trading backtest from SQLite data.")
    parser.add_argument("--workspace", default="quant_workspace")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--initial-cash", type=float, default=100000.0)
    args = parser.parse_args()
    result = run_year_backtest(args.workspace, args.start_date, args.end_date, args.initial_cash)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
