"""
╔══════════════════════════════════════════════════════════════╗
║           ROBOT 1 — فارکس تمام‌اتوماتیک                     ║
║   استراتژی: Fibonacci + Ichimoku (بهینه‌شده برای ۲۰۲۶)      ║
║   جفت ارز: GBP/USD  و  EUR/USD  |  تایم‌فریم: روزانه        ║
╚══════════════════════════════════════════════════════════════╝

اجرا:
    python robot1.py              ← اجرای زنده (DEMO یا LIVE بر اساس config.py)
    python robot1.py --backtest   ← بک‌تست سریع
    python robot1.py --signal     ← یک بار سیگنال بگیر و خروج کن
    python robot1.py --status     ← وضعیت فعلی پوزیشن‌ها
"""

import sys, os, argparse, time, logging, schedule
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
import warnings; warnings.filterwarnings("ignore")

from forex_robot.config import (
    SYMBOLS, TIMEFRAME, ACTIVE_STRATEGY, MODE,
    SCAN_TIMES, BACKTEST_START, BACKTEST_CAPITAL,
    RISK_PCT_PER_TRADE, TP1_RR, TP2_RR, TP3_RR,
    TRAIL_AFTER_TP1, LOG_FILE, ENABLE_SOUND,
)
from forex_robot.live.mt5_trader import MT5Trader
from forex_robot.data.fetcher import fetch_data
from forex_robot.strategies.indicators import add_all_indicators
from forex_robot.strategies.optimized_strategies import strategy_fib_ichimoku_retracement
from forex_robot.strategies.strategy_library import strategy_stochastic_reversal
from forex_robot.backtest.engine import BacktestEngine, BacktestConfig, compute_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("Robot1")

BANNER = r"""
╔══════════════════════════════════════════════════════╗
║   ROBOT 1 — فارکس تمام‌اتوماتیک                     ║
║   Fibonacci + Ichimoku  |  GBP/USD & EUR/USD         ║
╚══════════════════════════════════════════════════════╝
"""

def clr(c, t):
    cc = {"g":"\033[92m","r":"\033[91m","y":"\033[93m","c":"\033[96m","b":"\033[1m","0":"\033[0m"}
    return f"{cc.get(c,'')}{t}{cc['0']}"


# ── بک‌تست سریع ───────────────────────────────────────────────────────────────

def run_quick_backtest():
    print(clr("b", "\n  بک‌تست سریع — Fib_Ichi روی GBP/USD + EUR/USD"))
    print(f"  {'─'*60}")
    start_ts = None
    if BACKTEST_START:
        start_ts = __import__("pandas").Timestamp(BACKTEST_START, tz="UTC")

    for sym in SYMBOLS:
        raw = fetch_data(sym, TIMEFRAME)
        if start_ts:
            raw = raw[raw.index >= start_ts]
        df = add_all_indicators(raw.copy())
        signals, sl_pips = strategy_fib_ichimoku_retracement(df)
        cfg = BacktestConfig(
            initial_capital=BACKTEST_CAPITAL, symbol=sym, timeframe=TIMEFRAME,
            risk_pct=RISK_PCT_PER_TRADE,
            tp1_rr=TP1_RR, tp2_rr=TP2_RR, tp3_rr=TP3_RR,
            trail_after_tp1=TRAIL_AFTER_TP1,
        )
        engine = BacktestEngine(cfg)
        trades, equity = engine.run(df, signals, sl_pips, "Fib_Ichi")
        if not trades:
            print(f"  {sym}: بدون معامله")
            continue
        m = compute_metrics(trades, equity, BACKTEST_CAPITAL)
        ret = m["total_return_pct"]
        rc  = clr("g", f"{ret:+.2f}%") if ret >= 0 else clr("r", f"{ret:+.2f}%")
        print(f"  {sym}: بازدهی={rc}  نرخ برد={m['win_rate_pct']:.1f}%  "
              f"MaxDD={m['max_drawdown_pct']:.1f}%  معاملات={m['total_trades']}  "
              f"سرمایه=€{m['final_equity']:,.2f}")


# ── اجرای زنده ────────────────────────────────────────────────────────────────

