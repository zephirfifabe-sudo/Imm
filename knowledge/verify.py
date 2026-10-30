"""Confronte les HYPOTHÈSES de la base de connaissances aux prix réellement relevés par le bot.

Indice du marché suivi : pour chaque joueur, prix / prix médian du joueur sur la période ; puis, heure par
heure, médiane sur tous les joueurs (au moins 5). Seuls les relevés RÉELS sont utilisés (aucune interpolation).

Verdicts (data/knowledge_observed.json) :
  confirmee      ≥ 2/3 des observations vont dans le sens attendu (au-delà du seuil)
  contredite     ≥ 2/3 vont dans le sens contraire
  mitigee        ni l'un ni l'autre
  insuffisant    moins de 3 semaines observées (tests hebdo) ou événement pas encore passé / sans données
Ces verdicts ne modifient jamais le statut des fichiers YAML : c'est un humain qui met à jour la théorie.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config
from database import db
from knowledge.service import KnowledgeService, get_service, observed_path
from utils.helpers import iso, utcnow
from utils.logger import get_logger

log = get_logger("knowledge")
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
TOL = pd.Timedelta(hours=1.5)
MIN_WEEKS = 3


def market_index(days: int = 400, now: datetime | None = None) -> pd.Series:
    now = now or utcnow()
    rows = db.get_snapshots(since=now - timedelta(days=days))
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True).dt.floor("h")
    df = df[df["ts"] <= pd.Timestamp(now)]
    df["rel"] = df["price"] / df.groupby("player_id")["price"].transform("median")
    g = df.groupby("ts")["rel"]
    idx = g.median()[g.count() >= 5]
    return idx.sort_index()


def value_at(idx: pd.Series, ts: pd.Timestamp) -> float | None:
    near = idx[(idx.index >= ts - TOL) & (idx.index <= ts + TOL)]
    if near.empty:
        return None
    return float(near.iloc[int(np.argmin(np.abs((near.index - ts).total_seconds())))])


def _weeks(idx: pd.Series, tz: str) -> list[pd.Timestamp]:
    """Lundis 00h (fuseau tz) de chaque semaine couverte par l'indice."""
    loc = idx.index.tz_convert(tz)
    start = (loc.min() - pd.Timedelta(days=loc.min().weekday())).normalize()
    return list(pd.date_range(start, loc.max(), freq="7D"))


def _at(monday: pd.Timestamp, day: str, hhmm: str) -> pd.Timestamp:
    h, m = (int(x) for x in hhmm.split(":"))
    d = monday + pd.Timedelta(days=JOURS.index(day))
    return d.tz_localize(None).replace(hour=h, minute=m).tz_localize(monday.tz)


def obs_comparaison_jours(idx: pd.Series, t: dict) -> list[float]:
    loc = idx.copy()
    loc.index = loc.index.tz_convert(config.TZ)
    out = []
    for monday in _weeks(idx, config.TZ):
        week = loc[(loc.index >= monday) & (loc.index < monday + pd.Timedelta(days=7))]
        hi = week[week.index.weekday.isin([JOURS.index(d) for d in t["haut"]])]
        lo = week[week.index.weekday.isin([JOURS.index(d) for d in t["bas"]])]
        if len(hi) >= 12 and len(lo) >= 12:
            out.append(float(hi.mean() / lo.mean() - 1))
    return out


def obs_fenetre_hebdo(idx: pd.Series, t: dict, now: pd.Timestamp) -> list[float]:
    tz = t.get("tz", config.TZ)
    out = []
    for monday in _weeks(idx, tz):
        a, b = _at(monday, *t["debut"]), _at(monday, *t["fin"])
        if b <= a:
            b += pd.Timedelta(days=7)
        if b + TOL > now:
            continue
        va, vb = value_at(idx, a.tz_convert("UTC")), value_at(idx, b.tz_convert("UTC"))
        if va and vb:
            out.append(vb / va - 1)
    return out


