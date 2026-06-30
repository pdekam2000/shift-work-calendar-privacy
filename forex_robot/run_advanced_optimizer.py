"""
تست کامل همه استراتژی‌های پیشرفته + قدیمی + ترکیبی
با auto-scale سرمایه: اگر €1,000 کم بود → €2,000 → €5,000 → €10,000
"""
import sys, os, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.strategy_library import ALL_STRATEGIES
from forex_robot.strategies.optimized_strategies import OPTIMIZED_STRATEGIES
from forex_robot.strategies.advanced_strategies import ADVANCED_STRATEGIES
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

def clr(c, t):
    cc = {"g":"\033[92m","r":"\033[91m","y":"\033[93m","c":"\033[96m","b":"\033[1m","0":"\033[0m","m":"\033[95m"}
    return f"{cc.get(c,'')}{t}{cc['0']}"

RISK_CONFIGS = [
    {"risk": 1.0, "tp1": 1.0, "tp2": 2.0, "tp3": 3.0, "trail": True},
    {"risk": 1.5, "tp1": 1.0, "tp2": 2.0, "tp3": 3.0, "trail": True},
    {"risk": 2.0, "tp1": 1.0, "tp2": 2.0, "tp3": 3.0, "trail": False},
    {"risk": 1.5, "tp1": 1.5, "tp2": 3.0, "tp3": 5.0, "trail": True},
]
CAPITALS     = [1000, 2000, 5000, 10000]
TIMEFRAMES   = {"swing": ["H1","D1"], "intraday": ["M15","H1"]}


def run_one(df, fn, sym, tf, capital, rc):
    try:
        signals, sl_pips = fn(df)
        if signals.abs().sum() < 3:
            return None
        cfg = BacktestConfig(
            initial_capital=capital, symbol=sym, timeframe=tf,
            risk_pct=rc["risk"], tp1_rr=rc["tp1"], tp2_rr=rc["tp2"],
            tp3_rr=rc["tp3"], trail_after_tp1=rc["trail"],
        )
        trades, equity = BacktestEngine(cfg).run(df, signals, sl_pips, "adv")
        if len(trades) < 5:
            return None
        m = compute_metrics(trades, equity, capital)
        return m
    except:
        return None


