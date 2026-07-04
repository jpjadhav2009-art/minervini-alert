# ============================================================
# Minervini SEPA — Configuration
# Fill in your Telegram credentials below, then run:
# python minervini_alert.py --now (test immediately)
# python minervini_alert.py (run on schedule)
# ============================================================

# --- Telegram Credentials ---
# SECURITY: do NOT put a real token here. Set it as a GitHub Actions secret
# named TELEGRAM_TOKEN instead -- minervini_alert.py already reads it from
# the environment and overrides this placeholder at runtime. The previous
# token that was hardcoded here was exposed on a PUBLIC repo -- revoke it
# via @BotFather (/revoke) and generate a new one before using this again.
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Not sensitive on its own (just a numeric chat id), fine to keep committed.
TELEGRAM_CHAT_ID = "236473272"

# --- Schedule (IST, Mon–Fri only) ---
RUN_TIMES = {
    "15:15": ["breakout"],          # Scan 3 only — BUY signals
    "15:30": ["universe", "vcp"],   # Scan 1 + Scan 2 — watchlist update
}

# --- Filters ---
MIN_PRICE = 50               # Ignore stocks below this price (₹)
MAX_PRICE = 50000            # Ignore stocks above this price (₹)
MAX_STOCKS_PER_ALERT = 15    # Cap results per message to avoid Telegram limit

# ============================================================
# --- Trading Automation (Paper) ---
# Paper mode uses Yahoo Finance prices only -- no broker credentials needed
# until you're ready to place real orders. Keep PAPER_TRADING = True until
# you've watched it run cleanly for a few weeks.
# ============================================================
PAPER_TRADING      = True     # keep True until ready to go live
CAPITAL            = 500000   # Rs 5,00,000 paper capital
RISK_PERCENT       = 1.0      # % of capital risked per trade (sizing basis)
MAX_OPEN_POSITIONS = 8        # cap concurrent open positions

# Trailing-stop rule: breakeven at +1R, then trail below the rising 50-SMA
BREAKEVEN_AT_R   = 1.0    # move stop to entry price once trade is up this many R
TRAIL_SMA_LEN    = 50     # trail stop below this SMA once breakeven has triggered
TARGET_R_PARTIAL = 2.0    # book half the position at this many R
TARGET_R_FULL    = 3.0    # exit the remainder at this many R (or trail stop, whichever first)

DATA_DIR = "data"   # where watchlists + open_positions.json are persisted (committed by CI)

# --- Angel One SmartAPI (only needed once PAPER_TRADING = False) ---
# Leave blank while paper trading. When going live, set these as GitHub
# Actions secrets (ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD,
# ANGEL_TOTP_SECRET) -- never hardcode them here.
ANGEL_API_KEY     = ""
ANGEL_CLIENT_ID   = ""
ANGEL_PASSWORD    = ""
ANGEL_TOTP_SECRET = ""

# --- Chartink scan clauses ---
# Kept for reference / Chartink manual use. The live yfinance-based scan in
# minervini_alert.py implements the same 8 criteria directly in Python.
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
