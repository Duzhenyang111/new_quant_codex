from __future__ import annotations

import math
from dataclasses import dataclass

from quant_core.strategy.indicators import annualized_volatility, momentum, moving_average


@dataclass
class StockPick:
    symbol: str
    score: float
    target_weight: float
    reason: str
    metrics: dict[str, float]


@dataclass
class SelectionResult:
    trade_date: str
    picks: list[StockPick]
    rejected: dict[str, str]


def _latest_eligible_rows(rows: list[dict], trade_date: str) -> list[dict]:
    return [row for row in rows if str(row["date"]) <= trade_date]


def _zscore(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    mean = sum(values.values()) / len(values)
    variance = sum((value - mean) ** 2 for value in values.values()) / len(values)
    std = math.sqrt(variance)
    if std == 0:
        return {key: 0.0 for key in values}
    return {key: (value - mean) / std for key, value in values.items()}


def select_stocks(
    history_by_symbol: dict[str, list[dict]],
    trade_date: str,
    top_n: int = 5,
    min_history_days: int = 60,
    min_amount: float = 20_000_000,
    max_position_weight: float = 0.2,
) -> SelectionResult:
    raw_metrics: dict[str, dict[str, float]] = {}
    rejected: dict[str, str] = {}

    for symbol, rows in history_by_symbol.items():
        history = _latest_eligible_rows(rows, trade_date)
        if len(history) < min_history_days:
            rejected[symbol] = "insufficient_history"
            continue
        latest = history[-1]
        if latest.get("is_st"):
            rejected[symbol] = "st_or_risk_warning"
            continue
        if latest.get("paused"):
            rejected[symbol] = "paused"
            continue
        if float(latest.get("amount", 0)) < min_amount:
            rejected[symbol] = "low_liquidity"
            continue

        closes = [float(row["close"]) for row in history]
        ma20 = moving_average(closes, 20)
        ma60 = moving_average(closes, 60)
        vol20 = annualized_volatility(closes, 20)
        raw_metrics[symbol] = {
            "momentum_20": momentum(closes, 20),
            "momentum_60": momentum(closes, 60),
            "trend": (ma20 / ma60 - 1) if ma60 else 0.0,
            "liquidity": math.log(max(float(latest.get("amount", 0)), 1.0)),
            "low_volatility": -vol20,
        }

    z_metrics = {
        metric: _zscore({symbol: values[metric] for symbol, values in raw_metrics.items()})
        for metric in ("momentum_20", "momentum_60", "trend", "liquidity", "low_volatility")
    }
    weights = {
        "momentum_20": 0.35,
        "momentum_60": 0.25,
        "trend": 0.20,
        "liquidity": 0.10,
        "low_volatility": 0.10,
    }

    scored: list[StockPick] = []
    for symbol, metrics in raw_metrics.items():
        score = sum(weights[key] * z_metrics[key][symbol] for key in weights)
        scored.append(
            StockPick(
                symbol=symbol,
                score=round(score, 6),
                target_weight=max_position_weight,
                reason="technical_rank",
                metrics={key: round(value, 6) for key, value in metrics.items()},
            )
        )

    picks = sorted(scored, key=lambda item: item.score, reverse=True)[:top_n]
    if picks:
        target_weight = min(max_position_weight, 0.95 / len(picks))
        for pick in picks:
            pick.target_weight = round(target_weight, 4)
            pick.reason = f"rank_{picks.index(pick) + 1}_technical_score"
    return SelectionResult(trade_date=trade_date, picks=picks, rejected=rejected)
