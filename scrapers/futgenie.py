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

import config
from database import db
from scrapers.base import Fetcher, FetchError, page_title
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
SBC_RE = re.compile(r"SBC points\s+([\d,.]+\s*[kK]?)")
# « Achraf Hakimi 88: Price… » ou, pour une carte spéciale, « Christopher Nkunku 82 Team of the Week: Price… »
TITLE_RE = re.compile(r"^\s*(.+?)\s+(\d{2})(?:\s+([^:]+?))?\s*:\s*Price", re.S)


def filter_url(f: dict, page: int = 1) -> str:
    f = dict(f)
    if page > 1:
        f["page"] = page
    return f"{BASE}/players?f=" + quote(json.dumps(f, separators=(",", ":")), safe="")


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
        cm, gm, sm = CHANGE_RE.search(text), GRADE_RE.search(text), SBC_RE.search(text)
        out.append({
            "player_id": ID_PREFIX + m.group(1),
            "url": BASE + a["href"],
            "price": price,
            "change_7d": float(cm.group(1).replace(",", ".")) / 100 if cm else None,
            "grade": int(gm.group(1)) if gm else None,
            "sbc_points": parse_price(sm.group(1)) if sm else None,  # Item Score des SBC « Streamlined »
        })
    return out


def count_links(html: str) -> int:
    """Nombre de cartes affichées (SBC comprises) : sert à savoir si la recherche a atteint le plafond futgenie."""
    return len({m for m in re.findall(r'href="/player-items/(\d+)', html)})


def split_range(lo: int, hi: int) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Coupe [lo, hi] en deux (milieu arrondi à 100 crédits), None si la tranche est déjà trop fine."""
    if hi - lo < 2 * config.FG_MIN_WIDTH:
        return None
    mid = (lo + hi) // 2 // 100 * 100
    if not lo < mid < hi:
        mid = (lo + hi) // 2
    return (lo, mid), (mid + 1, hi)


def scan_budget() -> int:
    """Requêtes de liste autorisées par scan : tient dans ~60 % de l'intervalle entre deux scans."""
    if config.FG_SCAN_MAX_REQUESTS:
        return config.FG_SCAN_MAX_REQUESTS
    return max(20, int(config.SNAPSHOT_EVERY_MIN * 60 * 0.6 / config.FG_REQUEST_S))


