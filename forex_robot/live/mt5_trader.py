"""
موتور معامله زنده با MetaTrader 5
اتصال → دریافت داده → تولید سیگنال → ارسال سفارش خودکار
"""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Tuple

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

from forex_robot.config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH,
    SYMBOLS, RISK_PCT_PER_TRADE, MIN_LOT, MAX_LOT,
    ATR_SL_MULTIPLIER, TP1_RR, TP2_RR, TP3_RR,
    TRAIL_AFTER_TP1, MAX_OPEN_TRADES, MODE, LOG_FILE
)
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.optimized_strategies import strategy_fib_ichimoku_retracement
from forex_robot.strategies.strategy_library import strategy_stochastic_reversal, strategy_macd_trend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("Robot1")

STRATEGY_MAP = {
    "Fib_Ichi":         strategy_fib_ichimoku_retracement,
    "Stochastic_Rev":   strategy_stochastic_reversal,
    "MACD_Trend":       strategy_macd_trend,
}

TF_MAP = {
    "M5":  mt5.TIMEFRAME_M5  if MT5_AVAILABLE else 5,
    "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
    "M30": mt5.TIMEFRAME_M30 if MT5_AVAILABLE else 30,
    "H1":  mt5.TIMEFRAME_H1  if MT5_AVAILABLE else 60,
    "H4":  mt5.TIMEFRAME_H4  if MT5_AVAILABLE else 240,
    "D1":  mt5.TIMEFRAME_D1  if MT5_AVAILABLE else 1440,
}


