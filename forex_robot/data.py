"""Market data loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


YAHOO_SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "EUR/USD": "EURUSD=X",
    "EURUSD=X": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "GBP/USD": "GBPUSD=X",
    "GBPUSD=X": "GBPUSD=X",
}

TIMEFRAME_TO_INTERVAL = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "4h": "60m",
    "1d": "1d",
}

DEFAULT_PERIODS = {
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "730d",
    "4h": "730d",
    "1d": "10y",
}


@dataclass(frozen=True)
class MarketRequest:
    """Data request for a single market/timeframe pair."""

    symbol: str
    timeframe: str
    period: str | None = None

    @property
    def yahoo_symbol(self) -> str:
        return YAHOO_SYMBOLS.get(self.symbol.upper(), self.symbol)

    @property
    def yahoo_interval(self) -> str:
        try:
            return TIMEFRAME_TO_INTERVAL[self.timeframe]
        except KeyError as exc:
            supported = ", ".join(sorted(TIMEFRAME_TO_INTERVAL))
            raise ValueError(f"Unsupported timeframe {self.timeframe!r}; use one of {supported}.") from exc

    @property
    def yahoo_period(self) -> str:
        return self.period or DEFAULT_PERIODS[self.timeframe]


class YahooFinanceDataSource:
    """Download and cache Yahoo Finance OHLC data."""

    def __init__(self, cache_dir: str | Path = "data/cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(self, request: MarketRequest, refresh: bool = False) -> pd.DataFrame:
        cache_path = self._cache_path(request)
        if cache_path.exists() and not refresh:
            return normalize_ohlc(pd.read_csv(cache_path, parse_dates=["time"], index_col="time"))

        frame = self._download(request)
        frame.to_csv(cache_path, index_label="time")
        return frame

    def _download(self, request: MarketRequest) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install dependencies first: python -m pip install -e '.[dev]'") from exc

        raw = yf.download(
            tickers=request.yahoo_symbol,
            period=request.yahoo_period,
            interval=request.yahoo_interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if raw.empty:
            raise RuntimeError(
                f"Yahoo Finance returned no data for {request.yahoo_symbol} "
                f"({request.yahoo_period}, {request.yahoo_interval})."
            )

        frame = normalize_ohlc(raw)
        if request.timeframe == "4h":
            frame = resample_ohlc(frame, "4h")
        return frame

    def _cache_path(self, request: MarketRequest) -> Path:
        safe_symbol = request.yahoo_symbol.replace("=", "").replace("/", "")
        return self.cache_dir / f"{safe_symbol}_{request.timeframe}_{request.yahoo_period}.csv"


def normalize_ohlc(frame: pd.DataFrame) -> pd.DataFrame:
    """Return lower-case OHLC columns indexed by naive UTC timestamps."""

    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(col[0]).lower() for col in data.columns]
    else:
        data.columns = [str(col).lower().replace(" ", "_") for col in data.columns]

    rename = {
        "adj_close": "adj_close",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }
    data = data.rename(columns=rename)
    required = ["open", "high", "low", "close"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise ValueError(f"OHLC data is missing required columns: {missing}")

    data = data[required + [col for col in ["volume"] if col in data.columns]]
    data = data.dropna(subset=required).sort_index()
    data.index.name = "time"
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert("UTC").tz_localize(None)
    return data


def resample_ohlc(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in frame.columns:
        agg["volume"] = "sum"
    return frame.resample(rule).agg(agg).dropna(subset=["open", "high", "low", "close"])


def align_conversion_series(
    symbol: str,
    market: pd.DataFrame,
    eurusd: pd.DataFrame | None,
) -> pd.Series:
    """Return USD-per-EUR conversion rates aligned to a traded market.

    PnL for Yahoo FX symbols is naturally in USD. Dividing by EUR/USD converts
    it back to the requested EUR account currency.
    """

    normalized = YAHOO_SYMBOLS.get(symbol.upper(), symbol)
    if normalized == "EURUSD=X":
        return market["close"].reindex(market.index).ffill()
    if eurusd is None:
        return pd.Series(1.0, index=market.index)
    return eurusd["close"].reindex(market.index, method="ffill").fillna(method="bfill")


def load_many(
    symbols: Iterable[str],
    timeframes: Iterable[str],
    *,
    period: str | None = None,
    refresh: bool = False,
    cache_dir: str | Path = "data/cache",
) -> dict[tuple[str, str], pd.DataFrame]:
    source = YahooFinanceDataSource(cache_dir)
    return {
        (symbol, timeframe): source.load(MarketRequest(symbol, timeframe, period), refresh=refresh)
        for symbol in symbols
        for timeframe in timeframes
    }
