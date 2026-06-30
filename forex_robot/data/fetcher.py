"""
Data Fetcher - Downloads real OHLCV data for EUR/USD and GBP/USD
from Yahoo Finance across multiple timeframes.
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
import pickle
from datetime import datetime, timedelta

# Yahoo Finance ticker symbols
SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
}

# Timeframes: (yf_interval, yf_period_or_start, label)
TIMEFRAMES = {
    "M5":  {"interval": "5m",  "period": "60d",  "label": "5-Minute"},
    "M15": {"interval": "15m", "period": "60d",  "label": "15-Minute"},
    "M30": {"interval": "30m", "period": "60d",  "label": "30-Minute"},
    "H1":  {"interval": "1h",  "period": "730d", "label": "1-Hour"},
    "H4":  {"interval": "1d",  "start": "2018-01-01", "label": "Daily (proxy H4)"},
    "D1":  {"interval": "1d",  "start": "2015-01-01", "label": "Daily"},
}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")


def _cache_path(symbol: str, tf: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{symbol}_{tf}.pkl")


def fetch_data(symbol: str, tf: str, force_refresh: bool = False) -> pd.DataFrame:
    """Fetch OHLCV data for a symbol/timeframe. Uses local cache when available."""
    cache_file = _cache_path(symbol, tf)
    if not force_refresh and os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        # Cache valid for 1 day
        if (datetime.now().timestamp() - mtime) < 86400:
            with open(cache_file, "rb") as f:
                df = pickle.load(f)
            print(f"  [cache] {symbol} {tf} — {len(df)} bars")
            return df

    ticker_sym = SYMBOLS.get(symbol, symbol)
    tf_cfg = TIMEFRAMES[tf]
    print(f"  [fetch] {symbol} {tf} from Yahoo Finance…")

    kwargs = {"interval": tf_cfg["interval"], "auto_adjust": True, "progress": False}
    if "period" in tf_cfg:
        kwargs["period"] = tf_cfg["period"]
    else:
        kwargs["start"] = tf_cfg["start"]

    raw = yf.download(ticker_sym, **kwargs)
    if raw.empty:
        raise ValueError(f"No data returned for {symbol} {tf}")

    # Flatten MultiIndex columns if present
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df.index = pd.to_datetime(df.index, utc=True)
    df.dropna(inplace=True)
    df = df[df["close"] > 0]

    with open(cache_file, "wb") as f:
        pickle.dump(df, f)

    print(f"  [ok]    {symbol} {tf} — {len(df)} bars  ({df.index[0].date()} → {df.index[-1].date()})")
    return df


def fetch_all(symbols=None, timeframes=None, force_refresh=False):
    """Download all symbol × timeframe combinations."""
    symbols = symbols or list(SYMBOLS.keys())
    timeframes = timeframes or list(TIMEFRAMES.keys())
    result = {}
    for sym in symbols:
        result[sym] = {}
        for tf in timeframes:
            try:
                result[sym][tf] = fetch_data(sym, tf, force_refresh)
            except Exception as e:
                print(f"  [warn] {sym} {tf} failed: {e}")
    return result


if __name__ == "__main__":
    data = fetch_all()
    for sym, tfs in data.items():
        for tf, df in tfs.items():
            print(f"{sym} {tf}: {len(df)} rows, last close={df['close'].iloc[-1]:.5f}")
