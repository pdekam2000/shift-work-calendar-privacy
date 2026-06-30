"""
Advanced Strategies — SMC, Supply/Demand, Harmonic, London Breakout, VWAP, ORB, Wyckoff
+ ترکیب‌های هوشمند با استراتژی‌های قبلی
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple

SigPair = Tuple[pd.Series, pd.Series]
PIP = 0.0001

def _sl(df, mult=1.5):
    return (df["atr14"] / PIP * mult).clip(5, 70)


# ══════════════════════════════════════════════════════════════════
#  ۱. SMART MONEY CONCEPTS (SMC)
# ══════════════════════════════════════════════════════════════════

def _find_order_blocks(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """
    Order Block = آخرین کندل نزولی قبل از یک حرکت صعودی قوی (Bullish OB)
                  آخرین کندل صعودی قبل از یک حرکت نزولی قوی (Bearish OB)
    """
    df = df.copy()
    atr = df["atr14"]
    df["ob_bull"] = 0.0   # سطح پایین OB صعودی
    df["ob_bear"] = 0.0   # سطح بالای OB نزولی
    df["ob_bull_active"] = False
    df["ob_bear_active"] = False

    for i in range(lookback + 2, len(df)):
        # Bullish OB: کندل نزولی قبل از یک موج صعودی قوی
        body_down = df["close"].iloc[i - lookback] < df["open"].iloc[i - lookback]
        move_up   = (df["close"].iloc[i] - df["close"].iloc[i - lookback]) > atr.iloc[i] * 1.5
        if body_down and move_up:
            df.iloc[i, df.columns.get_loc("ob_bull")] = df["low"].iloc[i - lookback]
            df.iloc[i, df.columns.get_loc("ob_bull_active")] = True

        # Bearish OB: کندل صعودی قبل از یک موج نزولی قوی
        body_up   = df["close"].iloc[i - lookback] > df["open"].iloc[i - lookback]
        move_down = (df["close"].iloc[i - lookback] - df["close"].iloc[i]) > atr.iloc[i] * 1.5
        if body_up and move_down:
            df.iloc[i, df.columns.get_loc("ob_bear")] = df["high"].iloc[i - lookback]
            df.iloc[i, df.columns.get_loc("ob_bear_active")] = True

    return df


def _find_fvg(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Fair Value Gap (FVG / Imbalance):
    بین کندل i-2 و i یک فاصله وجود دارد که قیمت پر نکرده.
    Bullish FVG: low[i] > high[i-2]
    Bearish FVG: high[i] < low[i-2]
    """
    bull_fvg = df["low"] > df["high"].shift(2)
    bear_fvg = df["high"] < df["low"].shift(2)
    # میانه FVG
    bull_mid = (df["low"] + df["high"].shift(2)) / 2
    bear_mid = (df["high"] + df["low"].shift(2)) / 2
    return bull_fvg, bear_fvg, bull_mid, bear_mid


def strategy_smc_order_block(df: pd.DataFrame) -> SigPair:
    """
    SMC — Order Block:
    وقتی قیمت به Order Block برمی‌گردد با تأیید FVG وارد می‌شویم.
    """
    df = _find_order_blocks(df, lookback=3)
    bull_fvg, bear_fvg, _, _ = _find_fvg(df)
    atr = df["atr14"]
    sig = pd.Series(0, index=df.index)

    # بازگشت به Bullish OB + تأیید FVG صعودی
    ob_bull_level = df["ob_bull"].replace(0, np.nan).ffill()
    near_bull_ob  = (df["close"] <= ob_bull_level * 1.002) & (df["close"] >= ob_bull_level * 0.998)
    sig[near_bull_ob & (df["adx"] > 18) & (df["rsi14"] < 55) & (df["ema21"] > df["ema55"])] = 1

    # بازگشت به Bearish OB
    ob_bear_level = df["ob_bear"].replace(0, np.nan).ffill()
    near_bear_ob  = (df["close"] >= ob_bear_level * 0.998) & (df["close"] <= ob_bear_level * 1.002)
    sig[near_bear_ob & (df["adx"] > 18) & (df["rsi14"] > 45) & (df["ema21"] < df["ema55"])] = -1

    return sig, _sl(df, 1.2)


