from __future__ import annotations

import argparse
import json
from pathlib import Path

from quant_core.account.ledger import Account
from quant_core.data.index_adapter import index_for_date, read_index_rows
from quant_core.data.loader import bars_for_date, group_history, load_bars_csv
from quant_core.data.sqlite_store import bars_for_trade_date, history_until_trade_date, index_for_trade_date
from quant_core.execution.simulator import execute_plan_at_open
from quant_core.reports.daily_review import build_daily_review
from quant_core.strategy.stock_selector import select_stocks


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _reason_from_metrics(metrics: dict[str, float]) -> str:
    return (
        f"20日动量 {metrics.get('momentum_20', 0):.2%}，"
        f"60日动量 {metrics.get('momentum_60', 0):.2%}，"
        f"均线趋势 {metrics.get('trend', 0):.2%}，"
        f"成交额流动性得分 {metrics.get('liquidity', 0):.2f}，"
        f"波动率约 {-metrics.get('low_volatility', 0):.2%}"
    )


def _next_plan_from_selection(trade_date: str, selection) -> dict:
    return {
        "trade_date": trade_date,
        "execute_date": "next_open",
        "execute_price": "next_open",
        "orders": [
            {
                "symbol": pick.symbol,
                "action": "buy",
                "target_weight": pick.target_weight,
                "reason": _reason_from_metrics(pick.metrics),
                "score": pick.score,
                "metrics": pick.metrics,
            }
            for pick in selection.picks
        ],
        "risk_limits": {
            "max_total_equity_exposure": 0.95,
            "max_position_weight": 0.2,
            "cash_buffer": 0.05,
        },
    }


def _load_market_snapshot(root: Path, trade_date: str) -> tuple[dict[str, dict], dict[str, list[dict]], dict | None]:
    db_path = root / "data" / "market_data.sqlite"
    if db_path.exists():
        return (
            bars_for_trade_date(db_path, trade_date),
            history_until_trade_date(db_path, trade_date),
            index_for_trade_date(db_path, trade_date),
        )

    rows = load_bars_csv(root / "data" / "bars.csv")
    index_rows = read_index_rows(root / "data" / "indices.csv")
    return bars_for_date(rows, trade_date), group_history(rows), index_for_date(index_rows, trade_date)


def run_daily(workspace: str | Path, trade_date: str, previous_trade_date: str | None = None) -> dict:
    root = Path(workspace)
    previous_trade_date = previous_trade_date or trade_date
    today_bars, history, market_index = _load_market_snapshot(root, trade_date)

    account = Account.from_dict(_read_json(root / "account" / "latest.json", {"cash": 100000.0, "positions": {}}))
    previous_plan = _read_json(root / "plans" / f"{previous_trade_date}.json", {"orders": []})
    execution = execute_plan_at_open(account, previous_plan, today_bars)

    selection = select_stocks(history, trade_date=trade_date)
    next_plan = _next_plan_from_selection(trade_date, selection)
    review = build_daily_review(
        trade_date,
        execution.account,
        execution,
        selection,
        today_bars,
        market_index=market_index,
    )

    account_payload = execution.account.to_dict()
    _write_json(root / "account" / f"{trade_date}.json", account_payload)
    _write_json(root / "account" / "latest.json", account_payload)
    _write_json(root / "plans" / f"{trade_date}.json", next_plan)
    _write_json(root / "reports" / f"{trade_date}.json", review)
    _write_json(root / "reports" / "latest.json", {"review": review, "next_plan": next_plan})

    return {"review": review, "next_plan": next_plan}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one A-share daily simulated trading cycle.")
    parser.add_argument("--workspace", default="quant_workspace")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--previous-trade-date")
    args = parser.parse_args()
    result = run_daily(args.workspace, args.trade_date, args.previous_trade_date)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
