"""JOURNAL DES DÉCISIONS : chaque décision du cerveau (ACHAT, VENTE, SURVEILLANCE, AUCUNE ACTION) est
enregistrée avec les données dont il disposait, puis évaluée à 6 h / 24 h / 48 h / 7 j.

Toutes les évaluations sont THÉORIQUES : elles comparent des prix OBSERVÉS (futgenie), pas des ventes
réellement exécutées. Elles ne doivent jamais être présentées comme des gains réels.

Verdicts :
  ACHAT        favorable si (prix à l'horizon × 0,95) − prix observé > 0, sinon défavorable
  VENTE        favorable si le prix a baissé depuis (baisse évitée), sinon défavorable
  SURVEILLANCE / AUCUNE ACTION
               occasion_manquee si un achat aurait rapporté ≥ MIN_NET_MARGIN net, sinon abstention_ok
  sans_donnee  aucun relevé réel autour de l'heure visée (± tolérance) après 24 h d'attente
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta

import config
from database import db
from utils.helpers import iso, utcnow
from utils.logger import get_logger

log = get_logger("journal")
ACTIONS = ("ACHAT", "VENTE", "SURVEILLANCE", "AUCUNE ACTION")


def family(action: str) -> str:
    """'ACHAT FORT' -> 'ACHAT', 'HOLD' -> 'AUCUNE ACTION' (v1)."""
    a = (action or "").upper()
    return "ACHAT" if a.startswith("ACHAT") else "VENTE" if a.startswith("VENTE") else \
        "SURVEILLANCE" if a == "SURVEILLANCE" else "AUCUNE ACTION"


def log_decisions(signals, engine: str, now: datetime | None = None) -> int:
    """Enregistre toutes les décisions d'un scan (y compris les abstentions)."""
    ts = iso(now or utcnow())
    rows = []
    for s in signals:
        x = s.extra or {}
        payload = {k: x.get(k) for k in ("habit_validated", "habit_score", "vs_avg", "trend_7d", "buy_max",
                                          "sell_min", "net_profit", "change_48h", "quality") if x.get(k) is not None}
        payload["change_24h"] = s.change_24h
        payload["confidence"] = s.confidence
        rows.append((ts, engine, s.player_id, s.action, s.rule, s.score, x.get("opportunity"), x.get("data_quality"),
                     x.get("observed_price", s.price), x.get("observed_at"), x.get("target_price"),
                     x.get("reason") or "", json.dumps(payload, ensure_ascii=False, default=str)))
    with db.get_conn() as c:
        c.executemany("INSERT INTO decision_log (timestamp, engine, player_id, action, rule, score, opportunity, "
                      "data_quality, observed_price, observed_at, target_price, reason, payload) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def verdict(action: str, observed: int, price_h: int) -> tuple[str, int | None]:
    f = family(action)
    buy_net = round(price_h * (1 - config.EA_TAX) - observed)
    if f == "ACHAT":
        return ("favorable" if buy_net > 0 else "defavorable"), buy_net
    if f == "VENTE":
        return ("favorable" if price_h < observed else "defavorable"), None
    missed = buy_net >= config.MIN_NET_MARGIN * observed
    return ("occasion_manquee" if missed else "abstention_ok"), buy_net


def evaluate_outcomes(now: datetime | None = None, limit: int = 20000) -> int:
    """Évalue les décisions arrivées à échéance, sur des relevés réels uniquement."""
    now = now or utcnow()
    tol = timedelta(hours=config.REAL_POINT_TOLERANCE_H)
    done = 0
    with db.get_conn() as c:
        for h in config.OUTCOME_HORIZONS:
            due = c.execute(
                "SELECT d.id, d.player_id, d.action, d.observed_price, COALESCE(d.observed_at, d.timestamp) t "
                "FROM decision_log d LEFT JOIN decision_outcomes o ON o.decision_id = d.id AND o.horizon_h = ? "
                "WHERE o.decision_id IS NULL AND d.observed_price IS NOT NULL AND d.timestamp <= ? LIMIT ?",
                (h, iso(now - timedelta(hours=h) + tol), limit)).fetchall()
            for d in due:
                target = datetime.fromisoformat(d["t"]) + timedelta(hours=h)
                if target + tol > now:
                    continue
                r = c.execute("SELECT price, timestamp FROM price_snapshots WHERE player_id=? AND timestamp BETWEEN ? AND ? "
                              "ORDER BY ABS(julianday(timestamp) - julianday(?)) LIMIT 1",
                              (d["player_id"], iso(target - tol), iso(target + tol), iso(target))).fetchone()
                if r is None:
                    if now - target < timedelta(hours=24):
                        continue  # le relevé peut encore manquer temporairement : on réessaiera
                    c.execute("INSERT INTO decision_outcomes VALUES (?,?,?,?,?,?,?,?)",
                              (d["id"], h, iso(now), None, None, None, None, "sans_donnee"))
                else:
                    v, net = verdict(d["action"], d["observed_price"], r["price"])
                    c.execute("INSERT INTO decision_outcomes VALUES (?,?,?,?,?,?,?,?)",
                              (d["id"], h, iso(now), r["price"], r["timestamp"],
                               r["price"] / d["observed_price"] - 1, net, v))
                done += 1
    if done:
        log.info("Journal : %d évaluation(s) ajoutée(s)", done)
    return done


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d, (c + m) / d


def performance(engine: str | None = None, days: int = 30, now: datetime | None = None) -> list[dict]:
    """Résultats théoriques par moteur / action / horizon (fenêtre glissante)."""
    since = iso((now or utcnow()) - timedelta(days=days))
    sql = ("SELECT d.engine, d.action, o.horizon_h, o.verdict, o.change, o.theoretical_net FROM decision_outcomes o "
           "JOIN decision_log d ON d.id = o.decision_id WHERE d.timestamp >= ?")
    args: list = [since]
    if engine:
        sql += " AND d.engine = ?"
        args.append(engine)
    agg: dict = defaultdict(lambda: {"n": 0, "no_data": 0, "verdicts": defaultdict(int), "changes": [], "nets": []})
    with db.get_conn() as c:
        for r in c.execute(sql, args):
            a = agg[(r["engine"], family(r["action"]), r["horizon_h"])]
            if r["verdict"] == "sans_donnee":
                a["no_data"] += 1
                continue
            a["n"] += 1
            a["verdicts"][r["verdict"]] += 1
            a["changes"].append(r["change"])
            if r["theoretical_net"] is not None:
                a["nets"].append(r["theoretical_net"])
    out = []
    for (eng, action, h), a in sorted(agg.items(), key=lambda kv: (kv[0][0], ACTIONS.index(kv[0][1]), kv[0][2])):
        n = a["n"]
        good = a["verdicts"].get("favorable", 0) + a["verdicts"].get("abstention_ok", 0)
        ch = sorted(a["changes"])
        out.append({"engine": eng, "action": action, "horizon_h": h, "n": n, "no_data": a["no_data"],
                    "verdicts": dict(a["verdicts"]), "favorable_rate": round(good / n, 3) if n else None,
                    "median_change": ch[len(ch) // 2] if ch else None,
                    "avg_theoretical_net": round(sum(a["nets"]) / len(a["nets"])) if a["nets"] else None,
                    "enough_data": n >= config.PROBA_MIN_SAMPLES})
    return out


def track_records(engine: str, horizon_h: int = 24, now: datetime | None = None, days: int = 60) -> dict:
    """{(règle, action): {"n", "rate", "low", "high"}} : fréquence historique favorable (théorique)."""
    since = iso((now or utcnow()) - timedelta(days=days))
    until = iso(now or utcnow())
    agg: dict = defaultdict(lambda: [0, 0])
    with db.get_conn() as c:
        for r in c.execute("SELECT d.rule, d.action, o.verdict FROM decision_outcomes o JOIN decision_log d "
                           "ON d.id = o.decision_id WHERE d.engine=? AND o.horizon_h=? AND d.timestamp BETWEEN ? AND ? "
                           "AND o.verdict != 'sans_donnee' AND o.evaluated_at <= ?",
                           (engine, horizon_h, since, until, until)):
            a = agg[(r["rule"], r["action"])]
            a[1] += 1
            a[0] += r["verdict"] in ("favorable", "abstention_ok")
    out = {}
    for key, (k, n) in agg.items():
        lo, hi = wilson(k, n)
        out[key] = {"n": n, "rate": round(k / n, 3), "low": round(lo, 3), "high": round(hi, 3), "horizon_h": horizon_h}
    return out


def print_performance(days: int = 30) -> None:
    rows = performance(days=days)
    print(f"=== RÉSULTATS THÉORIQUES ({days} j) — prix observés, pas des ventes réelles ===")
    if not rows:
        print("Aucune décision évaluée pour l'instant (il faut au moins 6 h de journal).")
        return
    for r in rows:
        rate = f"{r['favorable_rate'] * 100:.0f} %" if r["favorable_rate"] is not None else "–"
        warn = "" if r["enough_data"] else f"  (échantillon < {config.PROBA_MIN_SAMPLES} : indicatif)"
        print(f"{r['engine']} {r['action']:<14} {r['horizon_h']:>4} h : n={r['n']:<5} favorable {rate:>5} "
              f"· variation médiane {(r['median_change'] or 0) * 100:+.1f} % · {r['verdicts']}{warn}")
