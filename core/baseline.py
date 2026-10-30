"""ÉTAPE 0 : photographie de référence des données et du cerveau, en LECTURE SEULE.

`python main.py baseline` : profondeur de l'historique, trous, doublons, fraîcheur, répartition des
signaux actuels et des alertes envoyées. Ne modifie rien (ni base, ni règles, ni alertes).
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

import config
from database import db
from utils.helpers import iso, utcnow


def data_report() -> dict:
    now = utcnow()
    with db.get_conn() as c:
        first, last, n, players = c.execute(
            "SELECT MIN(timestamp), MAX(timestamp), COUNT(*), COUNT(DISTINCT player_id) FROM price_snapshots").fetchone()
        by_source = dict(c.execute("SELECT source, COUNT(*) FROM price_snapshots GROUP BY source").fetchall())
        dupes = c.execute("SELECT COUNT(*), COALESCE(SUM(k - 1), 0) FROM (SELECT COUNT(*) k FROM price_snapshots "
                          "GROUP BY player_id, timestamp HAVING k > 1)").fetchone()
        last_by_player = c.execute("SELECT player_id, MAX(timestamp) FROM price_snapshots GROUP BY player_id").fetchall()
        rows = c.execute("SELECT player_id, timestamp FROM price_snapshots WHERE source != 'demo' "
                         "ORDER BY player_id, timestamp").fetchall()
        alerts = c.execute("SELECT action, COUNT(*) FROM alerts WHERE timestamp >= ? GROUP BY action",
                           (iso(now - timedelta(days=7)),)).fetchall()
    from datetime import datetime

    def age_h(ts: str) -> float:
        return (now - datetime.fromisoformat(ts)).total_seconds() / 3600

    stale = Counter("< 2 h" if age_h(t) < 2 else "2-24 h" if age_h(t) < 24 else "> 24 h" for _, t in last_by_player)
    gaps, prev = Counter(), None
    for pid, ts in rows:  # trous de plus de 2 h entre deux relevés d'un même joueur
        if prev and prev[0] == pid:
            g = (datetime.fromisoformat(ts) - datetime.fromisoformat(prev[1])).total_seconds() / 3600
            if g > 2:
                gaps["2-30 h (interpolés)" if g <= 30 else "> 30 h"] += 1
        prev = (pid, ts)
    days = round((datetime.fromisoformat(last) - datetime.fromisoformat(first)).total_seconds() / 86400, 1) if first else 0
    return {"db": str(config.DB_PATH), "first": first, "last": last, "days": days, "snapshots": n,
            "players": players, "by_source": by_source, "duplicate_keys": dupes[0], "duplicate_rows": dupes[1],
            "freshness": dict(stale), "gaps": dict(gaps), "alerts_7d": dict(alerts)}


def brain_report() -> dict:
    from core.analyzer import MarketAnalyzer
    from core.learner import load_rules, rule_for
    from scrapers.watchlist import load_watchlist

    wl = load_watchlist()
    rules = load_rules()
    g = rules.get("GLOBAL", {})
    sigs = MarketAnalyzer(wl, version="v1").full_scan() if wl else []
    sigs2 = MarketAnalyzer(wl, version="v2").full_scan() if wl else []
    habit_conf = Counter(round(rule_for(rules, p).get("confidence", 0), 1) for p in wl)
    return {"watchlist": len(wl), "rules_generated_at": rules.get("_meta", {}).get("generated_at"),
            "global_profile": bool(g.get("profile")), "global_confidence": g.get("confidence"),
            "weeks_observed": g.get("weeks_observed"), "habit_confidence_by_player": dict(habit_conf),
            "signals": dict(Counter(f"{s.rule} {s.action}" for s in sigs)),
            "signals_conf_ge_7": sum(s.confidence >= 7 and s.action != "HOLD" for s in sigs),
            "habit_only_trades": sum(s.rule == "HABITUDE" and s.action != "HOLD" for s in sigs),
            "signals_v2": dict(Counter(s.action for s in sigs2)),
            "reasons_v2": dict(Counter((s.extra.get("reason") or "-").split(" (")[0].split(" :")[0] for s in sigs2))}


def print_baseline() -> None:
    d, b = data_report(), brain_report()
    print("=== DONNÉES ===")
    print(f"Base : {d['db']}")
    print(f"Historique : {d['first']} -> {d['last']} ({d['days']} jours), {d['snapshots']} relevés, {d['players']} joueurs")
    print(f"Par source : {d['by_source']}")
    print(f"Doublons (joueur, heure) : {d['duplicate_keys']} clés, {d['duplicate_rows']} lignes en trop")
    print(f"Fraîcheur du dernier prix par joueur : {d['freshness']}")
    print(f"Trous entre relevés : {d['gaps']}")
    print(f"Alertes 7 j : {d['alerts_7d']}")
    print("\n=== CERVEAU (rien n'est modifié) ===")
    print(f"Watchlist : {b['watchlist']} joueurs · règles apprises le {b['rules_generated_at']}")
    print(f"Profil GLOBAL : {b['global_profile']} · confiance {b['global_confidence']} · semaines {b['weeks_observed']}")
    print(f"Confiance de l'habitude par joueur : {b['habit_confidence_by_player']}")
    print(f"Signaux actuels : {b['signals']}")
    print(f"  dont envoyables (>= 7/10, hors HOLD) : {b['signals_conf_ge_7']}")
    print(f"  dont ACHAT/VENTE dus à l'habitude seule : {b['habit_only_trades']}")
    print(f"Moteur v2 (même instant) : {b['signals_v2']}")
    print(f"  raisons : {b['reasons_v2']}")
