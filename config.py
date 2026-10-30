"""Configuration centrale (variables d'environnement + valeurs par défaut)."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv optionnel
    pass

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data"))
LOG_DIR = DATA_DIR / "logs"
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "market_history.db"))
WATCHLIST_PATH = DATA_DIR / "watchlist.json"
RULES_PATH = DATA_DIR / "market_rules.json"
DEFAULT_RULES_PATH = ROOT_DIR / "core" / "market_rules.json"

TZ = os.getenv("TZ_MARKET", os.getenv("TZ", "Europe/Paris")) or "Europe/Paris"

# --- Marché ---
GAME_YEAR = os.getenv("GAME_YEAR", "27")
PLATFORM = os.getenv("PLATFORM", "console")  # console | pc
PRICE_MIN = int(os.getenv("PRICE_MIN", "20000"))
PRICE_MAX = int(os.getenv("PRICE_MAX", "400000"))
WATCHLIST_SIZE = int(os.getenv("WATCHLIST_SIZE", "150"))
EVO_CHEAP_MAX = int(os.getenv("EVO_CHEAP_MAX", "20000"))

# --- Sources (surchargeables si FUT.GG change ses URLs) ---
FUTGG_BASE = os.getenv("FUTGG_BASE", "https://www.fut.gg")
FUTGG_POPULAR_URL = os.getenv("FUTGG_POPULAR_URL", f"{FUTGG_BASE}/players/?sorts=-popularity")
FUTGG_LATEST_URL = os.getenv("FUTGG_LATEST_URL", f"{FUTGG_BASE}/players/new/")
FUTGG_EVOS_URL = os.getenv("FUTGG_EVOS_URL", f"{FUTGG_BASE}/evolutions/")
FUTGG_SBC_URL = os.getenv("FUTGG_SBC_URL", f"{FUTGG_BASE}/sbc/")
FUTBIN_BASE = os.getenv("FUTBIN_BASE", "https://www.futbin.com")

LEAK_CHANNEL_URL = os.getenv("LEAK_CHANNEL_URL", "")
NITTER_URL = os.getenv("NITTER_URL", "")
NITTER_ACCOUNTS = [a.strip() for a in os.getenv("NITTER_ACCOUNTS", "FutSheriff").split(",") if a.strip()]

# --- Anti-bot ---
FETCH_MODE = os.getenv("FETCH_MODE", "auto")  # auto | httpx | playwright
FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "")
PLAYWRIGHT_CHROMIUM_PATH = os.getenv("PLAYWRIGHT_CHROMIUM_PATH", "")
REQUEST_MIN_DELAY = float(os.getenv("REQUEST_MIN_DELAY", "1.5"))
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
)

# --- Telegram / Discord (étape 3) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- Seuils du cerveau ---
SIMILARITY_ALERT = 0.85
DROP_48H_BUY = -0.15
PUMP_24H_SELL = 0.30
INSTANT_CRASH_ALERT = -0.15
SATURATION_COUNT = 3


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
