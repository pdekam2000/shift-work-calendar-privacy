"""Forex strategy research and backtesting package."""

from forex_robot.backtest import BacktestConfig, BacktestResult, Backtester
from forex_robot.strategy import StrategyParams, build_signals

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "Backtester",
    "StrategyParams",
    "build_signals",
]
