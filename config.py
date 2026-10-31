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
PRICE_MIN = int(os.getenv("PRICE_MIN", "20250"))
PRICE_MAX = int(os.getenv("PRICE_MAX", "200000"))
WATCHLIST_SIZE = int(os.getenv("WATCHLIST_SIZE", "250"))
# Répartition de la watchlist par fourchette de prix : "min-max:nombre,..." (cœur du marché = 20k-100k)
# Petites tranches : futgenie ne sert qu'environ 4 pages (~100 joueurs) par recherche, et la watchlist
# se répartit mieux sur tous les niveaux de prix (190 joueurs entre 20k et 100k, 60 au-dessus)
WATCHLIST_BANDS = os.getenv(
    "WATCHLIST_BANDS",
    "20000-35000:50,35001-50000:50,50001-75000:45,75001-100000:45,100001-150000:35,150001-250000:25",
)
# Source des prix : "futgenie" (prix exacts, accès autorisé par robots.txt) ou "futgg" (tranches)
PRICE_SOURCE = os.getenv("PRICE_SOURCE", "futgenie")
EVO_CHEAP_MAX = int(os.getenv("EVO_CHEAP_MAX", "20000"))

# --- Sources (surchargeables si FUT.GG change ses URLs) ---
FUTGG_BASE = os.getenv("FUTGG_BASE", "https://www.fut.gg")
# Liste de la watchlist : cartes or + spéciales échangeables (market_players), 20 250 - 200 000 crédits
FUTGG_POPULAR_URL = os.getenv(
    "FUTGG_POPULAR_URL",
    f"{FUTGG_BASE}/players/?page=1&price__gte=20250&price__lte=200000&market_players=true",
)
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
# Proxy (ex: résidentiel) si l'IP du VPS est bannie par Cloudflare : http://user:pass@host:port
PROXY_URL = os.getenv("PROXY_URL", "")
REQUEST_MIN_DELAY = float(os.getenv("REQUEST_MIN_DELAY", "3"))  # secondes entre 2 pages d'un même site
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
EA_TAX = 0.05  # taxe EA sur chaque vente
MIN_NET_MARGIN = float(os.getenv("MIN_NET_MARGIN", "0.04"))  # marge nette mini après taxe pour un ACHAT

# --- Moteur de décision ---
# v1 = moteur historique (référence, retour arrière) ; v2 = moteur fiabilisé (qualité des données, abstention).
BRAIN_VERSION = os.getenv("BRAIN_VERSION", "v1")  # moteur qui envoie les alertes et remplit le dashboard
BRAIN_SHADOW = os.getenv("BRAIN_SHADOW", "v2")  # moteur évalué en observation (journalisé, jamais envoyé) ; "" = aucun
MAX_PRICE_AGE_H = float(os.getenv("MAX_PRICE_AGE_H", "2.5"))  # au-delà : prix trop ancien -> AUCUNE ACTION
MIN_POINTS_48H = int(os.getenv("MIN_POINTS_48H", "24"))  # relevés réels mini sur 48 h
REAL_POINT_TOLERANCE_H = 1.5  # écart max entre l'heure visée et un relevé réel (pas d'interpolation)
HABIT_MIN_CONFIDENCE = float(os.getenv("HABIT_MIN_CONFIDENCE", "0.5"))  # habitude validée si confiance >= ...
HABIT_MIN_WEEKS = int(os.getenv("HABIT_MIN_WEEKS", "3"))  # ... ET au moins N semaines observées
TARGET_MIN_POINTS = 72  # relevés mini sur 7 j pour calculer une cible de revente (moyenne 7 j)
OUTCOME_HORIZONS = [int(h) for h in os.getenv("OUTCOME_HORIZONS", "6,24,48,168").split(",")]
PROBA_MIN_SAMPLES = int(os.getenv("PROBA_MIN_SAMPLES", "100"))  # résultats évalués mini avant d'afficher une fréquence

# --- Anti-spam des alertes ---
ALERT_MIN_CONFIDENCE = int(os.getenv("ALERT_MIN_CONFIDENCE", "7"))
ALERT_MAX_PER_REPORT = int(os.getenv("ALERT_MAX_PER_REPORT", "8"))
ALERT_COOLDOWN_HOURS = int(os.getenv("ALERT_COOLDOWN_HOURS", "6"))

# --- Rapport des prix sur Discord/Telegram (heures de Paris) ---
PRICE_REPORT_HOURS = os.getenv("PRICE_REPORT_HOURS", "10,22")
SUMMARY_HOUR = int(os.getenv("SUMMARY_HOUR", "23"))  # résumé des 24 dernières heures

# --- Dashboard ---
# Image de la carte : aperçu public (og:image) que futgenie déclare pour chaque fiche, chargé par le
# NAVIGATEUR de l'utilisateur (rien n'est téléchargé ni stocké par le bot). 0 = cartes dessinées seulement.
CARD_IMAGES = os.getenv("CARD_IMAGES", "1") == "1"
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
