"""
Minervini SEPA — Telegram Alert Automation
-------------------------------------------
Runs Chartink scans at 3:15 PM and 3:30 PM IST (Mon–Fri)
and sends results to Telegram.

Usage:
  python minervini_alert.py          # Start scheduler (keep running)
  python minervini_alert.py --now    # Run all scans immediately (test)

Requirements:
  pip install requests schedule pytz
"""

import sys
import time
import logging
import requests
import schedule
import pytz
from datetime import datetime

import minervini_config as cfg

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# ─── Helpers ─────────────────────────────────────────────────────────────────

def now_ist() -> datetime:
    return datetime.now(IST)


def is_weekday() -> bool:
    return now_ist().weekday() < 5  # Mon=0 … Fri=4


def format_volume(vol: float) -> str:
    """Convert volume number to human-readable string (L = lakhs)."""
    if vol >= 1_00_00_000:
        return f"{vol/1_00_00_000:.1f}Cr"
    elif vol >= 1_00_000:
        return f"{vol/1_00_000:.1f}L"
    elif vol >= 1_000:
        return f"{vol/1_000:.1f}K"
    return str(int(vol))


# ─── Chartink Scraper ────────────────────────────────────────────────────────

CHARTINK_URL = "https://chartink.com/screener/process"
CHARTINK_HOME = "https://chartink.com/screener/"


