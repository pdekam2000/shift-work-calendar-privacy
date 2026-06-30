"""Technical indicators used by the strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    if period < 1:
        raise ValueError("EMA period must be positive.")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(frame: pd.DataFrame, period: int) -> pd.Series:
    if period < 1:
        raise ValueError("ATR period must be positive.")
    return true_range(frame).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int) -> pd.Series:
    if period < 1:
        raise ValueError("RSI period must be positive.")
    delta = series.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    value = 100.0 - (100.0 / (1.0 + relative_strength))
    return value.fillna(50.0)


def rolling_slope(series: pd.Series, period: int) -> pd.Series:
    """Fast rolling linear-regression slope for trend strength filtering."""

    if period < 2:
        raise ValueError("Slope period must be at least 2.")
    x = np.arange(period, dtype=float)
    x_mean = x.mean()
    denominator = ((x - x_mean) ** 2).sum()

    def slope(values: np.ndarray) -> float:
        y = values.astype(float)
        return float(((x - x_mean) * (y - y.mean())).sum() / denominator)

    return series.rolling(period, min_periods=period).apply(slope, raw=True)