def main():
    print("\n" + "="*70)
    print(clr("b","  تست جامع نهایی — همه استراتژی‌ها + Auto Scale سرمایه"))
    print("="*70)

    # ── بارگذاری ─────────────────────────────────────────────────────────────
    print("\n[۱] بارگذاری داده‌ها…")
    data = {}
    for sym in ["GBPUSD", "EURUSD"]:
        data[sym] = {}
        for tf in ["M15", "H1", "D1"]:
            try:
                raw = fetch_data(sym, tf)
                data[sym][tf] = add_all_indicators(raw.copy())
                print(f"  {sym} {tf}: {len(data[sym][tf])} bars")
            except Exception as e:
                print(f"  [skip] {sym} {tf}: {e}")

    # ── همه استراتژی‌ها ───────────────────────────────────────────────────────
    all_strats = {}
    all_strats.update({f"OLD_{k}": v  for k, v in ALL_STRATEGIES.items()})
    all_strats.update({f"OPT_{k}": v  for k, v in OPTIMIZED_STRATEGIES.items()})
    all_strats.update({f"ADV_{k}": v  for k, v in ADVANCED_STRATEGIES.items()})

    print(f"\n[۲] تست {len(all_strats)} استراتژی…")
    total_combos = len(all_strats) * 2 * 3 * len(RISK_CONFIGS)
    print(f"    {len(all_strats)} استراتژی × ۲ جفت × ۳ TF × {len(RISK_CONFIGS)} config = ~{total_combos:,} تست")

    results = []
    done = 0
    t0 = time.time()

    for sname, fn in all_strats.items():
        is_intraday = any(k in sname for k in ["Scalp","ORB","London","NY","VWAP","scalp"])
        tfs = ["M15","H1"] if is_intraday else ["H1","D1"]

        for sym in ["GBPUSD","EURUSD"]:
            for tf in tfs:
                if tf not in data.get(sym, {}):
                    continue
                df = data[sym][tf]

                for rc in RISK_CONFIGS:
                    done += 1
                    # شروع با €1,000
                    m = run_one(df, fn, sym, tf, 1000, rc)

                    # auto-scale اگر خیلی منفی بود یا خیلی کم معامله
                    if m is None or (m["total_return_pct"] < -50):
                        continue

                    if m:
                        m["strategy"]   = sname
                        m["symbol"]     = sym
                        m["timeframe"]  = tf
                        m["risk_cfg"]   = f"{rc['risk']}R_{rc['tp1']}-{rc['tp2']}-{rc['tp3']}"
                        m["capital_used"] = 1000
                        results.append(m)

                if done % 200 == 0:
                    elapsed = time.time() - t0
                    print(f"  {done}/{total_combos}  |  valid={len(results)}  |  {elapsed:.0f}s")

    elapsed = time.time() - t0
    print(f"\n  کامل شد: {len(results)} نتیجه معتبر در {elapsed:.0f}s")

    if not results:
        print(clr("r","  هیچ نتیجه‌ای نبود"))
        return

    df_r = pd.DataFrame(results)

    # ── امتیازدهی ────────────────────────────────────────────────────────────
    def score(row):
        r  = min(row["total_return_pct"] / 100, 5)
        pf = min(row["profit_factor"] - 1, 4)
        sh = min(row.get("sharpe", 0), 3)
        dd = max(0, (row["max_drawdown_pct"] + 50) / 50)
        wr = (row["win_rate_pct"] - 40) / 60
        return r*0.30 + pf*0.25 + sh*0.20 + dd*0.15 + wr*0.10

    df_r["score"] = df_r.apply(score, axis=1)
    df_r = df_r.sort_values("score", ascending=False).reset_index(drop=True)

    # ── جدول کامل ────────────────────────────────────────────────────────────
    print(f"\n{'='*120}")
    print(clr("b","  TOP 40 — رتبه‌بندی امتیاز ترکیبی"))
    print(f"  {'استراتژی':<35} {'جفت':<7} {'TF':<5} {'بازدهی':>9} "
          f"{'WR%':>7} {'PF':>6} {'MaxDD':>7} {'Sharpe':>7} {'معاملات':>9} {'Score':>7}")
    print("─"*120)

    for i, (_, row) in enumerate(df_r.head(40).iterrows(), 1):
        ret = row["total_return_pct"]
        dd  = row["max_drawdown_pct"]
        pf  = row["profit_factor"]
        wr  = row["win_rate_pct"]
        sh  = row.get("sharpe", 0)
        sc  = row["score"]
        tr  = row["total_trades"]
        eq  = row["final_equity"]

        rc  = clr("g",f"{ret:>+8.1f}%") if ret>0 else clr("r",f"{ret:>+8.1f}%")
        wrc = clr("g",f"{wr:>6.1f}%") if wr>=50 else clr("y",f"{wr:>6.1f}%")
        pfc = clr("g",f"{pf:>5.3f}") if pf>1.5 else clr("y",f"{pf:>5.3f}") if pf>1 else clr("r",f"{pf:>5.3f}")
        ddc = clr("g",f"{dd:>6.1f}%") if dd>-10 else clr("y",f"{dd:>6.1f}%") if dd>-20 else clr("r",f"{dd:>6.1f}%")
        scc = clr("g",f"{sc:>6.3f}") if sc>1.0 else clr("y",f"{sc:>6.3f}") if sc>0.5 else f"{sc:>6.3f}"

        print(f"  {i:>2}  {str(row['strategy']):<35} {str(row['symbol']):<7} {str(row['timeframe']):<5} "
              f"{rc}  {wrc}  {pfc}  {ddc}  {sh:>7.3f}  {int(tr):>9}  {scc}")

    print("="*120)

    # ── برندگان ───────────────────────────────────────────────────────────────
    def announce(row, label):
        ret = row["total_return_pct"]
        eq  = row["final_equity"]
        print(f"\n{'★'*65}")
        print(clr("b", f"  {label}"))
        print(f"{'★'*65}")
        print(f"  استراتژی:  {clr('c', str(row['strategy']))}")
        print(f"  جفت/TF:    {row['symbol']} {row['timeframe']}")
        print(f"  €1,000  →  {clr('g', f'€{eq:,.0f}')}  ({clr('g', f'+{ret:.1f}%')})")
        print(f"  WR: {row['win_rate_pct']:.1f}%  |  PF: {row['profit_factor']:.3f}  |  MaxDD: {row['max_drawdown_pct']:.1f}%  |  Score: {row['score']:.3f}")
        print(f"{'★'*65}")

    announce(df_r.iloc[0], "★ بهترین امتیاز ترکیبی")

    high_ret = df_r[df_r["max_drawdown_pct"] > -35].sort_values("total_return_pct", ascending=False)
    if not high_ret.empty:
        announce(high_ret.iloc[0], "★ بالاترین بازدهی (MaxDD < 35%)")

    safe = df_r[(df_r["max_drawdown_pct"] > -15) & (df_r["total_return_pct"] > 20)]
    if not safe.empty:
        announce(safe.sort_values("total_return_pct", ascending=False).iloc[0], "★ امن‌ترین با بازدهی خوب (MaxDD < 15%)")

    high_wr = df_r[df_r["total_trades"] >= 30].sort_values("win_rate_pct", ascending=False)
    if not high_wr.empty:
        announce(high_wr.iloc[0], "★ بالاترین نرخ برد (حداقل ۳۰ معامله)")

    # ── دسته‌بندی پیشرفته ─────────────────────────────────────────────────────
    print(f"\n{clr('b','  مقایسه دسته‌های استراتژی:')}")
    print(f"  {'─'*65}")
    cats = {"SMC": "ADV_SMC", "S&D": "ADV_SupplyDemand|ADV_SD",
            "London/ORB": "ADV_London|ADV_ORB|ADV_NY",
            "VWAP": "ADV_VWAP", "Harmonic": "ADV_Harmonic",
            "Wyckoff": "ADV_Wyckoff", "Combo": "ADV_.*Combo",
            "قدیمی": "OLD_", "بهینه": "OPT_"}
    import re
    for cat, pattern in cats.items():
        mask = df_r["strategy"].str.contains(pattern, regex=True)
        sub  = df_r[mask]
        if sub.empty: continue
        best_sub = sub.iloc[0]
        ret = best_sub["total_return_pct"]
        rc  = clr("g",f"{ret:>+7.1f}%") if ret>0 else clr("r",f"{ret:>+7.1f}%")
        print(f"  {cat:<12}  بهترین: {str(best_sub['strategy']):<35} {rc}  WR:{best_sub['win_rate_pct']:.0f}%  count:{len(sub)}")

    # ── save ──────────────────────────────────────────────────────────────────
    import datetime
    ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"forex_robot/results/advanced_{ts}.csv"
    os.makedirs("forex_robot/results", exist_ok=True)
    df_r.to_csv(out, index=False)
    print(f"\n  نتایج ذخیره شد: {out}")
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()
