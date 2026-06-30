"""
HolyGrail Search — تست میلیون‌ها ترکیب پارامتر
هدف: ۱۰ معامله/روز با ۷۰%+ نرخ برد و سود پایدار

ساختار:
  هر استراتژی = ترکیبی از:
    - الگوی کندل (۱۵ الگو)
    - فیلتر روند (EMA/Supertrend/MACD/Ichimoku/none)
    - فیلتر مومنتوم (RSI/Stoch/CCI/none)
    - فیلتر سشن (london/ny/london_ny/active/all)
    - تایم‌فریم (M5/M15/M30/H1)
    - SL: ATR × mult
    - TP: SL × RR
"""
from __future__ import annotations
import sys, os, time, warnings, itertools
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd
from typing import Tuple

from forex_robot.strategies.candle_master import patterns, session_filter
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

INITIAL = 1000.0

# ─────────────────────────────────────────────────────────────────────────────
# پارامتر گرید — هر ترکیب یک استراتژی
# ─────────────────────────────────────────────────────────────────────────────

CANDLE_PATTERNS_BULL = [
    "pin_bull", "engulf_bull", "dragonfly", "morning_star",
    "wick_reject_bull", "kang_bull", "momentum_bull",
    "harami_bull", "tweezer_bottom", "inside_break_bull",
    "three_soldiers", "marubozu_bull",
]
CANDLE_PATTERNS_BEAR = [p.replace("bull","bear").replace("bottom","top")
                         .replace("soldiers","crows").replace("morning","evening")
                         .replace("dragon","grave") for p in CANDLE_PATTERNS_BULL]
CANDLE_PATTERNS_BEAR = [
    "pin_bear", "engulf_bear", "gravestone", "evening_star",
    "wick_reject_bear", "kang_bear", "momentum_bear",
    "harami_bear", "tweezer_top", "inside_break_bear",
    "three_crows", "marubozu_bear",
]

TREND_FILTERS = ["ema_bull", "supertrend_bull", "macd_bull", "ichimoku_bull", "none"]
MOMENTUM_FILTERS = ["rsi_os", "stoch_os", "cci_os", "none"]
SESSIONS = ["london_ny", "active", "all"]
SL_MULTS = [0.5, 0.8, 1.0, 1.3, 1.5]
TP_RRS   = [0.8, 1.0, 1.3, 1.5, 2.0]


def build_signal(df: pd.DataFrame, pat_bull: str, pat_bear: str,
                 trend_filt: str, mom_filt: str, session: str,
                 sl_mult: float, tp_rr: float) -> Tuple[pd.Series, pd.Series]:
    """یک ترکیب پارامتر → سیگنال‌ها."""

    # ── شرط الگوی کندل ────────────────────────────────────────────────────────
    has_bull = df.get(pat_bull, pd.Series(0, index=df.index)).astype(bool)
    has_bear = df.get(pat_bear, pd.Series(0, index=df.index)).astype(bool)

    # ── فیلتر روند ────────────────────────────────────────────────────────────
    if trend_filt == "ema_bull":
        trend_b = df["ema21"] > df["ema55"]
        trend_s = df["ema21"] < df["ema55"]
    elif trend_filt == "supertrend_bull":
        trend_b = df["supertrend_dir"] == 1
        trend_s = df["supertrend_dir"] == -1
    elif trend_filt == "macd_bull":
        trend_b = df["macd_hist"] > 0
        trend_s = df["macd_hist"] < 0
    elif trend_filt == "ichimoku_bull":
        trend_b = df["close"] > df[["ichi_senkou_a","ichi_senkou_b"]].max(axis=1)
        trend_s = df["close"] < df[["ichi_senkou_a","ichi_senkou_b"]].min(axis=1)
    else:
        trend_b = trend_s = pd.Series(True, index=df.index)

    # ── فیلتر مومنتوم ─────────────────────────────────────────────────────────
    if mom_filt == "rsi_os":
        mom_b = df["rsi14"] < 45
        mom_s = df["rsi14"] > 55
    elif mom_filt == "stoch_os":
        mom_b = df["stoch_k"] < 40
        mom_s = df["stoch_k"] > 60
    elif mom_filt == "cci_os":
        mom_b = df["cci20"] < -50
        mom_s = df["cci20"] > 50
    else:
        mom_b = mom_s = pd.Series(True, index=df.index)

    # ── فیلتر سشن ────────────────────────────────────────────────────────────
    sess = session_filter(df, session)

    # ── سیگنال نهایی ──────────────────────────────────────────────────────────
    buy  = has_bull & trend_b & mom_b & sess
    sell = has_bear & trend_s & mom_s & sess

    sig = pd.Series(0, index=df.index)
    sig[buy]  = 1
    sig[sell] = -1

    # SL/TP
    sl_pips = (df["atr14"] / 0.0001 * sl_mult).clip(3, 50)

    return sig, sl_pips


