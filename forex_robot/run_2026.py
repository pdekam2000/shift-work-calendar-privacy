"""
بک‌تست سال ۲۰۲۶ — از اول ژانویه تا الان
تست ۳ استراتژی برگزیده روی GBP/USD و EUR/USD
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timezone

from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.optimized_strategies import (
    strategy_sar_ichi_rsi_gate,
)
from forex_robot.strategies.strategy_library import strategy_macd_trend
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

INITIAL = 1000.0
START   = "2026-01-01"

STRATEGIES = {
    "SAR_Ichi_RSI_Gate [تهاجمی 3%]": {
        "fn":        strategy_sar_ichi_rsi_gate,
        "risk_pct":  3.0,
        "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,
        "trail":     True,
    },
    "SAR_Ichi_RSI_Gate [متعادل 1.5%]": {
        "fn":        strategy_sar_ichi_rsi_gate,
        "risk_pct":  1.5,
        "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,
        "trail":     True,
    },
    "MACD_Trend [محافظه‌کار 1%]": {
        "fn":        strategy_macd_trend,
        "risk_pct":  1.0,
        "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,
        "trail":     True,
    },
}

SYMBOLS = ["GBPUSD", "EURUSD"]


def clr(code, text):
    c = {"g":"\033[92m","r":"\033[91m","y":"\033[93m","c":"\033[96m","b":"\033[1m","0":"\033[0m"}
    return f"{c.get(code,'')}{text}{c['0']}"


def run():
    print("\n" + "="*68)
    print(clr("b","  بک‌تست سال ۲۰۲۶  (۱ ژانویه → الان)"))
    print(f"  سرمایه اولیه: €{INITIAL:,.0f}")
    print("="*68)

    # ── بارگذاری داده ─────────────────────────────────────────────────────────
    print("\n[۱] دانلود داده‌های ۲۰۲۶…")
    data = {}
    for sym in SYMBOLS:
        raw = fetch_data(sym, "D1")
        # فیلتر از اول ۲۰۲۶
        start_ts = pd.Timestamp(START, tz="UTC")
        df = raw[raw.index >= start_ts].copy()
        data[sym] = df
        print(f"  {sym}: {len(df)} روز  ({df.index[0].date()} → {df.index[-1].date()})")

    # ── اجرای هر استراتژی ─────────────────────────────────────────────────────
    print("\n[۲] اجرای استراتژی‌ها…\n")
    all_results = []

    for sname, scfg in STRATEGIES.items():
        for sym in SYMBOLS:
            df = add_all_indicators(data[sym].copy())
            fn = scfg["fn"]

            try:
                signals, sl_pips = fn(df)
            except Exception as e:
                print(f"  [خطا] {sname} {sym}: {e}")
                continue

            n_signals = int(signals.abs().sum())
            if n_signals == 0:
                print(f"  {sname} | {sym} → بدون سیگنال در این بازه")
                continue

            cfg = BacktestConfig(
                initial_capital=INITIAL,
                symbol=sym,
                timeframe="D1",
                risk_pct=scfg["risk_pct"],
                tp1_rr=scfg["tp1_rr"],
                tp2_rr=scfg["tp2_rr"],
                tp3_rr=scfg["tp3_rr"],
                trail_after_tp1=scfg["trail"],
            )
            engine  = BacktestEngine(cfg)
            trades, equity = engine.run(df, signals, sl_pips, sname)

            if not trades:
                print(f"  {sname} | {sym} → معامله‌ای انجام نشد")
                continue

            m = compute_metrics(trades, equity, INITIAL)
            m["strategy"] = sname
            m["symbol"]   = sym
            all_results.append((sname, sym, m, trades, equity))

    # ── نمایش جدول ────────────────────────────────────────────────────────────
    print("\n" + "="*100)
    print(clr("b", "  نتایج بک‌تست ۲۰۲۶"))
    print("="*100)
    print(f"  {'استراتژی':<40} {'جفت':<8} {'بازدهی':>9} {'سود/زیان':>10} "
          f"{'نرخ برد':>9} {'P.F':>6} {'MaxDD':>7} {'معاملات':>9} {'سرمایه نهایی':>14}")
    print("─"*100)

    for sname, sym, m, trades, equity in sorted(all_results, key=lambda x: -x[2]["total_return_pct"]):
        ret   = m["total_return_pct"]
        net   = m["net_profit"]
        wr    = m["win_rate_pct"]
        pf    = m["profit_factor"]
        dd    = m["max_drawdown_pct"]
        tr    = m["total_trades"]
        eq    = m["final_equity"]

        ret_c = clr("g", f"{ret:>+8.2f}%") if ret >= 0 else clr("r", f"{ret:>+8.2f}%")
        net_c = clr("g", f"€{net:>+8.2f}") if net >= 0 else clr("r", f"€{net:>+8.2f}")
        dd_c  = clr("g", f"{dd:>6.1f}%") if dd > -10 else clr("y", f"{dd:>6.1f}%") if dd > -20 else clr("r", f"{dd:>6.1f}%")
        pf_c  = clr("g", f"{pf:>5.3f}") if pf > 1.5 else clr("y", f"{pf:>5.3f}") if pf > 1.0 else clr("r", f"{pf:>5.3f}")

        print(f"  {sname:<40} {sym:<8} {ret_c}  {net_c}  "
              f"{wr:>8.1f}%  {pf_c}  {dd_c}  {tr:>8}  €{eq:>12,.2f}")

    print("="*100)

    # ── جزئیات هر معامله برای بهترین استراتژی ─────────────────────────────────
    if all_results:
        best = max(all_results, key=lambda x: x[2]["total_return_pct"])
        sname, sym, m, trades, equity = best

        print(f"\n{clr('b','  جزئیات معاملات: ')} {clr('c', sname)} | {sym}")
        print("─"*95)
        print(f"  {'#':>3}  {'تاریخ ورود':<13} {'جهت':<6} {'قیمت ورود':>11} "
              f"{'قیمت خروج':>11} {'SL':>9} {'TP3':>9} "
              f"{'سود(pip)':>9} {'سود(€)':>9} {'نتیجه':<8}")
        print("─"*95)

        for i, t in enumerate(trades, 1):
            side_c = clr("g","BUY ▲") if t.side.name == "BUY" else clr("r","SELL▼")
            res_c  = clr("g", t.exit_reason) if t.exit_reason in ("TP1","TP2","TP3","TRAIL") else clr("r", t.exit_reason)
            pnl_c  = clr("g", f"€{t.pnl_usd:>+7.2f}") if t.pnl_usd >= 0 else clr("r", f"€{t.pnl_usd:>+7.2f}")
            pip_c  = clr("g", f"{t.pnl_pips:>+8.1f}") if t.pnl_pips >= 0 else clr("r", f"{t.pnl_pips:>+8.1f}")
            print(f"  {i:>3}  {str(t.entry_time.date()):<13} {side_c}  "
                  f"{t.entry_price:>11.5f}  {t.exit_price:>11.5f}  "
                  f"{t.sl_price:>9.5f}  {t.tp3_price:>9.5f}  "
                  f"{pip_c}  {pnl_c}  {res_c}")

        print("─"*95)

        # خلاصه
        wins   = [t for t in trades if t.pnl_usd > 0]
        losses = [t for t in trades if t.pnl_usd <= 0]
        print(f"\n  خلاصه {sname} | {sym}:")
        print(f"  معاملات سودده:  {len(wins)}  |  معاملات زیان‌ده: {len(losses)}")
        print(f"  میانگین سود:   €{np.mean([t.pnl_usd for t in wins]):.2f}" if wins else "")
        print(f"  میانگین زیان:  €{np.mean([t.pnl_usd for t in losses]):.2f}" if losses else "")
        exit_br = m.get("exit_breakdown", {})
        print(f"  نحوه خروج‌ها:  " + "  |  ".join(f"{k}:{v}" for k,v in sorted(exit_br.items())))

        # منحنی سرمایه ماهانه
        print(f"\n  منحنی سرمایه ماهانه ۲۰۲۶:")
        monthly = equity.resample("ME").last()
        prev = INITIAL
        for dt, eq_val in monthly.items():
            chg = eq_val - prev
            bar = "█" * int(abs(chg) / max(abs(INITIAL*0.01), 1))
            bar = clr("g", bar) if chg >= 0 else clr("r", bar)
            chg_c = clr("g", f"+€{chg:,.2f}") if chg >= 0 else clr("r", f"-€{abs(chg):,.2f}")
            print(f"    {dt.strftime('%b %Y')}:  €{eq_val:>8,.2f}  {chg_c}  {bar}")
            prev = eq_val

    print(f"\n{'='*68}")
    print(clr("b","  بک‌تست ۲۰۲۶ تمام شد"))
    print(f"{'='*68}\n")


if __name__ == "__main__":
    run()
