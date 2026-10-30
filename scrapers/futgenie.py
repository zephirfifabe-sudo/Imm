"""Source futgenie.gg — prix exacts, accès normal (robots.txt autorise /players et /player-items).

Liste : /players?f={"sort":"grade-desc","minPrice":..,"maxPrice":..,"page":N}  -> 24 cartes par page.
  Texte d'une carte : « 98.0k | 98,000 | 8.30k | 93 | Price 98,000 · SBC points 8,300 · Genie Grade 93 | -15.4% | 7d »
Fiche : /player-items/{id} -> titre « Achraf Hakimi 88: Price & Stats (FC 27) | FUTGenie »
  puis dans le texte : « … Genie Grade 93 | Achraf Hakimi | Common | Paris SG | … »
Les fiches ne sont lues qu'une fois par joueur (mises en cache dans la table players).
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from database import db
from scrapers.base import FetchError, Fetcher, page_title
from utils import fut_ids
from utils.helpers import POSITIONS, parse_price
from utils.logger import get_logger
from utils.rarity import label as rarity_label

log = get_logger("futgenie")

BASE = "https://www.futgenie.gg"
PAGE_SIZE = 24
ID_PREFIX = "fgn-"  # évite toute collision avec les IDs FUT.GG déjà en base

PRICE_RE = re.compile(r"Price\s+([\d,.]+\s*[kKmM]?)")
CHANGE_RE = re.compile(r"([+-]?\d+(?:[.,]\d+)?)\s*%\s*\|\s*7d")
GRADE_RE = re.compile(r"Genie Grade\s+(\d+)")
# « Achraf Hakimi 88: Price… » ou, pour une carte spéciale, « Christopher Nkunku 82 Team of the Week: Price… »
TITLE_RE = re.compile(r"^\s*(.+?)\s+(\d{2})(?:\s+([^:]+?))?\s*:\s*Price", re.S)


def list_url(min_price: int, max_price: int, page: int = 1, sort: str = "grade-desc") -> str:
    f = {"sort": sort, "minPrice": min_price, "maxPrice": max_price}
    if page > 1:
        f["page"] = page
    return f"{BASE}/players?f=" + quote(json.dumps(f, separators=(",", ":")), safe="")


def parse_cards(html: str) -> list[dict]:
    """Cartes de la liste : id, prix exact, tendance 7 jours, Genie Grade."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.match(r"^/player-items/(\d+)", a["href"])
        if not m or m.group(1) in seen:
            continue
        text = a.get_text(" | ", strip=True)
        pm = PRICE_RE.search(text)
        price = parse_price(pm.group(1)) if pm else None
        if not price:
            continue
        seen.add(m.group(1))
        cm, gm = CHANGE_RE.search(text), GRADE_RE.search(text)
        out.append({
            "player_id": ID_PREFIX + m.group(1),
            "url": BASE + a["href"],
            "price": price,
            "change_7d": float(cm.group(1).replace(",", ".")) / 100 if cm else None,
            "grade": int(gm.group(1)) if gm else None,
        })
    return out


def parse_fiche(html: str, player_id: str, url: str) -> dict | None:
    title = page_title(html).replace("&amp;", "&")
    m = TITLE_RE.match(title)
    if not m:
        return None
    name, rating, promo = m.group(1).strip(), int(m.group(2)), (m.group(3) or "").strip()
    tokens = [t.strip() for t in BeautifulSoup(html, "html.parser").get_text(" | ", strip=True).split(" | ")]
    # le bloc d'infos suit la 2e occurrence du nom (la 1re est dans le titre de la page)
    idx = [i for i, t in enumerate(tokens) if t == name]
    start = idx[1] if len(idx) > 1 else (idx[0] if idx else 0)
    after = tokens[start + 1:start + 60]
    leagues, nations = set(fut_ids.LEAGUES.values()), set(fut_ids.NATIONS.values())
    pos = next((t for t in after if t.upper() in POSITIONS), None)
    # « Ligue 1 McDonald's », « Premier League »… : on accepte le nom connu en début de texte
    league = next((lg for t in after for lg in leagues if t == lg or t.startswith(lg + " ")), None)
    nation = next((t for t in after if t in nations), None)
    # la promo du titre (Team of the Week, Trailblazers…) prime sur la rareté de base affichée
    rarity = rarity_label(promo) if promo else (rarity_label(after[0]) if after else None)
    club = after[1] if len(after) > 1 and after[1] not in (pos, league, nation) else None
    pm = PRICE_RE.search(" | ".join(tokens))
    return {
        "player_id": player_id, "name": name, "rating": rating, "position": pos.upper() if pos else None,
        "league": league, "nation": nation, "club": club, "card_type": rarity, "url": url,
        "price": parse_price(pm.group(1)) if pm else None, "source": "futgenie",
    }


