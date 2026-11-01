"""Données du bot mises en forme pour l'assistant : fiches joueurs, top des signaux, contexte pour l'IA.

Tout est calculé avec le moteur actif (config.BRAIN_VERSION) et mis en cache quelques minutes : une question
ne relance pas une analyse complète à chaque fois.
"""
from __future__ import annotations

import statistics
import time
import unicodedata

import config
from core.analyzer import MarketAnalyzer
from database import db
from scrapers.watchlist import load_watchlist
from utils.helpers import fmt_coins, fmt_price, to_local, utcnow

_CACHE: dict = {}
CACHE_S = 300


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def scan() -> tuple[MarketAnalyzer, list, dict]:
    """(analyseur, signaux, {player_id: signal}) du moteur actif, en cache 5 min."""
    hit = _CACHE.get("scan")
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    wl = load_watchlist()
    an = MarketAnalyzer(wl)
    sigs = an.full_scan()
    out = (an, sigs, {s.player_id: s for s in sigs})
    _CACHE["scan"] = (time.time(), out)
    return out


def find_players(query: str, limit: int = 5) -> list[dict]:
    """Joueurs suivis dont le nom contient la recherche (sans accents ni majuscules), les plus proches d'abord."""
    q = _norm(query)
    if not q:
        return []
    wl = load_watchlist()
    hits = [p for p in wl if q in _norm(p.get("name", ""))]
    hits.sort(key=lambda p: (not _norm(p.get("name", "")).startswith(q), len(p.get("name", ""))))
    return hits[:limit]


def player_card(player: dict) -> dict:
    """Fiche d'un joueur : prix, variations, moyenne 7 j, décision du bot et raison."""
    an, _, by_id = scan()
    s = by_id.get(str(player["player_id"]))
    x = (s.extra if s else {}) or {}
    return {
        "name": player.get("name"), "rating": player.get("rating"), "position": player.get("position"),
        "card_type": player.get("card_type"), "price": s.price if s else player.get("price"),
        "change_24h": s.change_24h if s else None, "trend_7d": x.get("trend_7d"), "avg_7d": x.get("avg_7d"),
        "min_7d": x.get("min_7d"), "max_7d": x.get("max_7d"), "action": s.action if s else "?",
        "reason": x.get("reason") or (s.instant if s else ""), "action_text": s.action_text if s else "",
        "explain": x.get("explain"), "observed_at": x.get("observed_at"), "card_age": x.get("card_age"),
        "player_id": str(player["player_id"]),
    }


def pct(v) -> str:
    return "–" if v is None else f"{v * 100:+.1f} %"


def player_text(c: dict) -> str:
    lines = [f"**{c['name']} {c.get('rating') or ''}** · {c.get('card_type') or '?'} · {c.get('position') or '?'}",
             f"Prix : **{fmt_coins(c['price'])}** · 24 h {pct(c['change_24h'])} · 7 j {pct(c['trend_7d'])}"]
    if c.get("avg_7d"):
        lines.append(f"Moyenne 7 j : {fmt_price(c['avg_7d'])} (min {fmt_price(c['min_7d'])} – max {fmt_price(c['max_7d'])})")
    if c.get("card_age") and c["card_age"].get("discovery"):
        lines.append(f"🆕 Carte sortie il y a {c['card_age']['days']} j : prix encore en découverte")
    lines.append(f"Décision du bot : **{c['action']}**" + (f" — {c['reason']}" if c.get("reason") else ""))
    if c.get("explain"):
        lines.append(f"Contexte : {c['explain'].replace('**', '')}")
    return "\n".join(lines)


def top_text(n: int = 6) -> str:
    _, sigs, _ = scan()
    trades = sorted([s for s in sigs if s.action.startswith(("ACHAT", "VENTE"))], key=lambda s: -s.confidence)
    watch = sorted([s for s in sigs if s.action == "SURVEILLANCE"], key=lambda s: -(s.extra or {}).get("opportunity", 0))
    lines = ["🎯 **Opportunités du moment** (moteur " + config.BRAIN_VERSION + ")"]
    if trades:
        lines += [f"• {'🟢' if s.action.startswith('ACHAT') else '🔴'} **{s.player_name} {s.rating or ''}** "
                  f"{fmt_price(s.price)} — {s.action_text}" for s in trades[:n]]
    else:
        lines.append("Aucun ACHAT/VENTE validé pour l'instant (c'est voulu : rien d'assez fiable).")
    if watch:
        lines.append("\n👀 **À surveiller**")
        lines += [f"• {s.player_name} {s.rating or ''} {fmt_price(s.price)} — {(s.extra or {}).get('reason', '')}"
                  for s in watch[:n]]
    return "\n".join(lines)