def obs_evenement(idx: pd.Series, t: dict, ks: KnowledgeService, now: pd.Timestamp) -> list[float]:
    ev = ks.event(t["evenement"])
    if not ev:
        return []
    # les promos démarrent à 18h UK
    base = pd.Timestamp(datetime.combine(ev["debut"], datetime.min.time()).replace(hour=18), tz=ZoneInfo("Europe/London"))
    a, b = base + pd.Timedelta(days=t["de_j"]), base + pd.Timedelta(days=t["a_j"])
    if b + TOL > now:
        return []
    va, vb = value_at(idx, a.tz_convert("UTC")), value_at(idx, b.tz_convert("UTC"))
    return [vb / va - 1] if va and vb else []


def verdict(values: list[float], expected: str, seuil: float, weekly: bool) -> str:
    n = len(values)
    if not n or (weekly and n < MIN_WEEKS):
        return "insuffisant"
    sign = 1 if expected == "hausse" else -1
    hits = sum(v * sign >= seuil for v in values)
    contra = sum(v * sign <= -seuil for v in values)
    if hits >= 2 * n / 3:
        return "confirmee"
    if contra >= 2 * n / 3:
        return "contredite"
    return "mitigee"


def weekday_profile(idx: pd.Series) -> dict:
    """Connaissance PROPRE au bot : niveau moyen de l'indice par jour (écart à la moyenne de la semaine)."""
    if idx.empty:
        return {}
    loc = idx.copy()
    loc.index = loc.index.tz_convert(config.TZ)
    rel = loc / loc.rolling("7D", min_periods=48).mean() - 1
    rel = rel.dropna()
    if rel.empty:
        return {}
    g = rel.groupby(rel.index.weekday).mean()
    return {JOURS[int(k)]: round(float(v), 4) for k, v in g.items()}


def verify_all(now: datetime | None = None, save: bool = True, ks: KnowledgeService | None = None) -> dict:
    now = now or utcnow()
    ks = ks or get_service()
    idx = market_index(now=now)
    now_ts = pd.Timestamp(now)
    results = {}
    for e in ks.testable():
        t = e["test"]
        if idx.empty:
            vals = []
        elif t["type"] == "comparaison_jours":
            vals = obs_comparaison_jours(idx, t)
        elif t["type"] == "fenetre_hebdo":
            vals = obs_fenetre_hebdo(idx, t, now_ts)
        else:
            vals = obs_evenement(idx, t, ks, now_ts)
        seuil = float(t.get("seuil", 0.01))
        weekly = t["type"] != "evenement"
        results[e["cle"]] = {
            "id": e["id"], "titre": e["titre"], "type": t["type"], "attendu": t["attendu"], "seuil": seuil,
            "n": len(vals), "mediane": round(float(np.median(vals)), 4) if vals else None,
            "valeurs": [round(v, 4) for v in vals[-12:]], "verdict": verdict(vals, t["attendu"], seuil, weekly),
            "unite": "semaines" if weekly else "événement",
        }
    out = {"_meta": {"genere_le": iso(now), "points_indice": int(len(idx)),
                     "jours_couverts": round((idx.index.max() - idx.index.min()).total_seconds() / 86400, 1) if len(idx) else 0},
           "profil_jours_observe": weekday_profile(idx), "hypotheses": results}
    if save:
        config.ensure_dirs()
        observed_path().write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("Connaissances vérifiées : %s", {k: v["verdict"] for k, v in results.items()})
    return out


VERDICT_LABEL = {"confirmee": "✅ confirmée par nos données", "contredite": "❌ contredite par nos données",
                 "mitigee": "➖ mitigée", "insuffisant": "⏳ données insuffisantes"}


def print_verification() -> None:
    r = verify_all()
    m = r["_meta"]
    print(f"=== THÉORIE vs DONNÉES DU BOT ({m['jours_couverts']} jours d'indice, {m['points_indice']} points) ===")
    for cle, h in r["hypotheses"].items():
        med = f"{h['mediane'] * 100:+.1f} %" if h["mediane"] is not None else "–"
        print(f"{h['id']} {h['titre']}\n    attendu : {h['attendu']} · observé : médiane {med} sur {h['n']} "
              f"{h['unite']} -> {VERDICT_LABEL[h['verdict']]}")
    if r["profil_jours_observe"]:
        print("Profil observé par jour :", {k: f"{v * 100:+.1f} %" for k, v in r["profil_jours_observe"].items()})