def run_chartink_scan(scan_clause: str) -> list[dict]:
    """
    POST a scan clause to Chartink and return a list of stock dicts.
    Each dict: {name, nsecode, close, per_chg, volume}
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": CHARTINK_HOME,
        "X-Requested-With": "XMLHttpRequest",
    })

    # Step 1: fetch CSRF token
    try:
        resp = session.get(CHARTINK_HOME, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach Chartink homepage: {e}")

    # Extract CSRF token from meta tag
    csrf_token = None
    for line in resp.text.splitlines():
        if 'csrf-token' in line and 'content=' in line:
            # <meta name="csrf-token" content="TOKEN">
            start = line.find('content="') + len('content="')
            end = line.find('"', start)
            csrf_token = line[start:end]
            break

    if not csrf_token:
        raise RuntimeError("Could not find CSRF token on Chartink homepage.")

    session.headers.update({
        "X-CSRF-Token": csrf_token,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })

    # Step 2: POST scan
    payload = {"scan_clause": scan_clause}
    try:
        resp = session.post(CHARTINK_URL, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Chartink scan request failed: {e}")
    except ValueError:
        raise RuntimeError(f"Chartink returned non-JSON response: {resp.text[:200]}")

    stocks = data.get("data", [])

    # Filter by price
    filtered = [
        s for s in stocks
        if cfg.MIN_PRICE <= float(s.get("close", 0)) <= cfg.MAX_PRICE
    ]

    return filtered[:cfg.MAX_STOCKS_PER_ALERT]


# ─── Telegram Sender ─────────────────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    """Send a message to Telegram. Returns True on success."""
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": cfg.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()
        if not data.get("ok"):
            log.error(f"Telegram error: {data.get('description', 'unknown')}")
            return False
        return True
    except requests.RequestException as e:
        log.error(f"Telegram request failed: {e}")
        return False


def validate_telegram_config() -> bool:
    """Check that credentials are filled in."""
    if cfg.TELEGRAM_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.error("❌  TELEGRAM_TOKEN not set in minervini_config.py")
        return False
    if cfg.TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        log.error("❌  TELEGRAM_CHAT_ID not set in minervini_config.py")
        return False
    return True


# ─── Message Builder ─────────────────────────────────────────────────────────

def build_message(scan_key: str, stocks: list[dict]) -> str:
    scan = cfg.SCANS[scan_key]
    ts = now_ist().strftime("%d %b %Y  %H:%M IST")
    emoji = scan["emoji"]
    name = scan["name"]
    desc = scan["description"]
    divider = "─" * 32

    if not stocks:
        return (
            f"{emoji} <b>Minervini SEPA — {name}</b>\n"
            f"<i>{desc}</i>\n"
            f"🕐 {ts}\n"
            f"{divider}\n"
            f"⚪ No stocks found today.\n"
        )

    header = (
        f"{emoji} <b>Minervini SEPA — {name}</b>\n"
        f"<i>{desc}</i>\n"
        f"🕐 {ts}\n"
        f"{divider}\n"
        f"✅ <b>{len(stocks)} stock(s) found</b>\n\n"
    )

    rows = []
    for s in stocks:
        sym = s.get("nsecode", s.get("symbol", "?")).upper()
        close = float(s.get("close", 0))
        chg = float(s.get("per_chg", 0))
        vol = float(s.get("volume", 0))
        trend = "🟢" if chg >= 0 else "🔴"
        sign = "+" if chg >= 0 else ""
        rows.append(
            f"  <code>{sym:<14} ₹{close:>8.1f}  {sign}{chg:.2f}%  {format_volume(vol)}</code> {trend}"
        )

    footer = f"\n{divider}\n"
    if scan_key == "breakout":
        footer += "⚡ <b>ACTION:</b> Review charts. Buy at open tomorrow.\n   SL = VCP base low  |  Target: 2R and 3R"
    elif scan_key == "vcp":
        footer += "👁 <b>WATCH:</b> These are forming bases. Wait for Scan 3 breakout signal."
    else:
        footer += "📋 <b>INFO:</b> SEPA-qualified universe. Cross-check with VCP scans."

    return header + "\n".join(rows) + footer


# ─── Core Job ─────────────────────────────────────────────────────────────────

def run_scans(scan_keys: list[str], label: str = ""):
    if not is_weekday():
        log.info(f"Weekend — skipping {label or scan_keys}")
        return

    log.info(f"Running scans: {scan_keys}")
    for key in scan_keys:
        scan = cfg.SCANS[key]
        log.info(f"  → {scan['name']} ...")
        try:
            stocks = run_chartink_scan(scan["clause"])
            log.info(f"     {len(stocks)} result(s)")
            msg = build_message(key, stocks)
            ok = send_telegram(msg)
            if ok:
                log.info(f"     ✓ Telegram sent")
            else:
                log.warning(f"     ✗ Telegram failed")
        except Exception as e:
            err_msg = f"⚠️ <b>Minervini Bot Error</b>\nScan: {scan['name']}\nError: {str(e)[:300]}"
            log.error(f"     Error: {e}")
            send_telegram(err_msg)

        time.sleep(2)  # Polite delay between scans


def job_1515():
    run_scans(["breakout"], label="3:15 PM Breakout")


def job_1530():
    run_scans(["universe", "vcp"], label="3:30 PM Universe+VCP")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if not validate_telegram_config():
        sys.exit(1)

    # --now flag: run all scans immediately and exit
    if "--now" in sys.argv:
        log.info("⚡  --now flag detected — running all scans immediately")
        ok = send_telegram(
            "🔔 <b>Minervini Bot — Test Run</b>\n"
            "Running all scans now. Results incoming...\n"
            f"🕐 {now_ist().strftime('%d %b %Y  %H:%M IST')}"
        )
        if not ok:
            log.error("Could not send test message. Check your TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.")
            sys.exit(1)
        run_scans(["breakout", "universe", "vcp"], label="Test run")
        log.info("Done.")
        return

    # Startup confirmation
    log.info("Starting Minervini SEPA Alert Bot ...")
    send_telegram(
        "✅ <b>Minervini SEPA Bot Started</b>\n"
        f"Scheduled: 15:15 IST (Breakout) + 15:30 IST (Universe + VCP)\n"
        f"Active: Mon–Fri only\n"
        f"🕐 {now_ist().strftime('%d %b %Y  %H:%M IST')}"
    )

    # Schedule jobs (times in IST via environment; see note below)
    schedule.every().day.at("15:15").do(job_1515)
    schedule.every().day.at("15:30").do(job_1530)

    log.info("Scheduler running. Press Ctrl+C to stop.")
    log.info("Waiting for 15:15 and 15:30 IST ...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")


if __name__ == "__main__":
    main()
