"""Diagnostic des sources : que renvoie vraiment FUT.GG / FUTBIN au serveur ?

`python main.py diagnose` -> résumé court (lisible sur une capture de téléphone)
+ pages brutes sauvegardées dans data/debug/ pour analyse.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

import config
from scrapers.base import Fetcher, looks_blocked
from scrapers.parsing import FUTGG_LINK_RE, extract_players, iter_json_blobs


def _title(html: str) -> str:
    t = BeautifulSoup(html, "html.parser").title
    return (t.get_text(strip=True) if t else "")[:40]


def _check_page(f: Fetcher, name: str, url: str, out_dir) -> str | None:
    print(f"\n[{name}] {url.replace('https://', '')[:60]}")
    try:
        res = f.get(url, retries=1)
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ {str(e)[:160]}")
        return None
    html = res.text
    (out_dir / f"{name}.html").write_text(html, encoding="utf-8")
    links = sorted({m.group(0) for m in FUTGG_LINK_RE.finditer(html)})
    blobs = list(iter_json_blobs(html))
    players = extract_players(html, config.FUTGG_BASE)
    print(f"  via={res.via} http={res.status} taille={len(html) // 1024}Ko")
    print(f"  titre: {_title(html)}")
    print(f"  cloudflare={'OUI' if looks_blocked(res.status, html) else 'non'} "
          f"liens_joueurs={len(links)} json={len(blobs)} joueurs_extraits={len(players)}")
    for href in links[:3]:
        print(f"  ex: {href[:55]}")
    for p in players[:3]:
        print(f"  -> {p['name'][:18]} {p.get('rating')} {p.get('position')} prix={p.get('price')} rareté={p.get('card_type')}")
    if not links:
        # indices pour trouver les bonnes URLs si le site a changé
        hrefs = sorted({a["href"] for a in BeautifulSoup(html, "html.parser").find_all("a", href=True)
                        if "player" in a["href"].lower()})
        for h in hrefs[:5]:
            print(f"  lien?: {h[:55]}")
    return html


def run_diagnose() -> None:
    out_dir = config.DATA_DIR / "debug"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== DIAGNOSTIC (année {config.GAME_YEAR}, mode {config.FETCH_MODE}) ===")
    with Fetcher(min_delay=1.0) as f:
        f.max_host_failures = 99  # le diagnostic doit tester toutes les pages
        pages = {
            "accueil": config.FUTGG_BASE + "/",
            "populaires": config.FUTGG_POPULAR_URL,
            "nouveautes": config.FUTGG_LATEST_URL,
            "joueurs": config.FUTGG_BASE + "/players/",
            "evos": config.FUTGG_EVOS_URL,
        }
        found_id = None
        for name, url in pages.items():
            html = _check_page(f, name, url, out_dir)
            if html and not found_id:
                m = FUTGG_LINK_RE.search(html)
                if m:
                    found_id = m.group(4) or m.group(1)

        # API prix sur un vrai joueur trouvé
        if found_id:
            for kind in ("player-prices", "player-item-definitions"):
                url = f"{config.FUTGG_BASE}/api/fut/{kind}/{config.GAME_YEAR}/{found_id}/"
                print(f"\n[api {kind}] id={found_id}")
                try:
                    data = f.get_json(url, retries=1)
                    d = data.get("data", data) if isinstance(data, dict) else data
                    keys = list(d)[:10] if isinstance(d, dict) else type(d).__name__
                    print(f"  ✅ clés: {keys}")
                    (out_dir / f"api_{kind}.json").write_text(json.dumps(data, indent=1)[:200000], encoding="utf-8")
                except Exception as e:  # noqa: BLE001
                    print(f"  ❌ {str(e)[:160]}")
        else:
            print("\n[api] aucun ID joueur trouvé -> API non testée")

        _check_page(f, "futbin", config.FUTBIN_BASE + "/players", out_dir)

    years = sorted(set(re.findall(r"/players/\d+-[a-z0-9-]+/(\d{2})-", " ".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in out_dir.glob("*.html")))))
    if years:
        print(f"\nAnnées vues dans les liens : {years} (config GAME_YEAR={config.GAME_YEAR})")
    print(f"\nPages sauvegardées dans {out_dir}")
