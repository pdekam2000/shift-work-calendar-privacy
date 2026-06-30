"""
Backtesting Engine — event-driven vectorized backtester.

Features:
  • Fixed lot sizing based on risk % per trade
  • Stop Loss (ATR-based or fixed pips)
  • 3-level Take Profit (TP1 / TP2 / TP3) with partial exit
  • Trailing Stop after TP1 hit
  • Spread simulation
  • Realistic slippage model
  • Full equity curve tracking
  • Performance metrics: Sharpe, Sortino, Max DD, Win Rate, Profit Factor, etc.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class Side(Enum):
    BUY = 1
    SELL = -1


@dataclass
class TradeResult:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: Side
    entry_price: float
    exit_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    tp3_price: float
    lots: float
    pnl_pips: float
    pnl_usd: float
    exit_reason: str  # 'TP1','TP2','TP3','SL','TRAIL','EOD'
    symbol: str
    timeframe: str
    strategy_name: str


@dataclass
class BacktestConfig:
    initial_capital: float = 1000.0
    risk_pct: float = 1.0           # % of capital risked per trade
    spread_pips: float = 1.5        # typical EUR/USD spread
    slippage_pips: float = 0.5      # slippage on entry/exit
    pip_value: float = 10.0         # USD per pip for 1 standard lot
    min_lot: float = 0.01
    max_lot: float = 10.0
    # TP levels as Risk:Reward ratios
    tp1_rr: float = 1.0             # TP1 at 1×SL distance → partial exit
    tp2_rr: float = 2.0             # TP2 at 2×SL distance → partial exit
    tp3_rr: float = 3.0             # TP3 at 3×SL distance → full exit
    tp1_pct: float = 0.33           # % of position closed at TP1
    tp2_pct: float = 0.33           # % of position closed at TP2
    tp3_pct: float = 0.34           # % remaining closed at TP3
    trail_after_tp1: bool = True    # activate trailing stop after TP1
    trail_atr_mult: float = 1.5     # trailing stop = 1.5 × ATR
    max_open_trades: int = 3
    symbol: str = "EURUSD"
    timeframe: str = "H1"
    pip_size: float = 0.0001        # 0.0001 for most pairs, 0.01 for JPY


class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.cfg = config

    def _pip_to_price(self, pips: float) -> float:
        return pips * self.cfg.pip_size

    def _price_to_pips(self, price_diff: float) -> float:
        return price_diff / self.cfg.pip_size

    def _calc_lot_size(self, capital: float, sl_pips: float) -> float:
        """Kelly-adjusted lot sizing based on risk %."""
        risk_amount = capital * (self.cfg.risk_pct / 100)
        sl_value = sl_pips * self.cfg.pip_value
        if sl_value <= 0:
            return self.cfg.min_lot
        lots = risk_amount / sl_value
        return float(np.clip(lots, self.cfg.min_lot, self.cfg.max_lot))

    def run(self, df: pd.DataFrame, signals: pd.Series, sl_pips_series: pd.Series,
            strategy_name: str = "unknown") -> Tuple[List[TradeResult], pd.Series]:
        """
        Run backtest.

        signals: pd.Series aligned with df.index
                 1 = BUY, -1 = SELL, 0 = no signal
        sl_pips_series: per-bar ATR-based SL size in pips
        Returns (trades list, equity curve Series)
        """
        cfg = self.cfg
        equity = cfg.initial_capital
        equity_curve = []

        open_trades: List[dict] = []
        trades: List[TradeResult] = []

        spread = self._pip_to_price(cfg.spread_pips)
        slip = self._pip_to_price(cfg.slippage_pips)

        df = df.copy()
        df["_signal"] = signals.reindex(df.index).fillna(0).astype(int)
        df["_sl_pips"] = sl_pips_series.reindex(df.index).fillna(10.0)

        for i in range(1, len(df)):
            row = df.iloc[i]
            bar_high = row["high"]
            bar_low = row["low"]
            bar_close = row["close"]
            bar_time = df.index[i]

            # ── Process open trades ──────────────────────────────────────────
            closed_indices = []
            for j, t in enumerate(open_trades):
                side = t["side"]
                remaining = t["remaining"]
                if remaining <= 0:
                    closed_indices.append(j)
                    continue

                exit_price = None
                exit_reason = None

                if side == Side.BUY:
                    # Check SL
                    if bar_low <= t["sl"]:
                        exit_price = t["sl"] - slip
                        exit_reason = "SL"
                    # Check TP3
                    elif bar_high >= t["tp3"]:
                        exit_price = t["tp3"] - slip
                        exit_reason = "TP3"
                    # Check TP2
                    elif not t["tp2_hit"] and bar_high >= t["tp2"]:
                        exit_price = t["tp2"] - slip
                        partial_lots = t["lots"] * cfg.tp2_pct
                        pnl = self._price_to_pips(exit_price - t["entry"]) * partial_lots * cfg.pip_value
                        equity += pnl
                        t["tp2_hit"] = True
                        t["remaining"] -= partial_lots
                        if cfg.trail_after_tp1:
                            t["sl"] = max(t["sl"], t["entry"])  # move SL to breakeven
                    # Check TP1
                    elif not t["tp1_hit"] and bar_high >= t["tp1"]:
                        exit_price = t["tp1"] - slip
                        partial_lots = t["lots"] * cfg.tp1_pct
                        pnl = self._price_to_pips(exit_price - t["entry"]) * partial_lots * cfg.pip_value
                        equity += pnl
                        t["tp1_hit"] = True
                        t["remaining"] -= partial_lots
                    # Trailing stop
                    if cfg.trail_after_tp1 and t["tp1_hit"] and exit_reason is None:
                        trail_stop = bar_high - self._pip_to_price(t["trail_pips"])
                        t["sl"] = max(t["sl"], trail_stop)
                        if bar_low <= t["sl"]:
                            exit_price = t["sl"] - slip
                            exit_reason = "TRAIL"

                else:  # SELL
                    if bar_high >= t["sl"]:
                        exit_price = t["sl"] + slip
                        exit_reason = "SL"
                    elif bar_low <= t["tp3"]:
                        exit_price = t["tp3"] + slip
                        exit_reason = "TP3"
                    elif not t["tp2_hit"] and bar_low <= t["tp2"]:
                        exit_price = t["tp2"] + slip
                        partial_lots = t["lots"] * cfg.tp2_pct
                        pnl = self._price_to_pips(t["entry"] - exit_price) * partial_lots * cfg.pip_value
                        equity += pnl
                        t["tp2_hit"] = True
                        t["remaining"] -= partial_lots
                        if cfg.trail_after_tp1:
                            t["sl"] = min(t["sl"], t["entry"])
                    elif not t["tp1_hit"] and bar_low <= t["tp1"]:
                        exit_price = t["tp1"] + slip
                        partial_lots = t["lots"] * cfg.tp1_pct
                        pnl = self._price_to_pips(t["entry"] - exit_price) * partial_lots * cfg.pip_value
                        equity += pnl
                        t["tp1_hit"] = True
                        t["remaining"] -= partial_lots
                    if cfg.trail_after_tp1 and t["tp1_hit"] and exit_reason is None:
                        trail_stop = bar_low + self._pip_to_price(t["trail_pips"])
                        t["sl"] = min(t["sl"], trail_stop)
                        if bar_high >= t["sl"]:
                            exit_price = t["sl"] + slip
                            exit_reason = "TRAIL"

                if exit_price is not None and exit_reason is not None:
                    remaining_lots = t["remaining"]
                    if side == Side.BUY:
                        pnl = self._price_to_pips(exit_price - t["entry"]) * remaining_lots * cfg.pip_value
                    else:
                        pnl = self._price_to_pips(t["entry"] - exit_price) * remaining_lots * cfg.pip_value
                    equity += pnl
                    total_pnl_pips = self._price_to_pips(
                        abs(exit_price - t["entry"])) * (1 if pnl >= 0 else -1)
                    trades.append(TradeResult(
                        entry_time=t["entry_time"],
                        exit_time=bar_time,
                        side=side,
                        entry_price=t["entry"],
                        exit_price=exit_price,
                        sl_price=t["original_sl"],
                        tp1_price=t["tp1"],
                        tp2_price=t["tp2"],
                        tp3_price=t["tp3"],
                        lots=t["lots"],
                        pnl_pips=total_pnl_pips,
                        pnl_usd=pnl,
                        exit_reason=exit_reason,
                        symbol=cfg.symbol,
                        timeframe=cfg.timeframe,
                        strategy_name=strategy_name,
                    ))
                    closed_indices.append(j)

            for j in reversed(sorted(set(closed_indices))):
                open_trades.pop(j)

            # ── Open new trade on signal ─────────────────────────────────────
            sig = int(row["_signal"])
            sl_pips = float(row["_sl_pips"])
            if sig != 0 and len(open_trades) < cfg.max_open_trades and sl_pips > 0:
                lots = self._calc_lot_size(equity, sl_pips)
                if sig == 1:  # BUY
                    entry = bar_close + spread / 2 + slip
                    sl = entry - self._pip_to_price(sl_pips)
                    tp1 = entry + self._pip_to_price(sl_pips * cfg.tp1_rr)
                    tp2 = entry + self._pip_to_price(sl_pips * cfg.tp2_rr)
                    tp3 = entry + self._pip_to_price(sl_pips * cfg.tp3_rr)
                else:  # SELL
                    entry = bar_close - spread / 2 - slip
                    sl = entry + self._pip_to_price(sl_pips)
                    tp1 = entry - self._pip_to_price(sl_pips * cfg.tp1_rr)
                    tp2 = entry - self._pip_to_price(sl_pips * cfg.tp2_rr)
                    tp3 = entry - self._pip_to_price(sl_pips * cfg.tp3_rr)

                open_trades.append({
                    "side": Side(sig),
                    "entry": entry,
                    "entry_time": bar_time,
                    "sl": sl,
                    "original_sl": sl,
                    "tp1": tp1, "tp2": tp2, "tp3": tp3,
                    "lots": lots,
                    "remaining": lots,
                    "tp1_hit": False,
                    "tp2_hit": False,
                    "trail_pips": sl_pips * cfg.trail_atr_mult,
                })

            equity_curve.append((bar_time, equity))

        # Close any remaining open trades at last close
        if open_trades and len(df) > 0:
            last_close = df["close"].iloc[-1]
            last_time = df.index[-1]
            for t in open_trades:
                side = t["side"]
                remaining = t["remaining"]
                if remaining <= 0:
                    continue
                if side == Side.BUY:
                    pnl = self._price_to_pips(last_close - t["entry"]) * remaining * self.cfg.pip_value
                else:
                    pnl = self._price_to_pips(t["entry"] - last_close) * remaining * self.cfg.pip_value
                equity += pnl
                total_pnl_pips = self._price_to_pips(abs(last_close - t["entry"])) * (1 if pnl >= 0 else -1)
                trades.append(TradeResult(
                    entry_time=t["entry_time"],
                    exit_time=last_time,
                    side=side,
                    entry_price=t["entry"],
                    exit_price=last_close,
                    sl_price=t["original_sl"],
                    tp1_price=t["tp1"],
                    tp2_price=t["tp2"],
                    tp3_price=t["tp3"],
                    lots=t["lots"],
                    pnl_pips=total_pnl_pips,
                    pnl_usd=pnl,
                    exit_reason="EOD",
                    symbol=cfg.symbol,
                    timeframe=cfg.timeframe,
                    strategy_name=strategy_name,
                ))

        equity_series = pd.Series(
            [e for _, e in equity_curve],
            index=[t for t, _ in equity_curve]
        ) if equity_curve else pd.Series([cfg.initial_capital])

        return trades, equity_series


# ── Performance Metrics ────────────────────────────────────────────────────────

def compute_metrics(trades: List[TradeResult], equity_curve: pd.Series,
                    initial_capital: float = 1000.0) -> dict:
    if not trades:
        return {"error": "No trades"}

    # Use full per-trade pnl including partial exits
    # pnl_usd in TradeResult = only the *remaining* portion at final exit.
    # We use equity_curve for total_return; win/loss stats from trade exits.
    pnls = [t.pnl_usd for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    final_equity = equity_curve.iloc[-1] if len(equity_curve) > 0 else initial_capital
    total_return = (final_equity - initial_capital) / initial_capital * 100
    net_profit = final_equity - initial_capital
    win_rate = len(wins) / len(pnls) * 100 if pnls else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float("inf")

    # Drawdown
    running_max = equity_curve.cummax()
    dd = (equity_curve - running_max) / running_max * 100
    max_dd = dd.min()

    # Sharpe (annualised, assuming daily returns if 1D, else estimate)
    returns = equity_curve.pct_change().dropna()
    if len(returns) > 1:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0.0
        downside = returns[returns < 0].std()
        sortino = (returns.mean() / downside) * np.sqrt(252) if downside > 0 else 0.0
    else:
        sharpe = sortino = 0.0

    # Consecutive wins/losses
    streaks = []
    cur = 0
    for p in pnls:
        if (p > 0 and cur > 0) or (p <= 0 and cur < 0):
            cur += (1 if p > 0 else -1)
        else:
            streaks.append(cur)
            cur = (1 if p > 0 else -1)
    streaks.append(cur)
    max_consec_wins = max((s for s in streaks if s > 0), default=0)
    max_consec_losses = abs(min((s for s in streaks if s < 0), default=0))

    exit_counts = {}
    for t in trades:
        exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

    return {
        "total_trades": len(trades),
        "win_rate_pct": round(win_rate, 2),
        "total_return_pct": round(total_return, 2),
        "profit_factor": round(profit_factor, 3),
        "final_equity": round(final_equity, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "expectancy_usd": round((win_rate / 100) * avg_win + (1 - win_rate / 100) * avg_loss, 2),
        "gross_profit": round(sum(wins), 2),
        "gross_loss": round(sum(losses), 2),
        "net_profit": round(net_profit, 2),
        "max_consec_wins": max_consec_wins,
        "max_consec_losses": max_consec_losses,
        "exit_breakdown": exit_counts,
    }
