"""Leaks (FutSheriff & co) — info 2h à 6h avant EA.

Plan A : aperçu web PUBLIC d'un canal Telegram : https://t.me/s/<canal>
         -> aucun compte / API key nécessaire, HTML stable (.tgme_widget_message).
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


def fetch_leaks(watch_names: list[str] | None = None, fetcher: Fetcher | None = None) -> list[dict]:
    """Renvoie les leaks NOUVEAUX, tagués (promo, SBC, joueurs de la watchlist cités)."""
    watch_names = watch_names or []
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    raw: list[dict] = []
    try:
        if config.LEAK_CHANNEL_URL:
            url = telegram_url(config.LEAK_CHANNEL_URL)
            try:
                raw += parse_telegram_page(fetcher.get(url).text, url)
            except FetchError as e:
                log.warning("Plan A Telegram KO : %s", e)
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
    if not config.LEAK_CHANNEL_URL and not config.NITTER_URL:
        log.info("Aucune source de leaks configurée (LEAK_CHANNEL_URL / NITTER_URL)")
    new = []
    for leak in raw:
        leak["tags"] = tag_leak(leak["text"], watch_names)
        if db.save_leak(leak):
            if leak["tags"]:
                db.add_event("leak", title=leak["text"][:120], payload=leak)
            new.append(leak)
    log.info("Leaks : %d nouveaux", len(new))
    return new
