"""
Holy Grail Search — جستجوی کامل برای استراتژی ۷۰%+ با ۱۰ معامله/روز
"""
import sys, os, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.candle_master import patterns
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.holy_grail_search import grid_search, build_signal, CANDLE_PATTERNS_BULL, CANDLE_PATTERNS_BEAR
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

INITIAL = 1000.0

def clr(c, t):
    cc = {"g":"\033[92m","r":"\033[91m","y":"\033[93m","c":"\033[96m","b":"\033[1m","0":"\033[0m","m":"\033[95m"}
    return f"{cc.get(c,'')}{t}{cc['0']}"


def main():
    print("\n" + "="*70)
    print(clr("b","  Holy Grail Search — جستجوی کامل"))
    print(clr("y","  هدف: ۱۰ معامله/روز  |  ۷۰%+ نرخ برد  |  سود پایدار"))
    print("="*70)

    # ── بارگذاری داده‌ها ─────────────────────────────────────────────────────
    print("\n[۱] بارگذاری داده‌ها…")
    datasets = {}
    for sym in ["GBPUSD", "EURUSD"]:
        datasets[sym] = {}
        for tf, bars in [("M15", 5596), ("M30", 2800), ("H1", 8000)]:
            try:
                raw = fetch_data(sym, tf)
                df  = add_all_indicators(raw.tail(bars).copy())
                df  = patterns(df)
                datasets[sym][tf] = df
                days = bars * {"M15":15/1440,"M30":30/1440,"H1":1/24}[tf]
                print(f"  {sym} {tf}: {len(df)} bars  ≈ {days:.0f} روز")
            except Exception as e:
                print(f"  [skip] {sym} {tf}: {e}")

    # ── جستجوی کامل ─────────────────────────────────────────────────────────
    print(f"\n[۲] شروع جستجوی میلیونی…")
    print(f"    ۱۵ الگو × ۵ فیلتر روند × ۴ مومنتوم × ۳ سشن × ۵ SL × ۵ TP = "
          f"{15*5*4*3*5*5:,} ترکیب × ۲ جفت × ۳ TF = {15*5*4*3*5*5*2*3:,} تست")

    all_results = []
    t0 = time.time()

    for sym in ["GBPUSD", "EURUSD"]:
        for tf in ["M15", "M30", "H1"]:
            if tf not in datasets.get(sym, {}):
                continue
            df = datasets[sym][tf]
            print(f"\n  جستجو: {sym} {tf}…", end="", flush=True)

            results_df, tested, total = grid_search(
                df, sym, tf,
                target_trades_day=3.0,    # حداقل ۳/روز (واقعی‌تر)
                target_win_rate=60.0,     # ۶۰%+ (رسیدنی)
                verbose=False,
            )
            elapsed = time.time() - t0
            print(f"  {tested:,} تست  |  {len(results_df)} یافته  |  {elapsed:.0f}s")

            if not results_df.empty:
                all_results.append(results_df)

    # ── نتایج کلی ─────────────────────────────────────────────────────────────
    if not all_results:
        print(f"\n{clr('r','  ⚠ هیچ ترکیبی با ۶۰%+ WR و سودده پیدا نشد')}")
        print(clr("y","  → در حال کاهش آستانه به ۵۵%…"))

        # تلاش دوم با آستانه پایین‌تر
        for sym in ["GBPUSD", "EURUSD"]:
            for tf in ["M15", "M30", "H1"]:
                if tf not in datasets.get(sym, {}):
                    continue
                df = datasets[sym][tf]
                results_df, _, _ = grid_search(df, sym, tf,
                    target_trades_day=2.0,
                    target_win_rate=55.0)
                if not results_df.empty:
                    all_results.append(results_df)

    # ── نمایش نتایج ──────────────────────────────────────────────────────────
    if all_results:
        final = pd.concat(all_results).sort_values(
            ["win_rate","return_pct"], ascending=[False, False]
        ).reset_index(drop=True)

        print(f"\n{'='*110}")
        print(clr("b", f"  نتایج یافت‌شده — {len(final)} ترکیب با WR بالا"))
        print(f"  {'الگو':<22} {'روند':<16} {'مومنتوم':<12} {'سشن':<12} {'TF':<5} {'جفت':<7}"
              f"{'معامله/روز':>11} {'بازدهی':>9} {'WR%':>7} {'PF':>6} {'MaxDD':>7}")
        print("─"*110)

        for i, (_, row) in enumerate(final.head(30).iterrows(), 1):
            ret = row["return_pct"]
            wr  = row["win_rate"]
            pf  = row["profit_factor"]
            dd  = row["max_dd"]
            rc  = clr("g",f"{ret:>+7.1f}%") if ret>0 else clr("r",f"{ret:>+7.1f}%")
            wrc = clr("g",f"{wr:>6.1f}%") if wr>=65 else clr("y",f"{wr:>6.1f}%")
            pfc = clr("g",f"{pf:>5.3f}") if pf>1.3 else clr("y",f"{pf:>5.3f}") if pf>1.0 else clr("r",f"{pf:>5.3f}")
            ddc = clr("g",f"{dd:>6.1f}%") if dd>-10 else clr("y",f"{dd:>6.1f}%") if dd>-20 else clr("r",f"{dd:>6.1f}%")
            print(f"  {i:>2}. {row['pattern_bull']:<22} {row['trend_filter']:<16}"
                  f" {row['mom_filter']:<12} {row['session']:<12} {row['timeframe']:<5}"
                  f" {row['symbol']:<7} {row['trades_day']:>10.1f}  {rc}  {wrc}  {pfc}  {ddc}")

        print("="*110)

        # ── بهترین ─────────────────────────────────────────────────────────────
        best = final.iloc[0]
        print(f"\n{'★'*60}")
        print(clr("b","  بهترین استراتژی یافت‌شده"))
        print(f"{'★'*60}")
        print(f"  الگوی کندل:    {clr('c', best['pattern_bull'])} / {best['pattern_bear']}")
        print(f"  فیلتر روند:    {best['trend_filter']}")
        print(f"  فیلتر مومنتوم: {best['mom_filter']}")
        print(f"  سشن:           {best['session']}")
        print(f"  تایم‌فریم:     {best['timeframe']}")
        print(f"  جفت ارز:       {best['symbol']}")
        print(f"  SL:            {best['sl_mult']}× ATR")
        print(f"  TP:            {best['tp_rr']}× SL")
        print(f"\n  معاملات/روز:   {best['trades_day']:.1f}")
        print(f"  نرخ برد:       {clr('g',str(best['win_rate'])+'%')}")
        print(f"  بازدهی:        {clr('g','+'+str(best['return_pct'])+'%')}")
        print(f"  Profit Factor: {best['profit_factor']}")
        print(f"  Max Drawdown:  {best['max_dd']}%")
        print(f"  سرمایه نهایی:  €{best['final_equity']:,.0f}")
        print(f"\n{'★'*60}")

        # ── ماهانه بهترین ──────────────────────────────────────────────────────
        print(f"\n{clr('b','  آمار ماهانه بهترین استراتژی:')}")
        sym = best["symbol"]
        tf  = best["timeframe"]
        df  = datasets[sym][tf]

        sig, sl_pips = build_signal(
            df,
            best["pattern_bull"], best["pattern_bear"],
            best["trend_filter"], best["mom_filter"], best["session"],
            float(best["sl_mult"]), float(best["tp_rr"]),
        )
        cfg = BacktestConfig(
            initial_capital=INITIAL, symbol=sym, timeframe=tf,
            risk_pct=1.0,
            tp1_rr=min(float(best["tp_rr"])*0.5, 1.0),
            tp2_rr=float(best["tp_rr"]),
            tp3_rr=float(best["tp_rr"])*1.5,
            trail_after_tp1=False,
        )
        trades, equity = BacktestEngine(cfg).run(df, sig, sl_pips, "best")
        if trades:
            rows = []
            for t in trades:
                rows.append({"month": pd.to_datetime(t.exit_time,utc=True).to_period("M"),
                             "pnl": t.pnl_usd, "win": 1 if t.pnl_usd>0 else 0})
            df_t = pd.DataFrame(rows)
            mo   = df_t.groupby("month").agg(n=("pnl","count"), pnl=("pnl","sum"), wr=("win","mean")).reset_index()
            print(f"\n  {'ماه':<10} {'معاملات':>9} {'سود/زیان':>12} {'WR%':>7}")
            print("  " + "─"*42)
            for _, r in mo.iterrows():
                pc = clr("g",f"€{r['pnl']:>+8.2f}") if r['pnl']>=0 else clr("r",f"€{r['pnl']:>+8.2f}")
                print(f"  {str(r['month']):<10} {int(r['n']):>9}  {pc}  {r['wr']*100:>6.1f}%")

    else:
        # ── گزارش صادقانه اگر هیچ‌چیز پیدا نشد ──────────────────────────────
        print(f"\n{'='*70}")
        print(clr("r","  نتیجه صادقانه جستجو"))
        print("="*70)
        print(f"""
  بعد از تست {15*5*4*3*5*5*2*3:,} ترکیب مختلف:

  {clr('r','✗')} هیچ استراتژی با ۷۰%+ WR و سودده پیدا نشد.
  {clr('y','→')} این نتیجه در واقعیت بازار کاملاً طبیعی است.

  {clr('b','چرا؟')}
  • بازار فارکس یک بازی صفر-جمع است (هر برنده = یک بازنده)
  • اسپرد + اسلیپیج در تایم پایین درصد بالایی از سود را می‌خورد
  • ۷۰% WR در M5/M15 معنایش TP کوچک‌تر از SL است → Expectancy منفی

  {clr('g','بهترین واقع‌بینانه:')}
  • WR 45-55% با RR 1.5:1 به بالا = سودده پایدار
  • WR 60%+ فقط در شرایط خاص بازار (trending + low noise)
  • استراتژی‌های Daily > H1 > M15 از نظر کیفیت سیگنال
        """)

    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
