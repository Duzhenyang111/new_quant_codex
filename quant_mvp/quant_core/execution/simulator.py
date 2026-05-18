from __future__ import annotations

from dataclasses import asdict, dataclass

from quant_core.account.ledger import Account, Position


@dataclass
class Trade:
    symbol: str
    action: str
    quantity: int
    price: float
    amount: float
    fee: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionResult:
    account: Account
    trades: list[Trade]
    skipped: dict[str, str]


def _buy_fee(amount: float, commission_rate: float) -> float:
    return max(amount * commission_rate, 5.0) if amount > 0 else 0.0


def _sell_fee(amount: float, commission_rate: float, stamp_tax_rate: float) -> float:
    return max(amount * commission_rate, 5.0) + amount * stamp_tax_rate if amount > 0 else 0.0


def execute_plan_at_open(
    account: Account,
    plan: dict,
    today_bars: dict[str, dict],
    commission_rate: float = 0.0003,
    stamp_tax_rate: float = 0.001,
    lot_size: int = 100,
) -> ExecutionResult:
    working = Account(
        cash=float(account.cash),
        positions={symbol: Position(pos.symbol, pos.quantity, pos.cost_basis) for symbol, pos in account.positions.items()},
    )
    base_equity = working.equity_at_open(today_bars)
    trades: list[Trade] = []
    skipped: dict[str, str] = {}

    orders = sorted(plan.get("orders", []), key=lambda item: 0 if item.get("action") == "sell" else 1)
    for order in orders:
        symbol = str(order["symbol"])
        action = str(order.get("action", "")).lower()
        target_weight = float(order.get("target_weight", 0.0))
        reason = str(order.get("reason", "planned_order"))
        bar = today_bars.get(symbol)
        if not bar:
            skipped[symbol] = "missing_open_bar"
            continue
        if bar.get("paused"):
            skipped[symbol] = "paused"
            continue
        if action == "buy" and bar.get("limit_up"):
            skipped[symbol] = "limit_up"
            continue
        if action == "sell" and bar.get("limit_down"):
            skipped[symbol] = "limit_down"
            continue

        price = float(bar["open"])
        current_qty = working.positions.get(symbol, Position(symbol, 0, 0.0)).quantity
        target_value = max(0.0, base_equity * target_weight)
        target_qty = int(target_value // (price * lot_size)) * lot_size

        if action == "sell":
            quantity = current_qty if target_weight <= 0 else max(0, current_qty - target_qty)
            if quantity <= 0:
                skipped[symbol] = "nothing_to_sell"
                continue
            amount = quantity * price
            fee = _sell_fee(amount, commission_rate, stamp_tax_rate)
            working.cash += amount - fee
            remaining = current_qty - quantity
            if remaining > 0:
                working.positions[symbol].quantity = remaining
            else:
                working.positions[symbol] = Position(symbol, 0, working.positions.get(symbol, Position(symbol, 0, price)).cost_basis)
            trades.append(Trade(symbol, "sell", quantity, price, amount, fee, reason))

        if action == "buy":
            quantity = max(0, target_qty - current_qty)
            affordable = int((working.cash / (price * (1 + commission_rate))) // lot_size) * lot_size
            quantity = min(quantity, affordable)
            if quantity <= 0:
                skipped[symbol] = "insufficient_cash_or_already_target"
                continue
            amount = quantity * price
            fee = _buy_fee(amount, commission_rate)
            working.cash -= amount + fee
            old = working.positions.get(symbol)
            if old:
                new_qty = old.quantity + quantity
                old.cost_basis = ((old.quantity * old.cost_basis) + amount + fee) / new_qty
                old.quantity = new_qty
            else:
                working.positions[symbol] = Position(symbol, quantity, (amount + fee) / quantity)
            trades.append(Trade(symbol, "buy", quantity, price, amount, fee, reason))

    return ExecutionResult(account=working, trades=trades, skipped=skipped)
