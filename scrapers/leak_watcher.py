"""Leaks (FutSheriff & co) — info 2h à 6h avant EA.

Plan A : aperçu web PUBLIC de canaux Telegram : https://t.me/s/<canal>  (LEAK_CHANNELS, séparés par des virgules)
         -> aucun compte / API key nécessaire, HTML stable (.tgme_widget_message).
Chaque leak est classé (SBC, promo, Évo, objectif…), ses notes / postes / ligues / joueurs sont extraits et un
IMPACT ESTIMÉ est proposé. Un leak n'est jamais confirmé : il informe, il ne change aucune décision du bot.
Plan B : Nitter (miroir Twitter) via flux RSS : {NITTER_URL}/{compte}/rss
         -> les instances Nitter tombent souvent : à n'activer que si besoin.
"""
from __future__ import annotations

import hashlib
import re
from xml.etree import ElementTree

from bs4 import BeautifulSoup

import config
from database import db
from scrapers.base import FetchError, Fetcher
from utils.logger import get_logger

log = get_logger("leaks")

PROMO_KEYWORDS = [
    "totw", "team of the week", "potm", "player of the month", "sbc", "evolution", "evo", "objective",
    "promo", "loading screen", "team 1", "team 2", "flashback", "hero", "icon", "trailblazers", "centurions",
    "thunderstruck", "future stars", "fut birthday", "tots", "toty", "rttk", "road to the knockouts",
    "ultimate dynasties", "festival of football", "marquee matchups", "upgrade", "pack", "leak", "coming",
]


def telegram_url(raw: str) -> str:
    """Accepte 'canal', '@canal', 't.me/canal', 'https://t.me/canal' -> https://t.me/s/canal."""
    raw = raw.strip()
    m = re.search(r"(?:t\.me/(?:s/)?)?@?([A-Za-z0-9_]{4,})/?$", raw)
    return f"https://t.me/s/{m.group(1)}" if m else raw


def parse_telegram_page(html: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for msg in soup.select(".tgme_widget_message"):
        post = msg.get("data-post") or ""
        body = msg.select_one(".tgme_widget_message_text")
        if not body:
            continue
        text = body.get_text("\n", strip=True)
        t = msg.select_one("time[datetime]")
        out.append({
            "leak_id": f"tg:{post}" if post else "tg:" + hashlib.sha1(text.encode()).hexdigest()[:16],
            "timestamp": t["datetime"] if t else None,
            "source": source,
            "text": text,
        })
    return out


def parse_nitter_rss(xml: str, account: str) -> list[dict]:
    out = []
    root = ElementTree.fromstring(xml)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        desc = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)
        link = item.findtext("link") or ""
        out.append({
            "leak_id": "x:" + (link.rsplit("/", 1)[-1].split("#")[0] or hashlib.sha1(title.encode()).hexdigest()[:16]),
            "timestamp": item.findtext("pubDate"),
            "source": f"nitter:{account}",
            "text": desc or title,
        })
    return out


def tag_leak(text: str, watch_names: list[str]) -> list[str]:
    low = text.lower()
    tags = sorted({k for k in PROMO_KEYWORDS if re.search(rf"\b{re.escape(k)}\b", low)})
    for name in watch_names:
        last = name.split()[-1].lower()
        if len(last) >= 4 and re.search(rf"\b{re.escape(last)}\b", low):
            tags.append(f"player:{name}")
    return tags


# --------------------------------------------------------------------------- analyse d'un leak
POSITIONS_RE = re.compile(r"\b(GK|CB|LB|RB|LWB|RWB|CDM|CM|CAM|LM|RM|LW|RW|ST|CF)\b")
RATING_RE = re.compile(r"(?<![\d.,])(7[5-9]|8\d|9\d)(?![\d.,]|\s?[kK%]|\s?(?:min|h)\b)")
LEAGUE_ALIASES = {
    "Premier League": r"premier league|\bepl\b|\bpl\b", "LALIGA EA SPORTS": r"la ?liga", "Ligue 1": r"ligue 1",
    "Bundesliga": r"(?<!2\. )bundesliga", "Serie A": r"serie a\b", "Eredivisie": r"eredivisie",
    "Liga Portugal": r"liga portugal", "Roshn Saudi League": r"saudi|roshn", "MLS": r"\bmls\b",
}
KINDS = [  # (type, motif) : le premier qui correspond l'emporte
    ("sbc", r"\bsbc\b|squad building"), ("evo", r"\bevo(lution)?s?\b"), ("objectif", r"\bobjectives?\b"),
    ("totw", r"\btotw\b|team of the week"),
    ("promo", r"\bteam [1-9]\b|\bpromo\b|loading screen|thunderstruck|ultimate scream|\brttk\b|road to the knockouts|"
              r"\btoty\b|\btots\b|future stars|trailblazers|winter wildcards|centurions|fut birthday|flashback"),
    ("icone", r"\bicons?\b|\bheroe?s?\b"), ("packs", r"\bpacks?\b|lightning round"),
]
KIND_LABEL = {"sbc": "SBC", "evo": "Évolution", "objectif": "Objectif", "totw": "TOTW", "promo": "Promo",
              "icone": "Icône / Héros", "packs": "Packs", "info": "Info"}


