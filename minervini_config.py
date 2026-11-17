# ============================================================
#  Minervini SEPA — Configuration
#  Credentials come from the environment - see below.
#    python minervini_alert.py --now   (test immediately)
#    python minervini_alert.py         (run on schedule)
# ============================================================

# --- Telegram Credentials ---
# Never hardcode these: this repository is public.
# GitHub Actions supplies them from repository secrets
# (Settings -> Secrets and variables -> Actions).
# For a local run, set them in your shell first:
#   PowerShell:  $env:TELEGRAM_TOKEN = "..."
#   bash:        export TELEGRAM_TOKEN=...
# Token from @BotFather; chat id from
#   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
import os

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "YOUR_BOT_TOKEN_HERE")

TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# --- Schedule (IST, Mon–Fri only) ---
RUN_TIMES = {
    "15:15": ["breakout"],        # Scan 3 only — BUY signals
    "15:30": ["universe", "vcp"], # Scan 1 + Scan 2 — watchlist update
}

# --- Filters ---
MIN_PRICE = 50       # Ignore stocks below this price (₹)
MAX_PRICE = 50000    # Ignore stocks above this price (₹)
MAX_STOCKS_PER_ALERT = 15  # Cap results per message to avoid Telegram limit

# --- Chartink scan clauses ---
# You can edit these if you want to tighten/loosen the criteria
SCANS = {
    "universe": {
        "name": "Trend Template (Universe)",
        "emoji": "📊",
        "description": "All 8 criteria — master watchlist",
        "clause": (
            "( [Daily] close > [Daily] sma(close,150,0) ) "
            "AND ( [Daily] close > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] sma(close,150,0) > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] sma(close,200,0) > [Daily] sma(close,221,0) ) "
            "AND ( [Daily] sma(close,50,0) > [Daily] sma(close,150,0) ) "
            "AND ( [Daily] sma(close,50,0) > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] close > [Daily] sma(close,50,0) ) "
            "AND ( [Daily] close >= 1.25 * [Daily] lowest(low,252,0) ) "
            "AND ( [Daily] close >= 0.75 * [Daily] highest(high,252,0) ) "
            "AND ( [Daily] close > [Daily] close 63 candles ago * 1.05 )"
        ),
    },
    "vcp": {
        "name": "VCP Forming (Coiling Setups)",
        "emoji": "🔄",
        "description": "Range contraction + volume dry-up — base forming",
        "clause": (
            "( [Daily] close > [Daily] sma(close,150,0) ) "
            "AND ( [Daily] close > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] sma(close,150,0) > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] sma(close,200,0) > [Daily] sma(close,221,0) ) "
            "AND ( [Daily] sma(close,50,0) > [Daily] sma(close,150,0) ) "
            "AND ( [Daily] sma(close,50,0) > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] close > [Daily] sma(close,50,0) ) "
            "AND ( [Daily] close >= 1.25 * [Daily] lowest(low,252,0) ) "
            "AND ( [Daily] close >= 0.75 * [Daily] highest(high,252,0) ) "
            "AND ( [Daily] close > [Daily] close 63 candles ago * 1.05 ) "
            "AND ( [Daily] highest(high,30,0) - [Daily] lowest(low,30,0) < 0.80 * ( [Daily] highest(high,60,0) - [Daily] lowest(low,60,0) ) ) "
            "AND ( [Daily] volume < [Daily] sma(volume,50,0) )"
        ),
    },
    "breakout": {
        "name": "VCP Breakout (BUY Signal)",
        "emoji": "🚀",
        "description": "Pivot breakout + volume surge — enter tomorrow at open",
        "clause": (
            "( [Daily] close > [Daily] sma(close,150,0) ) "
            "AND ( [Daily] close > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] sma(close,150,0) > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] sma(close,200,0) > [Daily] sma(close,221,0) ) "
            "AND ( [Daily] sma(close,50,0) > [Daily] sma(close,150,0) ) "
            "AND ( [Daily] sma(close,50,0) > [Daily] sma(close,200,0) ) "
            "AND ( [Daily] close > [Daily] sma(close,50,0) ) "
            "AND ( [Daily] close >= 1.25 * [Daily] lowest(low,252,0) ) "
            "AND ( [Daily] close >= 0.75 * [Daily] highest(high,252,0) ) "
            "AND ( [Daily] close > [Daily] close 63 candles ago * 1.05 ) "
            "AND ( [Daily] close > [Daily] highest(high,30,1) ) "
            "AND ( [Daily] volume > 1.5 * [Daily] sma(volume,50,0) )"
        ),
    },
}
