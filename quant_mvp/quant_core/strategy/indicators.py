from __future__ import annotations

from statistics import pstdev


def momentum(closes: list[float], window: int) -> float:
    if len(closes) <= window or closes[-window - 1] == 0:
        return 0.0
    return closes[-1] / closes[-window - 1] - 1


def moving_average(closes: list[float], window: int) -> float:
    if len(closes) < window:
        return sum(closes) / len(closes)
    return sum(closes[-window:]) / window


def annualized_volatility(closes: list[float], window: int = 20) -> float:
    if len(closes) < 2:
        return 0.0
    sample = closes[-(window + 1) :]
    returns = [
        sample[index] / sample[index - 1] - 1
        for index in range(1, len(sample))
        if sample[index - 1] != 0
    ]
    if not returns:
        return 0.0
    return pstdev(returns) * (252 ** 0.5)
