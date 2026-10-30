"""Extraction générique de joueurs depuis du HTML.

Les sites FUT changent souvent leur HTML. Plutôt que de dépendre d'une seule classe CSS,
on combine 2 stratégies :
  1) JSON embarqué (Next.js __NEXT_DATA__, application/json, ld+json, window.__STATE__=...)
     -> on parcourt récursivement et on garde tout dict qui "ressemble" à une carte joueur.
  2) Ancres HTML /players/<id>-<slug>/<year>-<eaId>/ + texte de la carte (note, poste, prix).
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from utils.helpers import POSITIONS, normalize_position, parse_price
from utils import fut_ids
from utils.rarity import detect_in_text, label as rarity_label

NAME_KEYS = ("commonName", "common_name", "cardName", "displayName", "name", "lastName", "last_name")
RATING_KEYS = ("overall", "rating", "ovr", "overallRating")
ID_KEYS = ("eaId", "ea_id", "resourceId", "resource_id", "id", "playerId", "player_id")
PRICE_KEYS = ("price", "currentPrice", "lowestBin", "lcPrice", "LCPrice", "bin", "ps_LCPrice", "averageBin")

FUTGG_LINK_RE = re.compile(r"/players/(\d+)-([a-z0-9-]+)/(?:(\d{2})-(\d+)/?)?", re.I)
WINDOW_STATE_RE = re.compile(r"window\.__[A-Za-z_]+__\s*=\s*")


def _balanced_json(text: str, start: int) -> str | None:
    """Extrait l'objet JSON commençant à text[start] ('{' ou '[')."""
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth, in_str, esc = 0, False, False
    for i in range(start, min(len(text), start + 5_000_000)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def iter_json_blobs(html: str) -> Iterator[Any]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script"):
        txt = tag.string or tag.get_text() or ""
        txt = txt.strip()
        if not txt:
            continue
        typ = (tag.get("type") or "").lower()
        if "json" in typ or txt[:1] in "{[":
            try:
                yield json.loads(txt)
                continue
            except ValueError:
                pass
        for m in WINDOW_STATE_RE.finditer(txt):
            i = m.end()
            if i < len(txt) and txt[i] in "{[":
                blob = _balanced_json(txt, i)
                if blob:
                    try:
                        yield json.loads(blob)
                    except ValueError:
                        pass
    if "self.__next_f" in html:
        yield from next_flight_blobs(html)


NEXT_F_RE = re.compile(r'self\.__next_f\.push\(\[\s*1\s*,\s*("(?:[^"\\]|\\.)*")\s*\]\)', re.S)
RSC_ROW_RE = re.compile(r"^[0-9a-zA-Z]+:([\[{].*)$", re.M)


def next_flight_text(html: str) -> str:
    """Next.js (App Router) : les données de la page sont dans des blocs self.__next_f.push([1, "..."])."""
    parts = []
    for m in NEXT_F_RE.finditer(html):
        try:
            parts.append(json.loads(m.group(1)))
        except ValueError:
            continue
    return "".join(parts)


def next_flight_blobs(html: str) -> Iterator[Any]:
    """Chaque ligne « id:[...] » ou « id:{...} » du flux Next.js est du JSON."""
    text = next_flight_text(html)
    for m in RSC_ROW_RE.finditer(text):
        try:
            yield json.loads(m.group(1))
        except ValueError:
            continue


def walk_dicts(obj: Any, depth: int = 0) -> Iterator[dict]:
    if depth > 40:
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_dicts(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_dicts(v, depth + 1)


def pick(d: dict, *keys: str, default=None):
    """pick(d, 'league.name', 'leagueName') : premier chemin non vide (support des chemins pointés)."""
    for key in keys:
        cur: Any = d
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if cur not in (None, "", [], {}):
            return cur
    return default


def _name_of(v) -> str | None:
    if isinstance(v, dict):
        return pick(v, "name", "abbrName", "shortName", "longName")
    if isinstance(v, (str, int)):
        return str(v)
    return None


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def looks_like_player(d: dict) -> bool:
    rating = _int(pick(d, *RATING_KEYS))  # FUT.GG peut renvoyer "87" (texte) ou 87
    if rating is None or not (40 <= rating <= 99):
        return False
    if not any(isinstance(d.get(k), str) and d.get(k) for k in NAME_KEYS):
        if not (d.get("firstName") or d.get("lastName")):
            return False
    return pick(d, *ID_KEYS) is not None


def player_from_dict(d: dict, base_url: str = "") -> dict:
    name = pick(d, "commonName", "common_name", "cardName", "displayName", "nickname")
    if not name:
        first, last = d.get("firstName") or "", d.get("lastName") or ""
        name = (f"{first} {last}".strip() if first or last else None) or d.get("name")
    pos = normalize_position(pick(d, "position", "positionId", "positionEaId", "mainPosition", "positionShort",
                                  "preferredPosition", "pos"))
    alt = pick(d, "alternativePositionIds", "alternativePositions", "alternatePositions", "altPositions",
               "positions", default=[]) or []
    alt = [p for p in (normalize_position(x) for x in alt) if p and p != pos] if isinstance(alt, list) else []
    price = None
    for k in PRICE_KEYS:
        v = d.get(k)
        if isinstance(v, dict):
            v = pick(v, "price", "value", "lcPrice")
        price = parse_price(v)
        if price:
            break
    playstyles = []
    for k in ("playstylesPlus", "playStylesPlus", "playstyles", "playStyles", "traits"):
        v = d.get(k)
        if isinstance(v, list):
            for ps in v:
                n = _name_of(ps)
                if n and not n.isdigit():  # IDs numériques de playstyles : sans intérêt pour l'utilisateur
                    playstyles.append(n + ("+" if "Plus" in k and not n.endswith("+") else ""))
    url = d.get("url") or d.get("href")
    return {
        "player_id": str(pick(d, *ID_KEYS)),
        "base_id": str(pick(d, "basePlayerEaId", "baseId", "base_id", "basePlayerId", default="") or "") or None,
        "name": str(name or "?"),
        "rating": _int(pick(d, *RATING_KEYS)),
        "position": pos,
        "alt_positions": alt,
        "league": _name_of(pick(d, "league", "leagueName", "league_name"))
        or fut_ids.name(fut_ids.LEAGUES, pick(d, "leagueEaId", "leagueId"), "Ligue"),
        "nation": _name_of(pick(d, "nation", "nationName", "nation_name", "country"))
        or fut_ids.name(fut_ids.NATIONS, pick(d, "nationEaId", "nationId"), "Nation"),
        "club": _name_of(pick(d, "club", "clubName", "club_name", "team")) or _club_from_slug(d),
        "card_type": _card_type(d),
        "playstyles": playstyles,
        "price": price,
        "url": urljoin(base_url, url) if url else None,
    }


def _card_type(d: dict) -> str | None:
    """Nom de rareté lisible (TOTW, Trailblazers, Or rare...). Les IDs numériques sont ignorés."""
    for key in ("rarityName", "rarity.name", "cardRarity", "programName", "promo.name", "promo",
                "versionName", "version", "cardType", "rarity", "itemType"):
        lab = rarity_label(_name_of(pick(d, key)))
        if lab:
            return lab
    # FUT.GG : uniquement un ID (rarityEaId). Inconnu -> « Rareté #85 », affiché comme spéciale
    rid = pick(d, "rarityEaId", "rarityId")
    return rarity_label(fut_ids.name(fut_ids.RARITIES, rid, "Rareté")) if rid not in (None, "None") else None


def _club_from_slug(d: dict) -> str | None:
    """'114605-hero' -> 'Hero' ; sinon l'ID du club (suffisant pour comparer)."""
    slug = pick(d, "uniqueClubSlug", "clubSlug")
    if isinstance(slug, str) and "-" in slug:
        return slug.split("-", 1)[1].replace("-", " ").title()
    cid = pick(d, "clubEaId", "uniqueClubEaId", "clubId")
    return f"Club #{cid}" if cid not in (None, "None") else None


def players_from_json(html: str, base_url: str = "") -> list[dict]:
    out: dict[str, dict] = {}
    for blob in iter_json_blobs(html):
        fut_ids.learn_from_blobs(walk_dicts(blob))  # tables ID -> nom fournies par la page
        for d in walk_dicts(blob):
            if looks_like_player(d):
                p = player_from_dict(d, base_url)
                out.setdefault(p["player_id"], p)
    return list(out.values())


_TOKEN_PRICE = re.compile(r"^\d{1,3}(?:[.,]\d{1,3})*(?:[kKmM])?$")


def players_from_anchors(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        m = FUTGG_LINK_RE.search(a["href"])
        if not m:
            continue
        base_id, slug, _year, ea_id = m.groups()
        pid = ea_id or base_id
        tokens = a.get_text(" ", strip=True).split()
        img = a.find("img")
        if img and img.get("alt"):
            tokens += img["alt"].replace("-", " ").split()
        rating = next((int(t) for t in tokens if t.isdigit() and 40 <= int(t) <= 99), None)
        pos = next((t.upper() for t in tokens if t.upper() in POSITIONS), None)
        price = None
        for t in tokens:
            if _TOKEN_PRICE.match(t) and (t[-1] in "kKmM" or "," in t or "." in t):
                price = parse_price(t)
                if price:
                    break
        data_price = a.get("data-price") or (a.find(attrs={"data-price": True}) or {}).get("data-price")
        price = parse_price(data_price) or price
        name = slug.replace("-", " ").title()
        if pid in out:
            continue
        card_type = detect_in_text(" ".join(tokens))
        out[pid] = {
            "player_id": pid, "base_id": base_id, "name": name, "rating": rating, "position": pos,
            "alt_positions": [], "league": None, "nation": None, "club": None, "card_type": card_type,
            "playstyles": [], "price": price, "url": urljoin(base_url, a["href"]),
        }
    return list(out.values())


def extract_players(html: str, base_url: str) -> list[dict]:
    """Fusionne JSON embarqué (riche) + ancres (fiable). Ordre des ancres = ordre de la page (popularité)."""
    by_json = {p["player_id"]: p for p in players_from_json(html, base_url)}
    anchors = players_from_anchors(html, base_url)
    merged: list[dict] = []
    seen = set()
    for a in anchors:
        j = by_json.get(a["player_id"])
        p = {**a, **{k: v for k, v in (j or {}).items() if v not in (None, "", [], "?")}}
        merged.append(p)
        seen.add(a["player_id"])
    merged += [p for pid, p in by_json.items() if pid not in seen]
    return merged


def page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return re.sub(r"[ \t]+", " ", soup.get_text("\n", strip=True))