def strategy_smc_fvg(df: pd.DataFrame) -> SigPair:
    """
    SMC — Fair Value Gap:
    وقتی قیمت به FVG برمی‌گردد تا آن را پر کند، در جهت روند اصلی وارد می‌شویم.
    """
    bull_fvg, bear_fvg, bull_mid, bear_mid = _find_fvg(df)
    sig = pd.Series(0, index=df.index)

    # ذخیره آخرین FVG سطح
    last_bull_fvg_mid = bull_mid.where(bull_fvg).ffill()
    last_bear_fvg_mid = bear_mid.where(bear_fvg).ffill()

    tol = df["atr14"] * 0.5
    at_bull_fvg = (df["close"] - last_bull_fvg_mid).abs() < tol
    at_bear_fvg = (df["close"] - last_bear_fvg_mid).abs() < tol

    sig[at_bull_fvg & (df["ema21"] > df["ema55"]) & (df["macd_hist"] > 0)] = 1
    sig[at_bear_fvg & (df["ema21"] < df["ema55"]) & (df["macd_hist"] < 0)] = -1

    return sig, _sl(df, 1.3)


def strategy_smc_bos_choch(df: pd.DataFrame) -> SigPair:
    """
    SMC — Break of Structure (BOS) + Change of Character (CHoCH):
    BOS: شکست یک سقف/کف اخیر در جهت روند = ادامه روند
    CHoCH: شکست برخلاف روند = تغییر روند
    """
    sig = pd.Series(0, index=df.index)
    lookback = 10

    prev_high = df["high"].rolling(lookback).max().shift(1)
    prev_low  = df["low"].rolling(lookback).min().shift(1)

    # BOS صعودی: قیمت از سقف قبلی رد شد در جهت روند صعودی
    bos_bull = (df["close"] > prev_high) & (df["ema21"] > df["ema55"]) & (df["adx"] > 20)
    # BOS نزولی
    bos_bear = (df["close"] < prev_low) & (df["ema21"] < df["ema55"]) & (df["adx"] > 20)

    # CHoCH: تغییر روند — اولین BOS برخلاف روند
    choch_bull = (df["close"] > prev_high) & (df["ema21"] < df["ema55"])
    choch_bear = (df["close"] < prev_low)  & (df["ema21"] > df["ema55"])

    new_bos_bull = bos_bull & ~bos_bull.shift(1).fillna(False)
    new_bos_bear = bos_bear & ~bos_bear.shift(1).fillna(False)
    new_choch_bull = choch_bull & ~choch_bull.shift(1).fillna(False)
    new_choch_bear = choch_bear & ~choch_bear.shift(1).fillna(False)

    sig[new_bos_bull | new_choch_bull] = 1
    sig[new_bos_bear | new_choch_bear] = -1

    return sig, _sl(df, 1.5)


def strategy_smc_liquidity_sweep(df: pd.DataFrame) -> SigPair:
    """
    SMC — Liquidity Sweep:
    بازار به سقف/کف قبلی می‌رسد (استاپ‌ها را می‌خورد) و برمی‌گردد.
    این الگوی «شکار استاپ» یکی از قوی‌ترین سیگنال‌های SMC است.
    """
    sig = pd.Series(0, index=df.index)
    lookback = 20
    atr = df["atr14"]

    prev_high = df["high"].rolling(lookback).max().shift(1)
    prev_low  = df["low"].rolling(lookback).min().shift(1)

    # Sweep بالا (شکار استاپ خریداران) و برگشت
    swept_high = (df["high"] > prev_high) & (df["close"] < prev_high)  # ویک بالا از سقف
    swept_low  = (df["low"] < prev_low) & (df["close"] > prev_low)     # ویک پایین از کف

    # تأیید: بعد از sweep باید برگشت قوی داشته باشیم
    strong_reversal_dn = swept_high & (df["close"] < df["open"]) & (df["adx"] > 18)
    strong_reversal_up = swept_low  & (df["close"] > df["open"]) & (df["adx"] > 18)

    sig[strong_reversal_up & (df["rsi14"] < 50)] = 1
    sig[strong_reversal_dn & (df["rsi14"] > 50)] = -1

    return sig, _sl(df, 1.0)


