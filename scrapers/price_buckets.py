"""PRIX PAR TRANCHES : contourne l'API prix de FUT.GG (bloquée pour les serveurs).

La page liste de FUT.GG accepte des filtres price__gte / price__lte appliqués PAR FUT.GG.
On découpe la fourchette en tranches géométriques (~6 %) et on regarde quels joueurs
apparaissent dans chaque tranche : chaque joueur reçoit le prix central de sa tranche
(précision ±3 %), largement suffisant pour détecter un crash de -15 % ou le cycle hebdo.

Dans une tranche, la liste est triée par gg_rating : les meilleurs joueurs (ceux de la
watchlist) sont sur les premières pages -> on lit au plus `max_pages` pages par tranche.
"""
from __future__ import annotations

import math
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import config
from scrapers.base import FetchError, Fetcher
from scrapers.futgg import FutGGScraper, with_page
from utils.logger import get_logger

log = get_logger("buckets")
PAGE_SIZE = 30
_CACHE: dict = {"at": 0.0, "prices": {}}  # évite 2 passes complètes coup sur coup (watchlist + snapshot)


def bucket_bounds(lo: int, hi: int, ratio: float) -> list[tuple[int, int]]:
    n = max(1, math.ceil(math.log(hi / lo) / math.log(ratio)))
    edges = [round(lo * (hi / lo) ** (i / n)) for i in range(n + 1)]
    return [(edges[i], edges[i + 1] - 1 if i < n - 1 else edges[i + 1]) for i in range(n)]


def range_url(base_url: str, lo: int, hi: int) -> str:
    parts = urlsplit(base_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k not in ("price__gte", "price__lte", "page")]
    query += [("price__gte", str(lo)), ("price__lte", str(hi))]
    return urlunsplit(parts._replace(query=urlencode(query)))


def list_bounds(base_url: str) -> tuple[int, int]:
    q = dict(parse_qsl(urlsplit(base_url).query))
    return int(q.get("price__gte", config.PRICE_MIN)), int(q.get("price__lte", config.PRICE_MAX))


def bucket_prices(fetcher: Fetcher, base_url: str | None = None, ratio: float = 1.06, max_pages: int = 3,
                  wanted: set[str] | None = None, max_age_s: int = 1800) -> dict[str, dict]:
    """{player_id: {"price", "min", "max", "player"}} pour tous les joueurs vus dans les tranches.

    `wanted` : arrêt anticipé dès que tous ces joueurs ont un prix.
    """
    if _CACHE["prices"] and time.time() - _CACHE["at"] < max_age_s and (
            not wanted or wanted <= set(_CACHE["prices"])):
        return _CACHE["prices"]
    base_url = base_url or config.FUTGG_POPULAR_URL
    lo, hi = list_bounds(base_url)
    futgg = FutGGScraper(fetcher)
    prices: dict[str, dict] = {}
    t0, requests = time.time(), 0
    for b_lo, b_hi in bucket_bounds(lo, hi, ratio):
        mid = round(math.sqrt(b_lo * b_hi))
        for page in range(1, max_pages + 1):
            url = with_page(range_url(base_url, b_lo, b_hi), page)
            try:
                players = futgg.list_players(url)
                requests += 1
            except FetchError as e:
                log.warning("Tranche %s-%s page %d KO : %s", b_lo, b_hi, page, str(e)[:100])
                break
            for p in players:
                prev = prices.get(p["player_id"])
                if prev and prev["max"] < b_lo:
                    # vu dans 2 tranches voisines : prix pile à la limite -> valeur de la limite
                    prices[p["player_id"]] = {"price": b_lo, "min": prev["min"], "max": b_hi, "player": p}
                else:
                    prices[p["player_id"]] = {"price": mid, "min": b_lo, "max": b_hi, "player": p}
            if len(players) < PAGE_SIZE:
                break
        if wanted and wanted <= set(prices):
            break
    log.info("Prix par tranches : %d joueurs en %d requêtes (%.0f s)", len(prices), requests, time.time() - t0)
    if prices:
        _CACHE.update(at=time.time(), prices=prices)
    return prices