def parse_fiche(html: str, player_id: str, url: str) -> dict | None:
    # titre COMPLET (page_title le coupe à 60 caractères, trop court pour les noms longs + promo)
    t = BeautifulSoup(html, "html.parser").title
    title = t.get_text(strip=True) if t else ""
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
        log.info("Tranche %s-%s : %d/%d cartes en %d page(s)", lo, hi, min(len(cards), wanted), wanted, page)
        return cards[:wanted]

    # ------------------------------------------------------------- mode « toutes les cartes » (tranches auto)
    def read_range(self, lo: int, hi: int) -> tuple[list[dict], bool]:
        """Cartes vendables d'une tranche + True si futgenie a atteint son plafond (il en reste d'autres)."""
        html = self.f.get(list_url(lo, hi), retries=1).text
        return parse_cards(html), count_links(html) >= config.FG_LIST_CAP

    def discover(self, lo: int, hi: int, max_requests: int | None = None) -> tuple[list[list[int]], list[dict], dict]:
        """Toutes les cartes entre lo et hi : une tranche « pleine » est coupée en deux jusqu'à ne plus l'être.

        Renvoie (tranches finales triées, cartes, stats). Les tranches non explorées faute de budget restent
        telles quelles (elles seront relues, juste moins finement).
        """
        max_requests = max_requests or config.FG_DISCOVERY_MAX_REQUESTS
        stack, leaves, cards = [(lo, hi)], [], {}
        req = saturated = errors = 0
        while stack:
            a, b = stack.pop()
            if req >= max_requests or errors >= 3:
                leaves.append([a, b])
                continue
            try:
                found, full = self.read_range(a, b)
                errors = 0
            except FetchError as e:
                log.warning("futgenie %s-%s KO : %s", a, b, str(e)[:120])
                errors += 1
                leaves.append([a, b])
                continue
            req += 1
            for c in found:
                cards.setdefault(c["player_id"], c)
            halves = split_range(a, b) if full else None
            if halves:
                stack += [halves[1], halves[0]]
            else:
                saturated += full
                leaves.append([a, b])
        leaves.sort()
        stats = {"requests": req, "ranges": len(leaves), "cards": len(cards), "saturated": saturated,
                 "complete": not stack and req < max_requests and errors < 3}
        log.info("Recherche complète futgenie %s-%s : %d cartes, %d tranches, %d requêtes%s", lo, hi, len(cards),
                 len(leaves), req, f", {saturated} tranche(s) trop fines encore pleines" if saturated else "")
        return leaves, list(cards.values()), stats

    def build_all(self, lo: int, hi: int, max_new: int = 450) -> list[dict]:
        leaves, cards, stats = self.discover(lo, hi)
        db.set_status("fg_ranges", {"ranges": leaves, "cursor": 0, "stats": stats})
        budget = [max_new]
        cards.sort(key=lambda c: -(c.get("grade") or 0))  # popularité ≈ Genie Grade
        players = []
        for rank, card in enumerate(cards, 1):
            p = self.details(card, budget)
            p["popularity_rank"] = rank
            players.append(p)
        return players

    def scan_ranges(self, players: list[dict], last: dict[str, int], max_fiches: int = 10,
                    budget: int | None = None) -> dict[str, int]:
        """Prix actuels en relisant les tranches trouvées par la recherche complète.

        - s'il y a plus de tranches que le budget du scan, on les relit à tour de rôle (self.skipped = joueurs
          non relus ce tour-ci : ni relevé ni échec) ;
        - une tranche redevenue « pleine » (des cartes y sont entrées) est recoupée sur le champ.
        """
        st = (db.get_status().get("fg_ranges") or {}).get("value") or {}
        ranges = [list(r) for r in st.get("ranges") or []] or [[config.WATCHLIST_MIN, config.WATCHLIST_MAX]]
        budget = budget or scan_budget()
        cursor = int(st.get("cursor") or 0) % len(ranges)
        n_read = min(len(ranges), budget)
        todo = [ranges[(cursor + i) % len(ranges)] for i in range(n_read)]
        scheduled = [list(r) for r in todo]  # tranches prévues ce tour-ci (un échec réseau reste un échec)
        prices: dict[str, int] = {}
        self.trends = {}
        read, req, extra = [], 0, []
        while todo:
            a, b = todo.pop(0)
            try:
                found, full = self.read_range(a, b)
            except FetchError as e:
                log.warning("futgenie %s-%s KO : %s", a, b, str(e)[:120])
                break
            req += 1
            for c in found:
                prices[c["player_id"]] = c["price"]
                if c.get("change_7d") is not None:
                    self.trends[c["player_id"]] = c["change_7d"]
            halves = split_range(a, b) if full else None
            if halves and req + len(todo) + 2 <= budget + 10:  # recoupe dans la limite du budget (+10 de marge)
                extra.append(([a, b], halves))
                todo[:0] = [list(halves[0]), list(halves[1])]
            else:
                read.append([a, b])
        for old, (h1, h2) in extra:  # mémorise le nouveau découpage
            if old in ranges:
                i = ranges.index(old)
                ranges[i:i + 1] = [list(h1), list(h2)]
        new_cursor = (cursor + n_read) % len(ranges) if len(ranges) > budget else 0
        db.set_status("fg_ranges", {**st, "ranges": ranges, "cursor": new_cursor})
        self.skipped = {str(p["player_id"]) for p in players if str(p["player_id"]) not in prices
                        and last.get(str(p["player_id"])) and not any(a <= last[str(p["player_id"])] <= b for a, b in scheduled)}
        missing = [p for p in players if str(p["player_id"]) not in prices
                   and str(p["player_id"]) not in self.skipped and p.get("url")]
        for p in missing[:max_fiches]:  # sorti de sa tranche (au-dessus de 250k, carte retirée...) : fiche
            try:
                info = parse_fiche(self.f.get(p["url"], retries=0).text, p["player_id"], p["url"])
            except FetchError:
                break
            if info and info.get("price"):
                prices[str(p["player_id"])] = info["price"]
        self.scan_stats = {"ranges_read": len(read) + len(extra), "ranges_total": len(ranges), "requests": req,
                           "rotation": len(ranges) > budget}
        if len(ranges) > budget:
            log.info("Scan futgenie : %d/%d tranches relues ce tour-ci (rotation, budget %d requêtes)",
                     n_read, len(ranges), budget)
        return prices

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

    def build_watchlist(self, bands: list[tuple[int, int, int]], max_new: int = 450) -> list[dict]:
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
        self.trends: dict[str, float] = {}  # tendance 7 jours affichée par futgenie sur chaque carte
        for lo, hi, quota in bands:
            for c in self.band_cards(lo, hi, quota + PAGE_SIZE):
                prices[c["player_id"]] = c["price"]
                if c.get("change_7d") is not None:
                    self.trends[c["player_id"]] = c["change_7d"]
        missing = [p for p in players if str(p["player_id"]) not in prices and p.get("url")]
        for p in missing[:max_fiches]:
            try:
                info = parse_fiche(self.f.get(p["url"], retries=0).text, p["player_id"], p["url"])
            except FetchError:
                break
            if info and info.get("price"):
                prices[str(p["player_id"])] = info["price"]
        return prices