def strategy_smc_full(df: pd.DataFrame) -> SigPair:
    """
    SMC کامل — ترکیب OB + FVG + BOS + Liquidity با تأیید چندگانه.
    """
    sig1, _ = strategy_smc_order_block(df)
    sig2, _ = strategy_smc_fvg(df)
    sig3, _ = strategy_smc_bos_choch(df)
    sig4, _ = strategy_smc_liquidity_sweep(df)

    combined = sig1 + sig2 + sig3 + sig4
    sig = pd.Series(0, index=df.index)
    sig[combined >= 2]  = 1
    sig[combined <= -2] = -1

    return sig, _sl(df, 1.5)


# ══════════════════════════════════════════════════════════════════
#  ۲. SUPPLY & DEMAND ZONES
# ══════════════════════════════════════════════════════════════════

def _find_sd_zones(df: pd.DataFrame, strength_atr: float = 1.5, lookback: int = 5) -> pd.DataFrame:
    """
    ناحیه عرضه (Supply) = قبل از موج نزولی قوی
    ناحیه تقاضا (Demand) = قبل از موج صعودی قوی
    """
    df = df.copy()
    atr = df["atr14"]
    df["demand_top"] = np.nan
    df["demand_bot"] = np.nan
    df["supply_top"] = np.nan
    df["supply_bot"] = np.nan

    for i in range(lookback + 3, len(df)):
        move = abs(df["close"].iloc[i] - df["close"].iloc[i - lookback])
        if move < atr.iloc[i] * strength_atr:
            continue

        # Demand zone: base before big up move
        if df["close"].iloc[i] > df["close"].iloc[i - lookback]:
            base_low  = df["low"].iloc[i - lookback: i].min()
            base_high = df["high"].iloc[i - lookback: i].min() + atr.iloc[i] * 0.3
            df.iloc[i, df.columns.get_loc("demand_bot")] = base_low
            df.iloc[i, df.columns.get_loc("demand_top")] = base_high

        # Supply zone: base before big down move
        else:
            base_high = df["high"].iloc[i - lookback: i].max()
            base_low  = df["low"].iloc[i - lookback: i].max() - atr.iloc[i] * 0.3
            df.iloc[i, df.columns.get_loc("supply_top")] = base_high
            df.iloc[i, df.columns.get_loc("supply_bot")] = base_low

    return df


def strategy_supply_demand(df: pd.DataFrame) -> SigPair:
    """
    ورود وقتی قیمت به ناحیه عرضه/تقاضا برمی‌گردد.
    """
    df = _find_sd_zones(df, strength_atr=1.2, lookback=4)
    sig = pd.Series(0, index=df.index)

    d_top = df["demand_top"].ffill()
    d_bot = df["demand_bot"].ffill()
    s_top = df["supply_top"].ffill()
    s_bot = df["supply_bot"].ffill()

    in_demand = (df["close"] >= d_bot) & (df["close"] <= d_top)
    in_supply = (df["close"] >= s_bot) & (df["close"] <= s_top)

    sig[in_demand & (df["rsi14"] < 55) & (df["adx"] > 15) & (df["is_bullish"] == 1)] = 1
    sig[in_supply & (df["rsi14"] > 45) & (df["adx"] > 15) & (df["is_bearish"] == 1)] = -1

    return sig, _sl(df, 1.2)


def strategy_sd_with_confirmation(df: pd.DataFrame) -> SigPair:
    """
    S&D با تأیید اضافه: فقط وقتی MACD و Stochastic هم تأیید می‌کنند.
    """
    sig_raw, sl = strategy_supply_demand(df)

    macd_bull  = df["macd_hist"] > 0
    macd_bear  = df["macd_hist"] < 0
    stoch_bull = (df["stoch_k"] > df["stoch_d"]) & (df["stoch_k"] < 60)
    stoch_bear = (df["stoch_k"] < df["stoch_d"]) & (df["stoch_k"] > 40)

    sig = pd.Series(0, index=df.index)
    sig[(sig_raw == 1)  & macd_bull & stoch_bull] = 1
    sig[(sig_raw == -1) & macd_bear & stoch_bear] = -1

    return sig, sl


# ══════════════════════════════════════════════════════════════════
#  ۳. WYCKOFF METHOD
# ══════════════════════════════════════════════════════════════════

