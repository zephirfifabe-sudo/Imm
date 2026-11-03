"""Source futreveal.com — API JSON publique du site (aucun compte, robots.txt sans restriction, pas de Cloudflare).

GET https://api.futreveal.com/cards?page=N&price_from=..&price_to=..  -> {"items": [...50 cartes], "total", "has_more"}
Chaque carte : ea_id, rating, is_special / is_sbc / is_objective, created_at (= date de SORTIE de la carte),
price {"PS", "XB", "PC", "updated_at", "is_extinct_ps", ...} et des objets player / rarity / club / league / nation.

Observé le 03/11 : 20 473 cartes FC 27, 185 entre 20k et 300k (4 pages). Le filtre de prix du site ne précise pas la
plateforme : on demande une fourchette élargie et on filtre nous-mêmes sur le prix PlayStation.

Les joueurs déjà suivis via futgenie gardent leur identifiant (« fgn-… ») et donc tout leur historique : une carte
futreveal est rattachée par nom + note + prix proche ; sinon elle reçoit un identifiant « fr-<ea_id> ».
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta
from urllib.parse import urlencode

import config
from database import db
from scrapers.base import Fetcher, FetchError
from utils.helpers import utcnow
from utils.logger import get_logger
from utils.rarity import classify
from utils.rarity import label as rarity_label

log = get_logger("futreveal")

ID_PREFIX = "fr-"
SOURCE = "futreveal"


def _norm(s) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


def _text(obj, keys=("common_name", "name", "display_name", "short_name", "label", "abbreviation")) -> str | None:
    """Nom lisible d'un objet imbriqué (player, rarity, club...) quel que soit le nom exact du champ."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj or None
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if obj.get(k):
            return str(obj[k])
    first, last = obj.get("first_name") or obj.get("firstname"), obj.get("last_name") or obj.get("lastname")
    full = " ".join(x for x in (first, last) if x)
    return full or None


