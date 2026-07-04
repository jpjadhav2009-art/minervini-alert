"""
minervini_trader.py — Paper-trading automation for the Minervini SEPA scanner
------------------------------------------------------------------------------
Two modes, both driven by GitHub Actions on a schedule:

  python minervini_trader.py --enter
      Run at market open (~9:16 AM IST). Reads the most recent
      data/breakout_<date>.json watchlist (written by minervini_alert.py's
      3:15 PM breakout scan the previous trading day) and opens new PAPER
      positions, sized at RISK_PERCENT of CAPITAL against each stock's VCP
      base-low stop.

  python minervini_trader.py --trail
      Run end-of-day (~15:35 IST, after the close). For every open
      position: moves the stop to breakeven once the trade is up
      BREAKEVEN_AT_R, then trails it below the rising TRAIL_SMA_LEN-day SMA
      (never lowers it). Books half the position at TARGET_R_PARTIAL,
      closes the remainder at TARGET_R_FULL or if the trailing stop is hit.

All state lives in data/open_positions.json and data/closed_positions.json,
committed back to the repo by the GitHub Actions workflow after each run
(this script only reads/writes files -- it never touches git itself).

PAPER_TRADING only -- no broker order is placed. Angel One SmartAPI
integration gets added here once you're ready to go live (see
minervini_config.py's ANGEL_* placeholders).
"""

import os
import sys
import json
import glob
import logging
from datetime import datetime

import pytz
import yfinance as yf

import minervini_config as cfg
from minervini_alert import send_telegram, format_volume

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


DATA_DIR = getattr(cfg, "DATA_DIR", "data")
OPEN_FILE = os.path.join(DATA_DIR, "open_positions.json")
CLOSED_FILE = os.path.join(DATA_DIR, "closed_positions.json")


# ─── State I/O ────────────────────────────────────────────────────────────────

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to read {path}: {e} -- starting from empty state")
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_open_positions() -> list:
    return load_json(OPEN_FILE, [])


def save_open_positions(positions: list):
    save_json(OPEN_FILE, positions)


def append_closed_position(record: dict):
    closed = load_json(CLOSED_FILE, [])
    closed.append(record)
    save_json(CLOSED_FILE, closed)


# ─── Price helpers ────────────────────────────────────────────────────────────

def fetch_ltp(symbol: str) -> float | None:
    """Best-effort current/last price for entry sizing at market open."""
    ticker = symbol + ".NS"
    try:
        t = yf.Ticker(ticker)
        price = t.fast_info.get("last_price")
        if price:
            return float(price)
    except Exception:
        pass
    try:
        hist = yf.download(ticker, period="5d", interval="1d", progress=False)
        if len(hist):
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        log.error(f"  {symbol}: LTP fetch failed: {e}")
    return None


def fetch_daily_history(symbol: str, period: str = "6mo"):
    """Daily OHLC history used for EOD trailing-stop / target checks."""
    ticker = symbol + ".NS"
    try:
        hist = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
        if hist is None or len(hist) == 0:
            return None
        return hist
    except Exception as e:
        log.error(f"  {symbol}: history fetch failed: {e}")
        return None


# ─── Watchlist lookup ─────────────────────────────────────────────────────────

