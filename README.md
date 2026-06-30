# Forex Robot Backtester

Research framework for an automatic EUR/USD and GBP/USD forex robot. It downloads
real OHLC data from Yahoo Finance, builds ATR-adaptive pullback/scalping signals,
and backtests entries with stop loss, three professional take-profit levels,
breakeven protection, trailing stops, spread, slippage, commission, leverage, and
EUR account conversion.

> This is research software, not financial advice. Backtests can overfit and do
> not guarantee future profitability. Validate on broker-quality tick data and a
> demo account before any live deployment.

## Strategy idea

The default strategy combines:

- EMA trend filter (`fast_ema` above/below `slow_ema`)
- Corrective pullback toward the fast EMA
- RSI recovery after the pullback
- Small ATR breakout confirmation for scalping entries
- Dynamic ATR stop loss
- Three R-multiple take-profit levels
- Breakeven after TP1 and ATR trailing after TP2
- Risk-based position sizing from a default 1,000 EUR account

## Install

```bash
python -m pip install -e ".[dev]"
```

## Optimize on real data

```bash
forex-robot optimize \
  --symbols EURUSD=X GBPUSD=X \
  --timeframes 15m 1h 4h \
  --initial-capital 1000 \
  --risk-per-trade 0.01 \
  --evaluations 500 \
  --top-n 10 \
  --output-dir results
```

Outputs:

- `results/optimization_results.json` - ranked parameter candidates
- `results/best_params.json` - best parameter set
- `results/best_backtests.json` - detailed result for the best set
- `results/best_trades.csv` - trade list for inspection

## Backtest one parameter set

```bash
forex-robot backtest \
  --symbols EURUSD=X GBPUSD=X \
  --timeframes 15m 1h 4h \
  --params-json results/best_params.json \
  --initial-capital 1000 \
  --output-dir results/manual_backtest
```

## Notes for live trading integration

The repository intentionally stops at research/backtesting. A real full-auto
robot must add broker integration, order validation, connection monitoring,
duplicate-order protection, market-hours handling, news filters, deployment
observability, and kill-switch controls.
