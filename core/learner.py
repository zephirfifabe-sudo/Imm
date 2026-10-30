"""AUTO-APPRENTISSAGE : learn_patterns() (tous les lundis 05h00).

Analyse les 30 derniers jours de price_snapshots et génère market_rules.json :
{
  "GLOBAL": {"wl_crash_avg": "-15.8%", "best_buy": "Dim-Lun 22h-02h", ...},
  "Barcola_84": {"player_id": "...", "best_buy": "Dim-Lun 22h-02h", "avg_sunday_crash": "-12.5%",
                 "confidence": 0.92, "profile": [168 valeurs], ...}
}
Les règles s'affinent chaque semaine : plus il y a de semaines observées et plus le motif
se répète, plus la confiance monte.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import config
from core import pattern_detector as pdt
from database import db
from utils.helpers import iso, slugify, utcnow
from utils.logger import get_logger

log = get_logger("learner")


def _pct(v: float | None) -> str | None:
    return None if v is None else f"{v * 100:+.1f}%"


def _confidence(stats: dict, weeks: int) -> float:
    sc, rec = stats["sunday_crash"], stats["recovery"]
    if not sc["n"]:
        return 0.0
    hit = 0.7 * sc["hit_rate"] + 0.3 * (rec["hit_rate"] if rec["n"] else sc["hit_rate"])
    consistency = 1.0
    if sc["avg"] and sc["std"] is not None:
        consistency = float(np.clip(1 - sc["std"] / max(abs(sc["avg"]), 1e-6), 0, 1))
    coverage = min(1.0, weeks / 4)
    return round(float(hit * coverage * (0.6 + 0.4 * consistency)), 2)


def rule_key(player: dict) -> str:
    return f"{slugify(player.get('name') or player['player_id'])}_{player.get('rating') or ''}".rstrip("_")


def learn_player(s: pd.Series) -> dict | None:
    rel = pdt.relative(s, centered=True)
    prof = pdt.profile_from_rel(rel)
    if prof is None:
        return None
    stats = pdt.weekly_stats(s).summary()
    weeks = stats["sunday_crash"]["n"]
    buy_i, buy_v = pdt.best_window(prof, 4, lowest=True)
    sell_i, sell_v = pdt.best_window(prof, 4, lowest=False)
    return {
        "best_buy": pdt.window_label(buy_i, 4),
        "best_buy_how": buy_i,
        "best_sell": pdt.window_label(sell_i, 4),
        "best_sell_how": sell_i,
        "buy_sell_spread": _pct(sell_v - buy_v),
        "avg_sunday_crash": _pct(stats["sunday_crash"]["avg"]),
        "avg_sunday_crash_value": stats["sunday_crash"]["avg"],
        "avg_rivals_crash": _pct(stats["rivals_crash"]["avg"]),
        "avg_rivals_crash_value": stats["rivals_crash"]["avg"],
        "avg_recovery_to_thursday": _pct(stats["recovery"]["avg"]),
        "avg_recovery_value": stats["recovery"]["avg"],
        "weekday_cycle": pdt.cycle_by_weekday(rel),
        "weeks_observed": weeks,
        "confidence": _confidence(stats, weeks),
        "profile": [round(float(x), 4) for x in prof],
    }


def new_card_impact(df: pd.DataFrame, days: int, now: datetime) -> float | None:
    """Variation moyenne à 24h des joueurs du même groupe de poste après une nouvelle carte."""
    from utils.helpers import POSITION_GROUP

    events = db.get_events("new_card", since=now - timedelta(days=days))
    if not events or df.empty:
        return None
    pos_of = {p["player_id"]: p.get("position") for p in db.get_players(df["player_id"].unique())}
    changes = []
    for ev in events:
        grp = POSITION_GROUP.get(ev.get("position") or "")
        if not grp:
            continue
        t0 = pd.Timestamp(ev["timestamp"]).tz_convert(config.TZ)
        for pid, pos in pos_of.items():
            if POSITION_GROUP.get(pos or "") != grp or pid == ev.get("player_id"):
                continue
            s = df.loc[df["player_id"] == pid].set_index("ts")["price"].sort_index()
            a, b = s[s.index <= t0].tail(1), s[s.index >= t0 + pd.Timedelta(hours=24)].head(1)
            if len(a) and len(b):
                changes.append(float(b.iloc[0] / a.iloc[0] - 1))
    return float(np.mean(changes)) if changes else None


def learn_patterns(days: int = 30, now: datetime | None = None, save: bool = True) -> dict:
    now = now or utcnow()
    df = pdt.load_frame(days, now=now)
    players = {p["player_id"]: p for p in db.get_players()}
    rules: dict = {"_meta": {"generated_at": iso(now), "days": days, "players": 0, "tz": config.TZ}}
    if df.empty:
        log.warning("learn_patterns : aucune donnée (le bot doit tourner quelques jours)")
        rules["GLOBAL"] = load_rules().get("GLOBAL", {})
        if save:
            save_rules(rules)
        return rules

    rels, crashes, rivals, recs, confs = [], [], [], [], []
    for pid in df["player_id"].unique():
        s = pdt.hourly_series(df, pid)
        r = learn_player(s)
        if not r:
            continue
        p = players.get(pid, {"player_id": pid, "name": pid})
        r = {"player_id": pid, "name": p.get("name"), "rating": p.get("rating"), **r}
        rules[rule_key(p)] = r
        rels.append(pdt.relative(s).rename(pid))
        for lst, k in ((crashes, "avg_sunday_crash_value"), (recs, "avg_recovery_value"),
                       (rivals, "avg_rivals_crash_value")):
            if r.get(k) is not None:
                lst.append(r[k])
        confs.append(r["confidence"])

    glob: dict = {"players_learned": len(confs)}
    if rels:
        # profil global = médiane des profils relatifs, toutes séries confondues
        all_rel = pd.concat(rels)
        gprof = pdt.profile_from_rel(all_rel)
        if gprof is not None:
            bi, _ = pdt.best_window(gprof, 4, True)
            si, _ = pdt.best_window(gprof, 4, False)
            glob.update(best_buy=pdt.window_label(bi, 4), best_sell=pdt.window_label(si, 4),
                        profile=[round(float(x), 4) for x in gprof])
        glob["weekday_cycle"] = pdt.cycle_by_weekday(all_rel)
    glob.update(
        wl_crash_avg=_pct(float(np.mean(crashes))) if crashes else None,
        avg_sunday_crash_value=float(np.mean(crashes)) if crashes else None,
        rivals_crash_avg=_pct(float(np.mean(rivals))) if rivals else None,
        recovery_avg=_pct(float(np.mean(recs))) if recs else None,
        avg_recovery_value=float(np.mean(recs)) if recs else None,
        new_card_impact_24h=_pct(new_card_impact(df, days, now)),
        confidence=round(float(np.mean(confs)), 2) if confs else 0.0,
        weeks_observed=int(round(df["ts"].dt.isocalendar().week.nunique())),
    )
    rules["GLOBAL"] = glob
    rules["_meta"]["players"] = len(confs)
    if save:
        save_rules(rules)
        db.add_event("learn", title=f"Règles apprises : {len(confs)} joueurs", payload=rules["_meta"])
        db.set_status("last_learn", rules["_meta"])
    log.info("learn_patterns : %d joueurs appris, crash WL moyen %s", len(confs), glob.get("wl_crash_avg"))
    return rules


# --------------------------------------------------------------------------- persistance
def save_rules(rules: dict) -> None:
    config.ensure_dirs()
    config.RULES_PATH.write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")


def load_rules() -> dict:
    for path in (config.RULES_PATH, config.DEFAULT_RULES_PATH):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                log.error("market_rules.json illisible : %s", path)
    return {}


def rule_for(rules: dict, player: dict) -> dict:
    """Règle perso du joueur si assez fiable, sinon règle GLOBAL (avec confiance réduite)."""
    r = rules.get(rule_key(player))
    if not r:
        r = next((v for k, v in rules.items() if isinstance(v, dict) and v.get("player_id") == str(player["player_id"])), None)
    g = rules.get("GLOBAL", {})
    if r and r.get("confidence", 0) >= 0.4:
        return r
    if g.get("profile"):
        return {**g, "confidence": round(g.get("confidence", 0.5) * 0.8, 2), "weeks_observed": g.get("weeks_observed", 0)}
    return r or {}
