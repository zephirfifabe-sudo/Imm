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
        f.ignore_backoff = True
        pages = {
            "accueil": config.FUTGG_BASE + "/",
            "watchlist": config.FUTGG_POPULAR_URL,
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


def _price_paths(o, p=""):
    """Chemins JSON dont le nom évoque un prix (price, bin, auction...)."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _price_paths(v, f"{p}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o[:2]):
            yield from _price_paths(v, f"{p}[{i}]")
    elif re.search(r"price|bin|auction|sale", p, re.I):
        yield p, o


def _short(d: dict) -> dict:
    return {k: (str(v)[:15] if not isinstance(v, (dict, list)) else type(v).__name__) for k, v in d.items()}


def run_inspect(player_url: str = "https://www.fut.gg/players/1397-zinedine-zidane/27-1397/") -> None:
    """Montre les champs d'un joueur dans la liste FUT.GG + les champs de prix d'une page joueur."""
    from scrapers.parsing import looks_like_player, walk_dicts

    page = config.DATA_DIR / "debug" / "joueurs.html"
    if page.exists():
        for blob in iter_json_blobs(page.read_text(encoding="utf-8")):
            x = next((x for x in walk_dicts(blob) if looks_like_player(x)), None)
            if x:
                print("LISTE:", _short(x))
                break
    else:
        print("joueurs.html absent : lance d'abord `python main.py diagnose`")
    with Fetcher(min_delay=1.0) as f:
        f.max_host_failures = 99
        f.ignore_backoff = True
        try:
            r = f.get(player_url, retries=1)
        except Exception as e:  # noqa: BLE001
            print(f"\nFICHE ❌ {str(e)[:200]}")
            return
        (config.DATA_DIR / "debug" / "fiche.html").write_text(r.text, encoding="utf-8")
        print(f"\nFICHE via={r.via} http={r.status} {len(r.text) // 1024}Ko titre={_title(r.text)}")
        n = 0
        for blob in iter_json_blobs(r.text):
            for path, val in _price_paths(blob):
                print(f"  {path[-60:]} = {str(val)[:20]}")
                n += 1
                if n >= 30:
                    return
        if not n:
            txt = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
            hits = re.findall(r".{0,30}\d[\d,.]*\s?[KkMm]\b.{0,20}", txt)[:6]
            print("  aucun prix dans le JSON ; extraits de texte :", hits)


def run_price_test(player_url: str = "https://www.fut.gg/players/1397-zinedine-zidane/27-1397/") -> None:
    """Teste les façons de lire le prix d'une carte depuis le serveur."""
    from scrapers.futgg import FutGGScraper, price_from_rendered_html

    if not config.FLARESOLVERR_URL:
        print("❌ FLARESOLVERR_URL absent du .env")
        return
    out_dir = config.DATA_DIR / "debug"
    out_dir.mkdir(parents=True, exist_ok=True)
    with Fetcher(min_delay=1.0) as f:
        f.max_host_failures = 99
        f.ignore_backoff = True
        print("[RENDU FLARESOLVERR] page Zidane + 8 s d'attente")
        try:
            res = f.flaresolverr_render(player_url, wait_s=8)
            html = res.text
            (out_dir / "fiche_rendu.html").write_text(html, encoding="utf-8")
            print(f"  http={res.status} taille={len(html) // 1024}Ko titre={_title(html)}")
            soup = BeautifulSoup(html, "html.parser")
            els = soup.select("[class*='price' i], [data-testid*='price' i]")
            print(f"  éléments 'price' : {len(els)}")
            for el in els[:6]:
                cls = " ".join(el.get("class", []))[:30]
                print(f"   · [{cls}] {el.get_text(' ', strip=True)[:40]}")
            txt = soup.get_text(" ", strip=True)
            nums = re.findall(r"\b\d{1,3}(?:[,.\s]\d{3})+\b|\b\d+(?:[.,]\d)?\s?[KkMm]\b", txt)
            print(f"  nombres type prix dans le texte : {nums[:10]}")
            print(f"  -> prix détecté : {price_from_rendered_html(html)}")
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {str(e)[:200]}")

        print("\n[TRANCHES] 3 tranches de prix autour de 50k (méthode de secours)")
        from scrapers.price_buckets import bucket_bounds, range_url

        for b_lo, b_hi in [b for b in bucket_bounds(19750, 450000, 1.06) if 45000 <= b[0] <= 60000][:3]:
            try:
                players = FutGGScraper(f).list_players(range_url(config.FUTGG_POPULAR_URL, b_lo, b_hi))
                names = ", ".join(f"{p['name'][:14]} {p.get('rating')}" for p in players[:3])
                print(f"  ✅ {b_lo}-{b_hi} : {len(players)} joueurs ({names})")
            except Exception as e:  # noqa: BLE001
                print(f"  ❌ {b_lo}-{b_hi} : {str(e)[:120]}")

        print("\n[PRIX ANALYSÉ] (méthode utilisée par le bot)")
        res = FutGGScraper(f).prices_via_browser(player_url)
        if res:
            print(f"  ✅ prix={res['price']} source={res['source']} historique={len(res['history'])} points")
        else:
            print("  ❌ aucun prix lisible")


def run_latest_test() -> None:
    """Cherche une page FUT.GG qui liste les NOUVELLES cartes (pour la surveillance de 19h) + teste les SBC."""
    from scrapers.parsing import walk_dicts
    from scrapers.sbc import list_sbcs

    base = config.FUTGG_BASE
    candidates = [
        ("nouveautes", config.FUTGG_LATEST_URL),
        ("tri -created_at", f"{base}/players/?sorts=-created_at"),
        ("tri -release_date", f"{base}/players/?sorts=-release_date"),
        ("tri -date_added", f"{base}/players/?sorts=-date_added"),
        ("tri -id", f"{base}/players/?sorts=-id"),
        ("in-packs", f"{base}/players/in-packs/"),
        ("history", f"{base}/players/history/"),
    ]
    with Fetcher(min_delay=1.0) as f:
        f.max_host_failures = 99
        f.ignore_backoff = True
        for name, url in candidates:
            try:
                res = f.get(url, retries=0)
                players = extract_players(res.text, base)
                top = ", ".join(f"{p['name'][:12]} {p.get('rating')} {p.get('card_type') or ''}".strip()
                                for p in players[:4])
                print(f"[{name}] {res.via} {len(players)} joueurs : {top}")
                if not players:
                    # structure du JSON pour adapter la lecture
                    for blob in iter_json_blobs(res.text):
                        x = next((x for x in walk_dicts(blob) if "eaId" in x and len(x) > 4), None)
                        if x:
                            print(f"   json: {_short(x)}"[:300])
                            break
            except Exception as e:  # noqa: BLE001
                print(f"[{name}] ❌ {str(e)[:110]}")
        try:
            res = f.get(config.FUTGG_SBC_URL, retries=0)
            sbcs = list_sbcs(res.text, base)
            print(f"\n[SBC] {res.via} {len(sbcs)} SBC : {', '.join(s['name'][:20] for s in sbcs[:5])}")
            if not sbcs:
                hrefs = sorted({a['href'] for a in BeautifulSoup(res.text, 'html.parser').find_all('a', href=True)
                                if 'sbc' in a['href'].lower()})
                print("   liens sbc :", hrefs[:6])
        except Exception as e:  # noqa: BLE001
            print(f"\n[SBC] ❌ {str(e)[:120]}")


def run_futmind_test() -> None:
    """Inspecte futmind.com (non protégé par Cloudflare) : structure des joueurs, des prix et des API."""
    from scrapers.parsing import walk_dicts

    out_dir = config.DATA_DIR / "debug"
    out_dir.mkdir(parents=True, exist_ok=True)
    with Fetcher(min_delay=2.0) as f:
        f.max_host_failures = 99
        f.ignore_backoff = True
        for name, url in (("liste", "https://futmind.com/fr/players"),):
            try:
                r = f.get(url, retries=0)
            except Exception as e:  # noqa: BLE001
                print(f"[{name}] ❌ {str(e)[:200]}")
                continue
            html = r.text
            (out_dir / f"futmind_{name}.html").write_text(html, encoding="utf-8")
            print(f"[{name}] via={r.via} http={r.status} {len(html) // 1024}Ko titre={_title(html)}")
            players = extract_players(html, "https://futmind.com")
            print(f"  joueurs reconnus : {len(players)}")
            for p in players[:4]:
                print(f"   -> {p['name'][:18]} {p.get('rating')} {p.get('position')} prix={p.get('price')}")
            blobs = list(iter_json_blobs(html))
            print(f"  blocs JSON : {len(blobs)}")
            for blob in blobs:
                x = next((d for d in walk_dicts(blob)
                          if len(d) > 4 and any(k in d for k in ("rating", "overall", "ovr", "price", "name"))), None)
                if x:
                    print(f"   json: {_short(x)}"[:350])
                    break
            soup = BeautifulSoup(html, "html.parser")
            hrefs = sorted({a["href"] for a in soup.find_all("a", href=True) if "player" in a["href"].lower()})
            print(f"  liens 'player' ({len(hrefs)}) : {hrefs[:5]}")
            apis = sorted(set(re.findall(r"https?://[^\s\"'<>]*api[^\s\"'<>]*|[\"'](/api/[^\"'\s]+)", html)))
            print(f"  API vues : {[a if isinstance(a, str) else a for a in apis][:6]}")
            text = soup.get_text(" ", strip=True)
            for m in list(re.finditer(r"(?i)prix|price|coins?", text))[:5]:
                print(f"   « …{text[max(0, m.start() - 35):m.end() + 35]}… »")
            cls = sorted({c for el in soup.select("[class*='price' i]") for c in el.get("class", [])})[:8]
            print(f"  classes 'price' : {cls}")
