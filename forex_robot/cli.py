"""Command line interface for optimization and backtesting."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from forex_robot.backtest import BacktestConfig, Backtester
from forex_robot.data import MarketRequest, YahooFinanceDataSource, align_conversion_series
from forex_robot.optimizer import (
    candidate_results_to_dict,
    estimate_search_space_size,
    optimize,
)
from forex_robot.strategy import StrategyParams, build_signals


DEFAULT_SYMBOLS = ["EURUSD=X", "GBPUSD=X"]
DEFAULT_TIMEFRAMES = ["15m", "1h", "4h"]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "optimize":
        return command_optimize(args)
    if args.command == "backtest":
        return command_backtest(args)
    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forex pullback scalping robot research CLI.")
    subparsers = parser.add_subparsers(dest="command")

    optimize_parser = subparsers.add_parser("optimize", help="Search strategy parameters on real OHLC data.")
    add_common_args(optimize_parser)
    optimize_parser.add_argument("--evaluations", type=int, default=300)
    optimize_parser.add_argument("--top-n", type=int, default=10)
    optimize_parser.add_argument("--seed", type=int, default=42)
    optimize_parser.add_argument("--min-trades", type=int, default=8)

    backtest_parser = subparsers.add_parser("backtest", help="Run one parameter set on real OHLC data.")
    add_common_args(backtest_parser)
    backtest_parser.add_argument("--params-json", type=Path, help="Path to a StrategyParams JSON file.")
    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--timeframes", nargs="+", default=DEFAULT_TIMEFRAMES)
    parser.add_argument("--period", help="Override Yahoo Finance period, e.g. 60d or 730d.")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached market data.")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--initial-capital", type=float, default=1000.0)
    parser.add_argument("--risk-per-trade", type=float, default=0.01)
    parser.add_argument("--spread-pips", type=float, default=0.8)
    parser.add_argument("--slippage-pips", type=float, default=0.1)
    parser.add_argument("--max-leverage", type=float, default=20.0)


def command_optimize(args: argparse.Namespace) -> int:
    config = config_from_args(args)
    markets, conversions = load_market_bundle(args)
    results = optimize(
        markets,
        conversions,
        evaluations=args.evaluations,
        top_n=args.top_n,
        seed=args.seed,
        min_trades=args.min_trades,
        config=config,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": args.symbols,
        "timeframes": args.timeframes,
        "searched_candidates": args.evaluations,
        "estimated_search_space": estimate_search_space_size(),
        "initial_capital": args.initial_capital,
        "risk_per_trade": args.risk_per_trade,
        "results": candidate_results_to_dict(results),
    }
    write_json(args.output_dir / "optimization_results.json", output)

    if results:
        best_params = StrategyParams(**results[0].params)
        write_json(args.output_dir / "best_params.json", best_params.to_dict())
        best_backtests = run_backtests(markets, conversions, best_params, config)
        write_json(args.output_dir / "best_backtests.json", [item.to_dict() for item in best_backtests])
        write_trade_csv(args.output_dir / "best_trades.csv", best_backtests)
        print_summary(results[0].aggregate_metrics)
    else:
        print("No viable strategy candidate was found. Try more evaluations or wider data.")
    return 0


def command_backtest(args: argparse.Namespace) -> int:
    config = config_from_args(args)
    markets, conversions = load_market_bundle(args)
    params = load_params(args.params_json) if args.params_json else StrategyParams()
    results = run_backtests(markets, conversions, params, config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "backtest_results.json", [item.to_dict() for item in results])
    write_trade_csv(args.output_dir / "backtest_trades.csv", results)
    aggregate = {
        "net_profit": round(sum(float(item.metrics["net_profit"]) for item in results), 2),
        "trades": sum(int(item.metrics["trade_count"]) for item in results),
        "average_return_pct": round(
            sum(float(item.metrics["return_pct"]) for item in results) / max(len(results), 1),
            2,
        ),
    }
    print_summary(aggregate)
    return 0


def config_from_args(args: argparse.Namespace) -> BacktestConfig:
    return BacktestConfig(
        initial_capital=args.initial_capital,
        risk_per_trade=args.risk_per_trade,
        spread_pips=args.spread_pips,
        slippage_pips=args.slippage_pips,
        max_leverage=args.max_leverage,
    )


def load_market_bundle(
    args: argparse.Namespace,
) -> tuple[dict[tuple[str, str], pd.DataFrame], dict[tuple[str, str], pd.Series]]:
    source = YahooFinanceDataSource()
    markets: dict[tuple[str, str], pd.DataFrame] = {}
    eurusd_by_timeframe: dict[str, pd.DataFrame] = {}

    for timeframe in args.timeframes:
        eurusd_by_timeframe[timeframe] = source.load(
            MarketRequest("EURUSD=X", timeframe, args.period),
            refresh=args.refresh,
        )
        for symbol in args.symbols:
            markets[(symbol, timeframe)] = source.load(
                MarketRequest(symbol, timeframe, args.period),
                refresh=args.refresh,
            )

    conversions = {
        (symbol, timeframe): align_conversion_series(
            symbol,
            market,
            eurusd_by_timeframe.get(timeframe),
        )
        for (symbol, timeframe), market in markets.items()
    }
    return markets, conversions


def run_backtests(
    markets: dict[tuple[str, str], pd.DataFrame],
    conversions: dict[tuple[str, str], pd.Series],
    params: StrategyParams,
    config: BacktestConfig,
):
    backtester = Backtester(config)
    results = []
    for (symbol, timeframe), frame in markets.items():
        signals = build_signals(frame, params)
        result = backtester.run(
            signals,
            symbol=symbol,
            timeframe=timeframe,
            strategy=params.to_dict(),
            conversion=conversions.get((symbol, timeframe)),
        )
        for trade in result.trades:
            trade.symbol = symbol
        results.append(result)
    return results


def load_params(path: Path) -> StrategyParams:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return StrategyParams(**payload)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(make_json_safe(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_trade_csv(path: Path, results: list[Any]) -> None:
    rows: list[dict[str, Any]] = []
    for result in results:
        for trade in result.trades:
            row = {
                "symbol": result.symbol,
                "timeframe": result.timeframe,
                "direction": trade.direction,
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "units": trade.units,
                "pnl": trade.pnl,
                "return_pct": trade.return_pct,
                "exit_reason": trade.exit_reason,
            }
            rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)


def make_json_safe(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {str(key): make_json_safe(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [make_json_safe(value) for value in payload]
    if hasattr(payload, "item"):
        return payload.item()
    return payload


def print_summary(metrics: dict[str, Any]) -> None:
    print(json.dumps(make_json_safe(metrics), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
