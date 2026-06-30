"""
FOREX ROBOT — Full Automatic Strategy Optimizer & Backtester
============================================================
Currency Pairs: EUR/USD  and  GBP/USD
Capital:        €1,000 initial
Features:
  • 28 strategies tested automatically
  • Multiple timeframes: M5, M15, M30, H1, D1
  • Stop Loss + Triple Take Profit (TP1/TP2/TP3)
  • Smart trailing stop after TP1
  • Fibonacci retracement & corrective patterns
  • Scalping strategies (M5/M15)
  • Comprehensive performance metrics
  • Detailed final report

Usage:
    python -m forex_robot.main
    python -m forex_robot.main --quick      # fast test on fewer combos
    python -m forex_robot.main --refresh    # force re-download data
"""

import sys
import os
import time
import argparse
import warnings
import traceback
warnings.filterwarnings("ignore")

# ── Make sure package root is importable ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from forex_robot.data.fetcher import fetch_all, SYMBOLS, TIMEFRAMES
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.strategy_library import ALL_STRATEGIES, SCALPING_STRATEGIES
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics
from forex_robot.reports.reporter import (
    print_summary_table, print_strategy_detail,
    save_results, print_winner_announcement
)

INITIAL_CAPITAL = 1000.0


# ── Inline single-process optimizer (avoids multiprocessing spawn issues) ─────

def run_all_backtests(data: dict, strategies: dict, verbose: bool = True) -> pd.DataFrame:
    """
    Run all strategy × symbol × timeframe × risk_config combinations
    sequentially (single process, avoids pickle issues in notebooks/scripts).
    """
    from forex_robot.backtest.optimizer import RISK_CONFIGS, _get_timeframes_for_strategy

    all_results = []
    total_tried = 0
    total_valid = 0
    start_t = time.time()

    strategy_names = list(strategies.keys())
    symbols = list(data.keys())

    total_combos = 0
    for sname in strategy_names:
        tfs = _get_timeframes_for_strategy(sname)
        for sym in symbols:
            for tf in tfs:
                if tf in data.get(sym, {}):
                    total_combos += len(RISK_CONFIGS)

    if verbose:
        print(f"\n{'='*65}")
        print(f"  STRATEGY OPTIMIZER")
        print(f"  Testing {total_combos:,} combinations…")
        print(f"  Strategies: {len(strategy_names)} | Symbols: {len(symbols)}")
        print(f"{'='*65}")

    for sname, strategy_fn in strategies.items():
        tfs = _get_timeframes_for_strategy(sname)
        for sym in symbols:
            for tf in tfs:
                if tf not in data.get(sym, {}):
                    continue
                raw_df = data[sym][tf]
                if len(raw_df) < 150:
                    continue
                try:
                    df = add_all_indicators(raw_df.copy())
                except Exception:
                    continue

                for risk_cfg in RISK_CONFIGS:
                    total_tried += 1
                    try:
                        signals, sl_pips = strategy_fn(df)

                        if signals.abs().sum() < 5:
                            continue

                        cfg = BacktestConfig(
                            initial_capital=INITIAL_CAPITAL,
                            symbol=sym,
                            timeframe=tf,
                            risk_pct=risk_cfg["risk_pct"],
                            tp1_rr=risk_cfg["tp1_rr"],
                            tp2_rr=risk_cfg["tp2_rr"],
                            tp3_rr=risk_cfg["tp3_rr"],
                            trail_after_tp1=risk_cfg["trail_after_tp1"],
                        )
                        engine = BacktestEngine(cfg)
                        trades, equity = engine.run(df, signals, sl_pips, sname)

                        if len(trades) < 8:
                            continue

                        metrics = compute_metrics(trades, equity, INITIAL_CAPITAL)
                        if metrics.get("total_return_pct", -999) < -80:
                            continue

                        metrics["strategy"] = sname
                        metrics["symbol"] = sym
                        metrics["timeframe"] = tf
                        metrics["risk_config"] = risk_cfg["label"]
                        metrics["combo_id"] = f"{sname}|{sym}|{tf}|{risk_cfg['label']}"
                        all_results.append(metrics)
                        total_valid += 1

                    except Exception as e:
                        pass

                if verbose and total_tried % 50 == 0:
                    elapsed = time.time() - start_t
                    pct = total_tried / max(total_combos, 1) * 100
                    print(f"  [{pct:5.1f}%] {total_tried}/{total_combos}  "
                          f"valid={total_valid}  elapsed={elapsed:.0f}s")

    elapsed = time.time() - start_t
    if verbose:
        print(f"\n  COMPLETE: {total_valid}/{total_tried} valid combinations in {elapsed:.1f}s")

    if not all_results:
        return pd.DataFrame()
    df_r = pd.DataFrame(all_results)
    df_r = df_r.sort_values("total_return_pct", ascending=False).reset_index(drop=True)
    return df_r


