"""ATR-adaptive pullback scalping strategy."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from forex_robot.indicators import atr, ema, rolling_slope, rsi


@dataclass(frozen=True)
class StrategyParams:
    """Parameters for the pullback/scalping strategy.

    The strategy is intentionally adaptive: stop distance is tied to ATR, take
    profits are R-multiples of that dynamic stop, and position size is handled
    by the backtester based on account risk.
    """

    fast_ema: int = 20
    slow_ema: int = 80
    rsi_period: int = 14
    atr_period: int = 14
    slope_period: int = 20
    pullback_atr: float = 0.35
    breakout_atr: float = 0.05
    stop_atr: float = 1.4
    tp1_r: float = 0.8
    tp2_r: float = 1.4
    tp3_r: float = 2.4
    trailing_atr: float = 1.2
    rsi_long_max: float = 58.0
    rsi_short_min: float = 42.0
    min_slope_atr: float = 0.01
    session_start_hour: int = 6
    session_end_hour: int = 20

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def build_signals(frame: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    """Create indicator columns and trade signals.

    Signals are generated on a completed candle. The backtester enters on the
    following candle's open to avoid look-ahead bias.
    """

    if params.fast_ema >= params.slow_ema:
        raise ValueError("fast_ema must be lower than slow_ema.")
    if not (0 <= params.session_start_hour <= 23 and 0 <= params.session_end_hour <= 24):
        raise ValueError("Session hours must be within the 0-24 range.")
    if params.tp1_r <= 0 or params.tp2_r <= params.tp1_r or params.tp3_r <= params.tp2_r:
        raise ValueError("Take-profit R multiples must be positive and increasing.")

    data = frame.copy()
    data["ema_fast"] = ema(data["close"], params.fast_ema)
    data["ema_slow"] = ema(data["close"], params.slow_ema)
    data["atr"] = atr(data, params.atr_period)
    data["rsi"] = rsi(data["close"], params.rsi_period)
    data["slope"] = rolling_slope(data["ema_slow"], params.slope_period)
    data["slope_atr"] = data["slope"] / data["atr"].replace(0.0, pd.NA)

    previous_high = data["high"].shift(1)
    previous_low = data["low"].shift(1)
    previous_rsi = data["rsi"].shift(1)
    hour = data.index.hour
    if params.session_start_hour < params.session_end_hour:
        in_session = (hour >= params.session_start_hour) & (hour < params.session_end_hour)
    else:
        in_session = (hour >= params.session_start_hour) | (hour < params.session_end_hour)

    uptrend = (
        (data["ema_fast"] > data["ema_slow"])
        & (data["close"] > data["ema_slow"])
        & (data["slope_atr"] > params.min_slope_atr)
    )
    downtrend = (
        (data["ema_fast"] < data["ema_slow"])
        & (data["close"] < data["ema_slow"])
        & (data["slope_atr"] < -params.min_slope_atr)
    )

    long_pullback = data["low"] <= (data["ema_fast"] + params.pullback_atr * data["atr"])
    short_pullback = data["high"] >= (data["ema_fast"] - params.pullback_atr * data["atr"])
    long_recovery = (previous_rsi <= params.rsi_long_max) & (data["rsi"] > previous_rsi)
    short_recovery = (previous_rsi >= params.rsi_short_min) & (data["rsi"] < previous_rsi)
    long_break = data["close"] >= (previous_high + params.breakout_atr * data["atr"])
    short_break = data["close"] <= (previous_low - params.breakout_atr * data["atr"])

    data["signal"] = 0
    data.loc[in_session & uptrend & long_pullback & long_recovery & long_break, "signal"] = 1
    data.loc[in_session & downtrend & short_pullback & short_recovery & short_break, "signal"] = -1
    data["stop_distance"] = params.stop_atr * data["atr"]
    data["tp1_distance"] = params.tp1_r * data["stop_distance"]
    data["tp2_distance"] = params.tp2_r * data["stop_distance"]
    data["tp3_distance"] = params.tp3_r * data["stop_distance"]
    data["trailing_distance"] = params.trailing_atr * data["atr"]
    return data.dropna(subset=["ema_fast", "ema_slow", "atr", "slope_atr"])
