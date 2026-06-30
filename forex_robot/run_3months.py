"""
بک‌تست ۳ ماه اخیر — قوی‌ترین استراتژی‌ها با €5,000
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.advanced_strategies import strategy_smc_fvg, strategy_smc_full, strategy_mega_combo
from forex_robot.strategies.optimized_strategies import (
    strategy_sar_ichi_rsi_gate, strategy_fib_ichimoku_retracement,
    strategy_mega_trend, strategy_adx_breakout_rider,
)
from forex_robot.strategies.strategy_library import strategy_macd_trend, strategy_ichimoku
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

CAPITAL = 5000.0
START   = "2026-04-01"

def clr(c, t):
    cc = {"g":"\033[92m","r":"\033[91m","y":"\033[93m","c":"\033[96m","b":"\033[1m","0":"\033[0m","m":"\033[95m"}
    return f"{cc.get(c,'')}{t}{cc['0']}"

STRATEGIES = [
    ("SMC_FVG",              strategy_smc_fvg,                  1.5, 1.0, 2.0, 3.0, True),
    ("SMC_Full",             strategy_smc_full,                 1.5, 1.0, 2.0, 3.0, True),
    ("SAR_Ichi_RSI [1.5%]",  strategy_sar_ichi_rsi_gate,        1.5, 1.0, 2.0, 3.0, True),
    ("SAR_Ichi_RSI [3%]",    strategy_sar_ichi_rsi_gate,        3.0, 1.0, 2.0, 3.0, True),
    ("Fib_Ichi",             strategy_fib_ichimoku_retracement, 1.0, 1.0, 2.0, 3.0, False),
    ("MACD_Trend",           strategy_macd_trend,               1.0, 1.0, 2.0, 3.0, True),
    ("Ichimoku",             strategy_ichimoku,                 1.5, 1.0, 2.0, 3.0, True),
    ("MegaTrend_5F",         strategy_mega_trend,               2.0, 1.0, 2.0, 3.0, True),
    ("ADX_Breakout",         strategy_adx_breakout_rider,       1.5, 1.0, 2.0, 3.0, True),
    ("Mega_Combo",           strategy_mega_combo,               1.5, 1.0, 2.0, 3.0, True),
]


def run():
    print("\n" + "="*72)
    print(clr("b", f"  بک‌تست ۳ ماه اخیر  ({START} → ۳۰ ژوئن ۲۰۲۶)"))
    print(f"  سرمایه اولیه: {clr('c', f'€{CAPITAL:,.0f}')}")
    print("="*72)

    start_ts = pd.Timestamp(START, tz="UTC")
    raw_gbp  = fetch_data("GBPUSD", "D1")
    raw_eur  = fetch_data("EURUSD", "D1")
    gbp = raw_gbp[raw_gbp.index >= start_ts].copy()
    eur = raw_eur[raw_eur.index >= start_ts].copy()

    print(f"\n  GBP/USD: {len(gbp)} روز  ({gbp.index[0].date()} → {gbp.index[-1].date()})")
    print(f"  EUR/USD: {len(eur)} روز  ({eur.index[0].date()} → {eur.index[-1].date()})\n")

    results = []
    best_trades_data = {}

    for name, fn, rp, t1, t2, t3, trail in STRATEGIES:
        for sym, raw in [("GBPUSD", gbp), ("EURUSD", eur)]:
            try:
                df  = add_all_indicators(raw.copy())
                sig, sl_pips = fn(df)

                cfg = BacktestConfig(
                    initial_capital=CAPITAL, symbol=sym, timeframe="D1",
                    risk_pct=rp, tp1_rr=t1, tp2_rr=t2, tp3_rr=t3,
                    trail_after_tp1=trail,
                )
                trades, equity = BacktestEngine(cfg).run(df, sig, sl_pips, name)

                if not trades:
                    results.append({"strategy": name, "symbol": sym,
                        "n": 0, "pnl": 0.0, "ret": 0.0, "wr": 0.0,
                        "pf": 0.0, "dd": 0.0, "eq": CAPITAL})
                    continue

                m = compute_metrics(trades, equity, CAPITAL)
                key = f"{name}|{sym}"
                results.append({
                    "strategy": name, "symbol": sym,
                    "n":   m["total_trades"],
                    "pnl": m["net_profit"],
                    "ret": m["total_return_pct"],
                    "wr":  m["win_rate_pct"],
                    "pf":  m["profit_factor"],
                    "dd":  m["max_drawdown_pct"],
                    "eq":  m["final_equity"],
                })
                best_trades_data[key] = (trades, equity)
            except Exception as e:
                results.append({"strategy": name, "symbol": sym,
                    "n": 0, "pnl": 0.0, "ret": 0.0, "wr": 0.0,
                    "pf": 0.0, "dd": 0.0, "eq": CAPITAL})

    df_r = pd.DataFrame(results).sort_values("ret", ascending=False).reset_index(drop=True)

    # ── جدول اصلی ──────────────────────────────────────────────────────────────
    print(f"{'='*100}")
    print(clr("b", "  نتایج همه استراتژی‌ها — ۳ ماه اخیر"))
    print(f"  {'استراتژی':<26} {'جفت':<8} {'معاملات':>9} {'سود/زیان':>13} "
          f"{'بازدهی':>9} {'WR%':>7} {'PF':>6} {'MaxDD':>7} {'سرمایه نهایی':>15}")
    print("─"*100)

    for _, r in df_r.iterrows():
        n   = int(r["n"])
        pnl = r["pnl"]; ret = r["ret"]
        wr  = r["wr"];  pf  = r["pf"]
        dd  = r["dd"];  eq  = r["eq"]

        if n == 0:
            print(f"  {r['strategy']:<26} {r['symbol']:<8} {'—':>9}  {'بدون معامله':>13}  {'—':>9}  {'—':>7}  {'—':>6}  {'—':>7}  €{CAPITAL:>12,.2f}")
            continue

        pc  = clr("g", f"€{pnl:>+11.2f}") if pnl >= 0 else clr("r", f"€{pnl:>+11.2f}")
        rc  = clr("g", f"{ret:>+8.2f}%")  if ret >= 0 else clr("r", f"{ret:>+8.2f}%")
        wrc = clr("g", f"{wr:>6.1f}%") if wr >= 50 else clr("y", f"{wr:>6.1f}%") if wr >= 35 else clr("r", f"{wr:>6.1f}%")
        pfc = clr("g", f"{pf:>5.3f}") if pf > 1.5 else clr("y", f"{pf:>5.3f}") if pf > 1.0 else clr("r", f"{pf:>5.3f}")
        ddc = clr("g", f"{dd:>6.1f}%") if dd > -8 else clr("y", f"{dd:>6.1f}%") if dd > -15 else clr("r", f"{dd:>6.1f}%")
        eqc = clr("g", f"€{eq:>12,.2f}") if eq >= CAPITAL else clr("r", f"€{eq:>12,.2f}")
        print(f"  {r['strategy']:<26} {r['symbol']:<8} {n:>9}  {pc}  {rc}  {wrc}  {pfc}  {ddc}  {eqc}")

    print("="*100)

    # ── آمار کلی ───────────────────────────────────────────────────────────────
    with_trades = df_r[df_r["n"] > 0]
    winners  = with_trades[with_trades["ret"] > 0]
    losers   = with_trades[with_trades["ret"] < 0]
    no_trade = df_r[df_r["n"] == 0]

    print(f"\n  کل ترکیب‌های تست‌شده: {len(df_r)}")
    print(f"  {clr('g', f'سودده: {len(winners)}')}  |  {clr('r', f'زیان‌ده: {len(losers)}')}  |  {clr('y', f'بی‌معامله: {len(no_trade)}')}")

    # ── بهترین ─────────────────────────────────────────────────────────────────
    if not winners.empty:
        best = winners.iloc[0]
        key = f"{best['strategy']}|{best['symbol']}"

        print(f"\n{'★'*65}")
        print(clr("b", "  ★ بهترین استراتژی در ۳ ماه اخیر"))
        print(f"{'★'*65}")
        print(f"  استراتژی:     {clr('c', str(best['strategy']))}")
        print(f"  جفت ارز:      {clr('y', str(best['symbol']))}")
        print(f"  تعداد معامله: {int(best['n'])}")
        final_eq_str = f"€{best['eq']:,.2f}"
        pnl_str = f"€{best['pnl']:+,.2f}"
        ret_str = f"+{best['ret']:.2f}%"
        print(f"\n  سرمایه اول:   €{CAPITAL:,.2f}")
        print(f"  سرمایه آخر:   {clr('g', final_eq_str)}")
        print(f"  سود خالص:     {clr('g', pnl_str)}")
        print(f"  بازدهی:       {clr('g', ret_str)}")
        print(f"  نرخ برد:      {best['wr']:.1f}%")
        print(f"  Profit Factor:{best['pf']:.3f}")
        print(f"  Max Drawdown: {best['dd']:.1f}%")
        print(f"{'★'*65}")

        # جزئیات معاملات
        if key in best_trades_data:
            trades, equity = best_trades_data[key]
            print(f"\n  جزئیات هر معامله:")
            print(f"  {'─'*70}")
            print(f"  {'#':>3}  {'تاریخ ورود':>12}  {'تاریخ خروج':>12}  {'جهت':<5}  "
                  f"{'ورود':>9}  {'خروج':>9}  {'سود(€)':>10}  {'نتیجه'}")
            print(f"  {'─'*70}")

            running_eq = CAPITAL
            for i, t in enumerate(trades, 1):
                running_eq += t.pnl_usd
                side_s = clr("g", "BUY") if t.side.name == "BUY" else clr("r", "SEL")
                res_s  = clr("g", t.exit_reason) if t.exit_reason in ("TP1","TP2","TP3","TRAIL") else clr("r", t.exit_reason)
                pnl_s  = clr("g", f"€{t.pnl_usd:>+9.2f}") if t.pnl_usd >= 0 else clr("r", f"€{t.pnl_usd:>+9.2f}")
                print(f"  {i:>3}  {str(t.entry_time.date()):>12}  {str(t.exit_time.date()):>12}  {side_s}   "
                      f"{t.entry_price:>9.5f}  {t.exit_price:>9.5f}  {pnl_s}  {res_s}  "
                      f"(موجودی:€{running_eq:,.0f})")

            print(f"  {'─'*70}")

            # خلاصه ماهانه
            print(f"\n  خلاصه ماهانه:")
            print(f"  {'─'*45}")
            month_data = {}
            for t in trades:
                mo = pd.to_datetime(t.exit_time, utc=True).strftime("%Y-%m")
                if mo not in month_data:
                    month_data[mo] = {"pnl": 0, "n": 0, "wins": 0}
                month_data[mo]["pnl"]  += t.pnl_usd
                month_data[mo]["n"]    += 1
                if t.pnl_usd > 0:
                    month_data[mo]["wins"] += 1

            for mo, md in sorted(month_data.items()):
                wr_mo = md["wins"] / md["n"] * 100 if md["n"] > 0 else 0
                bar   = "█" * min(md["n"], 10)
                pnl_c = clr("g", f"€{md['pnl']:>+8.2f}") if md["pnl"] >= 0 else clr("r", f"€{md['pnl']:>+8.2f}")
                bar_c = clr("g", bar) if md["pnl"] >= 0 else clr("r", bar)
                print(f"  {mo}:  {md['n']:>3} معامله  {pnl_c}  WR:{wr_mo:.0f}%  {bar_c}")

    # ── نتیجه نهایی ─────────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(clr("b", "  خلاصه نهایی ۳ ماه با €5,000"))
    print(f"{'='*72}")

    top5 = df_r[df_r["n"] > 0].head(5)
    for _, r in top5.iterrows():
        ret = r["ret"]; eq = r["eq"]
        rc  = clr("g", f"{ret:>+7.2f}%") if ret >= 0 else clr("r", f"{ret:>+7.2f}%")
        eqc = clr("g", f"€{eq:>8,.0f}") if eq >= CAPITAL else clr("r", f"€{eq:>8,.0f}")
        print(f"  {r['strategy']:<26} {r['symbol']:<8}  {rc}   {eqc}  ({int(r['n'])} معامله)")

    print(f"\n{'='*72}\n")


if __name__ == "__main__":
    run()