def score_results(df: pd.DataFrame) -> pd.DataFrame:
    """Composite score ranking."""
    if df.empty:
        return df
    df = df.copy()
    filtered = df[
        (df["total_trades"] >= 10) &
        (df["profit_factor"] > 1.0) &
        (df["total_return_pct"] > 0) &
        (df["max_drawdown_pct"] > -40)
    ].copy()
    if filtered.empty:
        filtered = df[df["total_return_pct"] > 0].copy()
    if filtered.empty:
        return df

    def score(row):
        r = min(row.get("total_return_pct", 0) / 100, 5.0)
        pf = min(row.get("profit_factor", 1) - 1, 3.0)
        sh = min(row.get("sharpe", 0), 3.0)
        dd = max(0, (row.get("max_drawdown_pct", -50) + 50) / 50)
        wr = (row.get("win_rate_pct", 50) - 50) / 50
        return r * 0.3 + pf * 0.25 + sh * 0.2 + dd * 0.15 + wr * 0.1

    filtered["score"] = filtered.apply(score, axis=1)
    return filtered.sort_values("score", ascending=False).reset_index(drop=True)


def run_deep_analysis_on_winner(data: dict, best_row: dict):
    """Re-run the best strategy and print full trade-level detail."""
    from forex_robot.backtest.optimizer import RISK_CONFIGS, _get_timeframes_for_strategy

    sname = best_row["strategy"]
    sym = best_row["symbol"]
    tf = best_row["timeframe"]
    risk_label = best_row["risk_config"]

    risk_cfg = next((r for r in RISK_CONFIGS if r["label"] == risk_label), RISK_CONFIGS[0])

    if tf not in data.get(sym, {}):
        print(f"  [warn] Data not available for {sym} {tf}")
        return None, None

    df = add_all_indicators(data[sym][tf].copy())
    strategy_fn = ALL_STRATEGIES[sname]
    signals, sl_pips = strategy_fn(df)

    cfg = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        symbol=sym,
        timeframe=tf,
        risk_pct=risk_cfg["risk_pct"],
        tp1_rr=risk_cfg["tp1_rr"],
        tp2_rr=risk_cfg["tp2_rr"],
        tp3_rr=risk_cfg["tp3_rr"],
        trail_after_tp1=risk_cfg["trail_after_tp1"],
    )
    engine = BacktestEngine(cfg)
    trades, equity = engine.run(df, signals, sl_pips, sname)
    return trades, equity


