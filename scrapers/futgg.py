"""Scraper FUT.GG (source prioritaire).

FUT.GG expose des endpoints JSON utilisés par son propre front :
  /api/fut/player-prices/{year}/{eaId}/            -> prix actuel, overview, historique
  /api/fut/player-item-definitions/{year}/{eaId}/  -> fiche (note, poste, ligue, club...)
Ils sont tentés en premier ; si le format change, on retombe sur le HTML de la page joueur.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
from scrapers.base import FetchError, Fetcher
from scrapers.parsing import extract_players, pick, player_from_dict, walk_dicts
from utils.helpers import iso, parse_price
from utils.logger import get_logger

log = get_logger("futgg")


class FutGGScraper:
    name = "futgg"

    def __init__(self, fetcher: Fetcher, year: str | None = None, base: str | None = None):
        self.f = fetcher
        self.year = year or config.GAME_YEAR
        self.base = (base or config.FUTGG_BASE).rstrip("/")
        self.api_blocked = False

    # ------------------------------------------------------------ listes
    def list_players(self, url: str) -> list[dict]:
        res = self.f.get(url)
        players = extract_players(res.text, self.base)
        log.info("FUT.GG %s -> %d joueurs (via %s)", url, len(players), res.via)
        return players

    def popular_players(self, pages: int = 4) -> list[dict]:
        out = self._popular_from(config.FUTGG_POPULAR_URL, pages)
        if out:
            return out
        # URL bloquée (cas observé : les URLs avec ?sorts= sont plus protégées) -> pages qui passent
        for path in ("/players/", "/players/in-packs/", "/players/best/"):
            log.warning("Liste populaire indisponible -> repli sur %s", path)
            out = self._popular_from(self.base + path, pages)
            if out:
                return out
        return []

    def _popular_from(self, base_url: str, pages: int) -> list[dict]:
        out, seen = [], set()
        for page in range(1, pages + 1):
            url = base_url
            if page > 1:
                url += ("&" if "?" in url else "?") + f"page={page}"
            try:
                batch = self.list_players(url)
            except FetchError as e:
                log.warning("Page populaire %d KO : %s", page, e)
                break
            new = [p for p in batch if p["player_id"] not in seen]
            if not new:
                break
            for p in new:
                seen.add(p["player_id"])
                out.append(p)
        return out

    def latest_players(self) -> list[dict]:
        return self.list_players(config.FUTGG_LATEST_URL)

    # ------------------------------------------------------------ fiche + prix
    def player_definition(self, ea_id: str) -> dict | None:
        url = f"{self.base}/api/fut/player-item-definitions/{self.year}/{ea_id}/"
        try:
            data = self.f.get_json(url)
        except (FetchError, ValueError) as e:
            log.debug("definition API KO %s : %s", ea_id, e)
            return None
        if not data:
            return None
        d = data.get("data", data) if isinstance(data, dict) else None
        if isinstance(d, dict) and pick(d, "overall", "rating"):
            d.setdefault("eaId", ea_id)
            return player_from_dict(d, self.base)
        return None

    def player_prices(self, ea_id: str, page_url: str | None = None) -> dict | None:
        """Renvoie {price, min_24h, max_24h, volume, history:[(iso,price)], source}."""
        url = f"{self.base}/api/fut/player-prices/{self.year}/{ea_id}/"
        data = None
        if not self.api_blocked:
            try:
                data = self.f.get_json(url, retries=0)
            except (FetchError, ValueError) as e:
                # API protégée (cas observé sur VPS) : on ne la retente plus pendant ce job
                log.info("API prix FUT.GG bloquée (%s) -> capture via la page joueur", str(e)[:80])
                self.api_blocked = True
        parsed = self.parse_prices_payload(data) if data else None
        if parsed and parsed.get("price"):
            return parsed
        if page_url and config.FLARESOLVERR_URL:
            parsed = self.prices_via_browser(page_url)
            if parsed:
                return parsed
        if page_url:
            return self.prices_from_page(page_url, ea_id)
        return None

    def prices_via_browser(self, page_url: str) -> dict | None:
        """Chromium ouvre la page joueur ; on intercepte la réponse de l'API prix que le site appelle lui-même."""
        try:
            cap = self.f.capture_api(page_url, stop_on="player-prices")
        except Exception as e:  # noqa: BLE001
            log.warning("Capture prix KO %s : %s", page_url, str(e)[:120])
            return None
        for api_url, (status, body) in cap["api"].items():
            if "price" in api_url and status == 200 and body:
                parsed = self.parse_prices_payload(body)
                if parsed:
                    parsed["source"] = "futgg-browser"
                    return parsed
        return None

    @staticmethod
    def parse_prices_payload(data) -> dict | None:
        d = data.get("data", data) if isinstance(data, dict) else None
        if not isinstance(d, dict):
            return None
        cur = d.get("currentPrice")
        price = parse_price(pick(cur, "price") if isinstance(cur, dict) else cur)
        price = price or parse_price(pick(d, "price", "overview.averageBin", "overview.cheapestSale"))
        if not price:
            return None
        history: list[tuple[str, int]] = []
        hist_src = pick(d, "history", "priceHistory", "graph", "prices", default=[])
        for pt in hist_src if isinstance(hist_src, list) else []:
            if isinstance(pt, dict):
                ts = pick(pt, "date", "timestamp", "time", "updatedAt")
                p = parse_price(pick(pt, "price", "value", "averageBin"))
            elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                ts, p = pt[0], parse_price(pt[1])
            else:
                continue
            ts = _to_iso(ts)
            if ts and p:
                history.append((ts, p))
        history.sort()
        cutoff = iso(datetime.now(timezone.utc) - timedelta(days=1))
        last24 = [p for t, p in history if t >= cutoff] + [price]
        live = d.get("liveAuctions")
        volume = len(live) if isinstance(live, list) else parse_price(pick(d, "overview.totalAuctions", "volume"))
        return {
            "price": price,
            "min_24h": parse_price(pick(d, "overview.min24h", "min24h")) or min(last24),
            "max_24h": parse_price(pick(d, "overview.max24h", "max24h")) or max(last24),
            "volume": volume,
            "history": history[-200:],
            "source": "futgg",
        }

    def prices_from_page(self, page_url: str, ea_id: str) -> dict | None:
        res = self.f.get(page_url)
        from scrapers.parsing import iter_json_blobs

        for blob in iter_json_blobs(res.text):
            for d in walk_dicts(blob):
                if "currentPrice" in d or "liveAuctions" in d:
                    parsed = self.parse_prices_payload(d)
                    if parsed:
                        return parsed
        # dernier recours : le prix affiché de la carte
        for p in extract_players(res.text, self.base):
            if p["player_id"] == str(ea_id) and p.get("price"):
                return {"price": p["price"], "min_24h": None, "max_24h": None, "volume": None,
                        "history": [], "source": "futgg-html"}
        return None


def _to_iso(ts) -> str | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            if ts > 1e12:
                ts /= 1000
            return iso(datetime.fromtimestamp(ts, tz=timezone.utc))
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return iso(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
    except (ValueError, OSError):
        return None