class MT5Trader:
    def __init__(self, strategy_name: str = "Fib_Ichi",
                 timeframe: str = "D1",
                 symbols: list = None):
        self.strategy_name = strategy_name
        self.strategy_fn   = STRATEGY_MAP.get(strategy_name, strategy_fib_ichimoku_retracement)
        self.timeframe     = timeframe
        self.symbols       = symbols or SYMBOLS
        self.connected     = False
        self.account_info  = {}

    # ── اتصال ─────────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            log.warning("MetaTrader5 نصب نیست — حالت سیگنال‌فقط فعال است")
            return False
        kwargs = {}
        if MT5_PATH:
            kwargs["path"] = MT5_PATH
        if not mt5.initialize(**kwargs):
            log.error(f"اتصال MT5 ناموفق: {mt5.last_error()}")
            return False
        if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            ok = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
            if not ok:
                log.error(f"ورود به حساب ناموفق: {mt5.last_error()}")
                return False
        info = mt5.account_info()
        if info:
            self.account_info = {
                "login":   info.login,
                "balance": info.balance,
                "equity":  info.equity,
                "currency":info.currency,
                "server":  info.server,
                "leverage":info.leverage,
            }
            log.info(f"✓ متصل شد — حساب:{info.login}  موجودی:{info.balance:.2f}{info.currency}")
        self.connected = True
        return True

    def disconnect(self):
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()
            self.connected = False

    # ── دریافت داده ────────────────────────────────────────────────────────────

    def get_bars(self, symbol: str, n: int = 500) -> Optional[pd.DataFrame]:
        if not self.connected or not MT5_AVAILABLE:
            # فالبک: یاهو فایننس
            try:
                from forex_robot.data.fetcher import fetch_data
                df = fetch_data(symbol, self.timeframe)
                return df.tail(n)
            except Exception as e:
                log.error(f"خطا دریافت داده {symbol}: {e}")
                return None
        tf_code = TF_MAP.get(self.timeframe, mt5.TIMEFRAME_D1)
        rates   = mt5.copy_rates_from_pos(symbol, tf_code, 0, n)
        if rates is None or len(rates) == 0:
            log.warning(f"داده‌ای برای {symbol} نبود")
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        df = df.rename(columns={
            "open":"open","high":"high","low":"low",
            "close":"close","tick_volume":"volume"
        })
        return df[["open","high","low","close","volume"]]

    # ── تولید سیگنال ──────────────────────────────────────────────────────────

    def generate_signal(self, symbol: str) -> Tuple[int, float, dict]:
        """
        Returns: (signal, sl_pips, info)
        signal: 1=BUY, -1=SELL, 0=flat
        """
        df = self.get_bars(symbol, 500)
        if df is None or len(df) < 100:
            return 0, 0.0, {}
        df_ind = add_all_indicators(df)
        signals, sl_series = self.strategy_fn(df_ind)
        last_sig = int(signals.iloc[-1])
        last_sl  = float(sl_series.iloc[-1])
        last_row = df_ind.iloc[-1]
        info = {
            "close":   float(last_row["close"]),
            "atr14":   float(last_row.get("atr14", 0)),
            "rsi14":   float(last_row.get("rsi14", 50)),
            "adx":     float(last_row.get("adx", 0)),
            "time":    str(df.index[-1]),
        }
        return last_sig, last_sl, info

    # ── محاسبه حجم ────────────────────────────────────────────────────────────

    def calc_lot(self, symbol: str, sl_pips: float, balance: float) -> float:
        risk_amount = balance * (RISK_PCT_PER_TRADE / 100)
        pip_value   = 10.0   # $10 per pip per 1 standard lot (برای pairs با USD)
        if sl_pips <= 0:
            return MIN_LOT
        lot = risk_amount / (sl_pips * pip_value)
        return round(float(np.clip(lot, MIN_LOT, MAX_LOT)), 2)

    # ── ارسال سفارش ───────────────────────────────────────────────────────────

    def place_order(self, symbol: str, side: int, sl_pips: float,
                    price: float) -> Optional[dict]:
        if MODE == "DEMO" or not self.connected:
            direction = "BUY 📈" if side == 1 else "SELL 📉"
            log.info(f"[DEMO] سیگنال: {direction} {symbol}  قیمت={price:.5f}  SL={sl_pips:.1f}pip")
            return {"demo": True, "side": side, "symbol": symbol, "price": price}

        if not MT5_AVAILABLE:
            return None

        balance = mt5.account_info().balance
        lot     = self.calc_lot(symbol, sl_pips, balance)
        pip     = 0.0001 if "JPY" not in symbol else 0.01

        if side == 1:  # BUY
            order_type = mt5.ORDER_TYPE_BUY
            tick       = mt5.symbol_info_tick(symbol)
            entry      = tick.ask
            sl_price   = entry - sl_pips * pip
            tp1_price  = entry + sl_pips * pip * TP1_RR
            tp3_price  = entry + sl_pips * pip * TP3_RR
        else:  # SELL
            order_type = mt5.ORDER_TYPE_SELL
            tick       = mt5.symbol_info_tick(symbol)
            entry      = tick.bid
            sl_price   = entry + sl_pips * pip
            tp1_price  = entry - sl_pips * pip * TP1_RR
            tp3_price  = entry - sl_pips * pip * TP3_RR

        request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    symbol,
            "volume":    lot,
            "type":      order_type,
            "price":     entry,
            "sl":        round(sl_price, 5),
            "tp":        round(tp3_price, 5),
            "deviation": 20,
            "magic":     20260001,
            "comment":   f"Robot1_{self.strategy_name}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error(f"سفارش رد شد: {result.retcode} — {result.comment}")
            return None

        log.info(f"✓ سفارش ارسال شد: {'BUY' if side==1 else 'SELL'} {symbol} "
                 f"lot={lot}  SL={sl_price:.5f}  TP={tp3_price:.5f}")
        return {"order_id": result.order, "lot": lot, "sl": sl_price, "tp": tp3_price}

    # ── چک معاملات باز ────────────────────────────────────────────────────────

    def count_open_trades(self, symbol: str = None) -> int:
        if not self.connected or not MT5_AVAILABLE:
            return 0
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        magic_pos = [p for p in (positions or []) if p.magic == 20260001]
        return len(magic_pos)

    # ── اجرای یک چرخه سیگنال ─────────────────────────────────────────────────

    def run_cycle(self):
        log.info(f"{'─'*50}")
        log.info(f"چرخه جدید — استراتژی: {self.strategy_name} | TF: {self.timeframe}")
        if self.connected and MT5_AVAILABLE:
            info = mt5.account_info()
            balance = info.balance if info else 0
            log.info(f"موجودی: {balance:.2f}  |  equity: {info.equity:.2f}")
        else:
            balance = 1000.0

        for symbol in self.symbols:
            open_count = self.count_open_trades(symbol)
            if open_count >= MAX_OPEN_TRADES:
                log.info(f"{symbol}: حداکثر معامله باز ({open_count}) — رد شد")
                continue

            signal, sl_pips, market_info = self.generate_signal(symbol)

            log.info(f"{symbol}: سیگنال={signal:+d}  ADX={market_info.get('adx',0):.1f}  "
                     f"RSI={market_info.get('rsi14',50):.1f}  SL={sl_pips:.1f}pip  "
                     f"قیمت={market_info.get('close',0):.5f}")

            if signal != 0:
                self.place_order(
                    symbol=symbol,
                    side=signal,
                    sl_pips=sl_pips,
                    price=market_info.get("close", 0),
                )
            else:
                log.info(f"{symbol}: بدون سیگنال")
