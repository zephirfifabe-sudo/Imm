"""Surveillance des nouvelles cartes (Latest Players FUT.GG) — fenêtre 18h55-20h30 toutes les 3 min."""
from __future__ import annotations

from database import db
from scrapers.base import FetchError, Fetcher
from scrapers.futgg import FutGGScraper
from utils.logger import get_logger

log = get_logger("latest")


def check_new_cards(fetcher: Fetcher | None = None) -> list[dict]:
    """Renvoie uniquement les cartes jamais vues. Le tout premier passage initialise la base (aucune alerte)."""
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        futgg = FutGGScraper(fetcher)
        try:
            cards = futgg.latest_players()
        except FetchError as e:
            log.error("Latest players KO : %s", e)
            return []
        first_run = db.seen_count() == 0
        new_cards = []
        for c in cards:
            if not c.get("position") or not c.get("league"):
                d = futgg.player_definition(c["player_id"]) if not first_run else None
                if d:
                    c = {**c, **{k: v for k, v in d.items() if v not in (None, "", [], "?")}}
            if db.mark_seen(c["player_id"], c) and not first_run:
                c["source"] = "futgg-latest"
                db.upsert_player(c)
                db.add_event("new_card", title=f"{c['name']} {c.get('rating')}", player_id=c["player_id"],
                             position=c.get("position"), payload=c)
                new_cards.append(c)
        db.set_status("last_latest_scan", {"cards": len(cards), "new": len(new_cards), "init": first_run})
        if new_cards:
            log.info("🆕 %d nouvelles cartes : %s", len(new_cards), ", ".join(c["name"] for c in new_cards[:10]))
        return new_cards
    finally:
        if own:
            fetcher.close()
