"""Backtesting engine with risk-based sizing and three take-profit levels."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 1000.0
    risk_per_trade: float = 0.01
    max_leverage: float = 20.0
    spread_pips: float = 0.8
    slippage_pips: float = 0.1
    pip_size: float = 0.0001
    commission_per_million: float = 25.0
    min_stop_pips: float = 2.0


@dataclass
class Trade:
    symbol: str
    direction: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    units: float
    pnl: float
    return_pct: float
    exit_reason: str
    partial_exits: list[dict[str, float | str]] = field(default_factory=list)


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    config: dict[str, Any]
    strategy: dict[str, Any]
    metrics: dict[str, float | int]
    trades: list[Trade]
    equity_curve: list[dict[str, float | str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "config": self.config,
            "strategy": self.strategy,
            "metrics": self.metrics,
            "trades": [asdict(trade) for trade in self.trades],
            "equity_curve": self.equity_curve,
        }


@dataclass
class _OpenPosition:
    direction: int
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    targets: list[float]
    trailing_distance: float
    units: float
    remaining_units: float
    risk_amount: float
    hit_targets: int = 0
    realized_pnl: float = 0.0
    partial_exits: list[dict[str, float | str]] = field(default_factory=list)


class Backtester:
    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(
        self,
        signals: pd.DataFrame,
        *,
        symbol: str,
        timeframe: str,
        strategy: dict[str, Any],
        conversion: pd.Series | None = None,
    ) -> BacktestResult:
        data = signals.copy().sort_index()
        if data.empty:
            return self._empty_result(symbol, timeframe, strategy)
        conversion_series = self._conversion_series(data, conversion)

        equity = self.config.initial_capital
        peak_equity = equity
        max_drawdown = 0.0
        trades: list[Trade] = []
        equity_curve: list[dict[str, float | str]] = []
        position: _OpenPosition | None = None

        for idx in range(1, len(data)):
            previous = data.iloc[idx - 1]
            current = data.iloc[idx]
            timestamp = data.index[idx]
            conversion_rate = float(conversion_series.iloc[idx])

            if position is None and int(previous.get("signal", 0)) != 0:
                position = self._open_position(
                    signal=int(previous["signal"]),
                    row=previous,
                    timestamp=timestamp,
                    entry_open=float(current["open"]),
                    equity=equity,
                    conversion_rate=conversion_rate,
                )

            if position is not None:
                close_result = self._process_bar(position, current, timestamp, conversion_rate)
                if close_result is not None:
                    equity += close_result.pnl
                    trades.append(close_result)
                    position = None

            peak_equity = max(peak_equity, equity)
            drawdown = (peak_equity - equity) / peak_equity if peak_equity else 0.0
            max_drawdown = max(max_drawdown, drawdown)
            equity_curve.append({"time": str(timestamp), "equity": round(equity, 2)})

        if position is not None:
            final_timestamp = data.index[-1]
            final_conversion = float(conversion_series.iloc[-1])
            final_trade = self._close_position(
                position,
                exit_time=final_timestamp,
                exit_price=float(data.iloc[-1]["close"]),
                conversion_rate=final_conversion,
                reason="end_of_data",
            )
            equity += final_trade.pnl
            trades.append(final_trade)
            equity_curve.append({"time": str(final_timestamp), "equity": round(equity, 2)})

        metrics = self._metrics(trades, equity, max_drawdown)
        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            config=asdict(self.config),
            strategy=strategy,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
        )

    def _open_position(
        self,
        *,
        signal: int,
        row: pd.Series,
        timestamp: pd.Timestamp,
        entry_open: float,
        equity: float,
        conversion_rate: float,
    ) -> _OpenPosition | None:
        stop_distance = float(row.get("stop_distance", 0.0))
        if not isfinite(stop_distance) or stop_distance < self.config.min_stop_pips * self.config.pip_size:
            return None

        spread = self.config.spread_pips * self.config.pip_size
        slippage = self.config.slippage_pips * self.config.pip_size
        direction = 1 if signal > 0 else -1
        entry_price = entry_open + direction * (spread / 2.0 + slippage)
        stop_price = entry_price - direction * stop_distance
        targets = [
            entry_price + direction * float(row["tp1_distance"]),
            entry_price + direction * float(row["tp2_distance"]),
            entry_price + direction * float(row["tp3_distance"]),
        ]
        risk_amount = equity * self.config.risk_per_trade
        raw_units = risk_amount * conversion_rate / stop_distance
        max_units = equity * self.config.max_leverage * conversion_rate / entry_price
        units = max(0.0, min(raw_units, max_units))
        if units <= 0:
            return None

        return _OpenPosition(
            direction=direction,
            entry_time=timestamp,
            entry_price=entry_price,
            stop_price=stop_price,
            targets=targets,
            trailing_distance=float(row.get("trailing_distance", stop_distance)),
            units=units,
            remaining_units=units,
            risk_amount=risk_amount,
        )

    def _process_bar(
        self,
        position: _OpenPosition,
        row: pd.Series,
        timestamp: pd.Timestamp,
        conversion_rate: float,
    ) -> Trade | None:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        if position.direction == 1 and low <= position.stop_price:
            return self._close_position(position, timestamp, position.stop_price, conversion_rate, "stop_loss")
        if position.direction == -1 and high >= position.stop_price:
            return self._close_position(position, timestamp, position.stop_price, conversion_rate, "stop_loss")

        while position.hit_targets < 3:
            target = position.targets[position.hit_targets]
            target_hit = high >= target if position.direction == 1 else low <= target
            if not target_hit:
                break
            fraction = 1.0 / (3 - position.hit_targets)
            closed_units = position.remaining_units * fraction
            pnl = self._pnl(position, target, closed_units, conversion_rate)
            position.realized_pnl += pnl
            position.remaining_units -= closed_units
            position.hit_targets += 1
            position.partial_exits.append(
                {
                    "time": str(timestamp),
                    "price": round(target, 6),
                    "units": round(closed_units, 2),
                    "pnl": round(pnl, 2),
                    "reason": f"tp{position.hit_targets}",
                }
            )
            if position.hit_targets == 1:
                position.stop_price = position.entry_price
            if position.hit_targets == 3 or position.remaining_units <= 0:
                return self._close_position(position, timestamp, target, conversion_rate, "tp3")

        if position.hit_targets >= 2:
            if position.direction == 1:
                position.stop_price = max(position.stop_price, close - position.trailing_distance)
            else:
                position.stop_price = min(position.stop_price, close + position.trailing_distance)
        return None

    def _close_position(
        self,
        position: _OpenPosition,
        exit_time: pd.Timestamp,
        exit_price: float,
        conversion_rate: float,
        reason: str,
    ) -> Trade:
        if position.remaining_units > 0:
            position.realized_pnl += self._pnl(position, exit_price, position.remaining_units, conversion_rate)
        commission = self._commission(position.units)
        pnl = position.realized_pnl - commission
        return_pct = pnl / self.config.initial_capital * 100.0
        return Trade(
            symbol="",
            direction="long" if position.direction == 1 else "short",
            entry_time=str(position.entry_time),
            exit_time=str(exit_time),
            entry_price=round(position.entry_price, 6),
            exit_price=round(exit_price, 6),
            units=round(position.units, 2),
            pnl=round(pnl, 2),
            return_pct=round(return_pct, 3),
            exit_reason=reason,
            partial_exits=position.partial_exits,
        )

    def _pnl(
        self,
        position: _OpenPosition,
        exit_price: float,
        units: float,
        conversion_rate: float,
    ) -> float:
        quote_pnl = (exit_price - position.entry_price) * position.direction * units
        return quote_pnl / max(conversion_rate, 1e-9)

    def _commission(self, units: float) -> float:
        return units / 1_000_000.0 * self.config.commission_per_million

    def _conversion_series(self, data: pd.DataFrame, conversion: pd.Series | None) -> pd.Series:
        if conversion is None:
            return pd.Series(1.0, index=data.index)
        return conversion.reindex(data.index, method="ffill").bfill().astype(float)

    def _metrics(self, trades: list[Trade], final_equity: float, max_drawdown: float) -> dict[str, float | int]:
        wins = [trade.pnl for trade in trades if trade.pnl > 0]
        losses = [trade.pnl for trade in trades if trade.pnl < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        trade_count = len(trades)
        win_rate = len(wins) / trade_count * 100.0 if trade_count else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss else (gross_profit if gross_profit else 0.0)
        net_profit = final_equity - self.config.initial_capital
        daily = self._daily_metrics(trades)
        return {
            "initial_capital": round(self.config.initial_capital, 2),
            "final_equity": round(final_equity, 2),
            "net_profit": round(net_profit, 2),
            "return_pct": round(net_profit / self.config.initial_capital * 100.0, 2),
            "max_drawdown_pct": round(max_drawdown * 100.0, 2),
            "trade_count": trade_count,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 3),
            "average_trade": round(net_profit / trade_count, 2) if trade_count else 0.0,
            **daily,
        }

    def _daily_metrics(self, trades: list[Trade]) -> dict[str, float | int]:
        if not trades:
            return {
                "trading_day_count": 0,
                "average_daily_trades": 0.0,
                "average_daily_win_rate_pct": 0.0,
                "days_with_20_trades": 0,
                "days_with_20_trades_90_win": 0,
                "high_frequency_day_ratio": 0.0,
            }

        daily_rows = []
        trade_frame = pd.DataFrame(
            {
                "entry_time": pd.to_datetime([trade.entry_time for trade in trades]),
                "win": [trade.pnl > 0 for trade in trades],
            }
        )
        for _, day_trades in trade_frame.groupby(trade_frame["entry_time"].dt.date):
            day_count = len(day_trades)
            day_win_rate = float(day_trades["win"].mean() * 100.0)
            daily_rows.append((day_count, day_win_rate))

        trading_day_count = len(daily_rows)
        days_with_20 = sum(1 for count, _ in daily_rows if count >= 20)
        days_with_target = sum(1 for count, win_rate in daily_rows if count >= 20 and win_rate >= 90.0)
        return {
            "trading_day_count": trading_day_count,
            "average_daily_trades": round(sum(count for count, _ in daily_rows) / trading_day_count, 2),
            "average_daily_win_rate_pct": round(sum(win_rate for _, win_rate in daily_rows) / trading_day_count, 2),
            "days_with_20_trades": days_with_20,
            "days_with_20_trades_90_win": days_with_target,
            "high_frequency_day_ratio": round(days_with_target / trading_day_count, 3),
        }

    def _empty_result(self, symbol: str, timeframe: str, strategy: dict[str, Any]) -> BacktestResult:
        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            config=asdict(self.config),
            strategy=strategy,
            metrics=self._metrics([], self.config.initial_capital, 0.0),
            trades=[],
            equity_curve=[],
        )
