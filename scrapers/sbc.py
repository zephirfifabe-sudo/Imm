"""SBC actifs (FUT.GG /sbc/) : détecte les nouveaux défis et parse leurs prérequis."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from database import db
from scrapers.base import FetchError, Fetcher
from scrapers.parsing import page_text
from scrapers.requirements_parser import parse_sbc_requirements
from utils.logger import get_logger

log = get_logger("sbc")

SBC_LINK_RE = re.compile(r"/sbc/(?:[a-z-]+/)?(\d+)-([a-z0-9-]+)/?", re.I)


def list_sbcs(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        m = SBC_LINK_RE.search(a["href"])
        if m and m.group(1) not in out:
            out[m.group(1)] = {"sbc_id": m.group(1), "name": a.get_text(" ", strip=True) or m.group(2).replace("-", " ").title(),
                               "url": urljoin(base, a["href"])}
    return list(out.values())


def scrape_new_sbcs(fetcher: Fetcher | None = None) -> list[dict]:
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    new = []
    try:
        res = fetcher.get(config.FUTGG_SBC_URL)
        known = {e["payload"].get("sbc_id") for e in db.get_events("sbc")}
        for sbc in list_sbcs(res.text, config.FUTGG_BASE):
            if sbc["sbc_id"] in known:
                continue
            try:
                detail = fetcher.get(sbc["url"])
                sbc["requirements"] = parse_sbc_requirements(page_text(detail.text))
            except FetchError as e:
                log.warning("SBC %s KO : %s", sbc["name"], e)
                sbc["requirements"] = parse_sbc_requirements(sbc["name"])
            db.add_event("sbc", title=sbc["name"], payload=sbc)
            new.append(sbc)
    except FetchError as e:
        log.error("Page SBC KO : %s", e)
    finally:
        if own:
            fetcher.close()
    return new