def _date(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def parse_card(item: dict, platform: str | None = None) -> dict | None:
    """Carte futreveal -> dict au format du bot (None si inexploitable)."""
    platform = (platform or config.FUTREVEAL_PLATFORM).upper()
    pr = item.get("price") or {}
    if not isinstance(pr, dict):
        pr = {}
    name = _text(item.get("player")) or _text(item, ("common_name", "name", "card_name"))
    if not name or not item.get("id"):
        return None
    rarity_raw = _text(item.get("rarity"))
    card_type = rarity_label(rarity_raw) if rarity_raw else None
    special = bool(item.get("is_special") or item.get("is_icon") or item.get("is_hero"))
    if special and not (classify(card_type) or {}).get("special"):
        card_type = rarity_raw or "Spéciale"  # spéciale pour futreveal, même si le nom de rareté est inconnu chez nous
    price = pr.get(platform)
    return {
        "fr_id": str(item["id"]), "ea_id": item.get("ea_id"), "name": name, "rating": item.get("rating"),
        "position": _text(item.get("primary_position"), ("short_name", "abbreviation", "code", "name")),
        "club": _text(item.get("club")), "league": _text(item.get("league")), "nation": _text(item.get("nation")),
        "card_type": card_type, "special": special,
        "tradeable": not (item.get("is_sbc") or item.get("is_objective")),
        "price": int(price) if isinstance(price, (int, float)) and price > 0 else None,
        "extinct": bool(pr.get(f"is_extinct_{platform.lower()}")),
        "price_updated_at": pr.get("updated_at"), "released_at": item.get("created_at"),
        "image": item.get("player_image_url"),
    }


def price_is_fresh(card: dict, now: datetime | None = None) -> bool:
    ts = _date(card.get("price_updated_at"))
    return bool(ts) and (now or utcnow()) - ts <= timedelta(minutes=config.FUTREVEAL_MAX_PRICE_AGE_MIN)


class FutReveal:
    def __init__(self, fetcher: Fetcher | None = None):
        # accès normal à l'API publique, rythme lent ; en cas de refus on s'arrête (pas de contournement)
        self.f = fetcher or Fetcher(mode="httpx", min_delay=config.FUTREVEAL_MIN_DELAY)
        self._own = fetcher is None

    def close(self) -> None:
        if self._own:
            self.f.close()

    def page(self, n: int, lo: int, hi: int) -> dict:
        url = f"{config.FUTREVEAL_API.rstrip('/')}/cards?" + urlencode({"page": n, "price_from": lo, "price_to": hi})
        res = self.f.get(url, expect="json", retries=1)
        if res.status != 200:
            raise FetchError(f"futreveal page {n} : HTTP {res.status}")
        try:
            data = res.json()
        except ValueError as e:
            raise FetchError(f"futreveal page {n} : réponse non JSON") from e
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise FetchError(f"futreveal page {n} : format inattendu")
        return data

    def cards(self, lo: int | None = None, hi: int | None = None) -> list[dict]:
        """Toutes les cartes VENDABLES dont le prix PS est entre lo et hi (fourchette du site élargie)."""
        lo = lo or config.WATCHLIST_MIN
        hi = hi or config.WATCHLIST_MAX
        out, seen = [], set()
        for n in range(1, config.FUTREVEAL_MAX_PAGES + 1):
            data = self.page(n, int(lo * 0.6), int(hi * 1.6))
            for item in data["items"]:
                c = parse_card(item)
                if c and c["fr_id"] not in seen:
                    seen.add(c["fr_id"])
                    out.append(c)
            if not data.get("has_more") or not data["items"]:
                break
        self.raw_count = len(out)
        kept = [c for c in out if c["tradeable"] and c["price"] and lo <= c["price"] <= hi]
        log.info("futreveal : %d cartes lues (%d page(s)), %d vendables entre %s et %s sur %s", len(out), n,
                 len(kept), lo, hi, config.FUTREVEAL_PLATFORM)
        return kept


# --------------------------------------------------------------------------- rattachement aux joueurs déjà suivis
def assign_ids(cards: list[dict], known: list[dict], save: bool = True) -> list[dict]:
    """Donne à chaque carte son identifiant bot : celui déjà mémorisé, sinon un joueur futgenie correspondant
    (même nom, même note, prix à ±25 %), sinon « fr-<ea_id> »."""
    mapped = db.source_ids(SOURCE)  # fr_id -> player_id
    taken = set(mapped.values())
    by_key: dict[tuple, list[dict]] = {}
    for p in known:
        if str(p.get("player_id", "")).startswith(ID_PREFIX) or not p.get("name") or not p.get("rating"):
            continue
        by_key.setdefault((_norm(p["name"]), int(p["rating"])), []).append(p)
        last = _norm(p["name"]).split()[-1:]
        if last:
            by_key.setdefault(("~" + last[0], int(p["rating"])), []).append(p)
    out = []
    for c in cards:
        pid = mapped.get(c["fr_id"])
        if not pid and c.get("rating"):
            n = _norm(c["name"])
            cands = by_key.get((n, int(c["rating"]))) or by_key.get(("~" + (n.split() or [""])[-1], int(c["rating"])), [])
            cands = [p for p in cands if str(p["player_id"]) not in taken and p.get("price") and c.get("price")
                     and abs(p["price"] / c["price"] - 1) <= 0.25
                     and bool((classify(p.get("card_type")) or {}).get("special")) == bool(c["special"])]
            if cands:
                pid = str(min(cands, key=lambda p: abs(p["price"] / c["price"] - 1))["player_id"])
        if not pid:
            pid = f"{ID_PREFIX}{c.get('ea_id') or c['fr_id']}"
        if pid not in taken or mapped.get(c["fr_id"]) == pid:
            if save:
                db.set_source_id(pid, SOURCE, c["fr_id"])
            taken.add(pid)
            out.append({**c, "player_id": pid})
    return out


def known_players() -> dict[str, dict]:
    """Joueurs déjà connus du bot, avec leur dernier prix relevé (sert au rattachement)."""
    from scrapers.watchlist import load_watchlist

    known = {str(p["player_id"]): p for p in db.get_players()}
    for p in load_watchlist():  # watchlist actuelle (pour le rattachement)
        known.setdefault(str(p["player_id"]), {}).update({k: v for k, v in p.items() if v is not None})
    for pid, snap in db.latest_prices().items():  # dernier prix relevé = le plus fiable pour comparer
        if pid in known and snap.get("price"):
            known[pid]["price"] = snap["price"]
    return known


def build_watchlist() -> list[dict]:
    """Watchlist = toutes les cartes vendables futreveal de la fourchette (avec leur vraie date de sortie)."""
    fr = FutReveal()
    try:
        cards = fr.cards()
    finally:
        fr.close()
    known = known_players()
    players = assign_ids(cards, list(known.values()))
    players.sort(key=lambda c: -(c.get("price") or 0))
    for rank, p in enumerate(players, 1):
        p["popularity_rank"] = rank
        old = known.get(p["player_id"]) or {}
        db.upsert_player({**p, "url": old.get("url"), "source": SOURCE})
    return players


def current_prices(players: list[dict]) -> tuple[dict[str, int], dict]:
    """Prix PS frais des joueurs suivis. Lève FetchError si futreveal ne répond pas correctement."""
    fr = FutReveal()
    try:
        cards = fr.cards()
    finally:
        fr.close()
    by_fr = {c["fr_id"]: c for c in cards}
    mapped = db.source_ids(SOURCE)
    rev = {pid: fr_id for fr_id, pid in mapped.items()}
    prices, stale, extinct = {}, 0, 0
    now = utcnow()
    for p in players:
        pid = str(p["player_id"])
        c = by_fr.get(p.get("fr_id") or rev.get(pid) or "")
        if not c:
            continue
        if c["extinct"]:
            extinct += 1
        elif not price_is_fresh(c, now):
            stale += 1
        else:
            prices[pid] = c["price"]
    stats = {"cards": len(cards), "stale": stale, "extinct": extinct}
    if stale:
        log.warning("futreveal : %d prix trop anciens (> %d min) ignorés", stale, config.FUTREVEAL_MAX_PRICE_AGE_MIN)
    return prices, stats


def dry_run() -> str:
    """Test sans rien enregistrer : ce que futreveal donnerait (commande `main.py futreveal-test`)."""
    fr = FutReveal()
    try:
        cards = fr.cards()
    finally:
        fr.close()
    known = known_players()
    out = assign_ids(cards, list(known.values()), save=False)
    now = utcnow()
    kept = sum(1 for c in out if not str(c["player_id"]).startswith(ID_PREFIX))
    fresh = sum(1 for c in out if price_is_fresh(c, now))
    recent = sum(1 for c in out if (d := _date(c["released_at"])) and now - d < timedelta(days=4))
    lines = [(f"futreveal : {getattr(fr, 'raw_count', '?')} cartes lues, {len(out)} vendables entre "
              f"{config.WATCHLIST_MIN} et {config.WATCHLIST_MAX} (prix {config.FUTREVEAL_PLATFORM})"),
             f"  déjà suivies (historique conservé) : {kept} · nouvelles : {len(out) - kept} · prix frais : {fresh}",
             f"  cartes sorties il y a moins de 4 jours : {recent}",
             "  exemples :"]
    for c in out[:8]:
        lines.append(f"   {c['name']} {c['rating']} | {c['card_type']} | {c['position']} | {c['price']} | "
                     f"sortie {str(c['released_at'])[:10]} | {c['player_id']}")
    return "\n".join(lines)
