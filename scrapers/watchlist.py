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
        from scrapers.price_buckets import bucket_prices, parse_bands, select_by_bands

        # 1) Watchlist équilibrée par fourchettes de prix (cœur du marché 20k-100k), à partir des tranches
        balanced = select_by_bands(bucket_prices(fetcher), parse_bands(config.WATCHLIST_BANDS))
        if balanced:
            return _finalize(balanced, futgg)
        # 2) Repli : liste FUT.GG classée par note
        candidates = futgg.popular_players(pages=6)[:max_candidates]
        if not candidates:
            log.error("Aucun joueur populaire récupéré -> watchlist conservée")
            return load_watchlist()
        from scrapers.price_buckets import bucket_prices

        buckets = bucket_prices(fetcher, wanted={c["player_id"] for c in candidates})
        selected: list[dict] = []
        for rank, p in enumerate(candidates, 1):
            if len(selected) >= config.WATCHLIST_SIZE:
                break
            # Compléter la fiche si l'ancre seule ne donnait pas tout
            if not p.get("league") or not p.get("position"):
                d = futgg.player_definition(p["player_id"])
                if d:
                    p = {**p, **{k: v for k, v in d.items() if v not in (None, "", [], "?")}}
            price = p.get("price") or (buckets.get(p["player_id"]) or {}).get("price")
            if not price and not buckets:
                res = provider.get_price(p)
                price = res["price"] if res else None
            # la page FUT.GG choisie fixe déjà la fourchette de prix : elle fait foi
            if price and not futgg.list_price_filtered and not (config.PRICE_MIN <= price <= config.PRICE_MAX):
                continue
            if not price and not futgg.list_price_filtered:
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


def _finalize(players: list[dict], futgg: FutGGScraper) -> list[dict]:
    """Complète les fiches (poste, ligue, rareté via l'API des fiches), enregistre et sauvegarde."""
    selected = []
    for rank, p in enumerate(players, 1):
        if not p.get("league") or not p.get("position"):
            d = futgg.player_definition(p["player_id"])
            if d:
                p = {**p, **{k: v for k, v in d.items() if v not in (None, "", [], "?")}}
        p["popularity_rank"] = rank
        p["source"] = "futgg"
        db.upsert_player(p)
        selected.append(p)
    selected.sort(key=lambda p: p.get("price") or 0)
    save_watchlist(selected)
    cheap = sum(1 for p in selected if (p.get("price") or 0) <= 100000)
    log.info("Watchlist équilibrée : %d joueurs (%d entre 20k et 100k)", len(selected), cheap)
    return selected


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
