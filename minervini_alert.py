"""
Minervini SEPA — Telegram Alert (Yahoo Finance version)
--------------------------------------------------------
Downloads NSE stock data directly from Yahoo Finance.
No Chartink scraping — works from anywhere including GitHub Actions.

Usage:
  python minervini_alert.py          # Run on schedule (4:00 PM + 4:05 PM IST, after the close)
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
from datetime import datetime, timedelta

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
    format="%(asctime)s IST  %(levelname)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# Log timestamps follow the machine clock, which is UTC on a GitHub runner.
# Convert them so every time this bot prints - logs and alerts alike - is IST.
def _ist_logtime(secs):
    return datetime.fromtimestamp(secs, IST).timetuple()

# staticmethod, not a bare function: a plain function assigned here would be
# bound as a method and called with (self, secs).
logging.Formatter.converter = staticmethod(_ist_logtime)

# ─── NSE Universe (Nifty 500 major stocks) ───────────────────────────────────
# yfinance uses .NS suffix for NSE stocks
# Part 1 - the original watchlist, with symbols Yahoo no longer serves removed
# (renamed or delisted: ZOMATO, TATAMOTORS, GMRINFRA, MCDOWELL-N, ICICILOMBARD,
#  KALPATPOWR, MAHINDCIE, WELSPUNIND, JMFINANCL, GUJGASLTD, ISEC, VERITAS).
# The successors that still trade are Nifty 500 members, so they appear in part 2.
NSE_UNIVERSE_PART1 = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","HCLTECH","WIPRO",
    "NESTLEIND","ULTRACEMCO","BAJFINANCE","TITAN","SUNPHARMA","ONGC","NTPC","POWERGRID",
    "TECHM","BAJAJFINSV","INDUSINDBK","ADANIENT","GRASIM","JSWSTEEL","CIPLA","COALINDIA",
    "BPCL","BRITANNIA","DIVISLAB","EICHERMOT","APOLLOHOSP","TATASTEEL","HINDALCO","DRREDDY",
    "HEROMOTOCO","UPL","ADANIPORTS","SBILIFE","HDFCLIFE","BAJAJ-AUTO","M&M","SHREECEM",
    "TATACONSUM","ADANIGREEN","AMBUJACEM","AUROPHARMA","BANKBARODA","BERGEPAINT","BIOCON","BOSCHLTD",
    "CANBK","CHOLAFIN","COLPAL","DALBHARAT","DABUR","DLF","GAIL","GODREJCP",
    "GODREJPROP","HAL","HAVELLS","HDFCAMC","IDFCFIRSTB","INDUSTOWER","INDIGO","IRCTC",
    "JINDALSTEL","LICI","LUPIN","MARICO","MUTHOOTFIN","NAUKRI","PAGEIND","PIDILITIND",
    "POLYCAB","RECLTD","SIEMENS","SRF","TORNTPHARM","TRENT","TVSMOTOR","VEDL",
    "VOLTAS","PNB","IOC","MOTHERSON","ABCAPITAL","ABFRL","ACC","AARTIIND",
    "APLAPOLLO","ASTRAL","ATUL","AUBANK","BALKRISIND","BATAINDIA","BLUEDART","CANFINHOME",
    "CEATLTD","CESC","CHAMBLFERT","CONCOR","COROMANDEL","CROMPTON","CUMMINSIND","DEEPAKNTR",
    "DIXON","ELGIEQUIP","EMAMILTD","ESCORTS","EXIDEIND","FEDERALBNK","FLUOROCHEM","FORTIS",
    "GLENMARK","GODREJIND","GRANULES","GRAPHITE","HAPPSTMNDS","HUDCO","IGL","INDIAMART",
    "INDHOTEL","INTELLECT","IPCALAB","IRB","JBCHEPHARM","JKCEMENT","JUBLFOOD","KAJARIACER",
    "KEC","KPITTECH","LALPATHLAB","LAURUSLABS","LEMONTREE","LTTS","LUXIND","MANAPPURAM",
    "MAXHEALTH","METROPOLIS","MPHASIS","MRF","NATCOPHARM","NAVINFLUOR","NCC","NHPC",
    "NOCIL","OBEROIRLTY","OFSS","ORIENTELEC","PERSISTENT","PETRONET","PFIZER","PHOENIXLTD",
    "PNBHOUSING","POLYMED","PRAJIND","PRESTIGE","PRINCEPIPE","RBLBANK","RELAXO","RITES",
    "ROUTE","SAREGAMA","SCHAEFFLER","SOBHA","SONACOMS","STLTECH","SUDARSCHEM","SUMICHEM",
    "SUNTV","SUPRAJIT","SUPREMEIND","SYNGENE","TANLA","TATACOMM","TATAINVEST","TATAPOWER",
    "TEAMLEASE","TIMKEN","TORNTPOWER","TRIDENT","UJJIVANSFB","UNIONBANK","UNOMINDA","UTIAMC",
    "VGUARD","VINATIORGA","WELCORP","WESTLIFE","ZYDUSLIFE","AETHER","ALKEM","ANGELONE",
    "BAJAJHCARE","BANDHANBNK","BSOFT","CAMPUS","CARTRADE","CAMS","CDSL","CLEAN",
    "DELHIVERY","DEVYANI","EASEMYTRIP","EDELWEISS","FUSION","GLAND","HOMEFIRST","IDEAFORGE",
    "INDIGOPNTS","IXIGO","JYOTICNC","KAYNES","LATENTVIEW","MAPMYINDIA","MEDPLUS","NYKAA",
    "PAYTM","POLICYBZR","RAINBOW","SIGACHI","SOLARINDS","STARHEALTH","SUPRIYA","TRACXN",
    "UNIPARTS","BIKAJI","GOCOLORS","HARSHA","LANDMARK","POWERINDIA","SANSERA","SENCO",
    "SHYAMMETL","VPRPL","ICICIPRULI",
]

# Part 2 - every Nifty 500 constituent not already covered by part 1.
# Source: NSE ind_nifty500list.csv, fetched 17 Nov 2026.
# DUMMYHEG (an NSE placeholder row) and BAGMANE (no Yahoo listing) removed
# after run #1 of this workflow reported them as the only failed downloads.
NSE_UNIVERSE_PART2 = [
    "360ONE","ABB","ACMESOLAR","AIAENG","AWL","AADHARHFC","AAVAS","ABBOTINDIA",
    "ACE","ACUTAAS","ADANIENSOL","ADANIPOWER","ATGL","ABREL","ABSLAMC","CPPLUS",
    "AEGISLOG","AEGISVOPAK","AFCONS","AFFLE","AJANTPHARM","ABDL","ARE&M","AMBER",
    "ANANDRATHI","ANANTRAJ","ANTHEM","ANURAS","APARINDS","APOLLOTYRE","APTUS","ASAHIINDIA",
    "ASHOKLEY","ASTERDM","ATHERENERG","AIIL","AVANTIFEED","DMART","AZAD","BEML",
    "BLS","BSE","BAJAJHLDNG","BAJAJHFL","BALRAMCHIN","BANKINDIA","MAHABANK",
    "BELRISE","BHARATCOAL","BDL","BEL","BHARATFORG","BHEL","BHARTIHEXA","GROWW",
    "BBOX","BLUESTARCO","FIRSTCRY","BRIGADE","BIRET","CCL","CGPOWER","CIEINDIA",
    "CRISIL","CANHLIFE","CAPLIPOINT","CGCL","CARBORUNIV","CASTROLIND","CEMPRO","CENTRALBK",
    "CMPDI","CHENNPETRO","CHOICEIN","CHOLAHLDNG","CUB","CLEANMAX","COCHINSHIP","COFORGE",
    "COHANCE","CONCORDBIO","CRAFTSMAN","CREDITACC","CUPID","CYIENT","DOMS","DATAPATTNS",
    "DEEPAKFERT","EIDPARRY","EIHOTEL","EMBASSY","ELECON","EMCURE","EMMVEE",
    "ENDURANCE","ENGINERSIN","ETERNAL","FACT","FINCABLES","FSL","FIVESTAR","FORCEMOT",
    "FRACTAL","GVT&D","GMRAIRPORT","GABRIEL","GALLANTT","GRSE","GICRE","GILLETTE",
    "GLAXO","MEDANTA","GPIL","GODFRYPHLP","GRAVITA","GESHIP","GMDCLTD","HBLENGINE",
    "HDBFS","HEGAM","HFCL","HEXT","HSCL","HINDCOPPER","HINDPETRO","HINDZINC",
    "HONASA","HONAUT","HYUNDAI","ICICILIFE","ICICIGI","ICICIAMC","IDBI","IFCI",
    "IIFL","INOXINDIA","IRCON","ITCHOTELS","ITI","INDIACEM","INDIANB","IEX",
    "IOB","IRFC","IREDA","INOXWIND","IGIL","IKS","JBMA","JKTYRE",
    "JMFINANCIL","JSWCEMENT","JSWENERGY","JSWINFRA","JAINREC","JPPOWER","J&KBANK","JINDALSAW",
    "JSL","JIOFIN","JUBLINGREA","JWL","KPRMILL","KEI","KSB","KPIL",
    "KALYANKJIL","KARURVYSYA","KFINTECH","KIRLOSBROS","KIRLOSENG","KIMS","LTF","LGEINDIA",
    "LICHSGFIN","LTFOODS","LTM","LENSKART","LINDEINDIA","LLOYDSME","LODHA","MMTC",
    "MTARTECH","MGL","M&MFIN","MRPL","MANKIND","MFSL","MAZDOCK","MEESHO",
    "MINDACORP","MSUMI","MOTILALOFS","MCX","NBCC","NLCINDIA","NMDC","NSLNISP",
    "NTPCGREEN","NH","NATIONALUM","NAVA","NETWEB","NEULANDLAB","NAM-INDIA","NUVAMA",
    "NUVOCO","OIL","OLAELEC","OLECTRA","ONESOURCE","PCBL","PGEL","PIIND",
    "PTCIL","PVRINOX","PARADEEP","PATANJALI","PWL","PINELABS","PIRAMALFIN","PPLPHARMA",
    "POONAWALLA","PFC","PREMIERENE","PFOCUS","PRIVISCL","RRKABEL","RHIM","RADICO",
    "RVNL","RAILTEL","RKFORGE","REDINGTON","RPOWER","RUBICON","SBICARD","SJVN",
    "SHRIPISTON","SAGILITY","SAILIFE","SAMMAANCAP","SARDAEN","SCHNEIDER","SCI","SHRIRAMFIN",
    "ENRIN","SIGNATURE","SAIL","SUNDARMFIN","SUZLON","SWANCORP","SWIGGY","SYRMA",
    "TBOTEK","TDPOWERSYS","TATACAP","TATACHEM","TATAELXSI","TMCV","TMPV","TATATECH",
    "TTML","TECHNOE","TEGA","TEJASNET","TENNIND","THANGAMAYL","NIACL","RAMCOCEM",
    "THERMAX","TITAGARH","TARIL","TRITURBINE","TIINDIA","UCOBANK","UBL","UNITDSPR",
    "URBANCO","USHAMART","VTL","VBL","VAML","VISL","VOGL","VEDPOWER",
    "VIJAYA","VMM","IDEA","WAAREEENER","WELSPUNLIV","WHIRLPOOL","WOCKPHARMA","YESBANK",
    "ZFCVINDIA","ZEEL","ZENTEC","ZENSARTECH","ZYDUSWELL","ECLERX",
]

NSE_UNIVERSE_PART1 = list(dict.fromkeys(NSE_UNIVERSE_PART1))
NSE_UNIVERSE_PART2 = list(dict.fromkeys(NSE_UNIVERSE_PART2))

PART_NO = 1                        # overridden by --part on the command line
NSE_UNIVERSE = NSE_UNIVERSE_PART1  # the universe the current run scans

# ─── Helpers ──────────────────────────────────────────────────────────────────

def now_ist() -> datetime:
    return datetime.now(IST)

SESSION_ROLLOVER_HOUR = 6   # a run before 6 AM IST belongs to the previous session

def session_date() -> datetime:
    """The trading session this run reports on.

    GitHub's scheduler routinely delivers these runs 8+ hours late, well past
    midnight IST, so the wall clock is not the session being scanned. A run in
    the small hours is reporting on the previous day's close.
    """
    t = now_ist()
    if t.hour < SESSION_ROLLOVER_HOUR:
        t -= timedelta(days=1)
    return t

def is_weekday() -> bool:
    return session_date().weekday() < 5

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
    m = dict(SCAN_META[scan_type])
    m["desc"] = f"{m['desc']}\nPart {PART_NO} · {len(NSE_UNIVERSE)} stocks"
    ts = f"{session_date():%d %b %Y} close  |  sent {now_ist():%H:%M IST}"
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

def job_breakout():
    run_scans(["breakout"], label="4:00 PM Breakout")

def job_watchlist():
    run_scans(["universe", "vcp"], label="4:05 PM Universe+VCP")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global NSE_UNIVERSE, PART_NO

    if not validate_config():
        sys.exit(1)

    if "--part" in sys.argv:
        try:
            PART_NO = int(sys.argv[sys.argv.index("--part") + 1])
        except (IndexError, ValueError):
            log.error("--part needs a number: --part 1 or --part 2")
            sys.exit(2)
    if PART_NO not in (1, 2):
        log.error(f"Unknown part {PART_NO} - expected 1 or 2")
        sys.exit(2)

    NSE_UNIVERSE = NSE_UNIVERSE_PART2 if PART_NO == 2 else NSE_UNIVERSE_PART1
    log.info(f"Scanning part {PART_NO}: {len(NSE_UNIVERSE)} stocks")

    if "--now" in sys.argv:
        log.info("⚡  --now flag — running all scans immediately")
        if not is_weekday():
            log.info(f"{session_date():%a %d %b} is not a trading day - nothing to scan.")
            return
        send_telegram(
            f"🔔 <b>Minervini Bot — Test Run (Part {PART_NO})</b>\n"
            "Downloading NSE data from Yahoo Finance...\n"
            f"🕐 {now_ist().strftime('%d %b %Y  %H:%M IST')}"
        )
        failures = run_scans(["breakout", "universe", "vcp"], label="Test run")
        if failures:
            log.error(f"{failures} alert(s) failed to send - exiting non-zero")
            sys.exit(1)
        log.info(f"Done - all alerts delivered for the {session_date():%a %d %b} close.")
        return

    send_telegram(
        "✅ <b>Minervini SEPA Bot Started</b>\n"
        "Source: Yahoo Finance (NSE data)\n"
        "Schedule: 16:00 IST (Breakout) + 16:05 IST (Universe + VCP)\n"
        f"Universe: {len(NSE_UNIVERSE)} NSE stocks\n"
        f"🕐 {now_ist().strftime('%d %b %Y  %H:%M IST')}"
    )

    # NSE closes at 15:30 IST. Scanning before then reads a still-forming
    # daily candle, so every run waits for the confirmed close.
    # schedule reads the machine clock, so run this on an IST machine.
    schedule.every().day.at("16:00").do(job_breakout)
    schedule.every().day.at("16:05").do(job_watchlist)

    log.info("Scheduler running. Waiting for 16:00 and 16:05 IST ...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Bot stopped.")

if __name__ == "__main__":
    main()