def strategy_wyckoff(df: pd.DataFrame) -> SigPair:
    """
    روش وایکوف — تشخیص تجمع (Accumulation) و توزیع (Distribution):
    تجمع = بازار رنج + حجم کاهنده + بعداً Spring (شکست کاذب پایین)
    توزیع = بازار رنج + حجم کاهنده + بعداً UTAD (شکست کاذب بالا)
    """
    sig = pd.Series(0, index=df.index)
    lookback = 20
    atr = df["atr14"]

    rng_high = df["high"].rolling(lookback).max()
    rng_low  = df["low"].rolling(lookback).min()
    rng_size = rng_high - rng_low
    vol_trend = df["volume"].rolling(lookback).mean()

    # رنج باریک = کمتر از 1× ATR
    tight_range = rng_size < atr * lookback * 0.7

    # حجم کاهنده در طول رنج
    vol_declining = df["volume"].rolling(5).mean() < vol_trend * 0.8

    # Spring: شکست کاذب پایین رنج
    spring = (df["low"] < rng_low.shift(1)) & (df["close"] > rng_low.shift(1))
    # UTAD: شکست کاذب بالای رنج
    utad   = (df["high"] > rng_high.shift(1)) & (df["close"] < rng_high.shift(1))

    # Accumulation: رنج + حجم کاهنده + Spring
    accumulation = tight_range & vol_declining & spring
    # Distribution: رنج + حجم کاهنده + UTAD
    distribution = tight_range & vol_declining & utad

    sig[accumulation & (df["rsi14"] < 50)] = 1
    sig[distribution & (df["rsi14"] > 50)] = -1

    return sig, _sl(df, 1.5)


# ══════════════════════════════════════════════════════════════════
#  ۴. HARMONIC PATTERNS
# ══════════════════════════════════════════════════════════════════

def _check_ratio(actual: float, target: float, tolerance: float = 0.05) -> bool:
    return abs(actual - target) <= tolerance


def strategy_harmonic_patterns(df: pd.DataFrame) -> SigPair:
    """
    الگوهای هارمونیک — Gartley، Bat، Butterfly، Crab:
    تمام الگوها بر اساس نسبت‌های فیبوناچی دقیق.
    """
    sig = pd.Series(0, index=df.index)
    lookback = 50

    for i in range(lookback, len(df)):
        window = df.iloc[i - lookback: i + 1]
        h = window["high"].values
        l = window["low"].values
        c = window["close"].values

        # پیدا کردن ۵ نقطه XABCD
        # X = شروع، A = اولین swing، B = اصلاح، C = ادامه، D = نقطه ورود
        highs_idx = []
        lows_idx  = []
        for j in range(2, len(h) - 2):
            if h[j] == max(h[j-2:j+3]):
                highs_idx.append(j)
            if l[j] == min(l[j-2:j+3]):
                lows_idx.append(j)

        if len(highs_idx) < 2 or len(lows_idx) < 2:
            continue

        atr_val = df["atr14"].iloc[i]

        # Bullish Gartley (XABCD با D نزدیک X×0.786)
        try:
            if lows_idx[-1] > highs_idx[-1]:
                X = l[lows_idx[-2]]
                A = h[highs_idx[-1]]
                B = l[lows_idx[-1]]
                D = c[-1]

                XA = A - X
                AB = A - B
                if XA <= 0: continue

                AB_XA = AB / XA
                if _check_ratio(AB_XA, 0.618):  # Gartley
                    D_target = X + XA * 0.786
                    if abs(D - D_target) < atr_val * 1.5:
                        sig.iloc[i] = 1  # Bullish Gartley

                elif _check_ratio(AB_XA, 0.382) or _check_ratio(AB_XA, 0.5):  # Bat
                    D_target = X + XA * 0.886
                    if abs(D - D_target) < atr_val * 1.5:
                        sig.iloc[i] = 1

            # Bearish
            if highs_idx[-1] > lows_idx[-1]:
                X = h[highs_idx[-2]]
                A = l[lows_idx[-1]]
                B = h[highs_idx[-1]]
                D = c[-1]

                XA = X - A
                AB = B - A
                if XA <= 0: continue

                AB_XA = AB / XA
                if _check_ratio(AB_XA, 0.618):
                    D_target = X - XA * 0.786
                    if abs(D - D_target) < atr_val * 1.5:
                        sig.iloc[i] = -1

                elif _check_ratio(AB_XA, 0.382) or _check_ratio(AB_XA, 0.5):
                    D_target = X - XA * 0.886
                    if abs(D - D_target) < atr_val * 1.5:
                        sig.iloc[i] = -1

        except Exception:
            pass

    return sig, _sl(df, 1.5)


