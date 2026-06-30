"""
تحلیل بازار ۲۰۲۶ — چرا استراتژی‌ها در این سال کمتر کار می‌کنند؟
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.optimized_strategies import (
    strategy_sar_ichi_rsi_gate,
    strategy_mega_trend,
    strategy_sar_ichi_adx25,
    strategy_adx_breakout_rider,
    strategy_volatility_breakout_ichi,
    strategy_fib_ichimoku_retracement,
    OPTIMIZED_STRATEGIES,
)
from forex_robot.strategies.strategy_library import (
    strategy_macd_trend, strategy_ichimoku,
    strategy_bollinger_reversal, strategy_rsi_oversold,
    strategy_stochastic_reversal, strategy_cci_reversal,
    ALL_STRATEGIES,
)
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

INITIAL = 1000.0
START   = "2026-01-01"

def clr(c, t):
    cc = {"g":"\033[92m","r":"\033[91m","y":"\033[93m","c":"\033[96m","b":"\033[1m","0":"\033[0m","m":"\033[95m"}
    return f"{cc.get(c,'')}{t}{cc['0']}"


def analyze_market_2026(df_full, df_2026):
    """مقایسه شرایط بازار ۲۰۲۶ با میانگین تاریخی"""
    hist = add_all_indicators(df_full.copy())
    cur  = add_all_indicators(df_2026.copy())

    print(f"\n  {'شاخص':<22} {'میانگین تاریخی':>18} {'۲۰۲۶ فعلی':>14} {'وضعیت'}")
    print(f"  {'─'*70}")

    adx_hist = hist["adx"].mean()
    adx_cur  = cur["adx"].mean()
    adx_icon = clr("r","⚠ بازار ضعیف‌تر") if adx_cur < adx_hist else clr("g","✓ بازار قوی‌تر")
    print(f"  {'میانگین ADX':<22} {adx_hist:>18.1f} {adx_cur:>14.1f}  {adx_icon}")

    pct_trend_hist = (hist["adx"] > 25).mean() * 100
    pct_trend_cur  = (cur["adx"] > 25).mean() * 100
    t_icon = clr("r","⚠ کمتر روند‌دار") if pct_trend_cur < pct_trend_hist else clr("g","✓ روند‌دارتر")
    print(f"  {'% روزهای ADX>25':<22} {pct_trend_hist:>17.1f}% {pct_trend_cur:>13.1f}%  {t_icon}")

    bb_hist = hist["bb_width"].mean()
    bb_cur  = cur["bb_width"].mean()
    v_icon  = clr("r","⚠ نوسان کمتر") if bb_cur < bb_hist else clr("g","✓ نوسان بیشتر")
    print(f"  {'میانگین BB Width':<22} {bb_hist:>18.4f} {bb_cur:>14.4f}  {v_icon}")

    atr_hist = hist["atr14"].mean()
    atr_cur  = cur["atr14"].mean()
    a_icon   = clr("r","⚠ رنج کمتر") if atr_cur < atr_hist else clr("g","✓ رنج بزرگتر")
    print(f"  {'میانگین ATR14':<22} {atr_hist:>18.5f} {atr_cur:>14.5f}  {a_icon}")

    return {
        "adx_cur": adx_cur, "adx_hist": adx_hist,
        "pct_trend_cur": pct_trend_cur, "pct_trend_hist": pct_trend_hist,
        "bb_cur": bb_cur, "bb_hist": bb_hist,
    }


def run_strategy(df, fn, risk_pct, tp1, tp2, tp3, trail, sym):
    df_ind = add_all_indicators(df.copy())
    signals, sl_pips = fn(df_ind)
    if signals.abs().sum() < 1:
        return None, None, None
    cfg = BacktestConfig(
        initial_capital=INITIAL, symbol=sym, timeframe="D1",
        risk_pct=risk_pct, tp1_rr=tp1, tp2_rr=tp2, tp3_rr=tp3,
        trail_after_tp1=trail,
    )
    engine = BacktestEngine(cfg)
    trades, equity = engine.run(df_ind, signals, sl_pips, fn.__name__)
    if not trades:
        return None, None, None
    m = compute_metrics(trades, equity, INITIAL)
    return trades, equity, m


def main():
    print("\n" + "="*72)
    print(clr("b","  تحلیل کامل بازار ۲۰۲۶ — چرا و راه‌حل"))
    print("="*72)

    # بارگذاری داده
    raw_gbp  = fetch_data("GBPUSD", "D1")
    raw_eur  = fetch_data("EURUSD", "D1")
    start_ts = pd.Timestamp(START, tz="UTC")
    gbp_2026 = raw_gbp[raw_gbp.index >= start_ts].copy()
    eur_2026 = raw_eur[raw_eur.index >= start_ts].copy()

    print(f"\n  داده: {len(gbp_2026)} روز معاملاتی "
          f"({gbp_2026.index[0].date()} → {gbp_2026.index[-1].date()})")

    # ── تحلیل شرایط بازار ────────────────────────────────────────────────────
    print(f"\n{clr('b','  [آنالیز] مقایسه شرایط بازار')}")
    print(f"  {'─'*70}")
    print("  GBP/USD:")
    stats_gbp = analyze_market_2026(raw_gbp, gbp_2026)
    print("  EUR/USD:")
    stats_eur = analyze_market_2026(raw_eur, eur_2026)

    # ── تست همه استراتژی‌ها روی ۲۰۲۶ ─────────────────────────────────────────
    print(f"\n{clr('b','  [تست] تمام استراتژی‌ها روی ۲۰۲۶')}")

    # استراتژی‌های اضافی برای بازار رنج
    extra = {
        "Bollinger_Reversal":  strategy_bollinger_reversal,
        "RSI_Oversold":        strategy_rsi_oversold,
        "Stochastic_Reversal": strategy_stochastic_reversal,
        "CCI_Reversal":        strategy_cci_reversal,
    }

    test_strategies = {
        # ۳ استراتژی اصلی
        "SAR_Ichi_RSI_Gate [تهاجمی]":  (strategy_sar_ichi_rsi_gate,  3.0, 1,2,3, True),
        "SAR_Ichi_RSI_Gate [متعادل]":  (strategy_sar_ichi_rsi_gate,  1.5, 1,2,3, True),
        "MACD_Trend [محافظه‌کار]":      (strategy_macd_trend,         1.0, 1,2,3, True),
        # استراتژی‌های بهینه‌شده
        "SAR_Ichi_ADX25":               (strategy_sar_ichi_adx25,     1.5, 1,2,3, True),
        "ADX_Breakout_Rider":           (strategy_adx_breakout_rider, 1.5, 1,2,3, True),
        "Volatility_Breakout_Ichi":     (strategy_volatility_breakout_ichi, 1.5, 1,2,3, True),
        "Fib_Ichimoku_Retrace":         (strategy_fib_ichimoku_retracement, 1.5, 1,2,3, True),
        # استراتژی‌های مناسب رنج
        "Bollinger_Reversal":           (strategy_bollinger_reversal, 1.0, 1,1.5,2, False),
        "RSI_Oversold_OB":              (strategy_rsi_oversold,       1.0, 1,1.5,2, False),
        "Stochastic_Reversal":          (strategy_stochastic_reversal,1.0, 1,1.5,2, False),
        "Ichimoku [پایه]":              (strategy_ichimoku,           1.5, 1,2,3, True),
    }

    results_2026 = []
    for sym, df_2026 in [("GBPUSD", gbp_2026), ("EURUSD", eur_2026)]:
        for sname, (fn, rp, t1, t2, t3, tr) in test_strategies.items():
            try:
                trades, equity, m = run_strategy(df_2026, fn, rp, t1, t2, t3, tr, sym)
                if m is None:
                    continue
                m["strategy"] = sname
                m["symbol"]   = sym
                results_2026.append(m)
            except Exception as e:
                pass

    # جدول نتایج
    print(f"\n  {'استراتژی':<38} {'جفت':<8} {'بازدهی':>9} {'نرخ برد':>9} "
          f"{'P.F':>6} {'MaxDD':>7} {'معاملات':>9} {'سرمایه':>10}")
    print("─"*100)

    sorted_r = sorted(results_2026, key=lambda x: -x["total_return_pct"])
    for m in sorted_r:
        ret = m["total_return_pct"]
        wr  = m["win_rate_pct"]
        pf  = m["profit_factor"]
        dd  = m["max_drawdown_pct"]
        tr  = m["total_trades"]
        eq  = m["final_equity"]
        rc  = clr("g",f"{ret:>+8.2f}%") if ret>0 else clr("r",f"{ret:>+8.2f}%")
        dc  = clr("g",f"{dd:>6.1f}%") if dd>-10 else clr("y",f"{dd:>6.1f}%") if dd>-20 else clr("r",f"{dd:>6.1f}%")
        pfc = clr("g",f"{pf:>5.3f}") if pf>1.5 else clr("y",f"{pf:>5.3f}") if pf>1.0 else clr("r",f"{pf:>5.3f}")
        print(f"  {m['strategy']:<38} {m['symbol']:<8} {rc}  {wr:>8.1f}%  {pfc}  {dc}  {tr:>8}  €{eq:>8,.2f}")

    print("─"*100)

    # ── خلاصه و توضیح ─────────────────────────────────────────────────────────
    print(f"\n{clr('b','  [تشخیص] دلیل عملکرد ضعیف‌تر در ۲۰۲۶')}")
    print(f"  {'─'*65}")
    adx_2026 = stats_gbp["adx_cur"]
    adx_hist = stats_gbp["adx_hist"]
    pct_2026 = stats_gbp["pct_trend_cur"]
    pct_hist = stats_gbp["pct_trend_hist"]

    if adx_2026 < adx_hist:
        print(f"  {clr('r','⚠')} بازار ۲۰۲۶ ضعیف‌تر از میانگین تاریخی است:")
        print(f"     ADX میانگین ۱۱ سال: {adx_hist:.1f}")
        print(f"     ADX سال ۲۰۲۶:       {adx_2026:.1f}  ({clr('r','کمتر = رنج بیشتر')})")
        print(f"     روزهای با روند قوی (ADX>25): تاریخی {pct_hist:.0f}%  ←  ۲۰۲۶: {pct_2026:.0f}%")
        print(f"\n  {clr('y','→')} استراتژی‌های ترند‌فالوینگ در بازار رنج ضرر می‌دهند")
        print(f"  {clr('y','→')} استراتژی‌های مین‌ریورژن (Bollinger/RSI/Stoch) در این بازار بهترند")

    # بهترین برای ۲۰۲۶
    best_2026 = [m for m in sorted_r if m["total_return_pct"] > 0]
    if best_2026:
        b = best_2026[0]
        print(f"\n  {clr('g','★')} بهترین برای بازار ۲۰۲۶:")
        print(f"     استراتژی:  {clr('c', b['strategy'])}  |  {b['symbol']}")
        ret_str = f"+{b['total_return_pct']:.2f}%"
        print(f"     بازدهی:    {clr('g', ret_str)}")
        print(f"     نرخ برد:   {b['win_rate_pct']:.1f}%")
        print(f"     MaxDD:     {b['max_drawdown_pct']:.1f}%")

    print(f"\n{'='*72}\n")


if __name__ == "__main__":
    main()
