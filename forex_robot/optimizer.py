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
    "signal_mode": ["pullback"],
    "fast_ema": [8, 13, 20, 34],
    "slow_ema": [55, 80, 120, 160],
    "rsi_period": [7, 14],
    "atr_period": [10, 14, 21],
    "adx_period": [10, 14, 21],
    "slope_period": [10, 20, 30],
    "pullback_atr": [0.15, 0.3, 0.45, 0.65],
    "breakout_atr": [0.0, 0.03, 0.07],
    "breakout_lookback": [1, 2, 3, 5],
    "min_body_atr": [0.0, 0.05, 0.1, 0.2],
    "min_adx": [0.0, 12.0, 18.0, 25.0],
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

HIGH_FREQUENCY_PARAMETER_SPACE = {
    "signal_mode": ["hf_reversion", "hf_momentum", "hf_micro"],
    "fast_ema": [5, 8, 13, 20],
    "slow_ema": [21, 34, 55, 80],
    "rsi_period": [5, 7, 10, 14],
    "atr_period": [5, 7, 10, 14],
    "adx_period": [7, 10, 14],
    "slope_period": [5, 10, 20],
    "pullback_atr": [0.05, 0.1, 0.2, 0.35],
    "breakout_atr": [0.0, 0.01, 0.03, 0.05],
    "breakout_lookback": [1, 2, 3],
    "min_body_atr": [0.0, 0.03, 0.08, 0.15],
    "min_adx": [0.0, 10.0, 15.0, 20.0],
    "stop_atr": [1.2, 1.8, 2.4, 3.2, 4.0],
    "tp1_r": [0.15, 0.25, 0.35, 0.5],
    "tp2_r": [0.4, 0.6, 0.8, 1.0],
    "tp3_r": [0.9, 1.2, 1.6, 2.2],
    "trailing_atr": [0.5, 0.8, 1.2],
    "rsi_long_max": [38.0, 45.0, 50.0, 55.0, 60.0],
    "rsi_short_min": [40.0, 45.0, 50.0, 55.0, 62.0],
    "min_slope_atr": [0.0, 0.01, 0.03],
    "session": [(0, 24), (6, 20), (7, 17), (12, 20)],
    "max_hold_bars": [0, 3, 6, 12],
}


@dataclass(frozen=True)
class CandidateResult:
    score: float
    params: dict[str, Any]
    aggregate_metrics: dict[str, float]
    market_metrics: list[dict[str, Any]]


def parameter_space_for_objective(objective: str) -> dict[str, list[Any]]:
    if objective == "high-frequency":
        return HIGH_FREQUENCY_PARAMETER_SPACE
    if objective == "balanced":
        return PARAMETER_SPACE
    raise ValueError("objective must be balanced or high-frequency.")


def estimate_search_space_size(objective: str = "balanced") -> int:
    size = 1
    for values in parameter_space_for_objective(objective).values():
        size *= len(values)
    return size


def random_candidates(
    limit: int,
    seed: int = 42,
    *,
    objective: str = "balanced",
) -> list[StrategyParams]:
    rng = Random(seed)
    candidates: list[StrategyParams] = []
    seen: set[tuple[Any, ...]] = set()
    parameter_space = parameter_space_for_objective(objective)
    keys = list(parameter_space)

    max_attempts = max(limit * 20, 100)
    for _ in range(max_attempts):
        raw = {key: rng.choice(parameter_space[key]) for key in keys}
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


def grid_candidates(limit: int | None = None, *, objective: str = "balanced") -> list[StrategyParams]:
    parameter_space = parameter_space_for_objective(objective)
    keys = list(parameter_space)
    candidates: list[StrategyParams] = []
    for values in product(*(parameter_space[key] for key in keys)):
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
    objective: str = "balanced",
    target_daily_trades: float = 20.0,
    target_win_rate: float = 90.0,
    config: BacktestConfig | None = None,
) -> list[CandidateResult]:
    backtester = Backtester(config)
    candidates = random_candidates(evaluations, seed=seed, objective=objective)
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
        score = score_metrics(
            aggregate,
            min_trades=min_trades,
            objective=objective,
            target_daily_trades=target_daily_trades,
            target_win_rate=target_win_rate,
        )
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
    average_daily_win_rate = sum(float(item.get("average_daily_win_rate_pct", 0.0)) for item in market_metrics) / count
    average_profit_factor = sum(float(item["profit_factor"]) for item in market_metrics) / count
    estimated_robot_daily_trades = sum(float(item.get("average_daily_trades", 0.0)) for item in market_metrics)
    average_high_frequency_day_ratio = (
        sum(float(item.get("high_frequency_day_ratio", 0.0)) for item in market_metrics) / count
    )
    profitable_markets = sum(1 for item in market_metrics if float(item["net_profit"]) > 0)
    return {
        "markets": float(count),
        "total_trades": total_trades,
        "total_net_profit": round(total_net, 2),
        "average_return_pct": round(average_return, 2),
        "average_drawdown_pct": round(average_drawdown, 2),
        "average_win_rate_pct": round(average_win_rate, 2),
        "average_daily_win_rate_pct": round(average_daily_win_rate, 2),
        "estimated_robot_daily_trades": round(estimated_robot_daily_trades, 2),
        "average_profit_factor": round(average_profit_factor, 3),
        "average_high_frequency_day_ratio": round(average_high_frequency_day_ratio, 3),
        "profitable_market_ratio": round(profitable_markets / count, 3),
    }


def score_metrics(
    metrics: dict[str, float],
    *,
    min_trades: int,
    objective: str = "balanced",
    target_daily_trades: float = 20.0,
    target_win_rate: float = 90.0,
) -> float:
    if metrics["total_trades"] < min_trades:
        return -1_000_000.0 + metrics["total_trades"]
    if objective == "high-frequency":
        daily_trade_score = min(metrics["estimated_robot_daily_trades"], target_daily_trades) / target_daily_trades
        win_rate_gap = metrics["average_win_rate_pct"] - target_win_rate
        profit_penalty = min(metrics["total_net_profit"], 0.0) * 2.0
        return (
            metrics["average_return_pct"] * 1.5
            - metrics["average_drawdown_pct"] * 1.2
            + metrics["average_profit_factor"] * 8.0
            + metrics["profitable_market_ratio"] * 10.0
            + daily_trade_score * 40.0
            + win_rate_gap * 1.5
            + metrics["average_high_frequency_day_ratio"] * 50.0
            + profit_penalty
        )
    return (
        metrics["average_return_pct"]
        - 1.5 * metrics["average_drawdown_pct"]
        + 5.0 * metrics["average_profit_factor"]
        + 8.0 * metrics["profitable_market_ratio"]
        + min(metrics["total_trades"], 200.0) * 0.02
    )


def candidate_results_to_dict(results: list[CandidateResult]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]
