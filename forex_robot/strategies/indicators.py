"""
Technical Indicators library — all computed in-place on pandas DataFrames.
Covers: EMA, SMA, RSI, MACD, Bollinger Bands, Stochastic, ATR, ADX,
        CCI, Williams %R, Parabolic SAR, Ichimoku, Fibonacci Retracements,
        Pivot Points, Volume indicators, Divergence helpers.
"""

import numpy as np
import pandas as pd


# ── Moving Averages ────────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)


def hull_ma(series: pd.Series, period: int) -> pd.Series:
    half = wma(series, period // 2)
    full = wma(series, period)
    raw = 2 * half - full
    return wma(raw, int(np.sqrt(period)))


# ── RSI ───────────────────────────────────────────────────────────────────────

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ── MACD ──────────────────────────────────────────────────────────────────────

def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Returns (upper, middle, lower)."""
    mid = sma(series, period)
    std = series.rolling(period).std()
    return mid + std_dev * std, mid, mid - std_dev * std


# ── Stochastic ────────────────────────────────────────────────────────────────

def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k_period: int = 14, d_period: int = 3):
    """Returns (%K, %D)."""
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    d = sma(k, d_period)
    return k, d


# ── ATR ───────────────────────────────────────────────────────────────────────

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


# ── ADX ───────────────────────────────────────────────────────────────────────

def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """Returns (ADX, +DI, -DI)."""
    atr_val = atr(high, low, close, period)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=high.index).ewm(com=period - 1, adjust=False).mean()
    minus_dm = pd.Series(minus_dm, index=high.index).ewm(com=period - 1, adjust=False).mean()
    plus_di = 100 * plus_dm / atr_val.replace(0, np.nan)
    minus_di = 100 * minus_dm / atr_val.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(com=period - 1, adjust=False).mean()
    return adx_val, plus_di, minus_di


# ── CCI ───────────────────────────────────────────────────────────────────────

def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    mean_tp = sma(tp, period)
    mean_dev = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - mean_tp) / (0.015 * mean_dev.replace(0, np.nan))


# ── Williams %R ───────────────────────────────────────────────────────────────

def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    return -100 * (highest - close) / (highest - lowest).replace(0, np.nan)


# ── Parabolic SAR ─────────────────────────────────────────────────────────────

def parabolic_sar(high: pd.Series, low: pd.Series,
                  af_start: float = 0.02, af_step: float = 0.02, af_max: float = 0.2) -> pd.Series:
    n = len(high)
    sar = np.full(n, np.nan)
    bull = True
    af = af_start
    ep = low.iloc[0]
    sar[0] = high.iloc[0]
    for i in range(1, n):
        prev_sar = sar[i - 1]
        if bull:
            sar[i] = prev_sar + af * (ep - prev_sar)
            sar[i] = min(sar[i], low.iloc[i - 1], low.iloc[max(0, i - 2)])
            if low.iloc[i] < sar[i]:
                bull = False
                sar[i] = ep
                ep = low.iloc[i]
                af = af_start
            else:
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + af_step, af_max)
        else:
            sar[i] = prev_sar + af * (ep - prev_sar)
            sar[i] = max(sar[i], high.iloc[i - 1], high.iloc[max(0, i - 2)])
            if high.iloc[i] > sar[i]:
                bull = True
                sar[i] = ep
                ep = high.iloc[i]
                af = af_start
            else:
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + af_step, af_max)
    return pd.Series(sar, index=high.index)


# ── Ichimoku ──────────────────────────────────────────────────────────────────

def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series,
             tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, displacement: int = 26):
    tenkan_sen = (high.rolling(tenkan).max() + low.rolling(tenkan).min()) / 2
    kijun_sen = (high.rolling(kijun).max() + low.rolling(kijun).min()) / 2
    senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(displacement)
    senkou_b_val = ((high.rolling(senkou_b).max() + low.rolling(senkou_b).min()) / 2).shift(displacement)
    chikou = close.shift(-displacement)
    return tenkan_sen, kijun_sen, senkou_a, senkou_b_val, chikou


# ── Fibonacci Retracements ────────────────────────────────────────────────────

FIBO_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
FIBO_EXTENSION = [1.272, 1.618, 2.0, 2.618]


def fibonacci_levels(swing_high: float, swing_low: float, direction: str = "down"):
    """
    Calculate Fibonacci retracement and extension levels.
    direction='down' means price retraced down from high → compute support levels
    direction='up' means price retraced up from low → compute resistance levels
    """
    diff = swing_high - swing_low
    levels = {}
    for lvl in FIBO_LEVELS:
        if direction == "down":
            levels[f"ret_{lvl}"] = swing_high - diff * lvl
        else:
            levels[f"ret_{lvl}"] = swing_low + diff * lvl
    for ext in FIBO_EXTENSION:
        if direction == "down":
            levels[f"ext_{ext}"] = swing_high - diff * ext
        else:
            levels[f"ext_{ext}"] = swing_low + diff * ext
    return levels


def detect_swing_points(high: pd.Series, low: pd.Series, lookback: int = 10):
    """Detect local swing highs and lows with a rolling window."""
    n = len(high)
    swing_highs = []
    swing_lows = []
    for i in range(lookback, n - lookback):
        window_h = high.iloc[i - lookback: i + lookback + 1]
        window_l = low.iloc[i - lookback: i + lookback + 1]
        if high.iloc[i] == window_h.max():
            swing_highs.append((high.index[i], high.iloc[i]))
        if low.iloc[i] == window_l.min():
            swing_lows.append((low.index[i], low.iloc[i]))
    return swing_highs, swing_lows


# ── Pivot Points ─────────────────────────────────────────────────────────────

def pivot_points(high: pd.Series, low: pd.Series, close: pd.Series):
    """Classic pivot points (daily)."""
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    return pp, r1, s1, r2, s2, r3, s3


# ── Volume Indicators ─────────────────────────────────────────────────────────

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    tp = (high + low + close) / 3
    return (tp * volume).cumsum() / volume.cumsum()


# ── Momentum / Rate of Change ─────────────────────────────────────────────────

def roc(series: pd.Series, period: int = 10) -> pd.Series:
    return ((series - series.shift(period)) / series.shift(period).replace(0, np.nan)) * 100


def momentum(series: pd.Series, period: int = 10) -> pd.Series:
    return series - series.shift(period)


# ── Donchian Channel ──────────────────────────────────────────────────────────

def donchian_channel(high: pd.Series, low: pd.Series, period: int = 20):
    upper = high.rolling(period).max()
    lower = low.rolling(period).min()
    mid = (upper + lower) / 2
    return upper, mid, lower


# ── Keltner Channel ───────────────────────────────────────────────────────────

def keltner_channel(high: pd.Series, low: pd.Series, close: pd.Series,
                    period: int = 20, multiplier: float = 2.0):
    mid = ema(close, period)
    atr_val = atr(high, low, close, period)
    upper = mid + multiplier * atr_val
    lower = mid - multiplier * atr_val
    return upper, mid, lower


# ── Supertrend ────────────────────────────────────────────────────────────────

def supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
               period: int = 10, multiplier: float = 3.0):
    atr_val = atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr_val
    lower_band = hl2 - multiplier * atr_val

    n = len(close)
    supertrend_arr = np.full(n, np.nan)
    direction = np.ones(n)

    for i in range(1, n):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            direction[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

        if direction[i] == 1:
            lower_band.iloc[i] = max(lower_band.iloc[i], lower_band.iloc[i - 1])
            supertrend_arr[i] = lower_band.iloc[i]
        else:
            upper_band.iloc[i] = min(upper_band.iloc[i], upper_band.iloc[i - 1])
            supertrend_arr[i] = upper_band.iloc[i]

    return pd.Series(supertrend_arr, index=close.index), pd.Series(direction, index=close.index)


# ── Add all indicators to a DataFrame ────────────────────────────────────────

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute and attach every indicator to the OHLCV DataFrame."""
    df = df.copy()
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # EMAs
    for p in [5, 8, 13, 21, 34, 55, 89, 200]:
        df[f"ema{p}"] = ema(c, p)
    # SMAs
    for p in [10, 20, 50, 100, 200]:
        df[f"sma{p}"] = sma(c, p)

    df["hull21"] = hull_ma(c, 21)

    # RSI variants
    df["rsi14"] = rsi(c, 14)
    df["rsi7"] = rsi(c, 7)
    df["rsi21"] = rsi(c, 21)

    # MACD
    df["macd"], df["macd_sig"], df["macd_hist"] = macd(c)
    df["macd_fast"], df["macd_fast_sig"], df["macd_fast_hist"] = macd(c, 5, 13, 5)

    # Bollinger Bands
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(c, 20, 2.0)
    df["bb_upper_1"], df["bb_mid_1"], df["bb_lower_1"] = bollinger_bands(c, 20, 1.0)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["bb_pct"] = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)

    # Stochastic
    df["stoch_k"], df["stoch_d"] = stochastic(h, l, c, 14, 3)
    df["stoch_k_fast"], df["stoch_d_fast"] = stochastic(h, l, c, 5, 3)

    # ATR
    df["atr14"] = atr(h, l, c, 14)
    df["atr7"] = atr(h, l, c, 7)

    # ADX
    df["adx"], df["plus_di"], df["minus_di"] = adx(h, l, c, 14)

    # CCI
    df["cci20"] = cci(h, l, c, 20)
    df["cci14"] = cci(h, l, c, 14)

    # Williams %R
    df["wr14"] = williams_r(h, l, c, 14)

    # Parabolic SAR
    df["psar"] = parabolic_sar(h, l)

    # Ichimoku
    df["ichi_tenkan"], df["ichi_kijun"], df["ichi_senkou_a"], df["ichi_senkou_b"], df["ichi_chikou"] = ichimoku(h, l, c)

    # Donchian
    df["don_upper"], df["don_mid"], df["don_lower"] = donchian_channel(h, l, 20)

    # Keltner
    df["kelt_upper"], df["kelt_mid"], df["kelt_lower"] = keltner_channel(h, l, c)

    # Supertrend
    df["supertrend"], df["supertrend_dir"] = supertrend(h, l, c, 10, 3.0)

    # Volume
    df["obv"] = obv(c, v)
    df["vwap"] = vwap(h, l, c, v)

    # Momentum
    df["roc10"] = roc(c, 10)
    df["mom10"] = momentum(c, 10)

    # Candlestick patterns (simple)
    df["body"] = (c - df["open"]).abs()
    df["upper_wick"] = h - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - l
    df["is_bullish"] = (c > df["open"]).astype(int)
    df["is_bearish"] = (c < df["open"]).astype(int)
    df["is_doji"] = (df["body"] < df["atr14"] * 0.1).astype(int)
    df["is_hammer"] = ((df["lower_wick"] > 2 * df["body"]) &
                       (df["upper_wick"] < df["body"]) &
                       (df["body"] > 0)).astype(int)
    df["is_shooting_star"] = ((df["upper_wick"] > 2 * df["body"]) &
                              (df["lower_wick"] < df["body"]) &
                              (df["body"] > 0)).astype(int)

    # Trend context
    df["trend_up"] = (df["ema21"] > df["ema55"]).astype(int)
    df["trend_dn"] = (df["ema21"] < df["ema55"]).astype(int)
    df["above_200"] = (c > df["ema200"]).astype(int)

    return df
