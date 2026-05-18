from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Position:
    symbol: str
    quantity: int
    cost_basis: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Position":
        return cls(
            symbol=str(data["symbol"]),
            quantity=int(data.get("quantity", 0)),
            cost_basis=float(data.get("cost_basis", 0.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Account:
    cash: float
    positions: dict[str, Position]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Account":
        positions = {
            symbol: Position.from_dict({"symbol": symbol, **payload})
            for symbol, payload in (data.get("positions") or {}).items()
        }
        return cls(cash=float(data.get("cash", 0.0)), positions=positions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": round(self.cash, 4),
            "positions": {
                symbol: position.to_dict()
                for symbol, position in sorted(self.positions.items())
                if position.quantity > 0
            },
        }

    def equity_at_open(self, bars: dict[str, dict]) -> float:
        value = self.cash
        for symbol, position in self.positions.items():
            bar = bars.get(symbol)
            if bar:
                value += position.quantity * float(bar["open"])
            else:
                value += position.quantity * position.cost_basis
        return value
