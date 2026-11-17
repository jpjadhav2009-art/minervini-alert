"""
Minervini SEPA — Telegram Alert (Yahoo Finance version)
--------------------------------------------------------
Downloads NSE stock data directly from Yahoo Finance.
No Chartink scraping — works from anywhere including GitHub Actions.

Usage:
  python minervini_alert.py          # Run on schedule (3:15 PM + 3:30 PM IST)
  python minervini_alert.py --now    # Run all scans immediately (test)

Requirements:
  pip install requests schedule pytz yfinance pandas numpy
"""

import os
import sys
import time
import logging
import requests
import schedule
import pytz
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

import minervini_config as cfg

# Allow GitHub Actions secrets to override config file values
_env_token = os.environ.get("TELEGRAM_TOKEN")
_env_chat  = os.environ.get("TELEGRAM_CHAT_ID")
if _env_token:
    cfg.TELEGRAM_TOKEN = _env_token
if _env_chat:
    cfg.TELEGRAM_CHAT_ID = _env_chat

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# ─── NSE Universe (Nifty 500 major stocks) ───────────────────────────────────
# yfinance uses .NS suffix for NSE stocks
NSE_UNIVERSE = [
    # Nifty 50
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","HCLTECH",
    "WIPRO","NESTLEIND","ULTRACEMCO","BAJFINANCE","TITAN","SUNPHARMA","ONGC",
    "NTPC","POWERGRID","TECHM","BAJAJFINSV","INDUSINDBK","TATAMOTORS",
    "ADANIENT","GRASIM","JSWSTEEL","CIPLA","COALINDIA","BPCL","BRITANNIA",
    "DIVISLAB","EICHERMOT","APOLLOHOSP","TATASTEEL","HINDALCO","DRREDDY",
    "HEROMOTOCO","UPL","ADANIPORTS","SBILIFE","HDFCLIFE","BAJAJ-AUTO","M&M",
    "SHREECEM","TATACONSUM",
    # Nifty Next 50
    "ADANIGREEN","AMBUJACEM","AUROPHARMA","BANKBARODA","BERGEPAINT","BIOCON",
    "BOSCHLTD","CANBK","CHOLAFIN","COLPAL","DALBHARAT","DABUR","DLF","GAIL",
    "GODREJCP","GODREJPROP","HAL","HAVELLS","HDFCAMC","ICICIlombard",
    "ICICIPRU","IDFCFIRSTB","INDUSTOWER","INDIGO","IRCTC","JINDALSTEL",
    "LICI","LUPIN","MARICO","MUTHOOTFIN","NAUKRI","PAGEIND","PIDILITIND",
    "POLYCAB","RECLTD","SIEMENS","SRF","TORNTPHARM","TRENT","TVSMOTOR",
    "VEDL","VOLTAS","ZOMATO","PNB","IOC","MOTHERSON","ICICIPRU",
    # Nifty Midcap
    "ABCAPITAL","ABFRL","ACC","AARTIIND","APLAPOLLO","ASTRAL","ATUL",
    "AUBANK","BALKRISIND","BATAINDIA","BLUEDART","CANFINHOME","CEATLTD",
    "CESC","CHAMBLFERT","CONCOR","COROMANDEL","CROMPTON","CUMMINSIND",
    "DEEPAKNTR","DIXON","ELGIEQUIP","EMAMILTD","ESCORTS","EXIDEIND",
    "FEDERALBNK","FLUOROCHEM","FORTIS","GLENMARK","GMRINFRA","GODREJIND",
    "GRANULES","GRAPHITE","GUJGASLTD","HAPPSTMNDS","HUDCO","IGL",
    "INDIAMART","INDHOTEL","INTELLECT","IPCALAB","IRB","ISEC","JBCHEPHARM",
    "JKCEMENT","JMFINANCL","JUBLFOOD","KAJARIACER","KALPATPOWR","KEC",
    "KPITTECH","LALPATHLAB","LAURUSLABS","LEMONTREE","LTTS","LUXIND",
    "MAHINDCIE","MANAPPURAM","MAXHEALTH","MCDOWELL-N","METROPOLIS",
    "MPHASIS","MRF","NATCOPHARM","NAVINFLUOR","NCC","NHPC","NOCIL",
    "OBEROIRLTY","OFSS","ORIENTELEC","PERSISTENT","PETRONET","PFIZER",
    "PHOENIXLTD","PNBHOUSING","POLYMED","PRAJIND","PRESTIGE","PRINCEPIPE",
    "RBLBANK","RELAXO","RITES","ROUTE","SAREGAMA","SCHAEFFLER","SOBHA",
    "SONACOMS","STLTECH","SUDARSCHEM","SUMICHEM","SUNTV","SUPRAJIT",
    "SUPREMEIND","SYNGENE","TANLA","TATACOMM","TATAINVEST","TATAPOWER",
    "TEAMLEASE","TIMKEN","TORNTPOWER","TRIDENT","UJJIVANSFB","UNIONBANK",
    "UNOMINDA","UTIAMC","VGUARD","VINATIORGA","WELCORP","WELSPUNIND",
    "WESTLIFE","ZYDUSLIFE","AETHER","ALKEM","ANGELONE","BAJAJHCARE",
    "BANDHANBNK","BSOFT","CAMPUS","CARTRADE","CAMS","CDSL","CLEAN",
    "DELHIVERY","DEVYANI","EASEMYTRIP","EDELWEISS","FUSION","GLAND",
    "HOMEFIRST","IDEAFORGE","INDIGOPNTS","IXIGO","JYOTICNC","KAYNES",
    "LATENTVIEW","MAPMYINDIA","MEDPLUS","NYKAA","PAYTM","POLICYBZR",
    "RAINBOW","SIGACHI","SOLARINDS","STARHEALTH","SUPRIYA","TRACXN",
    "UNIPARTS","VERITAS","BIKAJI","DELHIVERY","GOCOLORS","HARSHA",
    "LANDMARK","POWERINDIA","SANSERA","SENCO","SHYAMMETL","VPRPL",
]

