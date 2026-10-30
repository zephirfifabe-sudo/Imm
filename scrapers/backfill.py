"""BACKFILL : donner une mémoire au bot dès le 1er jour.

FUT.GG / FUTBIN renvoient un historique de prix par joueur (souvent 1 point/jour, parfois
horaire sur les derniers jours). On l'injecte dans price_snapshots (source='backfill')
uniquement AVANT le premier vrai snapshot, pour ne jamais polluer les données horaires réelles.
Le learner détecte ensuite la densité des données et baisse la confiance si elles sont journalières.
"""
from __future__ import annotations

from datetime import datetime

from database import db
from scrapers.base import Fetcher
from scrapers.price_provider import PriceProvider
from utils.logger import get_logger

log = get_logger("backfill")


def backfill_history(players: list[dict], fetcher: Fetcher | None = None) -> dict:
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    provider = PriceProvider(fetcher)
    total, players_ok = 0, 0
    try:
        for p in players:
            res = provider.get_price(p)
            hist = (res or {}).get("history") or []
            if not hist:
                continue
            pid = str(p["player_id"])
            with db.get_conn() as c:
                first_real = c.execute(
                    "SELECT MIN(timestamp) FROM price_snapshots WHERE player_id=? AND source!='backfill'", (pid,)
                ).fetchone()[0]
                existing = {r[0] for r in c.execute(
                    "SELECT timestamp FROM price_snapshots WHERE player_id=? AND source='backfill'", (pid,))}
                db.insert_history(pid, hist, conn=c)
                n = 0
                for ts, price in hist:
                    if (first_real and ts >= first_real) or ts in existing:
                        continue
                    db.insert_snapshot(pid, price, datetime.fromisoformat(ts), source="backfill", conn=c)
                    n += 1
            total += n
            players_ok += 1 if n else 0
    finally:
        if own:
            fetcher.close()
    summary = {"players": players_ok, "points": total}
    db.set_status("last_backfill", summary)
    log.info("Backfill : %d points pour %d joueurs", total, players_ok)
    return summary
