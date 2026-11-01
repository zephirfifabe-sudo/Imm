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
# se répartit mieux sur tous les niveaux de prix (12 tranches : ~305 joueurs entre 20k et 110k, ~105 au-dessus)
WATCHLIST_BANDS = os.getenv(
    "WATCHLIST_BANDS",
    "20000-25000:40,25001-30000:40,30001-35000:35,35001-42000:40,42001-50000:40,50001-60000:35,60001-75000:40,75001-90000:35,90001-110000:30,110001-140000:30,140001-180000:25,180001-250000:20",
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

LEAK_CHANNEL_URL = os.getenv("LEAK_CHANNEL_URL", "")  # ancien réglage (1 canal), toujours accepté
# Canaux Telegram PUBLICS de leaks, séparés par des virgules (nom, @nom ou lien t.me)
LEAK_CHANNELS = [c.strip() for c in os.getenv("LEAK_CHANNELS", LEAK_CHANNEL_URL).split(",") if c.strip()]
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
DISCORD_LEAKS_WEBHOOK_URL = os.getenv("DISCORD_LEAKS_WEBHOOK_URL", "")  # salon dédié aux leaks (sinon salon principal)
DISCORD_FODDER_WEBHOOK_URL = os.getenv("DISCORD_FODDER_WEBHOOK_URL", "")  # salon dédié aux fodders (sinon salon principal)

# --- Seuils du cerveau ---
SIMILARITY_ALERT = 0.85
DROP_48H_BUY = -0.15
PUMP_24H_SELL = 0.30
# Moteur v2 — R4 en force relative : seule la part du mouvement PROPRE au joueur compte
R4_EXCESS_BUY = float(os.getenv("R4_EXCESS_BUY", "-0.10"))  # chute 48 h au moins 10 pts pire que le marché
R4_EXCESS_SELL = float(os.getenv("R4_EXCESS_SELL", "0.15"))  # hausse 24 h au moins 15 pts au-dessus du marché
R4_STABLE_3H = float(os.getenv("R4_STABLE_3H", "-0.02"))  # chute encore en cours si < -2 % sur les 3 dernières heures
# Nouvelles cartes : le prix « se cherche » pendant plusieurs jours (packs qui s'ouvrent) -> pas d'ACHAT/VENTE
NEW_CARD_DAYS_SPECIAL = float(os.getenv("NEW_CARD_DAYS_SPECIAL", "4"))  # TOTW, promos du vendredi...
NEW_CARD_DAYS_BASE = float(os.getenv("NEW_CARD_DAYS_BASE", "2"))
INSTANT_CRASH_ALERT = -0.15
SATURATION_COUNT = 3
EA_TAX = 0.05  # taxe EA sur chaque vente
MIN_NET_MARGIN = float(os.getenv("MIN_NET_MARGIN", "0.04"))  # marge nette mini après taxe pour un ACHAT

# --- Fréquence des relevés de prix ---
# futgenie rafraîchit ses prix environ toutes les 6 min (mesure refresh-test du 31/10/2026) :
# un relevé toutes les 15 min capte vite les mouvements sans surcharger la source.
SNAPSHOT_EVERY_MIN = int(os.getenv("SNAPSHOT_EVERY_MIN", "15"))

# --- Moteur de décision ---
# v1 = moteur historique (référence, retour arrière) ; v2 = moteur fiabilisé (qualité des données, abstention).
# Bascule v1 -> v2 le 01/11/2026 après 2,4 jours de journal : achats v1 favorables à 24 h dans 8 % des cas
# (n=984, marché en baisse), abstentions v2 justifiées à 99 %. v1 reste évalué en observation.
BRAIN_VERSION = os.getenv("BRAIN_VERSION", "v2")  # moteur qui envoie les alertes et remplit le dashboard
BRAIN_SHADOW = os.getenv("BRAIN_SHADOW", "v1")  # moteur évalué en observation (journalisé, jamais envoyé) ; "" = aucun
MAX_PRICE_AGE_H = float(os.getenv("MAX_PRICE_AGE_H", "2.5"))  # au-delà : prix trop ancien -> AUCUNE ACTION
MIN_POINTS_48H = int(os.getenv("MIN_POINTS_48H", "24"))  # relevés réels mini sur 48 h
REAL_POINT_TOLERANCE_H = 1.5  # écart max entre l'heure visée et un relevé réel (pas d'interpolation)
HABIT_MIN_CONFIDENCE = float(os.getenv("HABIT_MIN_CONFIDENCE", "0.5"))  # habitude validée si confiance >= ...
HABIT_MIN_WEEKS = int(os.getenv("HABIT_MIN_WEEKS", "3"))  # ... ET au moins N semaines observées
TARGET_MIN_POINTS = 72  # relevés mini sur 7 j pour calculer une cible de revente (moyenne 7 j)
OUTCOME_HORIZONS = [int(h) for h in os.getenv("OUTCOME_HORIZONS", "6,24,48,168").split(",")]
PROBA_MIN_SAMPLES = int(os.getenv("PROBA_MIN_SAMPLES", "100"))  # résultats évalués mini avant d'afficher une fréquence

# --- Tracker de fodders (moins cher par note) ---
FODDER_RATINGS = [int(r) for r in os.getenv("FODDER_RATINGS", "85,86,87,88,89,90,91").split(",") if r.strip()]
FODDER_ALERT_RISE = float(os.getenv("FODDER_ALERT_RISE", "0.12"))  # hausse vs médiane 7 j pour alerter
FODDER_ALERT_RISE_6H = 0.08  # ... et hausse récente (6 h) minimale
FODDER_ALERT_COOLDOWN_H = 12
FODDER_REPORT_HOUR = int(os.getenv("FODDER_REPORT_HOUR", "15"))  # tableau des fodders chaque jour à cette heure
FODDER_AVG_DAYS = os.getenv("FODDER_AVG_DAYS", "tue,sun")  # rapport des prix moyens (jours, format cron)
FODDER_AVG_HOUR = int(os.getenv("FODDER_AVG_HOUR", "10"))

# --- Supervision : alerte Discord si plus aucun prix relevé ---
STALE_ALERT_HOURS = float(os.getenv("STALE_ALERT_HOURS", "2"))
STALE_MIN_OK_RATIO = 0.5  # relevé « partiel » si moins de 50 % des joueurs ont un prix

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