def analyze_leak(text: str, watchlist: list[dict] | None = None) -> dict:
    """Type, notes, postes, ligues, joueurs suivis cités + impacts ESTIMÉS (hypothèses, jamais des faits)."""
    from utils.helpers import POSITION_GROUP

    watchlist = watchlist or []
    low = text.lower()
    kind = next((k for k, rx in KINDS if re.search(rx, low)), "info")
    ratings = sorted({int(r) for r in RATING_RE.findall(text)})
    positions = sorted(set(POSITIONS_RE.findall(text)))
    leagues = [lg for lg, rx in LEAGUE_ALIASES.items() if re.search(rx, low)]
    players = [p for p in watchlist if (last := (p.get("name") or "").split()[-1:]) and len(last[0]) >= 4
               and re.search(rf"\b{re.escape(last[0].lower())}\b", low)]
    impact = [f"⚠️ {p['name']} (ta liste) est cité : surveille son prix." for p in players[:3]]
    if kind == "sbc" and ratings:
        fodder = [r for r in ratings if 82 <= r <= 91]
        if fodder:
            impact.append(f"Demande SBC possible sur les {', '.join(map(str, fodder))} : leur prix pourrait monter "
                          f"avant la sortie (hypothèse, KB-K-001).")
    if kind in ("promo", "totw", "icone") and positions and ratings:
        groups = {POSITION_GROUP.get(pos) for pos in positions}
        top = max(ratings)
        rivals = [p for p in watchlist if POSITION_GROUP.get(p.get("position") or "") in groups
                  and (not leagues or p.get("league") in leagues) and (p.get("rating") or 0) <= top and p not in players]
        for p in rivals[:3]:
            impact.append(f"Nouvelle carte {'/'.join(positions)}{' ' + leagues[0] if leagues else ''} {top} : "
                          f"concurrence possible pour {p['name']} {p.get('rating') or ''} (hypothèse).")
    if kind == "evo":
        impact.append("Évolution annoncée : les cartes bon marché éligibles sont souvent recherchées à sa sortie (KB-K-003).")
    return {"kind": kind, "kind_label": KIND_LABEL.get(kind, kind), "ratings": ratings, "positions": positions,
            "leagues": leagues, "players": [p["name"] for p in players], "impact": impact}


def channels() -> list[str]:
    return [telegram_url(c) for c in config.LEAK_CHANNELS]


def fetch_leaks(watch_names: list[str] | None = None, fetcher: Fetcher | None = None) -> list[dict]:
    """Renvoie les leaks NOUVEAUX, tagués (promo, SBC, joueurs de la watchlist cités).

    `initial=True` : 1re lecture d'un canal (son historique récent), à ne pas notifier.
    """
    watch_names = watch_names or []
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    raw: list[dict] = []
    try:
        for url in channels():
            try:
                page = parse_telegram_page(fetcher.get(url).text, url)
            except FetchError as e:
                log.warning("Canal Telegram KO (%s) : %s", url, e)
                continue
            with db.get_conn() as c:
                known = c.execute("SELECT 1 FROM leaks WHERE source=? LIMIT 1", (url,)).fetchone()
            for leak in page:
                leak["initial"] = known is None
            raw += page
        if config.NITTER_URL and (not raw):
            for acc in config.NITTER_ACCOUNTS:
                try:
                    res = fetcher.get(f"{config.NITTER_URL.rstrip('/')}/{acc}/rss")
                    raw += parse_nitter_rss(res.text, acc)
                except (FetchError, ElementTree.ParseError) as e:
                    log.warning("Plan B Nitter KO (%s) : %s", acc, e)
    finally:
        if own:
            fetcher.close()
    if not config.LEAK_CHANNELS and not config.NITTER_URL:
        log.info("Aucune source de leaks configurée (LEAK_CHANNELS / NITTER_URL)")
    new = []
    for leak in raw:
        leak["tags"] = tag_leak(leak["text"], watch_names)
        if db.save_leak(leak):
            if leak["tags"]:
                db.add_event("leak", title=leak["text"][:120], payload=leak)
            new.append(leak)
    log.info("Leaks : %d nouveaux", len(new))
    return new
