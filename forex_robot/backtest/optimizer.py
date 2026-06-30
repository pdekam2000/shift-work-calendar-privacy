"""
Strategy Optimizer — tests all strategy × symbol × timeframe combinations
and ranks by profitability + quality metrics.

Uses multiprocessing for speed. Runs thousands of backtests automatically.
"""

from __future__ import annotations
import os
import json
import time
import traceback
from itertools import product
from typing import Dict, List, Optional
import concurrent.futures
import pandas as pd
import numpy as np

from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.strategy_library import ALL_STRATEGIES
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics


# ── Configuration sets to test ─────────────────────────────────────────────────

RISK_CONFIGS = [
    {"risk_pct": 1.0, "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,
     "trail_after_tp1": True,  "label": "1R_1-2-3_Trail"},
    {"risk_pct": 1.5, "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,
     "trail_after_tp1": True,  "label": "1.5R_1-2-3_Trail"},
    {"risk_pct": 1.0, "tp1_rr": 1.5, "tp2_rr": 2.5, "tp3_rr": 4.0,
     "trail_after_tp1": True,  "label": "1R_1.5-2.5-4_Trail"},
    {"risk_pct": 2.0, "tp1_rr": 1.0, "tp2_rr": 2.0, "tp3_rr": 3.0,
     "trail_after_tp1": False, "label": "2R_1-2-3_NoTrail"},
    {"risk_pct": 1.0, "tp1_rr": 0.8, "tp2_rr": 1.5, "tp3_rr": 2.5,
     "trail_after_tp1": True,  "label": "1R_0.8-1.5-2.5_Trail"},
]

# Timeframes appropriate for each strategy type
STRATEGY_TF_MAP = {
    "scalp": ["M5", "M15", "M30"],
    "swing": ["H1", "D1"],
    "fib":   ["H1", "D1"],
    "all":   ["M15", "H1", "D1"],
}


def _is_scalping(name: str) -> bool:
    return "Scalp" in name or "scalp" in name.lower()


def _get_timeframes_for_strategy(name: str) -> List[str]:
    if _is_scalping(name):
        return ["M5", "M15", "M30"]
    elif "Fibonacci" in name or "Wave" in name or "Fib" in name:
        return ["H1", "D1"]
    else:
        return ["M15", "H1", "D1"]


def run_single_backtest(args) -> Optional[dict]:
    """Worker function — runs one (strategy, symbol, timeframe, risk_config) combo."""
    strategy_name, symbol, tf, risk_cfg, df_serialized = args
    try:
        df = pd.read_json(df_serialized, orient="split")
        df.index = pd.to_datetime(df.index, utc=True)
        df = add_all_indicators(df)

        strategy_fn = ALL_STRATEGIES[strategy_name]
        signals, sl_pips = strategy_fn(df)

        if signals.abs().sum() < 5:
            return None  # too few signals

        cfg = BacktestConfig(
            initial_capital=1000.0,
            symbol=symbol,
            timeframe=tf,
            risk_pct=risk_cfg["risk_pct"],
            tp1_rr=risk_cfg["tp1_rr"],
            tp2_rr=risk_cfg["tp2_rr"],
            tp3_rr=risk_cfg["tp3_rr"],
            trail_after_tp1=risk_cfg["trail_after_tp1"],
        )
        engine = BacktestEngine(cfg)
        trades, equity = engine.run(df, signals, sl_pips, strategy_name)

        if len(trades) < 10:
            return None

        metrics = compute_metrics(trades, equity, 1000.0)
        metrics["strategy"] = strategy_name
        metrics["symbol"] = symbol
        metrics["timeframe"] = tf
        metrics["risk_config"] = risk_cfg["label"]
        metrics["combo_id"] = f"{strategy_name}|{symbol}|{tf}|{risk_cfg['label']}"
        return metrics

    except Exception as e:
        return None


class StrategyOptimizer:
    def __init__(self, data: Dict[str, Dict[str, pd.DataFrame]],
                 strategies: Optional[List[str]] = None,
                 max_workers: int = 4):
        self.data = data
        self.strategies = strategies or list(ALL_STRATEGIES.keys())
        self.max_workers = max_workers
        self.results: List[dict] = []

    def build_tasks(self) -> List[tuple]:
        tasks = []
        for strategy_name in self.strategies:
            tfs = _get_timeframes_for_strategy(strategy_name)
            for symbol, tf, risk_cfg in product(self.data.keys(), tfs, RISK_CONFIGS):
                if tf not in self.data.get(symbol, {}):
                    continue
                df = self.data[symbol][tf]
                if len(df) < 200:
                    continue
                df_json = df.to_json(orient="split", date_format="iso")
                tasks.append((strategy_name, symbol, tf, risk_cfg, df_json))
        return tasks

    def run(self, verbose: bool = True) -> pd.DataFrame:
        tasks = self.build_tasks()
        total = len(tasks)
        if verbose:
            print(f"\n{'='*60}")
            print(f"  STRATEGY OPTIMIZER — testing {total:,} combinations")
            print(f"  Strategies: {len(self.strategies)}  |  Workers: {self.max_workers}")
            print(f"{'='*60}\n")

        start = time.time()
        completed = 0
        valid = 0

        with concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(run_single_backtest, t): t for t in tasks}
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                result = future.result()
                if result and result.get("total_return_pct", -999) > -50:
                    self.results.append(result)
                    valid += 1

                if verbose and completed % max(1, total // 20) == 0:
                    elapsed = time.time() - start
                    pct = completed / total * 100
                    eta = (elapsed / completed) * (total - completed)
                    print(f"  [{pct:5.1f}%] {completed}/{total} done | "
                          f"valid={valid} | elapsed={elapsed:.0f}s | ETA={eta:.0f}s")

        elapsed = time.time() - start
        if verbose:
            print(f"\n  Done! {valid}/{total} valid combinations in {elapsed:.1f}s\n")

        if not self.results:
            return pd.DataFrame()

        df = pd.DataFrame(self.results)
        df = df.sort_values("total_return_pct", ascending=False).reset_index(drop=True)
        return df

    def get_top_strategies(self, df: pd.DataFrame, n: int = 20,
                           min_trades: int = 20,
                           min_win_rate: float = 45.0,
                           min_profit_factor: float = 1.2,
                           max_drawdown: float = -30.0) -> pd.DataFrame:
        """Filter and rank by composite score."""
        if df.empty:
            return df
        filtered = df[
            (df["total_trades"] >= min_trades) &
            (df["win_rate_pct"] >= min_win_rate) &
            (df["profit_factor"] >= min_profit_factor) &
            (df["max_drawdown_pct"] >= max_drawdown) &
            (df["total_return_pct"] > 0)
        ].copy()

        if filtered.empty:
            # Relax filters
            filtered = df[
                (df["total_trades"] >= 10) &
                (df["total_return_pct"] > 0)
            ].copy()

        if filtered.empty:
            return df.head(n)

        # Composite scoring: return, profit factor, sharpe, low drawdown
        def score(row):
            ret_score = min(row["total_return_pct"] / 100, 5.0)
            pf_score = min(row["profit_factor"] - 1, 3.0)
            sharpe_score = min(row["sharpe"], 3.0)
            dd_score = max(0, (row["max_drawdown_pct"] + 50) / 50)  # less negative = better
            wr_score = (row["win_rate_pct"] - 50) / 50
            return (ret_score * 0.3 + pf_score * 0.25 + sharpe_score * 0.2 +
                    dd_score * 0.15 + wr_score * 0.1)

        filtered["score"] = filtered.apply(score, axis=1)
        return filtered.nlargest(n, "score").reset_index(drop=True)
