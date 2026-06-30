"""Parameter search for the forex strategy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from random import Random
from typing import Any

import pandas as pd

from forex_robot.backtest import BacktestConfig, Backtester
from forex_robot.strategy import StrategyParams, build_signals


PARAMETER_SPACE = {
    "fast_ema": [8, 13, 20, 34],
    "slow_ema": [55, 80, 120, 160],
    "rsi_period": [7, 14],
    "atr_period": [10, 14, 21],
    "slope_period": [10, 20, 30],
    "pullback_atr": [0.15, 0.3, 0.45, 0.65],
    "breakout_atr": [0.0, 0.03, 0.07],
    "stop_atr": [0.9, 1.2, 1.5, 1.9, 2.3],
    "tp1_r": [0.5, 0.8, 1.0],
    "tp2_r": [1.2, 1.6, 2.0],
    "tp3_r": [2.2, 2.8, 3.6],
    "trailing_atr": [0.8, 1.2, 1.6],
    "rsi_long_max": [50.0, 55.0, 60.0],
    "rsi_short_min": [40.0, 45.0, 50.0],
    "min_slope_atr": [0.0, 0.01, 0.03],
    "session": [(0, 24), (6, 20), (7, 17)],
}


@dataclass(frozen=True)
class CandidateResult:
    score: float
    params: dict[str, Any]
    aggregate_metrics: dict[str, float]
    market_metrics: list[dict[str, Any]]


def estimate_search_space_size() -> int:
    size = 1
    for values in PARAMETER_SPACE.values():
        size *= len(values)
    return size


def random_candidates(limit: int, seed: int = 42) -> list[StrategyParams]:
    rng = Random(seed)
    candidates: list[StrategyParams] = []
    seen: set[tuple[Any, ...]] = set()
    keys = list(PARAMETER_SPACE)

    max_attempts = max(limit * 20, 100)
    for _ in range(max_attempts):
        raw = {key: rng.choice(PARAMETER_SPACE[key]) for key in keys}
        session_start, session_end = raw.pop("session")
        raw["session_start_hour"] = session_start
        raw["session_end_hour"] = session_end
        params = StrategyParams(**raw)
        if params.fast_ema >= params.slow_ema:
            continue
        key = tuple(params.to_dict().items())
        if key in seen:
            continue
        seen.add(key)
        candidates.append(params)
        if len(candidates) >= limit:
            break
    return candidates


def grid_candidates(limit: int | None = None) -> list[StrategyParams]:
    keys = list(PARAMETER_SPACE)
    candidates: list[StrategyParams] = []
    for values in product(*(PARAMETER_SPACE[key] for key in keys)):
        raw = dict(zip(keys, values, strict=True))
        session_start, session_end = raw.pop("session")
        raw["session_start_hour"] = session_start
        raw["session_end_hour"] = session_end
        params = StrategyParams(**raw)
        if params.fast_ema >= params.slow_ema:
            continue
        candidates.append(params)
        if limit is not None and len(candidates) >= limit:
            break
    return candidates


def optimize(
    markets: dict[tuple[str, str], pd.DataFrame],
    conversions: dict[tuple[str, str], pd.Series],
    *,
    evaluations: int = 300,
    top_n: int = 10,
    seed: int = 42,
    min_trades: int = 8,
    config: BacktestConfig | None = None,
) -> list[CandidateResult]:
    backtester = Backtester(config)
    candidates = random_candidates(evaluations, seed=seed)
    results: list[CandidateResult] = []

    for params in candidates:
        market_metrics: list[dict[str, Any]] = []
        for (symbol, timeframe), frame in markets.items():
            try:
                signals = build_signals(frame, params)
                result = backtester.run(
                    signals,
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy=params.to_dict(),
                    conversion=conversions.get((symbol, timeframe)),
                )
            except (ValueError, FloatingPointError, ZeroDivisionError):
                continue
            metrics = dict(result.metrics)
            metrics.update({"symbol": symbol, "timeframe": timeframe})
            market_metrics.append(metrics)
        if not market_metrics:
            continue
        aggregate = aggregate_metrics(market_metrics)
        score = score_metrics(aggregate, min_trades=min_trades)
        results.append(
            CandidateResult(
                score=score,
                params=params.to_dict(),
                aggregate_metrics=aggregate,
                market_metrics=market_metrics,
            )
        )

    return sorted(results, key=lambda item: item.score, reverse=True)[:top_n]


def aggregate_metrics(market_metrics: list[dict[str, Any]]) -> dict[str, float]:
    count = len(market_metrics)
    total_trades = sum(float(item["trade_count"]) for item in market_metrics)
    total_net = sum(float(item["net_profit"]) for item in market_metrics)
    average_return = sum(float(item["return_pct"]) for item in market_metrics) / count
    average_drawdown = sum(float(item["max_drawdown_pct"]) for item in market_metrics) / count
    average_win_rate = sum(float(item["win_rate_pct"]) for item in market_metrics) / count
    average_profit_factor = sum(float(item["profit_factor"]) for item in market_metrics) / count
    profitable_markets = sum(1 for item in market_metrics if float(item["net_profit"]) > 0)
    return {
        "markets": float(count),
        "total_trades": total_trades,
        "total_net_profit": round(total_net, 2),
        "average_return_pct": round(average_return, 2),
        "average_drawdown_pct": round(average_drawdown, 2),
        "average_win_rate_pct": round(average_win_rate, 2),
        "average_profit_factor": round(average_profit_factor, 3),
        "profitable_market_ratio": round(profitable_markets / count, 3),
    }


def score_metrics(metrics: dict[str, float], *, min_trades: int) -> float:
    if metrics["total_trades"] < min_trades:
        return -1_000_000.0 + metrics["total_trades"]
    return (
        metrics["average_return_pct"]
        - 1.5 * metrics["average_drawdown_pct"]
        + 5.0 * metrics["average_profit_factor"]
        + 8.0 * metrics["profitable_market_ratio"]
        + min(metrics["total_trades"], 200.0) * 0.02
    )


def candidate_results_to_dict(results: list[CandidateResult]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]
