"""
Loss Pattern Analyzer for SAR+Ichimoku
Finds exactly WHEN and WHY the strategy loses — market conditions during SL hits.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.strategy_library import strategy_sar_ichimoku
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig


def analyze():
    print("\n" + "="*65)
    print("  SAR+ICHIMOKU LOSS PATTERN ANALYSIS")
    print("="*65)

    df = fetch_data("GBPUSD", "D1")
    df = add_all_indicators(df)

    cfg = BacktestConfig(
        initial_capital=1000.0, symbol="GBPUSD", timeframe="D1",
        risk_pct=2.0, tp1_rr=1.0, tp2_rr=2.0, tp3_rr=3.0,
        trail_after_tp1=False,
    )
    signals, sl_pips = strategy_sar_ichimoku(df)
    engine = BacktestEngine(cfg)
    trades, equity = engine.run(df, signals, sl_pips, "SAR_Ichimoku")

    print(f"\n  Total trades: {len(trades)}")
    sl_trades  = [t for t in trades if t.exit_reason == "SL"]
    tp_trades  = [t for t in trades if t.exit_reason in ("TP1","TP2","TP3","TRAIL")]
    print(f"  SL hits:      {len(sl_trades)} ({len(sl_trades)/len(trades)*100:.1f}%)")
    print(f"  TP hits:      {len(tp_trades)} ({len(tp_trades)/len(trades)*100:.1f}%)")

    # ── Find market conditions at entry of SL trades ──────────────────────────
    loss_conditions = []
    win_conditions  = []

    for t in trades:
        try:
            idx = df.index.get_indexer([t.entry_time], method="nearest")[0]
            if idx < 0 or idx >= len(df): continue
            row = df.iloc[idx]
            cond = {
                "adx":       float(row.get("adx", 0)),
                "rsi14":     float(row.get("rsi14", 50)),
                "bb_pct":    float(row.get("bb_pct", 0.5)),
                "macd_hist": float(row.get("macd_hist", 0)),
                "atr14":     float(row.get("atr14", 0)),
                "bb_width":  float(row.get("bb_width", 0)),
                "trend_up":  int(row.get("trend_up", 0)),
                "above_200": int(row.get("above_200", 0)),
                "side":      t.side.name,
                "result":    t.exit_reason,
            }
        except Exception:
            continue

        if t.exit_reason == "SL":
            loss_conditions.append(cond)
        else:
            win_conditions.append(cond)

    def avg(lst, key):
        vals = [x[key] for x in lst if not np.isnan(x[key])]
        return np.mean(vals) if vals else 0

    print(f"\n  CONDITION COMPARISON (losses vs wins):")
    print(f"  {'Condition':<18}  {'Losses':>10}  {'Wins':>10}  {'Insight'}")
    print(f"  {'─'*65}")

    for key in ["adx", "rsi14", "bb_pct", "bb_width", "macd_hist"]:
        lv = avg(loss_conditions, key)
        wv = avg(win_conditions, key)
        diff = lv - wv
        insight = ""
        if key == "adx":
            insight = "⚠ trades in WEAK trend cause losses" if lv < wv else "OK"
        elif key == "rsi14":
            insight = "⚠ RSI too extreme at entry" if abs(lv - 50) > abs(wv - 50) else "OK"
        elif key == "bb_width":
            insight = "⚠ losses in RANGING market (narrow BB)" if lv < wv else "OK"
        elif key == "macd_hist":
            insight = "⚠ MACD diverges at loss entries" if abs(diff) > 0.0001 else "OK"
        print(f"  {key:<18}  {lv:>10.3f}  {wv:>10.3f}   {insight}")

    # ADX distribution at losses
    sl_adx = [c["adx"] for c in loss_conditions]
    print(f"\n  ADX at SL hits:")
    for threshold in [15, 20, 25, 30]:
        pct = sum(1 for x in sl_adx if x < threshold) / len(sl_adx) * 100
        print(f"    ADX < {threshold}: {pct:.1f}% of losses  ← filter these out!")

    # Consecutive loss runs
    results_seq = [1 if t.exit_reason != "SL" else 0 for t in trades]
    max_loss_run = 0
    cur_run = 0
    runs = []
    for r in results_seq:
        if r == 0:
            cur_run += 1
            max_loss_run = max(max_loss_run, cur_run)
        else:
            if cur_run > 0: runs.append(cur_run)
            cur_run = 0
    if cur_run: runs.append(cur_run)

    print(f"\n  CONSECUTIVE LOSS ANALYSIS:")
    print(f"    Max consecutive losses:  {max_loss_run}")
    print(f"    Runs of 3+ losses:       {sum(1 for r in runs if r >= 3)}")
    print(f"    Runs of 5+ losses:       {sum(1 for r in runs if r >= 5)}")
    print(f"    Runs of 10+ losses:      {sum(1 for r in runs if r >= 10)}")

    # Market condition during long loss runs
    print(f"\n  KEY FINDINGS:")
    print(f"  ─────────────────────────────────────────────────────")
    avg_sl_adx = np.mean(sl_adx)
    avg_win_adx = np.mean([c["adx"] for c in win_conditions])
    print(f"  1. Losses happen when ADX={avg_sl_adx:.1f} (wins at ADX={avg_win_adx:.1f})")
    print(f"     → Adding ADX > 20 filter will remove many bad trades")

    sl_bb = np.mean([c["bb_width"] for c in loss_conditions])
    win_bb = np.mean([c["bb_width"] for c in win_conditions])
    if sl_bb < win_bb:
        print(f"  2. Losses in narrow BB (ranging): {sl_bb:.4f} vs wins {win_bb:.4f}")
        print(f"     → Bollinger Width filter will skip ranging markets")

    sl_macd = np.mean([c["macd_hist"] for c in loss_conditions])
    win_macd = np.mean([c["macd_hist"] for c in win_conditions])
    print(f"  3. MACD histogram: losses={sl_macd:.5f}, wins={win_macd:.5f}")
    print(f"     → MACD alignment filter can improve quality")

    return {
        "avg_sl_adx": avg_sl_adx,
        "avg_win_adx": avg_win_adx,
        "sl_bb_width": sl_bb,
        "win_bb_width": win_bb,
        "max_consec_loss": max_loss_run,
    }


if __name__ == "__main__":
    analyze()