# Remove duplicates
NSE_UNIVERSE = list(dict.fromkeys(NSE_UNIVERSE))

# ─── Helpers ──────────────────────────────────────────────────────────────────

def now_ist() -> datetime:
    return datetime.now(IST)

def is_weekday() -> bool:
    return now_ist().weekday() < 5

def format_volume(vol: float) -> str:
    if vol >= 1_00_00_000:
        return f"{vol/1_00_00_000:.1f}Cr"
    elif vol >= 1_00_000:
        return f"{vol/1_00_000:.1f}L"
    elif vol >= 1_000:
        return f"{vol/1_000:.1f}K"
    return str(int(vol))

# ─── Data Download ────────────────────────────────────────────────────────────

def download_data() -> pd.DataFrame:
    """Download 15 months of daily OHLCV data for all NSE stocks."""
    tickers = [s + ".NS" for s in NSE_UNIVERSE]
    log.info(f"Downloading data for {len(tickers)} stocks from Yahoo Finance ...")
    raw = yf.download(
        tickers=tickers,
        period="15mo",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    log.info("Download complete.")
    return raw

# ─── Minervini Criteria ───────────────────────────────────────────────────────

def check_stock(raw: pd.DataFrame, symbol: str) -> dict | None:
    """
    Apply all 8 Minervini Trend Template criteria to a stock.
    Returns a result dict if all criteria pass, else None.
    """
    ticker = symbol + ".NS"
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            close  = raw["Close"][ticker].dropna()
            high   = raw["High"][ticker].dropna()
            low    = raw["Low"][ticker].dropna()
            volume = raw["Volume"][ticker].dropna()
        else:
            close  = raw["Close"].dropna()
            high   = raw["High"].dropna()
            low    = raw["Low"].dropna()
            volume = raw["Volume"].dropna()

        if len(close) < 221:
            return None  # Not enough history

        # Moving averages
        sma50  = close.rolling(50).mean()
        sma150 = close.rolling(150).mean()
        sma200 = close.rolling(200).mean()
        sma221 = close.rolling(221).mean()
        avg_vol50 = volume.rolling(50).mean()

        c   = close.iloc[-1]
        s50 = sma50.iloc[-1]
        s150= sma150.iloc[-1]
        s200= sma200.iloc[-1]
        s221= sma221.iloc[-1]
        v   = volume.iloc[-1]
        av  = avg_vol50.iloc[-1]

        # 52-week high/low (252 trading days)
        high52  = high.rolling(252).max().iloc[-1]
        low52   = low.rolling(252).min().iloc[-1]
        close63 = close.iloc[-63] if len(close) >= 63 else None

        # Trend Template — all 8 criteria
        c1 = c > s150 and c > s200
        c2 = s150 > s200
        c3 = s200 > s221
        c4 = s50 > s150 and s50 > s200
        c5 = c > s50
        c6 = c >= 1.25 * low52
        c7 = c >= 0.75 * high52
        c8 = (close63 is not None) and (c > close63 * 1.05)

        if not all([c1, c2, c3, c4, c5, c6, c7, c8]):
            return None

        # Price filter
        if not (cfg.MIN_PRICE <= c <= cfg.MAX_PRICE):
            return None

        # % change
        prev_close = close.iloc[-2] if len(close) >= 2 else c
        pct_chg = ((c - prev_close) / prev_close) * 100

        # VCP flags
        range30 = high.rolling(30).max().iloc[-1] - low.rolling(30).min().iloc[-1]
        range60 = high.rolling(60).max().iloc[-1] - low.rolling(60).min().iloc[-1]
        vcp_forming  = (range30 < 0.80 * range60) and (v < av)
        high30_lag1  = high.iloc[-31:-1].max() if len(high) >= 31 else None
        vcp_breakout = (high30_lag1 is not None) and (c > high30_lag1) and (v > 1.5 * av)

        return {
            "symbol":      symbol,
            "close":       round(c, 2),
            "pct_chg":     round(pct_chg, 2),
            "volume":      v,
            "avg_vol":     av,
            "vcp_forming": vcp_forming,
            "vcp_breakout":vcp_breakout,
        }

    except Exception:
        return None


def run_scan(raw: pd.DataFrame, scan_type: str) -> list[dict]:
    """
    scan_type: "universe" | "vcp" | "breakout"
    Returns list of qualifying stocks, capped at MAX_STOCKS_PER_ALERT.
    """
    results = []
    for symbol in NSE_UNIVERSE:
        r = check_stock(raw, symbol)
        if r is None:
            continue
        if scan_type == "universe":
            results.append(r)
        elif scan_type == "vcp" and r["vcp_forming"]:
            results.append(r)
        elif scan_type == "breakout" and r["vcp_breakout"]:
            results.append(r)

    # Sort by % change descending
    results.sort(key=lambda x: x["pct_chg"], reverse=True)
    return results[:cfg.MAX_STOCKS_PER_ALERT]

# ─── Telegram ─────────────────────────────────────────────────────────────────

SEND_ATTEMPTS = 3   # a single TCP reset should not cost a whole alert

def send_telegram(message: str) -> bool:
    """Send one Telegram message. Retries transient failures; returns success."""
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": cfg.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    for attempt in range(1, SEND_ATTEMPTS + 1):
        tag = f"attempt {attempt}/{SEND_ATTEMPTS}"
        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()

            if data.get("ok"):
                if attempt > 1:
                    log.info(f"     Telegram send succeeded on {tag}")
                return True

            log.error(f"Telegram error ({tag}): {data.get('description')}")

            # Flood control - obey the server's own wait time.
            retry_after = (data.get("parameters") or {}).get("retry_after")
            if retry_after:
                time.sleep(min(int(retry_after), 30))
                continue

            # A 4xx other than 429 means the request itself is bad (message too
            # long, bad chat id, bad HTML) - retrying cannot help.
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                return False

        except Exception as e:
            log.error(f"Telegram request failed ({tag}): {e}")

        if attempt < SEND_ATTEMPTS:
            time.sleep(2 * attempt)       # 2s, then 4s

    return False

def validate_config() -> bool:
    if cfg.TELEGRAM_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.error("TELEGRAM_TOKEN not set in minervini_config.py")
        return False
    if cfg.TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        log.error("TELEGRAM_CHAT_ID not set in minervini_config.py")
        return False
    return True

# ─── Message Builder ──────────────────────────────────────────────────────────

SCAN_META = {
    "universe": {
        "emoji": "📊",
        "name": "Trend Template (Universe)",
        "desc": "All 8 criteria — master watchlist",
        "footer": "📋 <b>INFO:</b> SEPA-qualified universe. Cross-check with VCP scans.",
    },
    "vcp": {
        "emoji": "🔄",
        "name": "VCP Forming (Coiling Setups)",
        "desc": "Range contraction + volume dry-up — base forming",
        "footer": "👁 <b>WATCH:</b> These are forming bases. Wait for Scan 3 breakout signal.",
    },
    "breakout": {
        "emoji": "🚀",
        "name": "VCP Breakout (BUY Signal)",
        "desc": "Pivot breakout + volume surge — enter tomorrow at open",
        "footer": "⚡ <b>ACTION:</b> Review charts. Buy at open tomorrow.\n   SL = VCP base low  |  Target: 2R and 3R",
    },
}

def build_message(scan_type: str, stocks: list[dict]) -> str:
    m = SCAN_META[scan_type]
    ts = now_ist().strftime("%d %b %Y  %H:%M IST")
    div = "─" * 32

    if not stocks:
        return (
            f"{m['emoji']} <b>Minervini SEPA — {m['name']}</b>\n"
            f"<i>{m['desc']}</i>\n"
            f"🕐 {ts}\n{div}\n"
            f"⚪ No stocks found today.\n"
        )

    header = (
        f"{m['emoji']} <b>Minervini SEPA — {m['name']}</b>\n"
        f"<i>{m['desc']}</i>\n"
        f"🕐 {ts}\n{div}\n"
        f"✅ <b>{len(stocks)} stock(s) found</b>\n\n"
    )

    rows = []
    for s in stocks:
        sym  = s["symbol"]
        c    = s["close"]
        chg  = s["pct_chg"]
        vol  = s["volume"]
        sign = "+" if chg >= 0 else ""
        icon = "🟢" if chg >= 0 else "🔴"
        rows.append(
            f"  <code>{sym:<14} ₹{c:>8.1f}  {sign}{chg:.2f}%  {format_volume(vol)}</code> {icon}"
        )

    return header + "\n".join(rows) + f"\n\n{div}\n{m['footer']}"

# ─── Job Runner ───────────────────────────────────────────────────────────────

def run_scans(scan_keys: list[str], label: str = "") -> int:
    """Run the scans. Returns how many alerts did NOT get through."""
    if not is_weekday():
        log.info(f"Weekend — skipping {label}")
        return 0

    log.info(f"Running: {scan_keys}")

    failures = 0

    try:
        raw = download_data()
    except Exception as e:
        msg = f"⚠️ <b>Minervini Bot Error</b>\nFailed to download data: {str(e)[:200]}"
        log.error(msg)
        send_telegram(msg)
        return 1

    for key in scan_keys:
        log.info(f"  → Scanning {key} ...")
        try:
            stocks = run_scan(raw, key)
            log.info(f"     {len(stocks)} result(s)")
            msg = build_message(key, stocks)
            if send_telegram(msg):
                log.info(f"     ✓ Sent")
            else:
                log.error(f"     !! NOT SENT - {key} alert lost")
                failures += 1
        except Exception as e:
            log.error(f"     Error: {e}")
            send_telegram(f"⚠️ <b>Error in {key} scan</b>: {str(e)[:200]}")
            failures += 1
        time.sleep(2)

    return failures

def job_1515():
    run_scans(["breakout"], label="3:15 PM Breakout")

def job_1530():
    run_scans(["universe", "vcp"], label="3:30 PM Universe+VCP")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not validate_config():
        sys.exit(1)

    if "--now" in sys.argv:
        log.info("⚡  --now flag — running all scans immediately")
        send_telegram(
            "🔔 <b>Minervini Bot — Test Run</b>\n"
            "Downloading NSE data from Yahoo Finance...\n"
            f"🕐 {now_ist().strftime('%d %b %Y  %H:%M IST')}"
        )
        failures = run_scans(["breakout", "universe", "vcp"], label="Test run")
        if failures:
            log.error(f"{failures} alert(s) failed to send - exiting non-zero")
            sys.exit(1)
        log.info("Done - all alerts delivered.")
        return

    send_telegram(
        "✅ <b>Minervini SEPA Bot Started</b>\n"
        "Source: Yahoo Finance (NSE data)\n"
        "Schedule: 15:15 IST (Breakout) + 15:30 IST (Universe + VCP)\n"
        f"Universe: {len(NSE_UNIVERSE)} NSE stocks\n"
        f"🕐 {now_ist().strftime('%d %b %Y  %H:%M IST')}"
    )

    schedule.every().day.at("15:15").do(job_1515)
    schedule.every().day.at("15:30").do(job_1530)

    log.info("Scheduler running. Waiting for 15:15 and 15:30 IST ...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Bot stopped.")

if __name__ == "__main__":
    main()
