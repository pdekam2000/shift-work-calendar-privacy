"""
تست نهایی کاندیداهای زنده — با بهبودهای پیشنهادی:
1. Fib_Ichimoku روی H1 (سیگنال بیشتر)
2. Stochastic_Reversal بهینه‌شده
3. Hybrid: تشخیص رژیم بازار + سوئیچ خودکار استراتژی
4. Fib + Stoch + RSI ترکیبی جدید
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.optimized_strategies import strategy_fib_ichimoku_retracement
from forex_robot.strategies.strategy_library import strategy_stochastic_reversal, strategy_macd_trend
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

INITIAL = 1000.0
START   = "2026-01-01"

def clr(c, t):
    cc = {"g":"\033[92m","r":"\033[91m","y":"\033[93m","c":"\033[96m","b":"\033[1m","0":"\033[0m","m":"\033[95m"}
    return f"{cc.get(c,'')}{t}{cc['0']}"

# ── استراتژی ترکیبی جدید: Regime-Adaptive ────────────────────────────────────

def strategy_regime_adaptive(df: pd.DataFrame):
    """
    تشخیص خودکار رژیم بازار + انتخاب استراتژی مناسب:
    - ADX > 25 + ATR بزرگ  →  ترند‌فالوینگ (Ichimoku + MACD)
    - ADX < 25 یا ATR کوچک →  میان‌برگشت  (Fibonacci + Stochastic)
    این استراتژی در هر بازاری کار می‌کند.
    """
    sig    = pd.Series(0, index=df.index)
    sl_out = (df["atr14"] / 0.0001 * 1.3).clip(5, 55)

    atr_median = df["atr14"].rolling(60).median()
    trending   = (df["adx"] >= 25) & (df["atr14"] >= atr_median)
    ranging    = ~trending

    # ── بخش ترند: Ichimoku + MACD + EMA ──────────────────────────────────────
    cloud_bull = df["close"] > df[["ichi_senkou_a","ichi_senkou_b"]].max(axis=1)
    cloud_bear = df["close"] < df[["ichi_senkou_a","ichi_senkou_b"]].min(axis=1)
    tk_bull    = df["ichi_tenkan"] > df["ichi_kijun"]
    tk_bear    = df["ichi_tenkan"] < df["ichi_kijun"]
    macd_bull  = df["macd_hist"] > 0
    macd_bear  = df["macd_hist"] < 0
    ema_bull   = df["ema21"] > df["ema55"]
    ema_bear   = df["ema21"] < df["ema55"]
    macd_cross_up = (df["macd"] > df["macd_sig"]) & (df["macd"].shift(1) <= df["macd_sig"].shift(1))
    macd_cross_dn = (df["macd"] < df["macd_sig"]) & (df["macd"].shift(1) >= df["macd_sig"].shift(1))

    trend_buy  = macd_cross_up & cloud_bull & tk_bull & ema_bull & trending
    trend_sell = macd_cross_dn & cloud_bear & tk_bear & ema_bear & trending

    # ── بخش رنج: Fibonacci + Stochastic + RSI ────────────────────────────────
    stoch_up = (df["stoch_k"] > df["stoch_d"]) & (df["stoch_k"].shift(1) <= df["stoch_d"].shift(1))
    stoch_dn = (df["stoch_k"] < df["stoch_d"]) & (df["stoch_k"].shift(1) >= df["stoch_d"].shift(1))
    from_os  = df["stoch_k"].shift(1) < 25
    from_ob  = df["stoch_k"].shift(1) > 75
    rsi_low  = df["rsi14"] < 50
    rsi_high = df["rsi14"] > 50

    # Fibonacci support: price near recent swing low retracement
    lookback = 20
    for i in range(lookback + 2, len(df)):
        window  = df.iloc[i - lookback: i]
        sh = window["high"].max()
        sl = window["low"].min()
        diff = sh - sl
        if diff < 0.0005: continue
        cur = df["close"].iloc[i]
        atr = df["atr14"].iloc[i]
        tol = atr * 0.7
        fib_levels_bull = [sh - diff * r for r in [0.382, 0.5, 0.618]]
        fib_levels_bear = [sl + diff * r for r in [0.382, 0.5, 0.618]]
        at_fib_bull = any(abs(cur - l) < tol for l in fib_levels_bull)
        at_fib_bear = any(abs(cur - l) < tol for l in fib_levels_bear)

        if ranging.iloc[i]:
            if at_fib_bull and stoch_up.iloc[i] and from_os.iloc[i] and rsi_low.iloc[i]:
                sig.iloc[i] = 1
            elif at_fib_bear and stoch_dn.iloc[i] and from_ob.iloc[i] and rsi_high.iloc[i]:
                sig.iloc[i] = -1

    # ترکیب سیگنال‌های ترند
    sig[trend_buy  & (sig == 0)] = 1
    sig[trend_sell & (sig == 0)] = -1

    return sig, sl_out


def strategy_fib_stoch_rsi(df: pd.DataFrame):
    """
    Fib + Stoch + RSI — بهترین برای بازار ۲۰۲۶:
    ورود فقط وقتی همه ۳ تأیید می‌کنند:
    - قیمت نزدیک سطح Fibonacci 38.2/50/61.8
    - Stochastic از OB/OS برگشته
    - RSI در zone مومنتوم
    - نزدیک Ichimoku Kijun (پشتیبان/مقاومت طبیعی)
    """
    sig    = pd.Series(0, index=df.index)
    sl_out = (df["atr14"] / 0.0001 * 1.2).clip(5, 50)

    stoch_up = (df["stoch_k"] > df["stoch_d"]) & (df["stoch_k"].shift(1) <= df["stoch_d"].shift(1))
    stoch_dn = (df["stoch_k"] < df["stoch_d"]) & (df["stoch_k"].shift(1) >= df["stoch_d"].shift(1))
    from_os  = df["stoch_k"].shift(1) < 30
    from_ob  = df["stoch_k"].shift(1) > 70

    lookback = 30
    for i in range(lookback + 5, len(df)):
        window = df.iloc[i - lookback: i]
        sh = window["high"].max()
        sl_ = window["low"].min()
        diff = sh - sl_
        if diff < 0.0007: continue

        cur   = df["close"].iloc[i]
        kijun = df["ichi_kijun"].iloc[i]
        atr   = df["atr14"].iloc[i]
        tol   = atr * 0.8
        rsi   = df["rsi14"].iloc[i]

        fib_bull = [sh - diff * r for r in [0.382, 0.5, 0.618]]
        fib_bear = [sl_ + diff * r for r in [0.382, 0.5, 0.618]]

        at_fb = any(abs(cur - l) < tol for l in fib_bull)
        at_fbe = any(abs(cur - l) < tol for l in fib_bear)
        near_k = abs(cur - kijun) < tol * 1.8

        # BUY: Fib support + Kijun support + Stoch از OS برگشت + RSI < 55
        if at_fb and near_k and stoch_up.iloc[i] and from_os.iloc[i] and rsi < 55:
            sig.iloc[i] = 1
        # SELL: Fib resistance + Kijun resistance + Stoch از OB برگشت + RSI > 45
        elif at_fbe and near_k and stoch_dn.iloc[i] and from_ob.iloc[i] and rsi > 45:
            sig.iloc[i] = -1

    return sig, sl_out


def run_backtest(df, fn, sym, tf, rp, t1, t2, t3, trail, label):
    df_i = add_all_indicators(df.copy())
    try:
        signals, sl_pips = fn(df_i)
    except Exception as e:
        return None
    if signals.abs().sum() < 2:
        return None
    cfg = BacktestConfig(
        initial_capital=INITIAL, symbol=sym, timeframe=tf,
        risk_pct=rp, tp1_rr=t1, tp2_rr=t2, tp3_rr=t3,
        trail_after_tp1=trail,
    )
    engine = BacktestEngine(cfg)
    trades, equity = engine.run(df_i, signals, sl_pips, label)
    if not trades:
        return None
    m = compute_metrics(trades, equity, INITIAL)
    m["strategy"] = label
    m["symbol"]   = sym
    m["timeframe"]= tf
    m["trades"]   = trades
    m["equity"]   = equity
    return m


def main():
    print("\n" + "="*72)
    print(clr("b","  تست کاندیداهای زنده ۲۰۲۶ + بهبودهای جدید"))
    print("="*72)

    start_ts = pd.Timestamp(START, tz="UTC")

    # بارگذاری داده‌ها
    print("\n[۱] بارگذاری داده‌ها…")
    datasets = {}
    for sym in ["GBPUSD", "EURUSD"]:
        datasets[sym] = {}
        for tf in ["H1", "D1"]:
            raw = fetch_data(sym, tf)
            datasets[sym][tf]         = raw.copy()
            datasets[sym][tf+"_2026"] = raw[raw.index >= start_ts].copy()
            print(f"  {sym} {tf}: کل={len(datasets[sym][tf])} | ۲۰۲۶={len(datasets[sym][tf+'_2026'])}")

    # استراتژی‌های تست
    strategies = [
        # --- کاندیداهای قبلی ---
        ("Fib_Ichi [D1 اصلی]",        strategy_fib_ichimoku_retracement, "D1",  1.0, 1,2,3, False),
        ("Stochastic_Rev [D1]",        strategy_stochastic_reversal,      "D1",  1.0, 1,1.5,2, False),
        ("MACD_Trend [D1]",            strategy_macd_trend,               "D1",  1.0, 1,2,3, True),
        # --- بهبودیافته ---
        ("Fib_Stoch_RSI [D1 جدید]",   strategy_fib_stoch_rsi,           "D1",  1.0, 1,2,3, False),
        ("Fib_Stoch_RSI [D1 ریسک بیشتر]", strategy_fib_stoch_rsi,       "D1",  1.5, 1,2,3, False),
        ("Regime_Adaptive [D1]",       strategy_regime_adaptive,          "D1",  1.0, 1,2,3, True),
        ("Fib_Stoch_RSI [H1]",        strategy_fib_stoch_rsi,           "H1",  0.5, 1,1.5,2.5, False),
        ("Regime_Adaptive [H1]",      strategy_regime_adaptive,          "H1",  0.5, 1,2,3, True),
    ]

    # تست روی ۲۰۲۶ و تاریخی
    print("\n[۲] اجرای بک‌تست…")
    results = {"2026": [], "history": []}

    for sym in ["GBPUSD", "EURUSD"]:
        for (name, fn, tf, rp, t1, t2, t3, trail) in strategies:
            # ۲۰۲۶
            df26 = datasets[sym].get(tf+"_2026")
            if df26 is not None and len(df26) > 60:
                m = run_backtest(df26, fn, sym, tf, rp, t1, t2, t3, trail, name)
                if m:
                    m["period"] = "2026"
                    m["symbol"] = sym
                    results["2026"].append(m)
            # تاریخی
            df_h = datasets[sym].get(tf)
            if df_h is not None and len(df_h) > 200:
                m = run_backtest(df_h, fn, sym, tf, rp, t1, t2, t3, trail, name)
                if m:
                    m["period"] = "historical"
                    m["symbol"] = sym
                    results["history"].append(m)

    # ── جدول ۲۰۲۶ ──────────────────────────────────────────────────────────
    def print_table(data, title):
        print(f"\n{'='*105}")
        print(clr("b", f"  {title}"))
        print(f"  {'استراتژی':<38} {'جفت':<8} {'TF':<5} {'بازدهی':>9} "
              f"{'نرخ برد':>9} {'P.F':>6} {'MaxDD':>7} {'معاملات':>9} {'سرمایه':>10}")
        print("─"*105)
        srt = sorted(data, key=lambda x: -x["total_return_pct"])
        for m in srt:
            ret = m["total_return_pct"]
            wr  = m["win_rate_pct"]
            pf  = m["profit_factor"]
            dd  = m["max_drawdown_pct"]
            tr  = m["total_trades"]
            eq  = m["final_equity"]
            rc  = clr("g",f"{ret:>+8.2f}%") if ret>0 else clr("r",f"{ret:>+8.2f}%")
            dc  = clr("g",f"{dd:>6.1f}%") if dd>-8 else clr("y",f"{dd:>6.1f}%") if dd>-18 else clr("r",f"{dd:>6.1f}%")
            pfc = clr("g",f"{pf:>5.3f}") if pf>1.5 else clr("y",f"{pf:>5.3f}") if pf>1.0 else clr("r",f"{pf:>5.3f}")
            print(f"  {m['strategy']:<38} {m['symbol']:<8} {m['timeframe']:<5} {rc}  "
                  f"{wr:>8.1f}%  {pfc}  {dc}  {tr:>8}  €{eq:>8,.2f}")
        print("="*105)

    print_table(results["2026"],    "نتایج ۲۰۲۶ (۱ ژانویه تا الان)")
    print_table(results["history"], "نتایج تاریخی کامل (تأیید بلندمدت)")

    # ── مقایسه بهترین ────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(clr("b","  مقایسه کاندیداها: ۲۰۲۶ در مقابل تاریخی"))
    print(f"  {'─'*70}")
    print(f"  {'استراتژی':<35} {'جفت':<8}  {'۲۰۲۶':>9}  {'تاریخی':>10}")
    print(f"  {'─'*70}")

    strats_26  = {(m["strategy"],m["symbol"]): m for m in results["2026"]}
    strats_his = {(m["strategy"],m["symbol"]): m for m in results["history"]}

    for key in sorted(strats_26.keys(), key=lambda k: -strats_26[k]["total_return_pct"]):
        m26 = strats_26[key]
        mh  = strats_his.get(key)
        r26 = m26["total_return_pct"]
        rh  = mh["total_return_pct"] if mh else 0
        c26 = clr("g",f"{r26:>+8.2f}%") if r26>0 else clr("r",f"{r26:>+8.2f}%")
        ch  = clr("g",f"{rh:>+9.2f}%") if rh>0 else clr("r",f"{rh:>+9.2f}%")
        consistent = clr("g","✓ هر دو سودده") if r26>0 and rh>0 else clr("y","⚠ فقط ۲۰۲۶") if r26>0 else clr("r","✗")
        print(f"  {key[0]:<35} {key[1]:<8}  {c26}   {ch}  {consistent}")

    print(f"\n{'='*72}\n")


if __name__ == "__main__":
    main()
