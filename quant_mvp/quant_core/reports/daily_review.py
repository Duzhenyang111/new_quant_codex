from __future__ import annotations

from quant_core.account.ledger import Account
from quant_core.execution.simulator import ExecutionResult
from quant_core.strategy.stock_selector import SelectionResult


def _market_summary(today_bars: dict[str, dict]) -> dict:
    daily_returns = []
    for bar in today_bars.values():
        open_price = float(bar.get("open", 0) or 0)
        close_price = float(bar.get("close", 0) or 0)
        if open_price:
            daily_returns.append(close_price / open_price - 1)
    advance_count = sum(1 for value in daily_returns if value > 0)
    decline_count = sum(1 for value in daily_returns if value < 0)
    flat_count = len(daily_returns) - advance_count - decline_count
    average_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0.0
    return {
        "type": "sample",
        "sample_count": len(daily_returns),
        "average_return": round(average_return, 6),
        "advance_count": advance_count,
        "decline_count": decline_count,
        "flat_count": flat_count,
        "advance_ratio": round(advance_count / len(daily_returns), 6) if daily_returns else 0.0,
    }


def _real_index_summary(market_index: dict) -> dict:
    open_price = float(market_index.get("open", 0) or 0)
    close_price = float(market_index.get("close", 0) or 0)
    daily_return = market_index.get("daily_return")
    if daily_return is None:
        daily_return = close_price / open_price - 1 if open_price else 0.0
    return {
        "type": "index",
        "symbol": market_index.get("symbol", ""),
        "name": market_index.get("name", market_index.get("symbol", "")),
        "open": round(open_price, 4),
        "close": round(close_price, 4),
        "daily_return": round(float(daily_return or 0), 6),
    }


def build_daily_review(
    trade_date: str,
    account: Account,
    execution: ExecutionResult,
    selection: SelectionResult,
    today_bars: dict[str, dict],
    market_index: dict | None = None,
) -> dict:
    equity = account.equity_at_open(today_bars)
    breadth = _market_summary(today_bars)
    market = _real_index_summary(market_index) if market_index else _market_summary(today_bars)
    holdings = []
    stock_market_value = 0.0
    for symbol, position in account.positions.items():
        if position.quantity <= 0:
            continue
        bar = today_bars.get(symbol, {})
        open_price = float(bar.get("open", position.cost_basis))
        close_price = float(bar.get("close", open_price))
        market_value = position.quantity * close_price
        stock_market_value += market_value
        holdings.append(
            {
                "symbol": symbol,
                "industry": "未知",
                "quantity": position.quantity,
                "cost_basis": round(position.cost_basis, 4),
                "open_price": round(open_price, 4),
                "close_price": round(close_price, 4),
                "daily_return": round(close_price / open_price - 1, 6) if open_price else 0.0,
                "position_pnl_pct": round(close_price / position.cost_basis - 1, 6) if position.cost_basis else 0.0,
                "market_value": round(market_value, 4),
            }
        )

    total_assets = account.cash + stock_market_value
    for holding in holdings:
        holding["weight"] = round(holding["market_value"] / total_assets, 6) if total_assets else 0.0

    stock_weight = stock_market_value / total_assets if total_assets else 0.0
    cash_weight = account.cash / total_assets if total_assets else 0.0
    trade_count = len(execution.trades)
    buys = sum(1 for trade in execution.trades if trade.action == "buy")
    sells = sum(1 for trade in execution.trades if trade.action == "sell")
    selected = [pick.symbol for pick in selection.picks]
    market_text = (
        f"{market['name']} 今日涨跌 {market['daily_return']:.2%}，开盘 {market['open']:.2f}，收盘 {market['close']:.2f}。"
        if market.get("type") == "index"
        else f"样本市场平均涨跌 {market['average_return']:.2%}，上涨 {market['advance_count']} 只，下跌 {market['decline_count']} 只。"
    )
    insights = [
        f"今日按开盘价执行 {trade_count} 笔交易：买入 {buys} 笔，卖出 {sells} 笔。",
        f"当前股票仓位 {stock_weight:.1%}，现金仓位 {cash_weight:.1%}。",
        market_text,
        f"明日候选池前列：{', '.join(selected[:5]) if selected else '暂无选股'}。",
    ]
    return {
        "trade_date": trade_date,
        "equity_at_open": round(equity, 4),
        "total_assets": round(total_assets, 4),
        "cash": round(account.cash, 4),
        "portfolio": {
            "position_count": len(holdings),
            "cash": round(account.cash, 4),
            "stock_market_value": round(stock_market_value, 4),
            "stock_weight": round(stock_weight, 6),
            "cash_weight": round(cash_weight, 6),
        },
        "risk": {
            "max_drawdown": 0.0,
            "annualized_volatility": 0.0,
            "sharpe": 0.0,
            "win_rate": 0.0,
        },
        "market": market,
        "breadth": breadth,
        "positions": account.to_dict()["positions"],
        "holdings": holdings,
        "trades": [trade.to_dict() for trade in execution.trades],
        "skipped_orders": execution.skipped,
        "selected_symbols": [pick.symbol for pick in selection.picks],
        "stock_pool": [
            {
                "symbol": pick.symbol,
                "score": pick.score,
                "target_weight": pick.target_weight,
                "reason": pick.reason,
                "metrics": pick.metrics,
            }
            for pick in selection.picks
        ],
        "rejected_symbols": selection.rejected,
        "insights": insights,
    }
