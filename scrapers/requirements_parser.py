"""Parsing texte des prérequis SBC / Evolutions et des boosts d'Evo.

Volontairement basé sur le TEXTE (pas sur des classes CSS) : le wording EA est stable
("Min. Team Rating: 84", "Max Overall 82", "+3 Overall"...), le HTML des sites ne l'est pas.
"""
from __future__ import annotations

import re

from utils.helpers import POSITIONS

META_PLAYSTYLES = {
    "rapid", "quick step", "first touch", "technical", "trickster", "press proven", "finesse shot",
    "power shot", "low driven shot", "incisive pass", "tiki taka", "whipped pass", "pinged pass",
    "intercept", "anticipate", "jockey", "bruiser", "block", "slide tackle", "aerial", "relentless",
    "acrobatic", "chip shot", "long ball pass", "far reach", "footwork", "rush out",
}
STATS = {"pace": "PAC", "pac": "PAC", "shooting": "SHO", "sho": "SHO", "passing": "PAS", "pas": "PAS",
         "dribbling": "DRI", "dri": "DRI", "defending": "DEF", "defence": "DEF", "def": "DEF",
         "physical": "PHY", "physicality": "PHY", "phy": "PHY", "overall": "OVR", "ovr": "OVR",
         "skill moves": "SM", "weak foot": "WF"}
_STAT_ALT = "|".join(sorted((re.escape(k) for k in STATS), key=len, reverse=True))


def parse_sbc_requirements(text: str) -> dict:
    t = text.replace("\xa0", " ")
    req: dict = {"min_team_rating": None, "min_player_rating": None, "leagues": [], "nations": [],
                 "clubs": [], "rarities": [], "squads": [], "raw": []}
    ratings = [int(x) for x in re.findall(r"(?:Min\.?\s*)?Team Rating[:\s]*(?:Min\.?\s*)?(\d{2})", t, re.I)]
    if ratings:
        req["min_team_rating"] = max(ratings)
    m = re.findall(r"Min\.?\s*OVR\s*(?:of\s*)?(\d{2})|Player (?:Rating|OVR)[:\s]*Min\.?\s*(\d{2})", t, re.I)
    vals = [int(a or b) for a, b in m if (a or b)]
    if vals:
        req["min_player_rating"] = max(vals)
    for mult, rating in re.findall(r"\b(\d{1,2})\s*x\s*(\d{2})\b", t):  # "84x10" ou "10x84"
        a, b = int(mult), int(rating)
        rating_val = a if 75 <= a <= 99 else b
        req["squads"].append(rating_val)
    for a, b in re.findall(r"\b(\d{2})\s*x\s*(\d{1,2})\b", t):
        if 75 <= int(a) <= 99 and int(a) not in req["squads"]:
            req["squads"].append(int(a))
    for kind, key in (("League", "leagues"), ("Nation", "nations"), ("Region", "nations"), ("Club", "clubs")):
        for v in re.findall(rf"(?:Players? from|{kind}s?)\s*[:\-]?\s*([A-Z][\w .'\-]+?)(?:\n|,|;|$| Min| Max)", t):
            v = v.strip(" .-")
            if v and v.lower() not in ("same", "different", "min", "max") and v not in req[key]:
                req[key].append(v)
    # alias courants
    aliases = {"L1": "Ligue 1", "Ligue 1": "Ligue 1", "Premier League": "Premier League", "LaLiga": "LALIGA EA SPORTS",
               "Serie A": "Serie A", "Bundesliga": "Bundesliga", "Eredivisie": "Eredivisie"}
    for k, v in aliases.items():
        if re.search(rf"\b{re.escape(k)}\b", t) and v not in req["leagues"]:
            req["leagues"].append(v)
    for rar in ("TOTW", "Team of the Week", "Rare", "Gold", "Inform", "IF"):
        if re.search(rf"\b{re.escape(rar)}\b", t, re.I):
            req["rarities"].append(rar)
    req["raw"] = [ln.strip() for ln in t.splitlines() if re.search(r"min|max|rating|league|nation|club|x\d", ln, re.I)][:30]
    return req


def parse_evo_requirements(text: str) -> dict:
    t = text.replace("\xa0", " ")
    req: dict = {"max": {}, "min": {}, "positions": [], "rarities": [], "max_playstyles_plus": None}
    for stat, val in re.findall(rf"(?:Max\.?\s*)({_STAT_ALT})\s*[:\-]?\s*(\d{{1,2}})", t, re.I):
        req["max"][STATS[stat.lower()]] = int(val)
    for stat, val in re.findall(rf"({_STAT_ALT})\s*[:\-]?\s*Max\.?\s*(\d{{1,2}})", t, re.I):
        req["max"].setdefault(STATS[stat.lower()], int(val))
    for stat, val in re.findall(rf"(?:Min\.?\s*)({_STAT_ALT})\s*[:\-]?\s*(\d{{1,2}})", t, re.I):
        req["min"][STATS[stat.lower()]] = int(val)
    m = re.search(r"Position[s]?\s*[:\-]?\s*([A-Z/, ]{2,40})", t)
    if m:
        req["positions"] = [p for p in re.split(r"[/, ]+", m.group(1).upper()) if p in POSITIONS]
    m = re.search(r"Max\.?\s*PlayStyles?\+\s*[:\-]?\s*(\d)", t, re.I)
    if m:
        req["max_playstyles_plus"] = int(m.group(1))
    for rar in ("Rare", "Common", "Gold", "Silver", "Bronze", "Special", "Non-Rare"):
        if re.search(rf"\bRarity\b[^\n]*\b{rar}\b", t, re.I):
            req["rarities"].append(rar)
    return req


def parse_evo_upgrades(text: str) -> dict:
    t = text.replace("\xa0", " ")
    up: dict = {"stats": {}, "playstyles": [], "playstyles_plus": [], "positions": []}
    for val, stat in re.findall(rf"\+\s*(\d{{1,2}})\s*({_STAT_ALT})\b", t, re.I):
        k = STATS[stat.lower()]
        up["stats"][k] = up["stats"].get(k, 0) + int(val)
    low = t.lower()
    for ps in sorted(META_PLAYSTYLES):
        if re.search(rf"{re.escape(ps)}\s*\+|{re.escape(ps)} plus|playstyle\+?\s*:?\s*{re.escape(ps)}\+", low):
            up["playstyles_plus"].append(ps.title())
        elif re.search(rf"\b{re.escape(ps)}\b", low):
            up["playstyles"].append(ps.title())
    for p in re.findall(r"(?:New|Add(?:ed)?|\+)\s*Position\s*[:\-]?\s*([A-Z]{2,3})", t):
        if p in POSITIONS:
            up["positions"].append(p)
    return up