def make_trader() -> MT5Trader:
    return MT5Trader(
        strategy_name=ACTIVE_STRATEGY,
        timeframe=TIMEFRAME,
        symbols=SYMBOLS,
    )


def run_live():
    print(BANNER)
    print(clr("b", f"  حالت: {MODE}  |  استراتژی: {ACTIVE_STRATEGY}  |  TF: {TIMEFRAME}"))
    print(f"  جفت ارزها: {', '.join(SYMBOLS)}")
    print(f"  ریسک هر معامله: {RISK_PCT_PER_TRADE}%")
    print(f"  TP1:{TP1_RR}R  TP2:{TP2_RR}R  TP3:{TP3_RR}R")
    print(f"  زمان‌بندی اسکن: {', '.join(SCAN_TIMES)} (GMT)\n")

    trader = make_trader()
    connected = trader.connect()
    if not connected:
        print(clr("y", "  ⚠ MT5 متصل نشد — حالت سیگنال‌فقط (بدون معامله واقعی)"))

    # اجرای فوری یک چرخه
    print(clr("c", "  اجرای اولین چرخه…"))
    trader.run_cycle()

    # زمان‌بندی خودکار
    for t in SCAN_TIMES:
        schedule.every().day.at(t).do(trader.run_cycle)
        print(f"  برنامه: هر روز {t} GMT")

    print(clr("g", "\n  ربات روشن است — Ctrl+C برای توقف\n"))
    log.info("Robot1 شروع به کار کرد")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print(clr("y", "\n  ربات متوقف شد"))
        trader.disconnect()


# ── گرفتن سیگنال یک‌بار ──────────────────────────────────────────────────────

def run_signal_once():
    trader = make_trader()
    trader.connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  سیگنال‌های فعلی  [{now}]")
    print(f"  {'─'*50}")
    for sym in SYMBOLS:
        sig, sl, info = trader.generate_signal(sym)
        direction = clr("g","BUY  ▲") if sig == 1 else clr("r","SELL ▼") if sig == -1 else clr("y","FLAT  —")
        print(f"  {sym:<8}  {direction}   "
              f"قیمت={info.get('close',0):.5f}  "
              f"ADX={info.get('adx',0):.1f}  "
              f"RSI={info.get('rsi14',50):.1f}  "
              f"SL={sl:.1f}pip")
    trader.disconnect()


# ── وضعیت پوزیشن‌ها ──────────────────────────────────────────────────────────

def run_status():
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            print(clr("r","  MT5 وصل نیست"))
            return
        positions = mt5.positions_get()
        robot_pos = [p for p in (positions or []) if p.magic == 20260001]
        print(f"\n  پوزیشن‌های باز Robot1: {len(robot_pos)}")
        print(f"  {'─'*60}")
        total_pnl = 0
        for p in robot_pos:
            pnl_c = clr("g",f"+{p.profit:.2f}$") if p.profit>=0 else clr("r",f"{p.profit:.2f}$")
            side  = clr("g","BUY") if p.type == 0 else clr("r","SELL")
            print(f"  {p.symbol:<8} {side}  lot={p.volume}  "
                  f"open={p.price_open:.5f}  SL={p.sl:.5f}  TP={p.tp:.5f}  P&L={pnl_c}")
            total_pnl += p.profit
        if robot_pos:
            tc = clr("g",f"+{total_pnl:.2f}$") if total_pnl>=0 else clr("r",f"{total_pnl:.2f}$")
            print(f"  {'─'*60}")
            print(f"  سود/زیان کل: {tc}")
        mt5.shutdown()
    except ImportError:
        print(clr("y","  MT5 نصب نیست — برای وضعیت live نیاز به MT5 است"))


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Robot 1 — فارکس تمام‌اتوماتیک")
    parser.add_argument("--backtest", action="store_true", help="بک‌تست سریع")
    parser.add_argument("--signal",   action="store_true", help="سیگنال الان")
    parser.add_argument("--status",   action="store_true", help="وضعیت پوزیشن‌ها")
    args = parser.parse_args()

    if args.backtest:
        run_quick_backtest()
    elif args.signal:
        run_signal_once()
    elif args.status:
        run_status()
    else:
        run_live()