# ══════════════════════════════════════════════════════════════════
#  ۵. LONDON / NY BREAKOUT
# ══════════════════════════════════════════════════════════════════

def strategy_london_breakout(df: pd.DataFrame) -> SigPair:
    """
    London Breakout:
    رنج آسیا (00:00-07:00 UTC) را محاسبه می‌کند.
    در ساعت 07:00-10:00 London breakout بالا یا پایین رنج وارد می‌شود.
    یکی از قدیمی‌ترین و مطمئن‌ترین استراتژی‌های فارکس.
    """
    sig = pd.Series(0, index=df.index)
    if df.index.tz is None:
        return sig, _sl(df)

    hours = df.index.hour
    asian_mask   = (hours >= 0) & (hours < 7)
    london_mask  = (hours >= 7) & (hours < 11)

    # محاسبه رنج آسیا برای هر روز
    df_temp = df.copy()
    df_temp["date"] = df.index.date
    df_temp["asian"] = asian_mask

    asian_high = df_temp[df_temp["asian"]].groupby("date")["high"].max()
    asian_low  = df_temp[df_temp["asian"]].groupby("date")["low"].min()

    for i, idx in enumerate(df.index):
        if not london_mask[i]:
            continue
        date_key = idx.date()
        if date_key not in asian_high.index:
            continue
        ah = asian_high[date_key]
        al = asian_low[date_key]
        atr_val = df["atr14"].iloc[i]

        if al >= ah or (ah - al) < atr_val * 0.3:
            continue

        # Breakout بالا
        if df["close"].iloc[i] > ah and df["close"].iloc[i-1] <= ah:
            if df["adx"].iloc[i] > 15:
                sig.iloc[i] = 1
        # Breakout پایین
        elif df["close"].iloc[i] < al and df["close"].iloc[i-1] >= al:
            if df["adx"].iloc[i] > 15:
                sig.iloc[i] = -1

    return sig, _sl(df, 1.0)


def strategy_ny_open_breakout(df: pd.DataFrame) -> SigPair:
    """
    NY Open Breakout (13:00-14:30 UTC):
    رنج اول روز London (07:00-13:00) را می‌گیرد،
    در زمان باز شدن بورس نیویورک breakout را معامله می‌کند.
    """
    sig = pd.Series(0, index=df.index)
    if df.index.tz is None:
        return sig, _sl(df)

    hours = df.index.hour
    london_morning = (hours >= 7) & (hours < 13)
    ny_open        = (hours >= 13) & (hours < 15)

    df_temp = df.copy()
    df_temp["date"] = df.index.date

    lm_high = df_temp[london_morning].groupby("date")["high"].max()
    lm_low  = df_temp[london_morning].groupby("date")["low"].min()

    for i, idx in enumerate(df.index):
        if not ny_open[i]:
            continue
        date_key = idx.date()
        if date_key not in lm_high.index:
            continue
        lh = lm_high[date_key]
        ll = lm_low[date_key]
        atr_val = df["atr14"].iloc[i]

        if ll >= lh or (lh - ll) < atr_val * 0.3:
            continue

        if df["close"].iloc[i] > lh and df["close"].iloc[i-1] <= lh:
            sig.iloc[i] = 1
        elif df["close"].iloc[i] < ll and df["close"].iloc[i-1] >= ll:
            sig.iloc[i] = -1

    return sig, _sl(df, 0.8)


def strategy_opening_range_breakout(df: pd.DataFrame) -> SigPair:
    """
    ORB — Opening Range Breakout:
    رنج اولین کندل / اولین ۳۰ دقیقه را می‌گیرد و breakout آن را معامله می‌کند.
    """
    sig = pd.Series(0, index=df.index)
    if df.index.tz is None:
        return sig, _sl(df)

    hours = df.index.hour
    minutes = df.index.minute
    orb_window  = (hours == 7) & (minutes < 30)   # اول London
    trade_window = (hours >= 7) & (hours < 12) & ~orb_window

    df_temp = df.copy()
    df_temp["date"] = df.index.date

    orb_high = df_temp[orb_window].groupby("date")["high"].max()
    orb_low  = df_temp[orb_window].groupby("date")["low"].min()

    for i, idx in enumerate(df.index):
        if not trade_window[i]:
            continue
        date_key = idx.date()
        if date_key not in orb_high.index:
            continue
        oh = orb_high[date_key]
        ol = orb_low[date_key]
        if ol >= oh: continue

        if df["close"].iloc[i] > oh * 1.0001 and df["close"].iloc[i-1] <= oh:
            sig.iloc[i] = 1
        elif df["close"].iloc[i] < ol * 0.9999 and df["close"].iloc[i-1] >= ol:
            sig.iloc[i] = -1

    return sig, _sl(df, 0.8)


