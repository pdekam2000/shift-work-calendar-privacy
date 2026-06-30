"""
Focused Optimizer — tests all optimized strategies with extended risk configs.
Goal: Return > 500%, MaxDD < 25%, Win Rate > 40%.
"""
import sys, os, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.optimized_strategies import OPTIMIZED_STRATEGIES
from forex_robot.strategies.strategy_library import ALL_STRATEGIES
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics
from forex_robot.reports.reporter import print_summary_table, print_strategy_detail, save_results

INITIAL_CAPITAL = 1000.0

# Extended risk configs with higher tp ratios to boost returns
RISK_CONFIGS = [
    {"risk_pct": 1.5, "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,  "trail": True,  "label": "1.5R_1-2-3_T"},
    {"risk_pct": 2.0, "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,  "trail": True,  "label": "2R_1-2-3_T"},
    {"risk_pct": 2.0, "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,  "trail": False, "label": "2R_1-2-3_NT"},
    {"risk_pct": 2.5, "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 4.0,  "trail": True,  "label": "2.5R_1-2-4_T"},
    {"risk_pct": 2.0, "tp1_rr": 1.5, "tp2_rr": 3.0, "tp3_rr": 5.0,  "trail": True,  "label": "2R_1.5-3-5_T"},
    {"risk_pct": 3.0, "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,  "trail": True,  "label": "3R_1-2-3_T"},
    {"risk_pct": 1.5, "tp1_rr": 0.5, "tp2_rr": 1.5, "tp3_rr": 3.0,  "trail": True,  "label": "1.5R_0.5-1.5-3_T"},
    {"risk_pct": 2.0, "tp1_rr": 2.0, "tp2_rr": 3.0, "tp3_rr": 5.0,  "trail": False, "label": "2R_2-3-5_NT"},
]

TF_MAP = {
    "PowerScalp_M15": ["M15", "M30"],
    "default_swing":  ["H1", "D1"],
    "default_trend":  ["D1"],
}


def get_tfs(name):
    if "Scalp" in name or "scalp" in name:
        return ["M15", "M30"]
    return ["H1", "D1"]


def run_focused_backtest(data, strategies, verbose=True):
    all_results = []
    total = sum(
        len(get_tfs(sn)) * len([sym for sym in data if any(tf in data[sym] for tf in get_tfs(sn))]) * len(RISK_CONFIGS)
        for sn in strategies
    )

    if verbose:
        print(f"\n{'='*65}")
        print(f"  FOCUSED OPTIMIZER — {len(strategies)} Optimized Strategies")
        print(f"  Target: Return>500%, MaxDD<25%, WinRate>40%")
        print(f"  Estimated combinations: ~{total}")
        print(f"{'='*65}\n")

    done = 0
    t0 = time.time()

    for sname, fn in strategies.items():
        tfs = get_tfs(sname)
        for sym in data:
            for tf in tfs:
                if tf not in data.get(sym, {}): continue
                raw_df = data[sym][tf]
                if len(raw_df) < 200: continue
                try:
                    df = add_all_indicators(raw_df.copy())
                except Exception as e:
                    continue

                for rc in RISK_CONFIGS:
                    done += 1
                    try:
                        signals, sl_pips = fn(df)
                        if signals.abs().sum() < 5: continue

                        cfg = BacktestConfig(
                            initial_capital=INITIAL_CAPITAL,
                            symbol=sym, timeframe=tf,
                            risk_pct=rc["risk_pct"],
                            tp1_rr=rc["tp1_rr"], tp2_rr=rc["tp2_rr"], tp3_rr=rc["tp3_rr"],
                            trail_after_tp1=rc["trail"],
                        )
                        engine = BacktestEngine(cfg)
                        trades, equity = engine.run(df, signals, sl_pips, sname)
                        if len(trades) < 5: continue

                        m = compute_metrics(trades, equity, INITIAL_CAPITAL)
                        m.update({
                            "strategy": sname, "symbol": sym, "timeframe": tf,
                            "risk_config": rc["label"],
                            "combo_id": f"{sname}|{sym}|{tf}|{rc['label']}",
                        })
                        all_results.append(m)
                    except Exception:
                        pass

    if verbose:
        print(f"\n  Done in {time.time()-t0:.1f}s — {len(all_results)} valid combos\n")

    if not all_results:
        return pd.DataFrame()
    df_r = pd.DataFrame(all_results)
    return df_r.sort_values("total_return_pct", ascending=False).reset_index(drop=True)


def composite_score(row):
    r  = min(row.get("total_return_pct", 0) / 200, 5.0)
    pf = min(row.get("profit_factor", 1) - 1, 4.0)
    sh = min(row.get("sharpe", 0), 3.0)
    dd = max(0, (row.get("max_drawdown_pct", -50) + 50) / 50)
    wr = (row.get("win_rate_pct", 50) - 40) / 60
    tr = min(row.get("total_trades", 0) / 100, 1.0)
    return r*0.30 + pf*0.25 + sh*0.20 + dd*0.15 + wr*0.07 + tr*0.03


def print_comparison_table(df: pd.DataFrame):
    """Show before/after comparison with base SAR+Ichimoku."""
    print(f"\n{'='*130}")
    print("  OPTIMIZED STRATEGIES — FULL RESULTS")
    print(f"  {'Strategy':<32} {'Sym':<7} {'TF':<5} {'Config':<20} "
          f"{'Return':>8} {'WR%':>6} {'PF':>6} {'MaxDD':>7} "
          f"{'Sharpe':>7} {'Trades':>7} {'Equity':>9} {'Score':>7}")
    print("-" * 130)

    df_disp = df.head(40)
    for i, (_, row) in enumerate(df_disp.iterrows(), 1):
        ret = float(row.get("total_return_pct", 0))
        dd  = float(row.get("max_drawdown_pct", 0))
        pf  = float(row.get("profit_factor", 0))
        wr  = float(row.get("win_rate_pct", 0))
        eq  = float(row.get("final_equity", 1000))
        sh  = float(row.get("sharpe", 0))
        tr  = int(row.get("total_trades", 0))
        sc  = float(row.get("score", 0))

        ret_c = "\033[92m" if ret > 0   else "\033[91m"
        dd_c  = "\033[92m" if dd > -15  else "\033[93m" if dd > -25 else "\033[91m"
        pf_c  = "\033[92m" if pf > 1.5  else "\033[93m" if pf > 1.0 else "\033[91m"
        R = "\033[0m"

        print(f"  {i:>2}  {str(row['strategy']):<32} "
              f"{str(row['symbol']):<7} {str(row['timeframe']):<5} "
              f"{str(row['risk_config']):<20} "
              f"{ret_c}{ret:>+8.1f}%{R} "
              f"{wr:>6.1f}% "
              f"{pf_c}{pf:>6.3f}{R} "
              f"{dd_c}{dd:>7.1f}%{R} "
              f"{sh:>7.3f} {tr:>7} "
              f"{'€'+str(int(eq)):>9} "
              f"{sc:>7.3f}")

    print("=" * 130)


def print_winner(row, label="BEST"):
    ret = float(row.get("total_return_pct", 0))
    dd  = float(row.get("max_drawdown_pct", 0))
    eq  = float(row.get("final_equity", 1000))
    wr  = float(row.get("win_rate_pct", 0))
    pf  = float(row.get("profit_factor", 0))
    sh  = float(row.get("sharpe", 0))
    tr  = int(row.get("total_trades", 0))

    print(f"\n{'★'*60}")
    print(f"\033[1m\033[96m  {label}\033[0m")
    print(f"{'★'*60}")
    print(f"  Strategy:    \033[96m{row['strategy']}\033[0m")
    print(f"  Symbol:      \033[93m{row['symbol']}\033[0m")
    print(f"  Timeframe:   {row['timeframe']}")
    print(f"  RiskConfig:  {row['risk_config']}")
    print(f"\n  €1,000  →  \033[92m€{eq:,.0f}\033[0m  (\033[92m{ret:+.1f}%\033[0m)")
    print(f"  Max Drawdown:  \033[{'91' if dd < -25 else '93' if dd < -15 else '92'}m{dd:.1f}%\033[0m")
    print(f"  Win Rate:      {wr:.1f}%")
    print(f"  Profit Factor: {pf:.3f}")
    print(f"  Sharpe:        {sh:.3f}")
    print(f"  Total Trades:  {tr}")
    print(f"{'★'*60}\n")


def main():
    print("\n" + "="*65)
    print("  FOREX ROBOT — OPTIMIZED STRATEGY SEARCH")
    print("  Looking for: High Return + Low Drawdown")
    print("="*65)

    # Load data
    print("\n[1/4] Loading data…")
    data = {}
    for sym in ["EURUSD", "GBPUSD"]:
        data[sym] = {}
        for tf in ["M15", "M30", "H1", "D1"]:
            try:
                data[sym][tf] = fetch_data(sym, tf)
            except Exception as e:
                print(f"  [skip] {sym} {tf}: {e}")

    # Merge all strategies
    print("\n[2/4] Merging base + optimized strategies…")
    all_strats = {**OPTIMIZED_STRATEGIES}
    # Add top base strategies too for comparison
    for k in ["SAR_Ichimoku", "MACD_Trend", "Ichimoku", "Fibonacci_Retracement",
              "Confluence_Master", "Wave_Correction", "EMA_Crossover_21_55"]:
        if k in ALL_STRATEGIES:
            all_strats[f"BASE_{k}"] = ALL_STRATEGIES[k]

    print(f"  Total strategies to test: {len(all_strats)}")

    # Run optimizer
    print("\n[3/4] Running optimized backtests…")
    results = run_focused_backtest(data, all_strats)

    if results.empty:
        print("  No results — check data download")
        return

    # Score
    results["score"] = results.apply(composite_score, axis=1)
    results = results.sort_values("score", ascending=False).reset_index(drop=True)

    # Print full table
    print_comparison_table(results)

    # Best by composite score
    best_score = results.iloc[0].to_dict()
    print_winner(best_score, "★ BEST COMPOSITE SCORE (Return + Low Risk)")

    # Best by raw return (with some DD tolerance)
    high_ret = results[results["max_drawdown_pct"] > -40].sort_values("total_return_pct", ascending=False)
    if not high_ret.empty:
        print_winner(high_ret.iloc[0].to_dict(), "★ HIGHEST RETURN (MaxDD < 40%)")

    # Best win rate
    best_wr = results[results["total_trades"] >= 20].sort_values("win_rate_pct", ascending=False)
    if not best_wr.empty:
        print_winner(best_wr.iloc[0].to_dict(), "★ HIGHEST WIN RATE")

    # Safe strategy: MaxDD < 20%
    safe = results[(results["max_drawdown_pct"] > -20) &
                   (results["total_return_pct"] > 50) &
                   (results["total_trades"] >= 15)]
    if not safe.empty:
        print_winner(safe.sort_values("total_return_pct", ascending=False).iloc[0].to_dict(),
                     "★ SAFEST HIGH-RETURN (MaxDD < 20%)")

    # Category summary
    print("\n  BEST PER STRATEGY CATEGORY:")
    print(f"  {'─'*80}")
    best_per = (results.sort_values("score", ascending=False)
                .drop_duplicates(subset=["strategy"])
                .head(15)
                .reset_index(drop=True))
    for _, row in best_per.iterrows():
        ret = float(row["total_return_pct"])
        dd  = float(row["max_drawdown_pct"])
        rc  = "\033[92m" if ret > 200 else "\033[93m" if ret > 50 else "\033[91m"
        dc  = "\033[92m" if dd > -15 else "\033[93m" if dd > -25 else "\033[91m"
        R   = "\033[0m"
        print(f"  {str(row['strategy']):<35} {str(row['symbol']):<7} {str(row['timeframe']):<5}  "
              f"{rc}{ret:>+8.1f}%{R}  DD:{dc}{dd:>6.1f}%{R}  "
              f"WR:{float(row['win_rate_pct']):.0f}%  Score:{float(row['score']):.3f}")

    # Save
    save_results(results, filename_prefix="optimized")

    print(f"\n{'='*65}")
    print("  OPTIMIZATION COMPLETE")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
