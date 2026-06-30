"""
CandleMaster — موتور جامع الگوهای کندل، ویک، و سایه
شامل ۲۵+ الگوی کندل ژاپنی + تحلیل ویک + فیلتر سشن
"""
import numpy as np
import pandas as pd


# ════════════════════════════════════════════════════════
#  بخش ۱: اندیکاتورهای پایه ویک/سایه
# ════════════════════════════════════════════════════════

def candle_features(df: pd.DataFrame) -> pd.DataFrame:
    """محاسبه تمام ویژگی‌های کندل."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    atr = df.get("atr14", (h - l).rolling(14).mean())

    df = df.copy()
    df["body"]        = (c - o).abs()
    df["body_dir"]    = np.sign(c - o)             # +1 صعودی / -1 نزولی
    df["upper_wick"]  = h - pd.concat([o, c], axis=1).max(axis=1)
    df["lower_wick"]  = pd.concat([o, c], axis=1).min(axis=1) - l
    df["total_range"] = h - l
    df["body_ratio"]  = df["body"] / df["total_range"].replace(0, np.nan)
    df["upper_ratio"] = df["upper_wick"] / df["total_range"].replace(0, np.nan)
    df["lower_ratio"] = df["lower_wick"] / df["total_range"].replace(0, np.nan)

    # نسبت سایه به ATR
    df["uw_atr"]  = df["upper_wick"] / atr.replace(0, np.nan)
    df["lw_atr"]  = df["lower_wick"] / atr.replace(0, np.nan)
    df["rng_atr"] = df["total_range"] / atr.replace(0, np.nan)

    # Mid body
    df["body_mid"] = (pd.concat([o, c], axis=1).max(axis=1) + pd.concat([o, c], axis=1).min(axis=1)) / 2
    return df


# ════════════════════════════════════════════════════════
#  بخش ۲: الگوهای کندل ژاپنی — ۲۵+ الگو
# ════════════════════════════════════════════════════════

def patterns(df: pd.DataFrame) -> pd.DataFrame:
    """تشخیص تمام الگوها — هر ستون 1=الگوی صعودی, -1=نزولی, 0=هیچ."""
    df = candle_features(df)
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    atr = df.get("atr14", (h - l).rolling(14).mean())

    # ── ۱. پین‌بار / Hammer / Shooting Star ──────────────────────────────────
    # پین‌بار صعودی: سایه پایین > ۲× بدنه، سایه بالا کوچک
    df["pin_bull"] = (
        (df["lower_wick"] >= 2.0 * df["body"].clip(lower=1e-8)) &
        (df["upper_wick"] <= 0.5 * df["body"].clip(lower=1e-8)) &
        (df["body"] > 0.0001)
    ).astype(int)

    # پین‌بار نزولی: سایه بالا > ۲× بدنه، سایه پایین کوچک
    df["pin_bear"] = (
        (df["upper_wick"] >= 2.0 * df["body"].clip(lower=1e-8)) &
        (df["lower_wick"] <= 0.5 * df["body"].clip(lower=1e-8)) &
        (df["body"] > 0.0001)
    ).astype(int)

    # ── ۲. Engulfing ─────────────────────────────────────────────────────────
    df["engulf_bull"] = (
        (df["body_dir"] == 1) &
        (df["body_dir"].shift(1) == -1) &
        (c > o.shift(1)) &
        (o < c.shift(1)) &
        (df["body"] > df["body"].shift(1) * 1.1)
    ).astype(int)

    df["engulf_bear"] = (
        (df["body_dir"] == -1) &
        (df["body_dir"].shift(1) == 1) &
        (c < o.shift(1)) &
        (o > c.shift(1)) &
        (df["body"] > df["body"].shift(1) * 1.1)
    ).astype(int)

    # ── ۳. Doji ───────────────────────────────────────────────────────────────
    df["doji"] = (df["body"] < atr * 0.05).astype(int)

    # ── ۴. Dragonfly Doji (بدنه بالا، سایه پایین بلند) ─────────────────────
    df["dragonfly"] = (
        (df["doji"] == 1) &
        (df["lower_wick"] > atr * 0.5) &
        (df["upper_wick"] < atr * 0.1)
    ).astype(int)

    # ── ۵. Gravestone Doji ───────────────────────────────────────────────────
    df["gravestone"] = (
        (df["doji"] == 1) &
        (df["upper_wick"] > atr * 0.5) &
        (df["lower_wick"] < atr * 0.1)
    ).astype(int)

    # ── ۶. Morning Star / Evening Star (۳ کندل) ────────────────────────────
    df["morning_star"] = (
        (df["body_dir"].shift(2) == -1) &
        (df["body"].shift(2) > atr * 0.3) &
        (df["doji"].shift(1) == 1) &
        (df["body_dir"] == 1) &
        (c > df["body_mid"].shift(2))
    ).astype(int)

    df["evening_star"] = (
        (df["body_dir"].shift(2) == 1) &
        (df["body"].shift(2) > atr * 0.3) &
        (df["doji"].shift(1) == 1) &
        (df["body_dir"] == -1) &
        (c < df["body_mid"].shift(2))
    ).astype(int)

    # ── ۷. Harami صعودی/نزولی ────────────────────────────────────────────────
    df["harami_bull"] = (
        (df["body_dir"].shift(1) == -1) &
        (df["body"].shift(1) > atr * 0.3) &
        (o > c.shift(1)) & (c < o.shift(1)) &
        (df["body"] < df["body"].shift(1) * 0.5)
    ).astype(int)

    df["harami_bear"] = (
        (df["body_dir"].shift(1) == 1) &
        (df["body"].shift(1) > atr * 0.3) &
        (o < c.shift(1)) & (c > o.shift(1)) &
        (df["body"] < df["body"].shift(1) * 0.5)
    ).astype(int)

    # ── ۸. Marubozu (بدون سایه، مومنتوم قوی) ────────────────────────────────
    df["marubozu_bull"] = (
        (df["body_dir"] == 1) &
        (df["upper_wick"] < atr * 0.03) &
        (df["lower_wick"] < atr * 0.03) &
        (df["body"] > atr * 0.4)
    ).astype(int)

    df["marubozu_bear"] = (
        (df["body_dir"] == -1) &
        (df["upper_wick"] < atr * 0.03) &
        (df["lower_wick"] < atr * 0.03) &
        (df["body"] > atr * 0.4)
    ).astype(int)

    # ── ۹. Three White Soldiers / Three Black Crows ──────────────────────────
    df["three_soldiers"] = (
        (df["body_dir"] == 1) &
        (df["body_dir"].shift(1) == 1) &
        (df["body_dir"].shift(2) == 1) &
        (c > c.shift(1)) & (c.shift(1) > c.shift(2)) &
        (df["body"] > atr * 0.2) &
        (df["body"].shift(1) > atr * 0.2)
    ).astype(int)

    df["three_crows"] = (
        (df["body_dir"] == -1) &
        (df["body_dir"].shift(1) == -1) &
        (df["body_dir"].shift(2) == -1) &
        (c < c.shift(1)) & (c.shift(1) < c.shift(2)) &
        (df["body"] > atr * 0.2) &
        (df["body"].shift(1) > atr * 0.2)
    ).astype(int)

    # ── ۱۰. Tweezer Top / Bottom ─────────────────────────────────────────────
    df["tweezer_bottom"] = (
        (abs(l - l.shift(1)) < atr * 0.05) &
        (df["body_dir"] == 1) &
        (df["body_dir"].shift(1) == -1)
    ).astype(int)

    df["tweezer_top"] = (
        (abs(h - h.shift(1)) < atr * 0.05) &
        (df["body_dir"] == -1) &
        (df["body_dir"].shift(1) == 1)
    ).astype(int)

    # ── ۱۱. Inside Bar (بارِ داخلی = تجمیع قبل از شکست) ─────────────────────
    df["inside_bar"] = (
        (h < h.shift(1).fillna(h)) & (l > l.shift(1).fillna(l))
    ).astype(int)

    # شکست Inside Bar
    df["inside_break_bull"] = (
        (df["inside_bar"].shift(1).fillna(0).astype(bool)) &
        (h > h.shift(2))
    ).astype(int)

    df["inside_break_bear"] = (
        (df["inside_bar"].shift(1).fillna(0).astype(bool)) &
        (l < l.shift(2))
    ).astype(int)

    # ── ۱۲. Wick Rejection از سطح کلیدی ────────────────────────────────────
    # ویک بلند پایین در نزدیکی حمایت → ریجکشن صعودی
    df["wick_reject_bull"] = (
        (df["lw_atr"] >= 1.5) &
        (df["lower_ratio"] >= 0.5) &
        (df["body_ratio"] <= 0.35)
    ).astype(int)

    # ویک بلند بالا در نزدیکی مقاومت → ریجکشن نزولی
    df["wick_reject_bear"] = (
        (df["uw_atr"] >= 1.5) &
        (df["upper_ratio"] >= 0.5) &
        (df["body_ratio"] <= 0.35)
    ).astype(int)

    # ── ۱۳. Kangaroo Tail (ویک بسیار بلند، الگوی معکوس) ────────────────────
    df["kang_bull"] = (df["lw_atr"] >= 2.5).astype(int)
    df["kang_bear"] = (df["uw_atr"] >= 2.5).astype(int)

    # ── ۱۴. Strong Momentum Candle ────────────────────────────────────────────
    df["momentum_bull"] = (
        (df["rng_atr"] >= 1.8) &
        (df["body_ratio"] >= 0.65) &
        (df["body_dir"] == 1)
    ).astype(int)

    df["momentum_bear"] = (
        (df["rng_atr"] >= 1.8) &
        (df["body_ratio"] >= 0.65) &
        (df["body_dir"] == -1)
    ).astype(int)

    # ── ۱۵. Fakey / False Break (شکست کاذب) ─────────────────────────────────
    prev_high = h.shift(1).rolling(5).max().shift(1)
    prev_low  = l.shift(1).rolling(5).min().shift(1)
    df["fakey_bull"] = (
        (h.shift(1) > prev_high) &
        (c < h.shift(1)) &
        (df["body_dir"] == -1) &
        (df["body_dir"].shift(1) == 1)
    ).astype(int)

    df["fakey_bear"] = (
        (l.shift(1) < prev_low) &
        (c > l.shift(1)) &
        (df["body_dir"] == 1) &
        (df["body_dir"].shift(1) == -1)
    ).astype(int)

    return df


# ════════════════════════════════════════════════════════
#  بخش ۳: فیلتر سشن معاملاتی
# ════════════════════════════════════════════════════════

def session_filter(df: pd.DataFrame, session: str = "london_ny") -> pd.Series:
    """
    فیلتر بر اساس ساعت معاملاتی (UTC):
    london:    07:00 - 16:00
    ny:        13:00 - 21:00
    london_ny: 13:00 - 17:00  ← بهترین نقدینگی
    tokyo:     00:00 - 08:00
    all:       همه ساعات
    """
    hours = df.index.hour
    if session == "london":
        mask = (hours >= 7) & (hours < 16)
    elif session == "ny":
        mask = (hours >= 13) & (hours < 21)
    elif session == "london_ny":
        mask = (hours >= 13) & (hours < 17)
    elif session == "tokyo":
        mask = (hours < 8)
    elif session == "active":
        mask = ((hours >= 7) & (hours < 17))   # لندن کامل
    else:
        mask = pd.Series(True, index=df.index)
        return mask
    return pd.Series(mask, index=df.index)