# ── Main entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Forex Robot Strategy Backtester")
    parser.add_argument("--quick",   action="store_true", help="Test fewer strategies for speed")
    parser.add_argument("--refresh", action="store_true", help="Force re-download market data")
    parser.add_argument("--scalp",   action="store_true", help="Only test scalping strategies")
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("  FOREX ROBOT — Full Automatic Strategy Optimizer")
    print("  Currency Pairs: EUR/USD | GBP/USD")
    print(f"  Initial Capital: €{INITIAL_CAPITAL:,.0f}")
    print("=" * 65 + "\n")

    # ── 1. Download data ──────────────────────────────────────────────────────
    print("[1/4] Downloading market data…")
    if args.quick:
        tfs = ["M15", "H1", "D1"]
    else:
        tfs = ["M5", "M15", "M30", "H1", "D1"]

    data = {}
    for sym in ["EURUSD", "GBPUSD"]:
        data[sym] = {}
        for tf in tfs:
            try:
                from forex_robot.data.fetcher import fetch_data
                data[sym][tf] = fetch_data(sym, tf, force_refresh=args.refresh)
            except Exception as e:
                print(f"  [skip] {sym} {tf}: {e}")

    # ── 2. Select strategies ──────────────────────────────────────────────────
    print("\n[2/4] Preparing strategies…")
    if args.scalp:
        strategies = SCALPING_STRATEGIES
        print(f"  Scalping mode: {len(strategies)} strategies")
    elif args.quick:
        # representative subset
        quick_keys = [
            "EMA_Crossover_21_55", "Triple_EMA", "MACD_Trend", "Supertrend",
            "Ichimoku", "Bollinger_Reversal", "RSI_Oversold_OB", "Stochastic_Reversal",
            "Fibonacci_Retracement", "Wave_Correction", "Scalp_EMA_Ribbon",
            "Scalp_BB_Squeeze", "Confluence_Master", "Fib_EMA_Confluence",
            "RSI_MACD_EMA_Combo", "SAR_Ichimoku",
        ]
        strategies = {k: ALL_STRATEGIES[k] for k in quick_keys if k in ALL_STRATEGIES}
        print(f"  Quick mode: {len(strategies)} strategies")
    else:
        strategies = ALL_STRATEGIES
        print(f"  Full mode: {len(strategies)} strategies")

    # ── 3. Run optimizer ──────────────────────────────────────────────────────
    print("\n[3/4] Running backtests…")
    results_df = run_all_backtests(data, strategies, verbose=True)

    if results_df.empty:
        print("\n  [!] No valid results found. Try --refresh to re-download data.")
        return

    scored_df = score_results(results_df)

    # ── 4. Show results ───────────────────────────────────────────────────────
    print("\n[4/4] Generating reports…\n")

    print_summary_table(scored_df, top_n=30)

    # Best strategy deep-dive
    if not scored_df.empty:
        best = scored_df.iloc[0].to_dict()
        print_winner_announcement(best, INITIAL_CAPITAL)

        print("  Running detailed analysis on winning strategy…")
        trades, equity = run_deep_analysis_on_winner(data, best)
        if trades and equity is not None:
            print_strategy_detail(
                trades, equity,
                strategy_name=best["strategy"],
                symbol=best["symbol"],
                timeframe=best["timeframe"],
                initial_capital=INITIAL_CAPITAL
            )

        # Save outputs
        save_results(scored_df, {"best": trades} if trades else None)

    # Summary by strategy category
    print("\n  CATEGORY SUMMARY (best per strategy)")
    print(f"  {'─'*60}")
    if not scored_df.empty:
        best_per_strategy = (
            scored_df.sort_values("total_return_pct", ascending=False)
            .drop_duplicates(subset=["strategy"])
            .head(10)
            .reset_index(drop=True)
        )
        for _, row in best_per_strategy.iterrows():
            ret = float(row["total_return_pct"])
            clr = "\033[92m" if ret > 0 else "\033[91m"
            rst = "\033[0m"
            print(f"  {str(row['strategy']):<32}  {str(row['symbol']):<8} {str(row['timeframe']):<5}  "
                  f"{clr}{ret:+7.1f}%{rst}  WR:{float(row['win_rate_pct']):.0f}%  "
                  f"PF:{float(row['profit_factor']):.2f}  "
                  f"Trades:{int(row['total_trades'])}")

    print(f"\n{'='*65}")
    print("  FOREX ROBOT — BACKTEST COMPLETE")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
