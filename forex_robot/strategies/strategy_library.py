"""
Strategy Library — 20+ trading strategies that each return:
    signals:      pd.Series (1=BUY, -1=SELL, 0=FLAT)
    sl_pips:      pd.Series (stop-loss distance in pips per bar)

All strategies are stateless functions that accept a DataFrame with
pre-computed indicators (from indicators.add_all_indicators).
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple

SigPair = Tuple[pd.Series, pd.Series]

ATR_SL_MULT = 1.5      # Default ATR multiplier for SL
MIN_SL_PIPS = 5.0
MAX_SL_PIPS = 80.0


def _atr_sl(df: pd.DataFrame, mult: float = ATR_SL_MULT) -> pd.Series:
    sl_pips = (df["atr14"] / df.get("pip_size", 0.0001)) * mult
    return sl_pips.clip(MIN_SL_PIPS, MAX_SL_PIPS)


def _shift_crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """Returns +1 on golden cross, -1 on death cross, 0 otherwise."""
    cross_up = (a > b) & (a.shift(1) <= b.shift(1))
    cross_dn = (a < b) & (a.shift(1) >= b.shift(1))
    sig = pd.Series(0, index=a.index)
    sig[cross_up] = 1
    sig[cross_dn] = -1
    return sig


# ─────────────────────────────────────────────────────────────────────────────
# TREND FOLLOWING STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────

def strategy_ema_crossover(df: pd.DataFrame, fast: int = 21, slow: int = 55) -> SigPair:
    """Classic EMA crossover with ADX trend filter."""
    fast_col = f"ema{fast}" if f"ema{fast}" in df else "ema21"
    slow_col = f"ema{slow}" if f"ema{slow}" in df else "ema55"
    sig = _shift_crossover(df[fast_col], df[slow_col])
    # Only trade when ADX > 20 (trending market)
    trending = df["adx"] > 20
    sig = sig.where(trending, 0)
    return sig, _atr_sl(df)


def strategy_triple_ema(df: pd.DataFrame) -> SigPair:
    """Triple EMA (8/21/55): all aligned → signal."""
    bull = (df["ema8"] > df["ema21"]) & (df["ema21"] > df["ema55"])
    bear = (df["ema8"] < df["ema21"]) & (df["ema21"] < df["ema55"])
    entry_bull = bull & ~bull.shift(1).fillna(False)
    entry_bear = bear & ~bear.shift(1).fillna(False)
    sig = pd.Series(0, index=df.index)
    sig[entry_bull] = 1
    sig[entry_bear] = -1
    return sig, _atr_sl(df)


def strategy_macd_trend(df: pd.DataFrame) -> SigPair:
    """MACD zero-line + signal cross with EMA200 direction filter."""
    cross_up = (df["macd"] > df["macd_sig"]) & (df["macd"].shift(1) <= df["macd_sig"].shift(1))
    cross_dn = (df["macd"] < df["macd_sig"]) & (df["macd"].shift(1) >= df["macd_sig"].shift(1))
    bull_filter = df["close"] > df["ema200"]
    bear_filter = df["close"] < df["ema200"]
    sig = pd.Series(0, index=df.index)
    sig[cross_up & bull_filter] = 1
    sig[cross_dn & bear_filter] = -1
    return sig, _atr_sl(df)


def strategy_supertrend(df: pd.DataFrame) -> SigPair:
    """Supertrend direction change signal."""
    sig = _shift_crossover(pd.Series(1, index=df.index), df["supertrend_dir"])
    flip_up = (df["supertrend_dir"] == 1) & (df["supertrend_dir"].shift(1) == -1)
    flip_dn = (df["supertrend_dir"] == -1) & (df["supertrend_dir"].shift(1) == 1)
    sig = pd.Series(0, index=df.index)
    sig[flip_up] = 1
    sig[flip_dn] = -1
    return sig, _atr_sl(df)


def strategy_ichimoku(df: pd.DataFrame) -> SigPair:
    """Ichimoku: TK cross above cloud = BUY, below cloud = SELL."""
    tk_bull = (df["ichi_tenkan"] > df["ichi_kijun"]) & \
              (df["ichi_tenkan"].shift(1) <= df["ichi_kijun"].shift(1))
    tk_bear = (df["ichi_tenkan"] < df["ichi_kijun"]) & \
              (df["ichi_tenkan"].shift(1) >= df["ichi_kijun"].shift(1))
    above_cloud = df["close"] > df[["ichi_senkou_a", "ichi_senkou_b"]].max(axis=1)
    below_cloud = df["close"] < df[["ichi_senkou_a", "ichi_senkou_b"]].min(axis=1)
    sig = pd.Series(0, index=df.index)
    sig[tk_bull & above_cloud] = 1
    sig[tk_bear & below_cloud] = -1
    return sig, _atr_sl(df, 2.0)


def strategy_hull_ma(df: pd.DataFrame) -> SigPair:
    """Hull MA direction change with momentum confirmation."""
    hull_up = (df["hull21"] > df["hull21"].shift(1)) & (df["hull21"].shift(1) <= df["hull21"].shift(2))
    hull_dn = (df["hull21"] < df["hull21"].shift(1)) & (df["hull21"].shift(1) >= df["hull21"].shift(2))
    sig = pd.Series(0, index=df.index)
    sig[hull_up & (df["roc10"] > 0)] = 1
    sig[hull_dn & (df["roc10"] < 0)] = -1
    return sig, _atr_sl(df)


# ─────────────────────────────────────────────────────────────────────────────
# MEAN REVERSION STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────

def strategy_bollinger_reversal(df: pd.DataFrame) -> SigPair:
    """Buy at lower BB, sell at upper BB — with RSI confirmation."""
    buy = (df["close"] < df["bb_lower"]) & (df["rsi14"] < 35)
    sell = (df["close"] > df["bb_upper"]) & (df["rsi14"] > 65)
    sig = pd.Series(0, index=df.index)
    sig[buy & buy.shift(1).fillna(False).ne(True)] = 1
    sig[sell & sell.shift(1).fillna(False).ne(True)] = -1
    return sig, _atr_sl(df, 1.2)


def strategy_rsi_oversold(df: pd.DataFrame,
                          ob: int = 70, os_: int = 30) -> SigPair:
    """RSI overbought/oversold with trend filter."""
    buy = (df["rsi14"] < os_) & (df["rsi14"].shift(1) >= os_) & (df["close"] > df["sma50"])
    sell = (df["rsi14"] > ob) & (df["rsi14"].shift(1) <= ob) & (df["close"] < df["sma50"])
    sig = pd.Series(0, index=df.index)
    sig[buy] = 1
    sig[sell] = -1
    return sig, _atr_sl(df)


def strategy_stochastic_reversal(df: pd.DataFrame) -> SigPair:
    """Stochastic cross in oversold/overbought with Bollinger zone."""
    k_cross_up = (df["stoch_k"] > df["stoch_d"]) & (df["stoch_k"].shift(1) <= df["stoch_d"].shift(1))
    k_cross_dn = (df["stoch_k"] < df["stoch_d"]) & (df["stoch_k"].shift(1) >= df["stoch_d"].shift(1))
    buy = k_cross_up & (df["stoch_k"] < 25) & (df["bb_pct"] < 0.3)
    sell = k_cross_dn & (df["stoch_k"] > 75) & (df["bb_pct"] > 0.7)
    sig = pd.Series(0, index=df.index)
    sig[buy] = 1
    sig[sell] = -1
    return sig, _atr_sl(df)


def strategy_cci_reversal(df: pd.DataFrame) -> SigPair:
    """CCI reversal from extreme zones."""
    buy = (df["cci20"] > -100) & (df["cci20"].shift(1) <= -100)
    sell = (df["cci20"] < 100) & (df["cci20"].shift(1) >= 100)
    sig = pd.Series(0, index=df.index)
    sig[buy & (df["close"] > df["sma50"])] = 1
    sig[sell & (df["close"] < df["sma50"])] = -1
    return sig, _atr_sl(df)


# ─────────────────────────────────────────────────────────────────────────────
# FIBONACCI / CORRECTIVE PATTERN STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────

def strategy_fibonacci_retracement(df: pd.DataFrame, lookback: int = 30) -> SigPair:
    """
    Fibonacci Corrective Strategy:
    1. Identify recent swing high/low over `lookback` bars
    2. Detect price retracing to 38.2%, 50%, or 61.8% level
    3. Enter on bounce with confirmation (RSI + candle direction)
    """
    sig = pd.Series(0, index=df.index)
    sl_pips = _atr_sl(df, 1.5)

    for i in range(lookback + 5, len(df)):
        window = df.iloc[i - lookback: i]
        swing_high = window["high"].max()
        swing_low = window["low"].min()
        diff = swing_high - swing_low

        if diff < 0.0005:  # too small a range
            continue

        cur_close = df["close"].iloc[i]
        cur_rsi = df["rsi14"].iloc[i]

        # Key Fibonacci levels
        ret_382 = swing_high - diff * 0.382
        ret_50 = swing_high - diff * 0.500
        ret_618 = swing_high - diff * 0.618

        # Uptrend retracement: price bouncing off 38.2/50/61.8 → BUY
        if df["trend_up"].iloc[i]:
            tolerance = df["atr14"].iloc[i] * 0.5
            at_fib = any(abs(cur_close - lvl) < tolerance for lvl in [ret_382, ret_50, ret_618])
            if at_fib and cur_rsi < 55 and df["is_bullish"].iloc[i]:
                sig.iloc[i] = 1

        # Downtrend retracement: price bouncing off 38.2/50/61.8 → SELL
        ext_382 = swing_low + diff * 0.382
        ext_50 = swing_low + diff * 0.500
        ext_618 = swing_low + diff * 0.618

        if df["trend_dn"].iloc[i]:
            tolerance = df["atr14"].iloc[i] * 0.5
            at_fib = any(abs(cur_close - lvl) < tolerance for lvl in [ext_382, ext_50, ext_618])
            if at_fib and cur_rsi > 45 and df["is_bearish"].iloc[i]:
                sig.iloc[i] = -1

    return sig, sl_pips


def strategy_fibonacci_extension_breakout(df: pd.DataFrame) -> SigPair:
    """
    Fibonacci Extension Breakout:
    After impulse move, trade breakout beyond 1.272 or 1.618 extension.
    """
    sig = pd.Series(0, index=df.index)
    lookback = 20
    for i in range(lookback + 2, len(df)):
        window = df.iloc[i - lookback: i]
        swing_high_idx = window["high"].idxmax()
        swing_low_idx = window["low"].idxmin()
        swing_high = window["high"].max()
        swing_low = window["low"].min()
        diff = swing_high - swing_low
        cur = df["close"].iloc[i]
        prev = df["close"].iloc[i - 1]
        # Bullish extension breakout
        ext_127 = swing_high + diff * 0.272
        ext_162 = swing_high + diff * 0.618
        if prev < ext_127 and cur >= ext_127 and df["adx"].iloc[i] > 25:
            sig.iloc[i] = 1
        # Bearish extension breakdown
        ext_127_dn = swing_low - diff * 0.272
        ext_162_dn = swing_low - diff * 0.618
        if prev > ext_127_dn and cur <= ext_127_dn and df["adx"].iloc[i] > 25:
            sig.iloc[i] = -1
    return sig, _atr_sl(df, 2.0)


def strategy_wave_correction(df: pd.DataFrame) -> SigPair:
    """
    Elliott Wave corrective pattern approximation:
    Identifies ABC corrections using swing structure and Fibonacci.
    Uses 3-wave retracement with 0.618 target entry.
    """
    sig = pd.Series(0, index=df.index)
    n = len(df)
    for i in range(60, n):
        closes = df["close"].iloc[i - 60: i]
        highs = df["high"].iloc[i - 60: i]
        lows = df["low"].iloc[i - 60: i]

        # Find wave A swing (first big move)
        wave_start = closes.iloc[0]
        max_idx = highs.argmax()
        min_idx = lows.argmin()

        if max_idx < min_idx:
            # Bullish impulse then correction
            wave_a_top = highs.iloc[max_idx]
            wave_b_low = lows.iloc[min_idx]
            diff = wave_a_top - wave_b_low
            wave_c_target = wave_a_top + diff * 0.618

            cur_close = df["close"].iloc[i]
            if abs(cur_close - wave_c_target) < df["atr14"].iloc[i] * 0.8:
                if df["rsi14"].iloc[i] > 50 and df["macd_hist"].iloc[i] > 0:
                    sig.iloc[i] = 1

        elif min_idx < max_idx:
            # Bearish impulse then correction
            wave_a_bot = lows.iloc[min_idx]
            wave_b_high = highs.iloc[max_idx]
            diff = wave_b_high - wave_a_bot
            wave_c_target = wave_a_bot - diff * 0.618

            cur_close = df["close"].iloc[i]
            if abs(cur_close - wave_c_target) < df["atr14"].iloc[i] * 0.8:
                if df["rsi14"].iloc[i] < 50 and df["macd_hist"].iloc[i] < 0:
                    sig.iloc[i] = -1

    return sig, _atr_sl(df, 2.0)


# ─────────────────────────────────────────────────────────────────────────────
# SCALPING STRATEGIES (designed for M1/M5/M15)
# ─────────────────────────────────────────────────────────────────────────────

def strategy_scalp_ema_ribbon(df: pd.DataFrame) -> SigPair:
    """
    Scalping: 5/8/13 EMA ribbon alignment + RSI momentum.
    Very short SL (0.8× ATR).
    """
    bull = (df["ema5"] > df["ema8"]) & (df["ema8"] > df["ema13"])
    bear = (df["ema5"] < df["ema8"]) & (df["ema8"] < df["ema13"])
    entry_bull = bull & ~bull.shift(1).fillna(False) & (df["rsi7"] > 50) & (df["rsi7"] < 70)
    entry_bear = bear & ~bear.shift(1).fillna(False) & (df["rsi7"] < 50) & (df["rsi7"] > 30)
    sig = pd.Series(0, index=df.index)
    sig[entry_bull] = 1
    sig[entry_bear] = -1
    return sig, _atr_sl(df, 0.8)


def strategy_scalp_bb_squeeze(df: pd.DataFrame) -> SigPair:
    """
    Bollinger Band squeeze breakout scalp.
    When bands narrow (low volatility) and then expand → trade the breakout.
    """
    bb_squeeze = df["bb_width"] < df["bb_width"].rolling(20).quantile(0.2)
    breakout_up = (df["close"] > df["bb_upper"]) & bb_squeeze.shift(1).fillna(False)
    breakout_dn = (df["close"] < df["bb_lower"]) & bb_squeeze.shift(1).fillna(False)
    sig = pd.Series(0, index=df.index)
    sig[breakout_up] = 1
    sig[breakout_dn] = -1
    return sig, _atr_sl(df, 0.7)


def strategy_scalp_stoch_rsi(df: pd.DataFrame) -> SigPair:
    """Fast Stochastic + RSI combo scalp for oversold/overbought bounces."""
    buy = (df["stoch_k_fast"] < 20) & (df["stoch_k_fast"] > df["stoch_d_fast"]) & \
          (df["rsi7"] < 35) & (df["close"] > df["ema13"])
    sell = (df["stoch_k_fast"] > 80) & (df["stoch_k_fast"] < df["stoch_d_fast"]) & \
           (df["rsi7"] > 65) & (df["close"] < df["ema13"])
    sig = pd.Series(0, index=df.index)
    sig[buy] = 1
    sig[sell] = -1
    return sig, _atr_sl(df, 0.6)


def strategy_scalp_donchian(df: pd.DataFrame) -> SigPair:
    """Donchian channel breakout scalp with volume confirmation."""
    breakout_up = (df["close"] > df["don_upper"].shift(1)) & (df["adx"] > 20)
    breakout_dn = (df["close"] < df["don_lower"].shift(1)) & (df["adx"] > 20)
    sig = pd.Series(0, index=df.index)
    sig[breakout_up] = 1
    sig[breakout_dn] = -1
    return sig, _atr_sl(df, 0.8)


def strategy_scalp_macd_fast(df: pd.DataFrame) -> SigPair:
    """Fast MACD (5/13/5) crossover on scalping timeframe."""
    cross_up = (df["macd_fast"] > df["macd_fast_sig"]) & \
               (df["macd_fast"].shift(1) <= df["macd_fast_sig"].shift(1))
    cross_dn = (df["macd_fast"] < df["macd_fast_sig"]) & \
               (df["macd_fast"].shift(1) >= df["macd_fast_sig"].shift(1))
    sig = pd.Series(0, index=df.index)
    sig[cross_up & (df["close"] > df["ema21"])] = 1
    sig[cross_dn & (df["close"] < df["ema21"])] = -1
    return sig, _atr_sl(df, 0.7)


# ─────────────────────────────────────────────────────────────────────────────
# BREAKOUT STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────

def strategy_keltner_breakout(df: pd.DataFrame) -> SigPair:
    """Price breaks outside Keltner Channel with ADX momentum."""
    bull = (df["close"] > df["kelt_upper"]) & (df["adx"] > 22) & (df["close"] > df["ema55"])
    bear = (df["close"] < df["kelt_lower"]) & (df["adx"] > 22) & (df["close"] < df["ema55"])
    sig = pd.Series(0, index=df.index)
    sig[bull & ~bull.shift(1).fillna(False)] = 1
    sig[bear & ~bear.shift(1).fillna(False)] = -1
    return sig, _atr_sl(df, 1.8)


def strategy_pivot_breakout(df: pd.DataFrame) -> SigPair:
    """Pivot point R1/S1 breakout strategy."""
    from forex_robot.strategies.indicators import pivot_points
    pp, r1, s1, r2, s2, r3, s3 = pivot_points(df["high"], df["low"], df["close"])
    bull = (df["close"] > r1) & (df["close"].shift(1) <= r1.shift(1))
    bear = (df["close"] < s1) & (df["close"].shift(1) >= s1.shift(1))
    sig = pd.Series(0, index=df.index)
    sig[bull] = 1
    sig[bear] = -1
    return sig, _atr_sl(df, 1.5)


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED / HYBRID STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────

def strategy_confluence_master(df: pd.DataFrame) -> SigPair:
    """
    High-confidence strategy requiring multiple confirmations:
    Trend (EMA) + Momentum (MACD) + RSI zone + Supertrend + ADX
    """
    # BUY conditions
    bull_trend = df["ema21"] > df["ema55"]
    bull_macd = df["macd"] > df["macd_sig"]
    bull_rsi = (df["rsi14"] > 45) & (df["rsi14"] < 65)
    bull_super = df["supertrend_dir"] == 1
    bull_adx = df["adx"] > 20
    buy = bull_trend & bull_macd & bull_rsi & bull_super & bull_adx
    # SELL conditions
    bear_trend = df["ema21"] < df["ema55"]
    bear_macd = df["macd"] < df["macd_sig"]
    bear_rsi = (df["rsi14"] > 35) & (df["rsi14"] < 55)
    bear_super = df["supertrend_dir"] == -1
    sell = bear_trend & bear_macd & bear_rsi & bear_super & bull_adx

    entry_buy = buy & ~buy.shift(1).fillna(False)
    entry_sell = sell & ~sell.shift(1).fillna(False)
    sig = pd.Series(0, index=df.index)
    sig[entry_buy] = 1
    sig[entry_sell] = -1
    return sig, _atr_sl(df, 1.5)


def strategy_fib_ema_confluence(df: pd.DataFrame) -> SigPair:
    """
    Fibonacci + EMA Confluence:
    Price at Fibonacci support/resistance AND near key EMA.
    """
    fib_sig, fib_sl = strategy_fibonacci_retracement(df)
    ema_sig, _ = strategy_ema_crossover(df, 21, 55)

    sig = pd.Series(0, index=df.index)
    # Trade only when both Fibonacci and EMA agree
    sig[(fib_sig == 1) & (ema_sig == 1)] = 1
    sig[(fib_sig == -1) & (ema_sig == -1)] = -1
    return sig, fib_sl


def strategy_rsi_macd_ema_combo(df: pd.DataFrame) -> SigPair:
    """Triple combo: RSI mean reversion + MACD cross + EMA trend filter."""
    rsi_buy = (df["rsi14"] < 40) & (df["rsi14"] > df["rsi14"].shift(1))
    rsi_sell = (df["rsi14"] > 60) & (df["rsi14"] < df["rsi14"].shift(1))
    macd_bull = df["macd_hist"] > 0
    macd_bear = df["macd_hist"] < 0
    ema_bull = df["close"] > df["ema55"]
    ema_bear = df["close"] < df["ema55"]

    sig = pd.Series(0, index=df.index)
    sig[rsi_buy & macd_bull & ema_bull] = 1
    sig[rsi_sell & macd_bear & ema_bear] = -1
    return sig, _atr_sl(df)


def strategy_sar_ichimoku(df: pd.DataFrame) -> SigPair:
    """Parabolic SAR + Ichimoku cloud for strong trend trades."""
    sar_buy = df["close"] > df["psar"]
    sar_sell = df["close"] < df["psar"]
    cloud_bull = df["close"] > df[["ichi_senkou_a", "ichi_senkou_b"]].max(axis=1)
    cloud_bear = df["close"] < df[["ichi_senkou_a", "ichi_senkou_b"]].min(axis=1)
    tk_bull = df["ichi_tenkan"] > df["ichi_kijun"]
    tk_bear = df["ichi_tenkan"] < df["ichi_kijun"]

    sar_flip_buy = sar_buy & ~sar_buy.shift(1).fillna(False)
    sar_flip_sell = sar_sell & ~sar_sell.shift(1).fillna(False)

    sig = pd.Series(0, index=df.index)
    sig[sar_flip_buy & cloud_bull & tk_bull] = 1
    sig[sar_flip_sell & cloud_bear & tk_bear] = -1
    return sig, _atr_sl(df, 2.0)


def strategy_williams_reversal(df: pd.DataFrame) -> SigPair:
    """Williams %R reversal with MACD and volume confirmation."""
    wr_os = (df["wr14"] < -80) & (df["wr14"] > df["wr14"].shift(1))
    wr_ob = (df["wr14"] > -20) & (df["wr14"] < df["wr14"].shift(1))
    vol_confirm = df["obv"] > df["obv"].shift(3)
    sig = pd.Series(0, index=df.index)
    sig[wr_os & (df["macd_hist"] > 0) & vol_confirm] = 1
    sig[wr_ob & (df["macd_hist"] < 0)] = -1
    return sig, _atr_sl(df)


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY — all strategies available for testing
# ─────────────────────────────────────────────────────────────────────────────

ALL_STRATEGIES = {
    # Trend Following
    "EMA_Crossover_21_55":        lambda df: strategy_ema_crossover(df, 21, 55),
    "EMA_Crossover_8_21":         lambda df: strategy_ema_crossover(df, 8, 21),
    "EMA_Crossover_13_34":        lambda df: strategy_ema_crossover(df, 13, 34),
    "Triple_EMA":                 strategy_triple_ema,
    "MACD_Trend":                 strategy_macd_trend,
    "Supertrend":                 strategy_supertrend,
    "Ichimoku":                   strategy_ichimoku,
    "Hull_MA":                    strategy_hull_ma,
    # Mean Reversion
    "Bollinger_Reversal":         strategy_bollinger_reversal,
    "RSI_Oversold_OB":            strategy_rsi_oversold,
    "Stochastic_Reversal":        strategy_stochastic_reversal,
    "CCI_Reversal":               strategy_cci_reversal,
    "Williams_Reversal":          strategy_williams_reversal,
    # Fibonacci / Corrective
    "Fibonacci_Retracement":      strategy_fibonacci_retracement,
    "Fibonacci_Extension":        strategy_fibonacci_extension_breakout,
    "Wave_Correction":            strategy_wave_correction,
    "Fib_EMA_Confluence":         strategy_fib_ema_confluence,
    # Scalping
    "Scalp_EMA_Ribbon":           strategy_scalp_ema_ribbon,
    "Scalp_BB_Squeeze":           strategy_scalp_bb_squeeze,
    "Scalp_Stoch_RSI":            strategy_scalp_stoch_rsi,
    "Scalp_Donchian":             strategy_scalp_donchian,
    "Scalp_MACD_Fast":            strategy_scalp_macd_fast,
    # Breakout
    "Keltner_Breakout":           strategy_keltner_breakout,
    "Pivot_Breakout":             strategy_pivot_breakout,
    # Hybrid / Confluence
    "Confluence_Master":          strategy_confluence_master,
    "RSI_MACD_EMA_Combo":         strategy_rsi_macd_ema_combo,
    "SAR_Ichimoku":               strategy_sar_ichimoku,
}

# Scalping-optimized strategies (best on M5/M15)
SCALPING_STRATEGIES = {k: v for k, v in ALL_STRATEGIES.items() if "Scalp" in k}

# Swing strategies (best on H1/H4/D1)
SWING_STRATEGIES = {k: v for k, v in ALL_STRATEGIES.items()
                    if k not in SCALPING_STRATEGIES}
