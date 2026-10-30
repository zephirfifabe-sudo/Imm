"""Petits utilitaires : parsing de prix, temps, positions FUT."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config

_PRICE_RE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)*)\s*([kKmM]?)\s*$")


def parse_price(value) -> int | None:
    """'67.5K' -> 67500, '1,2M' -> 1200000, '67,500' -> 67500, 67500 -> 67500."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    s = str(value).replace("\xa0", " ").replace(" ", "").strip()
    s = s.replace("coins", "").replace("Coins", "")
    m = _PRICE_RE.match(s)
    if not m:
        return None
    num, suffix = m.groups()
    suffix = suffix.lower()
    if suffix:
        num = num.replace(",", ".")
        if num.count(".") > 1:
            return None
        val = float(num) * (1_000 if suffix == "k" else 1_000_000)
    else:
        # séparateurs de milliers
        val = float(num.replace(",", "").replace(".", ""))
    return int(round(val)) or None


def fmt_price(p: float | int | None) -> str:
    if p is None:
        return "?"
    p = float(p)
    if p >= 1_000_000:
        return f"{p / 1_000_000:.2f}M"
    if p >= 1_000:
        return f"{p / 1_000:.1f}k".replace(".0k", "k")
    return str(int(p))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(config.TZ))


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")


# --- Positions ---
# IDs de position EA (utilisés dans certaines API)
EA_POSITION_IDS = {
    0: "GK", 1: "SW", 2: "RWB", 3: "RB", 4: "CB", 5: "CB", 6: "CB", 7: "LB", 8: "LWB",
    9: "CDM", 10: "CDM", 11: "CDM", 12: "RM", 13: "CM", 14: "CM", 15: "CM", 16: "LM",
    17: "CAM", 18: "CAM", 19: "CAM", 20: "CF", 21: "CF", 22: "CF", 23: "RW", 24: "ST",
    25: "ST", 26: "ST", 27: "LW",
}
POSITIONS = {"GK", "CB", "LB", "RB", "LWB", "RWB", "CDM", "CM", "CAM", "LM", "RM", "LW", "RW", "CF", "ST"}

# "poste ±1" : postes voisins sur le terrain
ADJACENT = {
    "GK": {"GK"},
    "CB": {"CB", "CDM"},
    "LB": {"LB", "LWB"},
    "RB": {"RB", "RWB"},
    "LWB": {"LWB", "LB", "LM"},
    "RWB": {"RWB", "RB", "RM"},
    "CDM": {"CDM", "CM", "CB"},
    "CM": {"CM", "CDM", "CAM"},
    "CAM": {"CAM", "CM", "CF"},
    "LM": {"LM", "LW", "LWB"},
    "RM": {"RM", "RW", "RWB"},
    "LW": {"LW", "LM", "ST"},
    "RW": {"RW", "RM", "ST"},
    "CF": {"CF", "ST", "CAM"},
    "ST": {"ST", "CF"},
}

# Groupes larges pour la règle de saturation
POSITION_GROUP = {
    "GK": "GK", "CB": "CB",
    "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    "CDM": "MDC", "CM": "MC",
    "CAM": "MOC", "CF": "ATT", "ST": "ATT",
    "LM": "AIL", "RM": "AIL", "LW": "AIL", "RW": "AIL",
}


def normalize_position(pos) -> str | None:
    if pos is None:
        return None
    if isinstance(pos, int) or (isinstance(pos, str) and pos.isdigit()):
        return EA_POSITION_IDS.get(int(pos))
    p = str(pos).upper().strip()
    return p if p in POSITIONS else None


def position_distance_score(a: str | None, b: str | None) -> float:
    """1.0 même poste, 0.75 poste voisin (±1), 0 sinon."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if b in ADJACENT.get(a, set()) or a in ADJACENT.get(b, set()):
        return 0.75
    return 0.0
