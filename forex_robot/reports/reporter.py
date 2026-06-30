"""
Report Generator — creates detailed terminal reports and saves results to JSON/CSV.
"""

from __future__ import annotations
import os
import json
import datetime
import pandas as pd
import numpy as np
from typing import List, Dict, Optional

from forex_robot.backtest.engine import TradeResult, compute_metrics

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def _clr(code: str, text: str) -> str:
    codes = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
             "cyan": "\033[96m", "bold": "\033[1m", "reset": "\033[0m",
             "blue": "\033[94m", "magenta": "\033[95m"}
    return f"{codes.get(code, '')}{text}{codes['reset']}"


def print_summary_table(results_df: pd.DataFrame, top_n: int = 30):
    """Print a formatted table of top strategy results."""
    if results_df.empty:
        print(_clr("red", "  No results to display."))
        return

    display = results_df.head(top_n)
    cols = ["strategy", "symbol", "timeframe", "risk_config",
            "total_return_pct", "win_rate_pct", "profit_factor",
            "max_drawdown_pct", "sharpe", "total_trades", "final_equity"]

    cols = [c for c in cols if c in display.columns]
    df_show = display[cols].copy()

    header = f"\n{'='*120}\n"
    header += _clr("bold", f"  TOP {top_n} STRATEGY RESULTS (ranked by composite score)\n")
    header += f"{'='*120}\n"
    print(header)

    # Column headers
    print(f"{'#':>3}  {'Strategy':<28} {'Symbol':<8} {'TF':<5} {'Config':<22} "
          f"{'Return%':>8} {'WinRate%':>9} {'PF':>6} {'MaxDD%':>7} "
          f"{'Sharpe':>7} {'Trades':>7} {'Equity€':>9}")
    print("-" * 120)

    for i, (_, row) in enumerate(df_show.iterrows(), 1):
        ret = row.get("total_return_pct", 0)
        ret_str = _clr("green" if ret > 0 else "red", f"{ret:+.1f}%")
        dd = row.get("max_drawdown_pct", 0)
        dd_str = _clr("yellow" if dd > -10 else "red", f"{dd:.1f}%")
        pf = row.get("profit_factor", 0)
        pf_str = _clr("green" if pf > 1.5 else "yellow" if pf > 1.0 else "red", f"{pf:.3f}")

        print(f"{i:>3}  {str(row.get('strategy','')):<28} "
              f"{str(row.get('symbol','')):<8} "
              f"{str(row.get('timeframe','')):<5} "
              f"{str(row.get('risk_config','')):<22} "
              f"{ret_str:>15} "
              f"{row.get('win_rate_pct', 0):>9.1f}% "
              f"{pf_str:>13} "
              f"{dd_str:>14} "
              f"{row.get('sharpe', 0):>7.3f} "
              f"{int(row.get('total_trades', 0)):>7} "
              f"{'€'+str(int(row.get('final_equity', 0))):>9}")

    print("=" * 120)


def print_strategy_detail(trades: List[TradeResult], equity: pd.Series,
                          strategy_name: str, symbol: str, timeframe: str,
                          initial_capital: float = 1000.0):
    """Print detailed breakdown for a single strategy."""
    metrics = compute_metrics(trades, equity, initial_capital)

    print(f"\n{'='*70}")
    print(_clr("bold", f"  DETAILED REPORT: {strategy_name}"))
    print(f"  Symbol: {symbol} | Timeframe: {timeframe}")
    print(f"  Period: {trades[0].entry_time.date() if trades else 'N/A'} → "
          f"{trades[-1].exit_time.date() if trades else 'N/A'}")
    print(f"{'='*70}")

    print(f"\n  {'PERFORMANCE METRICS':^50}")
    print(f"  {'─'*50}")
    ret = metrics.get("total_return_pct", 0)
    print(f"  Initial Capital:   €{initial_capital:>10,.2f}")
    print(f"  Final Equity:      €{metrics.get('final_equity', 0):>10,.2f}  "
          + _clr("green" if ret > 0 else "red", f"({ret:+.2f}%)"))
    net = metrics.get('net_profit', 0)
    print(f"  Net Profit:        €{net:>+10,.2f}  (from equity curve)")
    print(f"  Wins P&L:          €{metrics.get('gross_profit', 0):>10,.2f}")
    print(f"  Losses P&L:        €{metrics.get('gross_loss', 0):>10,.2f}")
    print()
    print(f"  Total Trades:      {metrics.get('total_trades', 0):>12}")
    print(f"  Win Rate:          {metrics.get('win_rate_pct', 0):>11.2f}%")
    print(f"  Profit Factor:     {metrics.get('profit_factor', 0):>12.3f}")
    print(f"  Expectancy:        €{metrics.get('expectancy_usd', 0):>+10.2f} per trade")
    print(f"  Avg Win:           €{metrics.get('avg_win_usd', 0):>+10.2f}")
    print(f"  Avg Loss:          €{metrics.get('avg_loss_usd', 0):>+10.2f}")
    print()
    print(f"  Max Drawdown:      {metrics.get('max_drawdown_pct', 0):>11.2f}%")
    print(f"  Sharpe Ratio:      {metrics.get('sharpe', 0):>12.3f}")
    print(f"  Sortino Ratio:     {metrics.get('sortino', 0):>12.3f}")
    print(f"  Max Consec. Wins:  {metrics.get('max_consec_wins', 0):>12}")
    print(f"  Max Consec. Loss:  {metrics.get('max_consec_losses', 0):>12}")
    print()

    # Exit breakdown
    exits = metrics.get("exit_breakdown", {})
    print(f"  EXIT BREAKDOWN:")
    total_t = metrics.get("total_trades", 1)
    for reason, count in sorted(exits.items(), key=lambda x: -x[1]):
        bar = "█" * int(count / total_t * 30)
        pct = count / total_t * 100
        color = "green" if reason in ("TP1", "TP2", "TP3", "TRAIL") else "red"
        print(f"    {reason:<8} {count:>5} ({pct:4.1f}%)  {_clr(color, bar)}")

    print(f"{'='*70}\n")


