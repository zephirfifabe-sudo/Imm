"""Scraper FUTBIN (fallback quand FUT.GG ne répond pas).

FUTBIN utilise ses propres IDs : on les retrouve via la recherche (nom + note) et on les met
en cache dans la table source_map pour ne chercher qu'une fois.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

import config
from database import db
from scrapers.base import FetchError, Fetcher
from utils.helpers import parse_price
from utils.logger import get_logger

log = get_logger("futbin")

PLAYER_LINK_RE = re.compile(r"/(\d{2})/player/(\d+)/([\w-]+)")


class FutbinScraper:
    name = "futbin"

    def __init__(self, fetcher: Fetcher, year: str | None = None):
        self.f = fetcher
        self.year = year or config.GAME_YEAR
        self.base = config.FUTBIN_BASE.rstrip("/")
        self.platform_key = "pc" if config.PLATFORM == "pc" else "ps"

    def find_id(self, player: dict) -> str | None:
        cached = db.get_source_id(player["player_id"], "futbin")
        if cached:
            return cached
        term = quote(player["name"])
        candidates: list[tuple[str, int | None]] = []
        try:
            data = self.f.get_json(f"{self.base}/search?year={self.year}&extra=1&term={term}")
            for item in data or []:
                if isinstance(item, dict) and item.get("id"):
                    candidates.append((str(item["id"]), _int(item.get("rating"))))
        except (FetchError, ValueError):
            try:
                res = self.f.get(f"{self.base}/players?search={term}")
                soup = BeautifulSoup(res.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    m = PLAYER_LINK_RE.search(a["href"])
                    if m:
                        rating = next((int(t) for t in a.get_text(" ").split() if t.isdigit() and 40 <= int(t) <= 99), None)
                        candidates.append((m.group(2), rating))
            except FetchError as e:
                log.warning("FUTBIN recherche KO %s : %s", player["name"], e)
                return None
        best = next((cid for cid, r in candidates if r == player.get("rating")), None)
        best = best or (candidates[0][0] if candidates else None)
        if best:
            db.set_source_id(player["player_id"], "futbin", best)
        return best

    def player_prices(self, player: dict) -> dict | None:
        fid = self.find_id(player)
        if not fid:
            return None
        res = self.f.get(f"{self.base}/{self.year}/player/{fid}")
        return self.parse_player_page(res.text, self.platform_key)

    @staticmethod
    def parse_player_page(html: str, platform_key: str = "ps") -> dict | None:
        soup = BeautifulSoup(html, "html.parser")
        price = None
        # 1) attributs data-* (anciennes versions) ; 2) blocs "price" visibles
        for attr in ("data-ps-lowest", "data-pc-lowest", "data-price"):
            el = soup.find(attrs={attr: True})
            if el and (platform_key in attr or attr == "data-price"):
                price = parse_price(el[attr])
                if price:
                    break
        if not price:
            for el in soup.select(".price-box-original-player .price, .lowest-price-1, .price.inline-with-icon, [class*='price-box'] [class*='price']"):
                price = parse_price(el.get_text(strip=True))
                if price:
                    break
        if not price:
            return None
        lo = hi = None
        txt = soup.get_text(" ", strip=True)
        m = re.search(r"Price Range:?\s*([\d.,KMkm]+)\s*-\s*([\d.,KMkm]+)", txt)
        if m:
            lo, hi = parse_price(m.group(1)), parse_price(m.group(2))
        return {"price": price, "min_24h": lo, "max_24h": hi, "volume": None, "history": [], "source": "futbin"}


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
