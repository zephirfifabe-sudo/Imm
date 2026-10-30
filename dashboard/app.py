"""Dashboard web FastAPI (port 8000) — consultable depuis l'iPhone.

  /                       page HTML (Tailwind + Chart.js)
  /api/status             statut du bot (ONLINE si heartbeat < 10 min)
  /api/players            tableau watchlist : prix, var 24h, var vs habitude, signal, confiance
  /api/player/{id}/chart  prix réel 7j vs prix prédit par l'habitude (+ prévision 48h)
  /api/alerts             dernières alertes
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
        "tz": config.TZ,
    }


@app.get("/api/players", dependencies=[Depends(auth)])
def api_players():
    with _lock:  # calcul coûteux (150 joueurs) -> cache 60 s
        if _cache.get("players") and time.time() - _cache["players"][0] < 60:
            return _cache["players"][1]
        wl = load_watchlist()
        an = MarketAnalyzer(wl)
        rows = []
        for s in an.full_scan():
            rows.append({
                "player_id": s.player_id, "name": s.player_name, "rating": s.rating, "position": s.position,
                "price": s.price, "change_24h": s.change_24h, "habit_dev": s.extra.get("habit_deviation"),
                "action": s.action, "confidence": s.confidence, "rule": s.rule, "instant": s.instant,
                "habit": s.habit, "action_text": s.action_text,
            })
        known = {r["player_id"] for r in rows}
        rows += [{"player_id": p["player_id"], "name": p["name"], "rating": p.get("rating"), "position": p.get("position"),
                  "price": p.get("price"), "action": "?", "confidence": None} for p in wl if p["player_id"] not in known]
        _cache["players"] = (time.time(), rows)
        return rows


@app.get("/api/player/{player_id}/chart", dependencies=[Depends(auth)])
def api_chart(player_id: str):
    return real_vs_predicted(player_id)


@app.get("/api/alerts", dependencies=[Depends(auth)])
def api_alerts(limit: int = 30):
    return db.recent_alerts(min(limit, 200))
