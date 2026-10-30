"""Tables EA : ID -> nom (ligues, nations, raretés).

FUT.GG renvoie des IDs EA (leagueEaId, nationEaId, rarityEaId) au lieu des noms.
Ces tables couvrent les cas courants ; un ID inconnu reste comparable (R1 compare
les IDs) et s'affiche « Ligue #123 ». Les tables trouvées dans les pages FUT.GG
complètent automatiquement ces valeurs (voir learn_from_blobs).
"""
from __future__ import annotations

LEAGUES = {
    13: "Premier League", 16: "Ligue 1", 53: "LALIGA EA SPORTS", 19: "Bundesliga", 31: "Serie A",
    10: "Eredivisie", 308: "Liga Portugal", 14: "EFL Championship", 4: "Pro League (BEL)", 68: "Süper Lig",
    350: "Roshn Saudi League", 39: "MLS", 17: "Ligue 2", 20: "2. Bundesliga", 32: "Serie B", 54: "LALIGA HYPERMOTION",
    50: "Scottish Premiership", 1: "Superliga (DEN)", 80: "Bundesliga (AUT)", 189: "Super League (SUI)",
    2118: "Icons", 2136: "Heroes",
}

NATIONS = {
    14: "England", 18: "France", 21: "Germany", 27: "Italy", 45: "Spain", 38: "Portugal", 34: "Netherlands",
    7: "Belgium", 54: "Brazil", 52: "Argentina", 60: "Uruguay", 56: "Colombia", 10: "Croatia", 13: "Denmark",
    36: "Norway", 46: "Sweden", 47: "Switzerland", 4: "Austria", 37: "Poland", 48: "Türkiye", 49: "Ukraine",
    51: "Serbia", 12: "Czechia", 42: "Scotland", 50: "Wales", 25: "Republic of Ireland", 129: "Morocco",
    97: "Algeria", 136: "Senegal", 133: "Nigeria", 108: "Côte d'Ivoire", 117: "Ghana", 103: "Cameroon",
    111: "Egypt", 95: "United States", 83: "Mexico", 70: "Canada", 163: "Japan", 167: "Korea Republic",
    195: "Australia", 58: "Ecuador", 55: "Chile",
}

# rarityEaId -> libellé (utils.rarity.classify le normalise ensuite)
RARITIES = {
    0: "Gold Common", 1: "Gold Rare", 3: "TOTW", 12: "Icon", 72: "Heroes",
}


def name(table: dict, value, prefix: str) -> str | None:
    if value in (None, "", "None"):
        return None
    try:
        key = int(value)
    except (TypeError, ValueError):
        return str(value)
    return table.get(key) or f"{prefix} #{key}"


def learn_from_blobs(dicts) -> int:
    """Complète les tables avec les listes {id/eaId, name} trouvées dans le JSON des pages FUT.GG."""
    added = 0
    for d in dicts:
        for key, val in d.items():
            if not isinstance(val, list) or not val or not isinstance(val[0], dict):
                continue
            k = key.lower()
            table = LEAGUES if "league" in k else NATIONS if "nation" in k else RARITIES if "rarit" in k else None
            if table is None:
                continue
            for item in val:
                i = item.get("eaId", item.get("id"))
                n = item.get("name") or item.get("longName")
                try:
                    i = int(i)
                except (TypeError, ValueError):
                    continue
                if isinstance(n, str) and n and i not in table:
                    table[i] = n
                    added += 1
    return added