def latest_breakout_watchlist() -> dict | None:
    """Most recently written data/breakout_<date>.json (yesterday's EOD scan)."""
    pattern = os.path.join(DATA_DIR, "breakout_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    latest = files[-1]
    try:
        with open(latest, "r", encoding="utf-8") as f:
            payload = json.load(f)
        log.info(f"Using watchlist: {latest} ({len(payload.get('stocks', []))} stock(s), dated {payload.get('date')})")
        return payload
    except Exception as e:
        log.error(f"Failed to read {latest}: {e}")
        return None


# ─── Position sizing ──────────────────────────────────────────────────────────

def position_size(capital: float, risk_pct: float, entry: float, stop: float) -> int:
    risk_amount = capital * (risk_pct / 100.0)
    sl_distance = entry - stop
    if sl_distance <= 0:
        return 0
    return int(risk_amount // sl_distance)


# ─── ENTER mode ───────────────────────────────────────────────────────────────

def run_enter():
    if now_ist().weekday() >= 5:
        log.info("Weekend -- skipping entry run")
        return

    watchlist = latest_breakout_watchlist()
    if not watchlist or not watchlist.get("stocks"):
        log.info("No breakout watchlist available -- nothing to enter today")
        return

    open_positions = load_open_positions()
    open_symbols = {p["symbol"] for p in open_positions if p["status"] == "open"}
    open_count = len(open_symbols)

    entered = []
    for stock in watchlist["stocks"]:
        symbol = stock["symbol"]
        base_low = stock.get("base_low")

        if symbol in open_symbols:
            log.info(f"  {symbol}: already have an open position -- skipping")
            continue
        if open_count >= cfg.MAX_OPEN_POSITIONS:
            log.info(f"  {symbol}: MAX_OPEN_POSITIONS ({cfg.MAX_OPEN_POSITIONS}) reached -- skipping")
            continue
        if base_low is None:
            log.info(f"  {symbol}: no base_low computed -- skipping")
            continue

        entry_price = fetch_ltp(symbol)
        if entry_price is None:
            log.info(f"  {symbol}: could not fetch entry price -- skipping")
            continue
        if entry_price <= base_low:
            log.info(f"  {symbol}: price ({entry_price}) already below base_low ({base_low}) -- skipping, setup invalidated")
            continue

        qty = position_size(cfg.CAPITAL, cfg.RISK_PERCENT, entry_price, base_low)
        if qty < 1:
            log.info(f"  {symbol}: position size < 1 share at this risk -- skipping")
            continue

        r_distance = entry_price - base_low
        record = {
            "symbol": symbol,
            "status": "open",
            "entry_date": now_ist().strftime("%Y-%m-%d"),
            "entry_price": round(entry_price, 2),
            "initial_stop": round(float(base_low), 2),
            "current_stop": round(float(base_low), 2),
            "qty": qty,
            "initial_qty": qty,
            "breakeven_triggered": False,
            "partial_booked": False,
            "target_partial": round(entry_price + cfg.TARGET_R_PARTIAL * r_distance, 2),
            "target_full": round(entry_price + cfg.TARGET_R_FULL * r_distance, 2),
            "booked_pnl": 0.0,
            "exit_price": None,
            "exit_date": None,
            "exit_reason": None,
        }
        open_positions.append(record)
        open_symbols.add(symbol)
        open_count += 1
        entered.append(record)

        send_telegram(
            f"🟢 <b>Minervini — PAPER ENTRY</b>\n"
            f"<code>{symbol}</code>\n"
            f"Entry: ₹{entry_price:,.2f}  Qty: {qty}\n"
            f"Stop: ₹{base_low:,.2f}  (initial risk ₹{r_distance*qty:,.2f})\n"
            f"Target 2R: ₹{record['target_partial']:,.2f}  Target 3R: ₹{record['target_full']:,.2f}\n"
            f"🕐 {now_ist().strftime('%d %b %Y %H:%M IST')}"
        )

    save_open_positions(open_positions)
    log.info(f"Entry run complete: {len(entered)} new position(s), {open_count} total open")

    if not entered:
        log.info("No new entries taken this morning")


# ─── TRAIL mode ───────────────────────────────────────────────────────────────

def run_trail():
    open_positions = load_open_positions()
    if not open_positions:
        log.info("No open positions -- nothing to trail")
        return

    changed = False
    for pos in open_positions:
        if pos["status"] != "open":
            continue

        symbol = pos["symbol"]
        hist = fetch_daily_history(symbol)
        if hist is None or len(hist) < cfg.TRAIL_SMA_LEN:
            log.info(f"  {symbol}: not enough history to trail -- leaving as-is")
            continue

        latest_close = float(hist["Close"].iloc[-1])
        latest_low = float(hist["Low"].iloc[-1])
        latest_high = float(hist["High"].iloc[-1])

        entry_price = pos["entry_price"]
        initial_stop = pos["initial_stop"]
        r_distance = entry_price - initial_stop
        if r_distance <= 0:
            continue

        current_r = (latest_close - entry_price) / r_distance
        old_stop = pos["current_stop"]

        # 1) Breakeven trigger
        if not pos["breakeven_triggered"] and current_r >= cfg.BREAKEVEN_AT_R:
            pos["current_stop"] = max(pos["current_stop"], entry_price)
            pos["breakeven_triggered"] = True
            log.info(f"  {symbol}: breakeven triggered (R={current_r:.2f}) -- stop moved to {pos['current_stop']}")

        # 2) Trail below rising SMA once breakeven has triggered (only ever raises the stop)
        if pos["breakeven_triggered"]:
            sma = float(hist["Close"].rolling(cfg.TRAIL_SMA_LEN).mean().iloc[-1])
            if sma == sma:  # not NaN
                pos["current_stop"] = max(pos["current_stop"], round(sma, 2))

        if pos["current_stop"] != old_stop:
            changed = True
            log.info(f"  {symbol}: stop trailed {old_stop} -> {pos['current_stop']}")

        # 3) Exit checks (stop hit takes priority over targets on the same bar)
        if latest_low <= pos["current_stop"]:
            exit_price = pos["current_stop"]
            realized = pos["booked_pnl"] + (exit_price - entry_price) * pos["qty"]
            pos["status"] = "closed"
            pos["exit_price"] = round(exit_price, 2)
            pos["exit_date"] = now_ist().strftime("%Y-%m-%d")
            pos["exit_reason"] = "Stop hit" if not pos["breakeven_triggered"] else "Trailing stop hit"
            append_closed_position({**pos, "realized_pnl": round(realized, 2)})
            send_telegram(
                f"🔴 <b>Minervini — PAPER EXIT (Stop)</b>\n"
                f"<code>{symbol}</code>\n"
                f"Exit: ₹{exit_price:,.2f}  Qty: {pos['qty']}\n"
                f"Realized P&amp;L: ₹{realized:,.2f}\n"
                f"Reason: {pos['exit_reason']}\n"
                f"🕐 {now_ist().strftime('%d %b %Y %H:%M IST')}"
            )
            changed = True
            continue

        if not pos["partial_booked"] and latest_high >= pos["target_partial"]:
            half_qty = pos["qty"] // 2
            if half_qty >= 1:
                booked = (pos["target_partial"] - entry_price) * half_qty
                pos["booked_pnl"] += booked
                pos["qty"] -= half_qty
                pos["partial_booked"] = True
                send_telegram(
                    f"🟡 <b>Minervini — PAPER PARTIAL EXIT (2R)</b>\n"
                    f"<code>{symbol}</code>\n"
                    f"Booked: ₹{pos['target_partial']:,.2f} x {half_qty}  (₹{booked:,.2f})\n"
                    f"Remaining qty: {pos['qty']}, trailing continues\n"
                    f"🕐 {now_ist().strftime('%d %b %Y %H:%M IST')}"
                )
                changed = True

        elif latest_high >= pos["target_full"]:
            exit_price = pos["target_full"]
            realized = pos["booked_pnl"] + (exit_price - entry_price) * pos["qty"]
            pos["status"] = "closed"
            pos["exit_price"] = round(exit_price, 2)
            pos["exit_date"] = now_ist().strftime("%Y-%m-%d")
            pos["exit_reason"] = "Target 3R hit"
            append_closed_position({**pos, "realized_pnl": round(realized, 2)})
            send_telegram(
                f"🟢 <b>Minervini — PAPER EXIT (3R Target)</b>\n"
                f"<code>{symbol}</code>\n"
                f"Exit: ₹{exit_price:,.2f}  Qty: {pos['qty']}\n"
                f"Realized P&amp;L: ₹{realized:,.2f}\n"
                f"🕐 {now_ist().strftime('%d %b %Y %H:%M IST')}"
            )
            changed = True

    if changed:
        save_open_positions(open_positions)
    log.info("Trail run complete")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if "--enter" in sys.argv:
        run_enter()
    elif "--trail" in sys.argv:
        run_trail()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