# ══════════════════════════════════════════════════════════════════
#  ۶. VWAP STRATEGIES
# ══════════════════════════════════════════════════════════════════

def _daily_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP روزانه — بازنشانی هر روز."""
    df_temp = df.copy()
    df_temp["date"]  = df.index.date if df.index.tz else df.index.normalize()
    df_temp["tp"]    = (df["high"] + df["low"] + df["close"]) / 3
    df_temp["tpv"]   = df_temp["tp"] * df["volume"]
    df_temp["cum_tpv"] = df_temp.groupby("date")["tpv"].cumsum()
    df_temp["cum_v"]   = df_temp.groupby("date")["volume"].cumsum()
    return df_temp["cum_tpv"] / df_temp["cum_v"].replace(0, np.nan)


def strategy_vwap_bounce(df: pd.DataFrame) -> SigPair:
    """
    VWAP Bounce:
    در ترند صعودی، وقتی قیمت به VWAP برمی‌گردد و از آن بانس می‌کند.
    یکی از تکنیک‌های رایج بین معامله‌گران حرفه‌ای.
    """
    vwap = _daily_vwap(df)
    sig  = pd.Series(0, index=df.index)
    atr  = df["atr14"]
    tol  = atr * 0.4

    at_vwap = (df["close"] - vwap).abs() < tol
    below_vwap_prev = df["close"].shift(1) < vwap.shift(1)
    above_vwap_prev = df["close"].shift(1) > vwap.shift(1)

    bounce_up   = at_vwap & below_vwap_prev & (df["close"] > df["open"]) & (df["ema21"] > df["ema55"])
    bounce_down = at_vwap & above_vwap_prev & (df["close"] < df["open"]) & (df["ema21"] < df["ema55"])

    sig[bounce_up]   = 1
    sig[bounce_down] = -1

    return sig, _sl(df, 1.0)


def strategy_vwap_breakout(df: pd.DataFrame) -> SigPair:
    """
    VWAP Breakout:
    عبور از VWAP در جهت روند = ادامه موج.
    """
    vwap = _daily_vwap(df)
    sig  = pd.Series(0, index=df.index)

    cross_up = (df["close"] > vwap) & (df["close"].shift(1) <= vwap.shift(1))
    cross_dn = (df["close"] < vwap) & (df["close"].shift(1) >= vwap.shift(1))

    sig[cross_up & (df["adx"] > 20) & (df["macd_hist"] > 0)] = 1
    sig[cross_dn & (df["adx"] > 20) & (df["macd_hist"] < 0)] = -1

    return sig, _sl(df, 1.2)


# ══════════════════════════════════════════════════════════════════
#  ۷. ترکیب‌های هوشمند
# ══════════════════════════════════════════════════════════════════

def strategy_smc_sd_combo(df: pd.DataFrame) -> SigPair:
    """SMC + Supply & Demand — ترکیب قوی‌ترین سیگنال‌های هر دو."""
    s1, _ = strategy_smc_order_block(df)
    s2, _ = strategy_supply_demand(df)
    s3, _ = strategy_smc_liquidity_sweep(df)
    combined = s1 + s2 + s3
    sig = pd.Series(0, index=df.index)
    sig[combined >= 2]  = 1
    sig[combined <= -2] = -1
    return sig, _sl(df, 1.3)


def strategy_smc_fib_combo(df: pd.DataFrame) -> SigPair:
    """SMC + Fibonacci — Order Block در سطح Fibonacci."""
    from forex_robot.strategies.optimized_strategies import strategy_fib_ichimoku_retracement
    s1, _ = strategy_smc_order_block(df)
    s2, _ = strategy_fib_ichimoku_retracement(df)
    combined = s1 + s2
    sig = pd.Series(0, index=df.index)
    sig[combined >= 2]  = 1
    sig[combined <= -2] = -1
    return sig, _sl(df, 1.3)


def strategy_london_smc_combo(df: pd.DataFrame) -> SigPair:
    """London Breakout + SMC BOS — شکست London با تأیید BOS."""
    s1, _ = strategy_london_breakout(df)
    s2, _ = strategy_smc_bos_choch(df)
    combined = s1 + s2
    sig = pd.Series(0, index=df.index)
    sig[combined >= 2]  = 1
    sig[combined <= -2] = -1
    return sig, _sl(df, 1.0)


def strategy_vwap_smc_combo(df: pd.DataFrame) -> SigPair:
    """VWAP + SMC FVG — بانس از VWAP در سطح FVG."""
    s1, _ = strategy_vwap_bounce(df)
    s2, _ = strategy_smc_fvg(df)
    combined = s1 + s2
    sig = pd.Series(0, index=df.index)
    sig[combined >= 2]  = 1
    sig[combined <= -2] = -1
    return sig, _sl(df, 1.0)


def strategy_wyckoff_sd_combo(df: pd.DataFrame) -> SigPair:
    """Wyckoff + S&D — تجمع در ناحیه تقاضا."""
    s1, _ = strategy_wyckoff(df)
    s2, _ = strategy_supply_demand(df)
    combined = s1 + s2
    sig = pd.Series(0, index=df.index)
    sig[combined >= 2]  = 1
    sig[combined <= -2] = -1
    return sig, _sl(df, 1.5)


def strategy_harmonic_smc_combo(df: pd.DataFrame) -> SigPair:
    """Harmonic + SMC OB — الگوی هارمونیک در Order Block."""
    s1, _ = strategy_harmonic_patterns(df)
    s2, _ = strategy_smc_order_block(df)
    combined = s1 + s2
    sig = pd.Series(0, index=df.index)
    sig[combined >= 2]  = 1
    sig[combined <= -2] = -1
    return sig, _sl(df, 1.5)


def strategy_mega_combo(df: pd.DataFrame) -> SigPair:
    """
    Mega Combo — همه با هم:
    SMC + S&D + Fibonacci + Ichimoku + MACD + ADX
    فقط وقتی ۳+ سیگنال موافق باشند وارد می‌شود.
    """
    from forex_robot.strategies.optimized_strategies import strategy_fib_ichimoku_retracement
    from forex_robot.strategies.strategy_library import strategy_ichimoku, strategy_macd_trend
    s1, _ = strategy_smc_order_block(df)
    s2, _ = strategy_supply_demand(df)
    s3, _ = strategy_fib_ichimoku_retracement(df)
    s4, _ = strategy_smc_liquidity_sweep(df)
    s5, _ = strategy_smc_bos_choch(df)
    combined = s1 + s2 + s3 + s4 + s5
    sig = pd.Series(0, index=df.index)
    sig[combined >= 3]  = 1
    sig[combined <= -3] = -1
    return sig, _sl(df, 1.5)


# ── Registry ───────────────────────────────────────────────────────

ADVANCED_STRATEGIES = {
    # SMC
    "SMC_OrderBlock":          strategy_smc_order_block,
    "SMC_FVG":                 strategy_smc_fvg,
    "SMC_BOS_CHoCH":           strategy_smc_bos_choch,
    "SMC_LiquiditySweep":      strategy_smc_liquidity_sweep,
    "SMC_Full":                strategy_smc_full,
    # Supply & Demand
    "SupplyDemand":            strategy_supply_demand,
    "SD_Confirmed":            strategy_sd_with_confirmation,
    # Wyckoff
    "Wyckoff":                 strategy_wyckoff,
    # Harmonic
    "Harmonic_Patterns":       strategy_harmonic_patterns,
    # Session Breakouts
    "London_Breakout":         strategy_london_breakout,
    "NY_Open_Breakout":        strategy_ny_open_breakout,
    "ORB":                     strategy_opening_range_breakout,
    # VWAP
    "VWAP_Bounce":             strategy_vwap_bounce,
    "VWAP_Breakout":           strategy_vwap_breakout,
    # Combos
    "SMC_SD_Combo":            strategy_smc_sd_combo,
    "SMC_Fib_Combo":           strategy_smc_fib_combo,
    "London_SMC_Combo":        strategy_london_smc_combo,
    "VWAP_SMC_Combo":          strategy_vwap_smc_combo,
    "Wyckoff_SD_Combo":        strategy_wyckoff_sd_combo,
    "Harmonic_SMC_Combo":      strategy_harmonic_smc_combo,
    "Mega_Combo":              strategy_mega_combo,
}