# ─────────────────────────────────────────────────────────────────────────────
# گرید جستجو
# ─────────────────────────────────────────────────────────────────────────────

def grid_search(df: pd.DataFrame, symbol: str, tf: str,
                target_trades_day: float = 5.0,
                target_win_rate: float = 60.0,
                verbose: bool = False):

    trading_days = len(df) * {"M5": 5/1440, "M15": 15/1440,
                               "M30": 30/1440, "H1": 1/24,
                               "D1": 1.0}.get(tf, 1/24)

    best_results = []
    tested = 0
    found = 0

    combo_iter = itertools.product(
        range(len(CANDLE_PATTERNS_BULL)),
        TREND_FILTERS,
        MOMENTUM_FILTERS,
        SESSIONS,
        SL_MULTS,
        TP_RRS,
    )

    total = (len(CANDLE_PATTERNS_BULL) * len(TREND_FILTERS) *
             len(MOMENTUM_FILTERS) * len(SESSIONS) *
             len(SL_MULTS) * len(TP_RRS))

    for (pi, tf_filt, mf, sess, sl_m, tp_r) in combo_iter:
        tested += 1
        pb = CANDLE_PATTERNS_BULL[pi]
        ps = CANDLE_PATTERNS_BEAR[pi]

        try:
            sig, sl_pips = build_signal(df, pb, ps, tf_filt, mf, sess, sl_m, tp_r)
            n_sigs = int(sig.abs().sum())
            tpd    = n_sigs / max(trading_days, 1)

            if tpd < target_trades_day * 0.5:
                continue

            cfg = BacktestConfig(
                initial_capital=INITIAL, symbol=symbol, timeframe=tf,
                risk_pct=1.0,
                tp1_rr=min(tp_r * 0.5, 1.0),
                tp2_rr=tp_r,
                tp3_rr=tp_r * 1.5,
                trail_after_tp1=False,
                spread_pips=1.5,
                slippage_pips=0.5,
            )
            engine = BacktestEngine(cfg)
            trades, equity = engine.run(df, sig, sl_pips, "grid")

            if len(trades) < int(trading_days * target_trades_day * 0.4):
                continue

            m = compute_metrics(trades, equity, INITIAL)
            wr  = m["win_rate_pct"]
            ret = m["total_return_pct"]
            pf  = m["profit_factor"]
            dd  = m["max_drawdown_pct"]

            if wr >= target_win_rate and ret > 0 and dd > -30:
                found += 1
                best_results.append({
                    "pattern_bull":  pb,
                    "pattern_bear":  ps,
                    "trend_filter":  tf_filt,
                    "mom_filter":    mf,
                    "session":       sess,
                    "sl_mult":       sl_m,
                    "tp_rr":         tp_r,
                    "trades_day":    round(tpd, 2),
                    "total_trades":  len(trades),
                    "win_rate":      round(wr, 2),
                    "return_pct":    round(ret, 2),
                    "profit_factor": round(pf, 3),
                    "max_dd":        round(dd, 2),
                    "sharpe":        round(m["sharpe"], 3),
                    "final_equity":  round(m["final_equity"], 2),
                    "symbol":        symbol,
                    "timeframe":     tf,
                })

        except Exception:
            pass

    return pd.DataFrame(best_results) if best_results else pd.DataFrame(), tested, total
