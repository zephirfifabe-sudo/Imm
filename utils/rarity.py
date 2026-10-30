"""Raretés / versions des cartes FUT : nom court, couleur et catégorie (base, spéciale, héros, icône, evo).

Les sites écrivent la même rareté de plusieurs façons ("Team of the Week", "TOTW", "Inform", "IF"...).
classify() renvoie un libellé unique et court pour le dashboard et les alertes.
"""
from __future__ import annotations

import re

# (motif, libellé court, couleur, catégorie). Ordre important : le plus spécifique d'abord.
RARITIES: list[tuple[str, str, str, str]] = [
    (r"\btotw moments?\b", "TOTW Moments", "#e5e7eb", "special"),
    (r"\b(totw|team of the week|inform|in-form)\b|^if$", "TOTW", "#d4d4d8", "special"),
    (r"\b(toty|team of the year)\b", "TOTY", "#3b82f6", "special"),
    (r"\b(tots|team of the season)\b", "TOTS", "#0ea5e9", "special"),
    (r"\b(potm|player of the month)\b", "POTM", "#f59e0b", "special"),
    (r"\btrailblazers?\b", "Trailblazers", "#f97316", "special"),
    (r"\bthunderstruck\b", "Thunderstruck", "#a855f7", "special"),
    (r"\bcenturions?\b", "Centurions", "#f87171", "special"),
    (r"\bfuture stars?\b", "Future Stars", "#22d3ee", "special"),
    (r"\b(fut )?birthday\b", "FUT Birthday", "#ec4899", "special"),
    (r"\bflashback\b", "Flashback", "#14b8a6", "special"),
    (r"\b(rttk|road to the knockouts?)\b", "RTTK", "#60a5fa", "special"),
    (r"\b(rttf|road to the final)\b", "RTTF", "#ea580c", "special"),
    (r"\b(ucl|champions league)\b", "UCL", "#818cf8", "special"),
    (r"\b(uel|europa league)\b", "UEL", "#f97316", "special"),
    (r"\b(uecl|conference league)\b", "UECL", "#22c55e", "special"),
    (r"\bultimate dynast(y|ies)\b", "Ultimate Dynasties", "#eab308", "special"),
    (r"\bfestival of football\b", "Festival of Football", "#84cc16", "special"),
    (r"\b(ones to watch|otw)\b", "OTW", "#f43f5e", "special"),
    (r"\bwinter wildcards?\b", "Winter Wildcards", "#60a5fa", "special"),
    (r"\brulebreakers?\b", "Rulebreakers", "#8b5cf6", "special"),
    (r"\bshowdown\b", "Showdown", "#ef4444", "special"),
    (r"\btotal rush\b", "Total Rush", "#facc15", "special"),
    (r"\btrack stars?\b", "Track Stars", "#06b6d4", "special"),
    (r"\bfantasy\b", "Fantasy FC", "#10b981", "special"),
    (r"\bmoments?\b", "Moments", "#c084fc", "special"),
    (r"\bfoundations?\b", "Foundations", "#a3a3a3", "special"),
    (r"\b(sbc|squad building)\b", "SBC", "#2dd4bf", "special"),
    (r"\bobjectives?\b", "Objectif", "#4ade80", "special"),
    (r"\b(evo|evolution)s?\b", "Evo", "#34d399", "evo"),
    (r"\bheroe?s?\b", "Héros", "#facc15", "hero"),
    (r"\bicons?\b", "Icône", "#fde68a", "icon"),
    (r"\b(gold|^or)\b.*\b(non[- ]?rare|common)\b|\b(non[- ]?rare|common)\b.*\bgold\b|^common$", "Or non rare", "#b8860b", "base"),
    (r"\b(gold|^or)\b.*\brare\b|\brare\b.*\bgold\b|^rare$", "Or rare", "#ca8a04", "base"),
    (r"\bgold\b|^or$", "Or", "#b8860b", "base"),
    (r"\b(silver|argent)\b", "Argent", "#94a3b8", "base"),
    (r"\bbronze\b", "Bronze", "#d97706", "base"),
]
_COMPILED = [(re.compile(p, re.I), label, color, cat) for p, label, color, cat in RARITIES]
SPECIAL_CATEGORIES = {"special", "hero", "icon", "evo"}


def classify(raw) -> dict | None:
    """'Team of the Week' -> {'label': 'TOTW', 'color': '#d4d4d8', 'category': 'special', 'special': True}."""
    if raw is None or isinstance(raw, bool):
        return None
    text = str(raw).strip()
    if not text or text.isdigit():  # un ID numérique ne dit rien d'utile à l'utilisateur
        return None
    for rx, label, color, cat in _COMPILED:
        if rx.search(text):
            return {"label": label, "color": color, "category": cat, "special": cat in SPECIAL_CATEGORIES, "raw": text}
    # promo inconnue (nouvelle promo FC27) : on garde le nom d'origine, considérée comme spéciale
    return {"label": text[:24], "color": "#e879f9", "category": "special", "special": True, "raw": text}


def label(raw) -> str | None:
    c = classify(raw)
    return c["label"] if c else None


def detect_in_text(text: str) -> str | None:
    """Cherche une promo connue dans un texte libre (texte d'une carte, alt d'image). Ignore les cartes de base."""
    for rx, lab, _color, cat in _COMPILED:
        if cat != "base" and rx.search(text or ""):
            return lab
    return None
