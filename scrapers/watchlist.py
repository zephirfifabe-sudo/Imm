"""Watchlist quotidienne (08h00) : joueurs populaires/meta FUT.GG entre PRICE_MIN et PRICE_MAX."""
from __future__ import annotations

import json

import config
from database import db
from scrapers.base import Fetcher
from scrapers.futgg import FutGGScraper
from scrapers.price_provider import PriceProvider
from utils.helpers import iso, utcnow
from utils.logger import get_logger

log = get_logger("watchlist")


def build_watchlist(fetcher: Fetcher | None = None, max_candidates: int = 260) -> list[dict]:
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        futgg = FutGGScraper(fetcher)
        provider = PriceProvider(fetcher)
        candidates = futgg.popular_players()[:max_candidates]
        if not candidates:
            log.error("Aucun joueur populaire récupéré -> watchlist conservée")
            return load_watchlist()
        selected: list[dict] = []
        for rank, p in enumerate(candidates, 1):
            if len(selected) >= config.WATCHLIST_SIZE:
                break
            # Compléter la fiche si l'ancre seule ne donnait pas tout
            if not p.get("league") or not p.get("position"):
                d = futgg.player_definition(p["player_id"])
                if d:
                    p = {**p, **{k: v for k, v in d.items() if v not in (None, "", [], "?")}}
            price = p.get("price")
            if not price:
                res = provider.get_price(p)
                price = res["price"] if res else None
            if not price or not (config.PRICE_MIN <= price <= config.PRICE_MAX):
                continue
            p["price"] = price
            p["popularity_rank"] = rank
            p["source"] = "futgg"
            db.upsert_player(p)
            selected.append(p)
        save_watchlist(selected)
        log.info("Watchlist : %d joueurs (sur %d candidats)", len(selected), len(candidates))
        return selected
    finally:
        if own:
            fetcher.close()


def save_watchlist(players: list[dict]) -> None:
    config.ensure_dirs()
    payload = {
        "generated_at": iso(utcnow()),
        "price_range": [config.PRICE_MIN, config.PRICE_MAX],
        "players": [
            {k: p.get(k) for k in ("player_id", "name", "rating", "position", "league", "nation", "club",
                                   "card_type", "price", "url", "popularity_rank")}
            for p in players
        ],
    }
    config.WATCHLIST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    db.set_status("watchlist", {"count": len(players), "generated_at": payload["generated_at"]})


def load_watchlist() -> list[dict]:
    """Watchlist enrichie avec les infos de la table players."""
    if not config.WATCHLIST_PATH.exists():
        return []
    data = json.loads(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
    entries = data.get("players", [])
    known = {p["player_id"]: p for p in db.get_players([e["player_id"] for e in entries])}
    return [{**e, **{k: v for k, v in known.get(e["player_id"], {}).items() if v not in (None, "", [])}}
            for e in entries]