class FutGenie:
    def __init__(self, fetcher: Fetcher | None = None):
        # Accès normal uniquement : en cas de blocage on s'arrête (pas de contournement)
        self.f = fetcher or Fetcher(mode="httpx", min_delay=4.0)
        self._own = fetcher is None

    def close(self) -> None:
        if self._own:
            self.f.close()

    def band_cards(self, lo: int, hi: int, wanted: int) -> list[dict]:
        """Les `wanted` meilleures cartes (Genie Grade) entre lo et hi, page après page."""
        cards, seen = [], set()
        for page in range(1, wanted // PAGE_SIZE + 6):
            try:
                batch = parse_cards(self.f.get(list_url(lo, hi, page), retries=1).text)
            except FetchError as e:
                log.warning("futgenie %s-%s page %d KO : %s", lo, hi, page, str(e)[:120])
                break
            new = [c for c in batch if c["player_id"] not in seen]
            if not new:  # page vide ou identique à la précédente : fin de liste
                break
            for c in new:
                seen.add(c["player_id"])
                cards.append(c)
            # pas d'arrêt sur une page « incomplète » : une carte sans prix affiché ne signifie pas la fin
            if len(cards) >= wanted:
                break
        return cards[:wanted]

    def details(self, card: dict, max_new: list[int]) -> dict:
        """Fiche joueur : depuis la base si déjà connue, sinon lue sur futgenie (limite max_new[0] par passe)."""
        known = db.get_player(card["player_id"])
        if known and known.get("name") and known.get("rating"):
            return {**known, **{k: v for k, v in card.items() if v is not None}}
        if max_new[0] <= 0:
            return {**card, "name": card["player_id"], "source": "futgenie"}
        max_new[0] -= 1
        try:
            info = self.read_fiche(card["player_id"], card["url"])
        except FetchError as e:
            log.warning("Fiche futgenie KO %s : %s", card["url"], str(e)[:150])
            info = None
        p = {**(info or {"name": card["player_id"], "source": "futgenie"}), **card}
        if info:
            db.upsert_player(p)
        return p

    def read_fiche(self, player_id: str, url: str) -> dict | None:
        """Fiche lue et décodée, None si illisible. Lève FetchError si le site ne répond pas."""
        res = self.f.get(url, retries=1)
        info = parse_fiche(res.text, player_id, url)
        if not info:
            log.warning("Fiche futgenie illisible %s (http=%s, titre « %s »)", url, res.status, page_title(res.text)[:80])
        return info

    def fill_missing(self, players: list[dict], limit: int = 20) -> int:
        """Complète les joueurs restés sans fiche (nom « fgn-… ») : quelques-uns à chaque passage."""
        done = 0
        for p in players:
            if done >= limit:
                break
            known = db.get_player(p["player_id"]) or {}
            if known.get("rating") or not p.get("url"):
                continue
            try:
                info = self.read_fiche(p["player_id"], p["url"])
            except FetchError as e:
                log.warning("Fiche futgenie KO %s : %s", p["url"], str(e)[:150])
                break  # site lent ou en pause : on réessaiera au prochain passage
            if info:  # une fiche illisible ne bloque plus les suivantes
                db.upsert_player({**info, "price": None})
                done += 1
        if done:
            log.info("Fiches futgenie complétées : %d", done)
        return done

    def build_watchlist(self, bands: list[tuple[int, int, int]], max_new: int = 300) -> list[dict]:
        budget = [max_new]
        players = []
        for lo, hi, quota in bands:
            for rank, card in enumerate(self.band_cards(lo, hi, quota), 1):
                p = self.details(card, budget)
                p["popularity_rank"] = rank
                players.append(p)
        log.info("Watchlist futgenie : %d joueurs", len(players))
        return players

    def current_prices(self, players: list[dict], bands: list[tuple[int, int, int]],
                       max_fiches: int = 40) -> dict[str, int]:
        """Prix actuels : relit les listes des fourchettes, puis la fiche des joueurs sortis des listes."""
        prices: dict[str, int] = {}
        for lo, hi, quota in bands:
            for c in self.band_cards(lo, hi, quota + PAGE_SIZE):
                prices[c["player_id"]] = c["price"]
        missing = [p for p in players if str(p["player_id"]) not in prices and p.get("url")]
        for p in missing[:max_fiches]:
            try:
                info = parse_fiche(self.f.get(p["url"], retries=0).text, p["player_id"], p["url"])
            except FetchError:
                break
            if info and info.get("price"):
                prices[str(p["player_id"])] = info["price"]
        return prices
