"""Evolutions actives (FUT.GG /evolutions/) : prérequis d'entrée + boost final."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from database import db
from scrapers.base import FetchError, Fetcher
from scrapers.parsing import page_text
from scrapers.requirements_parser import parse_evo_requirements, parse_evo_upgrades
from utils.logger import get_logger

log = get_logger("evos")

EVO_LINK_RE = re.compile(r"/evolutions/(\d+)-([a-z0-9-]+)/?", re.I)


def list_evolutions(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        m = EVO_LINK_RE.search(a["href"])
        if m and m.group(1) not in out:
            out[m.group(1)] = {"evo_id": m.group(1), "name": a.get_text(" ", strip=True) or m.group(2).replace("-", " ").title(),
                               "url": urljoin(base, a["href"])}
    return list(out.values())


def parse_evo_page(html: str) -> dict:
    text = page_text(html)
    # Sépare grossièrement "Requirements" / "Upgrades" si les titres existent
    req_txt, up_txt = text, text
    m_req = re.search(r"Requirements?(.*?)(Upgrades?|Levels?|Rewards?)", text, re.S | re.I)
    m_up = re.search(r"(Upgrades?|Levels?)(.*)", text, re.S | re.I)
    if m_req:
        req_txt = m_req.group(1)
    if m_up:
        up_txt = m_up.group(2)
    return {"requirements": parse_evo_requirements(req_txt), "upgrades": parse_evo_upgrades(up_txt)}


def scrape_evolutions(fetcher: Fetcher | None = None) -> list[dict]:
    """Renvoie les NOUVELLES evos (jamais vues) avec prérequis et boosts."""
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    new = []
    try:
        res = fetcher.get(config.FUTGG_EVOS_URL)
        for evo in list_evolutions(res.text, config.FUTGG_BASE):
            try:
                detail = fetcher.get(evo["url"])
            except FetchError as e:
                log.warning("Evo %s KO : %s", evo["name"], e)
                continue
            evo.update(parse_evo_page(detail.text))
            if db.save_evolution(evo):
                db.add_event("evo", title=evo["name"], payload=evo)
                new.append(evo)
        log.info("Evos : %d nouvelles", len(new))
    except FetchError as e:
        log.error("Page Evolutions KO : %s", e)
    finally:
        if own:
            fetcher.close()
    return new
