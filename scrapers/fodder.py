"""TRACKER DE FODDERS : la carte la moins chère pour chaque note (85 à 91 par défaut), chaque heure.

Source : listes futgenie filtrées par note et triées par prix croissant. Le format exact du filtre n'est pas
documenté : au premier passage, `discover()` essaie quelques formats plausibles, garde celui qui renvoie bien
des cartes d'une seule note triées par prix, et le mémorise dans data/fodder_filter.json (1 requête par essai,
une seule fois). Accès normal uniquement, avec le même délai que le reste du bot.

Avec les SBC « Streamlined » de FC 27, chaque carte rapporte des points (Item Score) : le meilleur fodder est
la note dont le prix par point est le plus bas (KB-K-001 / KB-K-002).
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime, timedelta

import config
from database import db
from scrapers.base import FetchError, Fetcher
from scrapers.futgenie import filter_url, parse_cards
from utils.helpers import iso, utcnow
from utils.logger import get_logger

log = get_logger("fodder")

# formats de filtre essayés (clé note min, clé note max) x tri par prix croissant
RATING_KEYS = [("minRating", "maxRating"), ("minOvr", "maxOvr"), ("minOverall", "maxOverall"),
               ("ratingMin", "ratingMax"), ("minRat", "maxRat")]
SORTS = ["price-asc", "price_asc", "priceAsc", "price"]


def spec_path():
    return config.DATA_DIR / "fodder_filter.json"


def load_spec() -> dict | None:
    try:
        return json.loads(spec_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rating_url(spec: dict, rating: int, page: int = 1) -> str:
    return filter_url({"sort": spec["sort"], spec["min"]: rating, spec["max"]: rating}, page)


def _dominant_points(cards: list[dict]) -> tuple[int | None, float]:
    pts = [c["sbc_points"] for c in cards if c.get("sbc_points")]
    if not pts:
        return None, 0.0
    value, n = Counter(pts).most_common(1)[0]
    return value, n / len(cards)


def looks_filtered(cards: list[dict]) -> bool:
    """Cartes d'UNE note (mêmes points SBC pour la plupart) triées par prix croissant."""
    head = cards[:10]
    if len(head) < 4:
        return False
    prices = [c["price"] for c in head]
    ascending = sum(a <= b for a, b in zip(prices, prices[1:])) >= 0.8 * (len(prices) - 1)
    _, share = _dominant_points(head)
    return ascending and share >= 0.6


def discover(fetcher: Fetcher) -> dict | None:
    """Trouve le format de filtre qui marche (note 85 puis 88 : points différents) et le mémorise."""
    for kmin, kmax in RATING_KEYS:
        for sort in SORTS:
            spec = {"min": kmin, "max": kmax, "sort": sort}
            try:
                a = parse_cards(fetcher.get(rating_url(spec, 85), retries=0).text)
                if not looks_filtered(a):
                    continue
                b = parse_cards(fetcher.get(rating_url(spec, 88), retries=0).text)
            except FetchError as e:
                log.warning("Découverte du filtre fodder interrompue : %s", e)
                return None
            if looks_filtered(b) and _dominant_points(a)[0] != _dominant_points(b)[0]:
                spec["found_at"] = iso(utcnow())
                config.ensure_dirs()
                spec_path().write_text(json.dumps(spec), encoding="utf-8")
                log.info("Filtre fodder trouvé : %s", spec)
                return spec
    log.warning("Aucun format de filtre par note ne fonctionne sur futgenie (tracker de fodders inactif)")
    db.set_status("fodder_discovery_failed", {"at": iso(utcnow())})
    return None


def snapshot_fodder(fetcher: Fetcher | None = None, now: datetime | None = None) -> dict:
    """Relève la carte la moins chère de chaque note et l'enregistre (1 requête par note)."""
    own = fetcher is None
    fetcher = fetcher or Fetcher(mode="httpx", min_delay=4.0)
    ts = (now or utcnow()).replace(minute=0, second=0, microsecond=0)
    done = {}
    try:
        spec = load_spec()
        if spec is None:
            failed = (db.get_status().get("fodder_discovery_failed") or {}).get("value") or {}
            if failed.get("at") and utcnow() - datetime.fromisoformat(failed["at"]) < timedelta(hours=24):
                return {}  # échec récent : on ne réessaie qu'une fois par jour
            spec = discover(fetcher)
            if spec is None:
                return {}
        for r in config.FODDER_RATINGS:
            try:
                cards = parse_cards(fetcher.get(rating_url(spec, r), retries=1).text)
            except FetchError as e:
                log.warning("Fodder %d KO : %s", r, e)
                break
            # la moins chère de la note, QUELLE QUE SOIT sa version : en 90-91 les fodders bon marché sont des cartes
            # spéciales (points SBC différents des cartes or, qui sont des stars hors de prix)
            cards = sorted((c for c in cards if c.get("price")), key=lambda c: c["price"])
            if not cards:
                continue
            points = cards[0].get("sbc_points")
            row = {"min_price": cards[0]["price"], "avg5": round(statistics.mean(c["price"] for c in cards[:5])),
                   "sbc_points": points, "n": len(cards)}
            with db.get_conn() as c:
                c.execute("INSERT OR REPLACE INTO fodder_snapshots VALUES (?,?,?,?,?,?)",
                          (iso(ts), r, row["min_price"], row["avg5"], points, row["n"]))
            done[r] = row
    finally:
        if own:
            fetcher.close()
    log.info("Fodders : %s", {r: v["min_price"] for r, v in done.items()})
    return done


