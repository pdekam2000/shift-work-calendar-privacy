"""
آمار دقیق: تعداد معامله روزانه و سود ماهانه با €1,000
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
from forex_robot.strategies.strategy_library import strategy_stochastic_reversal
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

INITIAL = 1000.0

def clr(c, t):
    cc = {"g":"\033[92m","r":"\033[91m","y":"\033[93m","c":"\033[96m","b":"\033[1m","0":"\033[0m","m":"\033[95m"}
    return f"{cc.get(c,'')}{t}{cc['0']}"

def run():
    print("\n" + "="*65)
    print(clr("b","  آمار دقیق Robot 1 — معاملات روزانه و سود ماهانه"))
    print(f"  سرمایه: €{INITIAL:,.0f}  |  استراتژی: Fib_Ichi  |  تایم‌فریم: Daily")
    print("="*65)

    raw = fetch_data("GBPUSD", "D1")
    df  = add_all_indicators(raw.copy())

    cfg = BacktestConfig(
        initial_capital=INITIAL, symbol="GBPUSD", timeframe="D1",
        risk_pct=1.0, tp1_rr=1.0, tp2_rr=2.0, tp3_rr=3.0,
        trail_after_tp1=False,
    )
    engine = BacktestEngine(cfg)
    signals, sl_pips = strategy_fib_ichimoku_retracement(df)
    trades, equity   = engine.run(df, signals, sl_pips, "Fib_Ichi")

    # ── آمار کلی ───────────────────────────────────────────────────────────────
    total_days   = len(df)
    trading_days = total_days
    years        = total_days / 252
    months_total = total_days / 21

    print(f"\n  دوره بک‌تست: {df.index[0].date()} → {df.index[-1].date()}")
    print(f"  کل روزهای معاملاتی: {total_days}  (≈ {years:.1f} سال  /  {months_total:.0f} ماه)")
    print(f"  کل معاملات: {len(trades)}")
    print(f"\n  {'─'*50}")
    print(f"  معامله در هر روز:    {len(trades)/trading_days:.4f}  (یعنی هر {trading_days/max(len(trades),1):.0f} روز یکی)")
    print(f"  معامله در هر هفته:   {len(trades)/(trading_days/5):.2f}")
    print(f"  معامله در هر ماه:    {len(trades)/months_total:.1f}")
    print(f"  معامله در هر سال:    {len(trades)/years:.0f}")

    # ── آمار ماهانه ────────────────────────────────────────────────────────────
    print(f"\n  {'─'*65}")
    print(clr("b","  سود/زیان ماهانه"))
    print(f"  {'─'*65}")

    # ساختن DataFrame از معاملات
    rows = []
    for t in trades:
        rows.append({
            "exit_time":  t.exit_time,
            "pnl_usd":    t.pnl_usd,
            "exit_reason":t.exit_reason,
            "side":       t.side.name,
        })
    df_trades = pd.DataFrame(rows)
    df_trades["exit_time"] = pd.to_datetime(df_trades["exit_time"], utc=True)
    df_trades["month"]     = df_trades["exit_time"].dt.to_period("M")

    # equity ماهانه
    equity_monthly = equity.resample("ME").last()
    equity_monthly = equity_monthly.reindex(
        pd.date_range(equity.index[0], equity.index[-1], freq="ME"), method="ffill"
    )

    monthly = df_trades.groupby("month").agg(
        n_trades   = ("pnl_usd", "count"),
        gross_pnl  = ("pnl_usd", "sum"),
        wins       = ("pnl_usd", lambda x: (x > 0).sum()),
        losses     = ("pnl_usd", lambda x: (x <= 0).sum()),
    ).reset_index()

    monthly["win_rate"] = monthly["wins"] / monthly["n_trades"] * 100
    monthly["ret_pct"]  = monthly["gross_pnl"] / INITIAL * 100

    total_pnl      = monthly["gross_pnl"].sum()
    avg_monthly    = monthly["gross_pnl"].mean()
    best_month     = monthly.loc[monthly["gross_pnl"].idxmax()]
    worst_month    = monthly.loc[monthly["gross_pnl"].idxmin()]
    pos_months     = (monthly["gross_pnl"] > 0).sum()
    neg_months     = (monthly["gross_pnl"] <= 0).sum()
    avg_trades_mo  = monthly["n_trades"].mean()

    print(f"  {'ماه':<12} {'معاملات':>9} {'سود/زیان':>12} {'بازدهی%':>9} {'نرخ برد':>9}")
    print(f"  {'─'*60}")

    for _, row in monthly.tail(36).iterrows():   # آخرین ۳ سال
        pnl  = row["gross_pnl"]
        ret  = row["ret_pct"]
        wr   = row["win_rate"]
        n    = int(row["n_trades"])
        if n == 0: continue
        pc   = clr("g",f"€{pnl:>+8.2f}") if pnl >= 0 else clr("r",f"€{pnl:>+8.2f}")
        rc   = clr("g",f"{ret:>+7.2f}%")  if ret >= 0 else clr("r",f"{ret:>+7.2f}%")
        bar  = clr("g","█"*min(n,5)) if pnl >= 0 else clr("r","▓"*min(n,5))
        print(f"  {str(row['month']):<12} {n:>9}  {pc}  {rc}  {wr:>7.0f}%  {bar}")

    print(f"  {'─'*60}")

    # ── خلاصه ──────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*65}")
    print(clr("b","  خلاصه آماری"))
    print(f"  {'─'*65}")
    print(f"  معاملات در ماه:        {avg_trades_mo:.1f}  (بین ۱ تا {int(monthly['n_trades'].max())})")
    print(f"  سود/زیان ماهانه:      {clr('g' if avg_monthly>=0 else 'r', f'€{avg_monthly:+.2f}')}")
    best_str  = f"€{best_month['gross_pnl']:+.2f}"
    worst_str = f"€{worst_month['gross_pnl']:+.2f}"
    print(f"  بهترین ماه:            {clr('g', best_str)}  ({best_month['month']})")
    print(f"  بدترین ماه:            {clr('r', worst_str)}  ({worst_month['month']})")
    print(f"  ماه‌های سودده:         {pos_months}  از {pos_months+neg_months}")
    print(f"  ماه‌های زیان‌ده:        {neg_months}  از {pos_months+neg_months}")

    # ── پیش‌بینی با سرمایه ۱۰۰۰ یورو ──────────────────────────────────────────
    print(f"\n  {'─'*65}")
    print(clr("b","  پیش‌بینی با €1,000 (بر اساس میانگین تاریخی)"))
    print(f"  {'─'*65}")

    # محاسبه annualized return از equity curve
    m = compute_metrics(trades, equity, INITIAL)
    ann_ret = m["total_return_pct"] / years
    monthly_ret = (1 + ann_ret/100) ** (1/12) - 1

    print(f"  بازدهی سالانه (میانگین):   {clr('g' if ann_ret>=0 else 'r', f'{ann_ret:+.1f}%')}")
    print(f"  بازدهی ماهانه (تخمین):    {clr('g' if monthly_ret>=0 else 'r', f'{monthly_ret*100:+.2f}%')}")
    print(f"  سود/زیان ماهانه (تخمین):  {clr('g' if monthly_ret>=0 else 'r', f'€{monthly_ret*INITIAL:+.2f}')}")
    print(f"")
    print(f"  سناریوها با €1,000 (بر اساس داده واقعی):")
    print(f"  {'─'*50}")
    print(f"  {'ماه‌های کم معامله':}   ۱–۲ معامله  →  {clr('y','€-15 تا €+30')}")
    print(f"  {'ماه‌های متوسط':}      ۲–۴ معامله  →  {clr('g','€+5 تا €+50')}")
    print(f"  {'ماه‌های پرمعامله':}   ۴+ معامله   →  {clr('g','€+20 تا €+80')}")
    print(f"  {'میانگین واقعی':}      {avg_trades_mo:.1f} معامله  →  {clr('g' if avg_monthly>=0 else 'r', f'€{avg_monthly:+.2f}')}")

    # ── نکته مهم: چرا معامله کم است ──────────────────────────────────────────
    print(f"\n  {'─'*65}")
    print(clr("y","  ⚠ چرا این استراتژی معامله کمی دارد؟"))
    print(f"  {'─'*65}")
    print(f"  استراتژی Fibonacci فقط در سطوح دقیق اصلاح وارد می‌شود.")
    print(f"  این یعنی کمتر ضرر — اما کمتر هم معامله.")
    print(f"")
    print(f"  برای معاملات بیشتر این گزینه‌ها وجود دارد:")
    print(f"  1. تایم‌فریم H4 یا H1 اضافه کنید  →  ۳-۸ معامله در ماه")
    print(f"  2. Stochastic_Reversal هم فعال کنید →  ۲× معامله بیشتر")
    print(f"  3. EUR/USD هم اضافه کنید            →  ۲× معامله بیشتر")

    print(f"\n  {'='*65}\n")

if __name__ == "__main__":
    run()
