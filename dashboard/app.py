"""Dashboard web FastAPI (port 8000) — consultable depuis l'iPhone.

  /                       page HTML (Tailwind + Chart.js)
  /api/status             statut du bot (ONLINE si heartbeat < 10 min)
  /api/players            tableau watchlist : prix, var 24h, var vs habitude, signal, confiance
  /api/player/{id}/chart  prix réel 7j vs prix prédit par l'habitude (+ prévision 48h)
  /api/alerts             dernières alertes
  /api/performance        résultats THÉORIQUES des décisions journalisées (v1 / v2)
  ?engine=v1|v2           sur /api/players : moteur actif (défaut) ou moteur en observation
  /health                 healthcheck Docker (sans auth)

Protection : si DASHBOARD_USER / DASHBOARD_PASSWORD sont définis -> authentification HTTP Basic.
"""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

import config
from alerts.charts import real_vs_predicted
from core.analyzer import MarketAnalyzer
from core.learner import load_rules
from database import db
from scrapers.watchlist import load_watchlist
from utils.rarity import classify

@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="FC27 Sniper Analyst", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
security = HTTPBasic(auto_error=False)
INDEX = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
_cache: dict = {}
_lock = threading.Lock()


def auth(creds: HTTPBasicCredentials | None = Depends(security)) -> None:
    if not (config.DASHBOARD_USER and config.DASHBOARD_PASSWORD):
        return
    ok = creds is not None and secrets.compare_digest(creds.username, config.DASHBOARD_USER) \
        and secrets.compare_digest(creds.password, config.DASHBOARD_PASSWORD)
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Basic"})


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth)])
def index():
    return INDEX


def _age_minutes(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    dt = datetime.fromisoformat(iso_ts)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 60


@app.get("/api/status", dependencies=[Depends(auth)])
def api_status():
    st = db.get_status()
    hb = _age_minutes((st.get("heartbeat") or {}).get("updated_at"))
    rules = load_rules()
    return {
        "online": hb is not None and hb < 10,
        "heartbeat_minutes": round(hb, 1) if hb is not None else None,
        "last_snapshot": (st.get("last_snapshot") or {}).get("value"),
        "last_snapshot_at": (st.get("last_snapshot") or {}).get("updated_at"),
        "watchlist": (st.get("watchlist") or {}).get("value"),
        "demo": (st.get("mode") or {}).get("value") == "demo",
        "learned": rules.get("_meta"),
        "global": {k: v for k, v in rules.get("GLOBAL", {}).items() if k != "profile"},
        "jobs": {k[4:]: v["value"] for k, v in st.items() if k.startswith("job:")},
        "brain": {"active": config.BRAIN_VERSION, "shadow": config.BRAIN_SHADOW or None},
        # le « meilleur moment appris » n'est affiché que si l'habitude est validée
        "habit_validated": (rules.get("GLOBAL", {}).get("confidence") or 0) >= config.HABIT_MIN_CONFIDENCE
                           and (rules.get("GLOBAL", {}).get("weeks_observed") or 0) >= config.HABIT_MIN_WEEKS,
        "tz": config.TZ,
    }


@app.get("/api/players", dependencies=[Depends(auth)])
def api_players(engine: str | None = None):
    engine = engine if engine in ("v1", "v2") else config.BRAIN_VERSION
    with _lock:  # calcul coûteux (150 joueurs) -> cache 60 s par moteur
        hit = _cache.get(("players", engine))
        if hit and time.time() - hit[0] < 60:
            return hit[1]
        wl = load_watchlist()
        an = MarketAnalyzer(wl, version=engine)
        rows, scans = [], db.last_scan_times()
        for s in an.full_scan():
            x = s.extra
            rows.append({
                "player_id": s.player_id, "name": s.player_name, "rating": s.rating, "position": s.position,
                "rarity": classify(s.card_type),
                "price": s.price, "change_24h": s.change_24h, "habit_dev": x.get("habit_deviation"),
                "action": s.action, "confidence": s.confidence, "rule": s.rule, "instant": s.instant,
                "habit": s.habit, "action_text": s.action_text,
                "avg_7d": x.get("avg_7d"), "min_7d": x.get("min_7d"), "max_7d": x.get("max_7d"),
                "vs_avg": x.get("vs_avg"), "trend_7d": x.get("trend_7d"), "explain": x.get("explain"),
                "scanned_at": scans.get(s.player_id), "engine": engine,
                **{k: (an.by_id.get(s.player_id) or {}).get(k) for k in ("club", "league", "nation")},
                # moteur v2 : décision expliquée et prix explicites
                "reason": x.get("reason"), "opportunity": x.get("opportunity"), "data_quality": x.get("data_quality"),
                "probability": x.get("probability"), "habit_validated": x.get("habit_validated"),
                "observed_at": x.get("observed_at"), "buy_max": x.get("buy_max"), "sell_min": x.get("sell_min"),
                "target_price": x.get("target_price"), "net_profit": x.get("net_profit"),
            })
        known = {r["player_id"] for r in rows}
        rows += [{"player_id": p["player_id"], "name": p["name"], "rating": p.get("rating"), "position": p.get("position"),
                  "rarity": classify(p.get("card_type")), "price": p.get("price"), "action": "?", "confidence": None,
                  "scanned_at": scans.get(p["player_id"]), "engine": engine,
                  "club": p.get("club"), "league": p.get("league"), "nation": p.get("nation")}
                 for p in wl if p["player_id"] not in known]
        _cache[("players", engine)] = (time.time(), rows)
        return rows


@app.get("/api/knowledge", dependencies=[Depends(auth)])
def api_knowledge():
    from knowledge.service import STATUT_LABEL, get_service

    ks = get_service()
    observed = ks.observed()
    hyp = observed.get("hypotheses", {})
    cats: dict = {}
    for e in ks.entries.values():
        cats.setdefault(e["categorie"], []).append({
            "id": e["id"], "cle": e["cle"], "niveau": e["niveau"], "titre": e["titre"], "contenu": e["contenu"],
            "statut": e["statut"], "statut_label": STATUT_LABEL[e["statut"]], "fiabilite": e["fiabilite"],
            "sources": e["sources"], "verifie_le": str(e["verifie_le"]), "observe": hyp.get(e["cle"])})
    return {"categories": cats, "upcoming": ks.upcoming_text(days=14),
            "observed_meta": observed.get("_meta"), "profil_jours": observed.get("profil_jours_observe")}


@app.get("/api/performance", dependencies=[Depends(auth)])
def api_performance(days: int = 30):
    from core.decision_journal import performance

    return {"rows": performance(days=min(days, 180)), "min_samples": config.PROBA_MIN_SAMPLES,
            "note": "Résultats théoriques calculés sur des prix observés, pas des ventes réelles."}


@app.get("/api/player/{player_id}/chart", dependencies=[Depends(auth)])
def api_chart(player_id: str):
    return real_vs_predicted(player_id)


@app.get("/api/summary", dependencies=[Depends(auth)])
def api_summary():
    ev = db.get_events("summary")
    if not ev:
        return {"text": None, "timestamp": None}
    last = ev[-1]
    return {"text": last["payload"].get("text"), "timestamp": last["timestamp"]}


@app.get("/api/alerts", dependencies=[Depends(auth)])
def api_alerts(limit: int = 30):
    return db.recent_alerts(min(limit, 200))