# --------------------------------------------------------------------------- analyse
def _series(rating: int, since: datetime, until: datetime) -> list[tuple[datetime, int, int | None]]:
    with db.get_conn() as c:
        rows = c.execute("SELECT timestamp, min_price, sbc_points FROM fodder_snapshots WHERE rating=? AND timestamp "
                         "BETWEEN ? AND ? ORDER BY timestamp", (rating, iso(since), iso(until))).fetchall()
    return [(datetime.fromisoformat(t), p, s) for t, p, s in rows]


def _at(series, ts: datetime, tol_h: float = 1.5):
    near = [x for x in series if abs((x[0] - ts).total_seconds()) <= tol_h * 3600]
    return min(near, key=lambda x: abs((x[0] - ts).total_seconds()))[1] if near else None


def fodder_status(now: datetime | None = None) -> list[dict]:
    """Une ligne par note : prix actuel, variations 6 h / 24 h, médiane / min / max 7 j, prix par 1 000 points."""
    now = now or utcnow()
    out = []
    for r in config.FODDER_RATINGS:
        s = _series(r, now - timedelta(days=7), now)
        if not s:
            out.append({"rating": r, "price": None})
            continue
        last_ts, price, points = s[-1]
        prices = [p for _, p, _ in s]
        p6, p24 = _at(s, last_ts - timedelta(hours=6)), _at(s, last_ts - timedelta(hours=24))
        out.append({
            "rating": r, "price": price, "observed_at": iso(last_ts), "sbc_points": points,
            "per_1k_points": round(price / points * 1000) if points else None,
            "change_6h": price / p6 - 1 if p6 else None, "change_24h": price / p24 - 1 if p24 else None,
            "median_7d": round(statistics.median(prices)), "min_7d": min(prices), "max_7d": max(prices), "n": len(s),
            "spark": [[iso(t), p] for t, p, _ in s[::3]] + ([[iso(last_ts), price]] if (len(s) - 1) % 3 else []),
        })
    valued = [x for x in out if x.get("per_1k_points")]
    if valued:
        min(valued, key=lambda x: x["per_1k_points"])["best_value"] = True
    return out


def rising_alerts(status: list[dict], now: datetime | None = None) -> list[dict]:
    """Notes qui grimpent d'un coup (signal précoce d'un SBC) : hausse vs médiane 7 j ET hausse récente."""
    now = now or utcnow()
    st = db.get_status()
    out = []
    for x in status:
        if not x.get("price") or x.get("n", 0) < 24 or x.get("change_6h") is None:
            continue
        rise = x["price"] / x["median_7d"] - 1
        if rise < config.FODDER_ALERT_RISE or x["change_6h"] < config.FODDER_ALERT_RISE_6H:
            continue
        key = f"fodder_alert:{x['rating']}"
        last = (st.get(key) or {}).get("updated_at")
        if last and now - datetime.fromisoformat(last) < timedelta(hours=config.FODDER_ALERT_COOLDOWN_H):
            continue
        db.set_status(key, {"price": x["price"], "rise": round(rise, 3)})
        out.append({**x, "rise_7d": rise})
    return out


def format_report(status: list[dict]) -> str:
    """Tableau des fodders pour Discord : le prix le moins cher par note (prix observés)."""
    from utils.helpers import fmt_coins

    rows = [x for x in status if x.get("price")]
    if not rows:
        return "🧱 Fodders : aucun relevé pour l'instant."
    lines = ["🧱 **FODDERS — moins cher par note** (prix observés sur futgenie)"]
    for x in rows:
        ch = f" ({x['change_24h'] * 100:+.0f} % / 24 h)" if x.get("change_24h") is not None else ""
        lines.append(f"• **{x['rating']}** : {fmt_coins(x['price'])}{ch}")
    return "\n".join(lines)


def format_rising(alerts: list[dict]) -> str:
    from utils.helpers import fmt_coins

    lines = ["📈 **FODDERS EN HAUSSE** (signal précoce possible d'un SBC — hypothèse, KB-K-001)"]
    for a in alerts:
        lines.append(f"• **{a['rating']}** : {fmt_coins(a['price'])} ({a['rise_7d'] * 100:+.0f} % vs médiane 7 j, "
                     f"{a['change_6h'] * 100:+.0f} % en 6 h)")
    lines.append("Prix observés sur futgenie, pas des ventes garanties. Taxe EA de 5 % à la revente.")
    return "\n".join(lines)
