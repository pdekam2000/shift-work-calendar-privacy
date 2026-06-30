from __future__ import annotations

import pandas as pd

from forex_robot.backtest import BacktestConfig, Backtester
from forex_robot.strategy import StrategyParams, build_signals


def test_backtester_closes_three_take_profits() -> None:
    index = pd.date_range("2026-01-01 08:00", periods=5, freq="h")
    frame = pd.DataFrame(
        {
            "open": [1.1000, 1.1000, 1.1010, 1.1020, 1.1030],
            "high": [1.1005, 1.1035, 1.1040, 1.1040, 1.1040],
            "low": [1.0998, 1.1000, 1.1010, 1.1020, 1.1030],
            "close": [1.1002, 1.1030, 1.1035, 1.1030, 1.1030],
            "signal": [1, 0, 0, 0, 0],
            "stop_distance": [0.0010] * 5,
            "tp1_distance": [0.0008] * 5,
            "tp2_distance": [0.0014] * 5,
            "tp3_distance": [0.0024] * 5,
            "trailing_distance": [0.0010] * 5,
        },
        index=index,
    )

    result = Backtester(
        BacktestConfig(
            initial_capital=1000.0,
            risk_per_trade=0.01,
            spread_pips=0.0,
            slippage_pips=0.0,
            commission_per_million=0.0,
        )
    ).run(
        frame,
        symbol="EURUSD=X",
        timeframe="1h",
        strategy={},
        conversion=pd.Series(1.1, index=index),
    )

    assert result.metrics["trade_count"] == 1
    assert result.trades[0].exit_reason == "tp3"
    assert result.metrics["net_profit"] > 0
    assert len(result.trades[0].partial_exits) == 3


def test_strategy_generates_required_columns() -> None:
    index = pd.date_range("2026-01-01", periods=220, freq="h")
    close = pd.Series([1.1000 + i * 0.0001 for i in range(220)], index=index)
    frame = pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.0004,
            "low": close - 0.0004,
            "close": close,
        },
        index=index,
    )

    signals = build_signals(
        frame,
        StrategyParams(
            fast_ema=8,
            slow_ema=34,
            slope_period=10,
            session_start_hour=0,
            session_end_hour=24,
        ),
    )

    assert {"ema_fast", "ema_slow", "atr", "rsi", "signal", "stop_distance"}.issubset(signals.columns)
    assert set(signals["signal"].unique()).issubset({-1, 0, 1})