def calendar_text(days: int = 30) -> str:
    from knowledge.service import get_service

    ups = get_service().upcoming_text(days=days)
    return "📅 **À venir**\n" + ("\n".join(f"• {u}" for u in ups) if ups else "Rien de daté dans les 30 jours.")


def summary_text() -> str:
    ev = db.get_events("summary")
    return ev[-1]["payload"].get("text", "") if ev else "Pas encore de résumé (il est publié chaque soir à 23h)."


def fodder_text() -> str:
    from scrapers.fodder import fodder_status, format_report

    return format_report(fodder_status())


# --------------------------------------------------------------------------- contexte pour l'IA
def llm_context(question: str) -> str:
    """Faits fournis à l'IA : elle ne doit répondre qu'à partir de ça (et le dire quand ça ne suffit pas)."""
    from knowledge.service import get_service
    from scrapers.fodder import fodder_status

    an, sigs, _ = scan()
    ks = get_service()
    now = to_local(utcnow())
    parts = [f"Date et heure (Paris) : {now:%A %d/%m/%Y %H:%M}. Joueurs suivis : {len(sigs)}. Moteur : {an.version}."]
    m24, m48 = an.market_change(24), an.market_change(48)
    ch7 = [s.extra.get("trend_7d") for s in sigs if (s.extra or {}).get("trend_7d") is not None]
    parts.append(f"Marché suivi (médiane) : {pct(m24)} sur 24 h, {pct(m48)} sur 48 h, "
                 f"{pct(statistics.median(ch7)) if ch7 else '–'} sur 7 j.")
    ups = ks.upcoming_text(days=21)
    if ups:
        parts.append("Calendrier (statuts : confirmé / probable / à vérifier) : " + " ; ".join(ups))
    obs = ks.observed().get("hypotheses", {})
    kb = []
    for e in ks.active():
        if e["categorie"] in ("strategies", "calendrier", "marche"):
            v = obs.get(e["cle"], {}).get("verdict")
            kb.append(f"- [{e['id']} · {e['statut']}{' · vérif. données : ' + v if v else ''}] {e['titre']} : "
                      f"{' '.join(e['contenu'].split())[:260]}")
    parts.append("Base de connaissances (théorie sourcée) :\n" + "\n".join(kb))
    fod = [f"{x['rating']}: {fmt_coins(x['price'])} ({pct(x.get('change_24h'))} 24 h)" for x in fodder_status() if x.get("price")]
    if fod:
        parts.append("Fodders (moins cher par note) : " + " · ".join(fod))
    trades = [s for s in sigs if s.action.startswith(("ACHAT", "VENTE"))][:8]
    watch = sorted([s for s in sigs if s.action == "SURVEILLANCE"],
                   key=lambda s: -(s.extra or {}).get("opportunity", 0))[:8]
    for title, lst in (("Décisions ACHAT/VENTE actuelles", trades), ("Cartes en surveillance", watch)):
        if lst:
            parts.append(title + " :\n" + "\n".join(
                f"- {s.player_name} {s.rating or ''} ({s.card_type or '?'}) {fmt_coins(s.price)}, 24 h {pct(s.change_24h)} : "
                f"{s.action} — {(s.extra or {}).get('reason') or s.instant}" for s in lst))
    for p in _players_in(question):
        parts.append("Fiche demandée :\n" + player_text(player_card(p)).replace("**", ""))
    return "\n\n".join(parts)


def _players_in(question: str, limit: int = 3) -> list[dict]:
    q = _norm(question)
    out = []
    for p in load_watchlist():
        last = _norm(p.get("name", "")).split()[-1:] or [""]
        if len(last[0]) >= 4 and f" {last[0]}" in f" {q}":
            out.append(p)
    return out[:limit]