def save_results(results_df: pd.DataFrame, top_trades_dict: Optional[Dict] = None,
                 filename_prefix: str = "backtest"):
    """Save results to CSV and JSON."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = os.path.join(RESULTS_DIR, f"{filename_prefix}_{ts}.csv")
    results_df.to_csv(csv_path, index=False)
    print(f"\n  Results saved → {csv_path}")

    if top_trades_dict:
        json_path = os.path.join(RESULTS_DIR, f"{filename_prefix}_{ts}_top_trades.json")
        serializable = {}
        for k, v in top_trades_dict.items():
            serializable[k] = [
                {
                    "entry_time": str(t.entry_time),
                    "exit_time": str(t.exit_time),
                    "side": t.side.name,
                    "entry_price": round(t.entry_price, 5),
                    "exit_price": round(t.exit_price, 5),
                    "sl_price": round(t.sl_price, 5),
                    "tp1_price": round(t.tp1_price, 5),
                    "tp2_price": round(t.tp2_price, 5),
                    "tp3_price": round(t.tp3_price, 5),
                    "lots": round(t.lots, 4),
                    "pnl_pips": round(t.pnl_pips, 1),
                    "pnl_usd": round(t.pnl_usd, 2),
                    "exit_reason": t.exit_reason,
                }
                for t in v
            ]
        with open(json_path, "w") as f:
            json.dump(serializable, f, indent=2)
        print(f"  Trade details saved → {json_path}")


def print_winner_announcement(top_strategy: dict, initial_capital: float = 1000.0):
    """Print a highlighted announcement for the best strategy."""
    print("\n" + "🏆" * 30)
    print(_clr("bold", "\n  ★ BEST PERFORMING STRATEGY FOUND ★\n"))
    print("🏆" * 30)
    print(f"\n  Strategy:     {_clr('cyan', str(top_strategy.get('strategy', 'N/A')))}")
    print(f"  Symbol:       {_clr('yellow', str(top_strategy.get('symbol', 'N/A')))}")
    print(f"  Timeframe:    {str(top_strategy.get('timeframe', 'N/A'))}")
    print(f"  Risk Config:  {str(top_strategy.get('risk_config', 'N/A'))}")
    ret = top_strategy.get('total_return_pct', 0)
    eq = top_strategy.get('final_equity', initial_capital)
    print(f"\n  Starting Capital:  €{initial_capital:,.0f}")
    print(f"  Final Equity:      {_clr('green', f'€{eq:,.2f}')}")
    print(f"  Total Return:      {_clr('green', f'{ret:+.2f}%')}")
    print(f"  Win Rate:          {top_strategy.get('win_rate_pct', 0):.1f}%")
    print(f"  Profit Factor:     {top_strategy.get('profit_factor', 0):.3f}")
    print(f"  Max Drawdown:      {top_strategy.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Sharpe Ratio:      {top_strategy.get('sharpe', 0):.3f}")
    print(f"  Total Trades:      {int(top_strategy.get('total_trades', 0))}")
    print("\n" + "🏆" * 30 + "\n")
