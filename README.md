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

## Search for high-frequency targets

For aggressive scalping research, use the high-frequency objective. It scores
candidates against daily trade count and win-rate targets, but it will report
when real data does not satisfy the target.

```bash
forex-robot optimize \
  --symbols EURUSD=X GBPUSD=X \
  --timeframes 1m 5m \
  --objective high-frequency \
  --target-daily-trades 20 \
  --target-win-rate 90 \
  --risk-per-trade 0.005 \
  --evaluations 100 \
  --output-dir results/high_frequency
```

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

The repository includes an experimental MetaTrader 5 Expert Advisor under
`mt5/Experts/ForexBreakoutPullbackEA.mq5`. Treat it as a demo/forward-testing
bridge from the research code, not as a guaranteed production trading system.
The EA also displays a small chart panel with the owner name, a colorful
`DRAGON FX` logo, and live strategy-duty status.

Read the Persian MT5 guide before use:

```text
docs/MT5_RUN_GUIDE_FA.md
```

The latest focused summary is:

```text
results/focused_final_package_summary.json
```

An experimental M1 scalping research preset is also included, but recent tests
did not find it profitable after costs:

```text
mt5/Experts/ForexM1ScalpingResearchEA.mq5
docs/M1_SCALPING_RESEARCH_FA.md
packages/forex_m1_scalping_research_package.zip
```

A real full-auto robot still needs broker-specific validation, order execution
monitoring, news filters, VPS monitoring, and kill-switch controls.
