from datetime import datetime

from fastapi.testclient import TestClient

import config
from alerts import notifier
from alerts.charts import chart_png, real_vs_predicted
from alerts.telegram import split_message
from core.analyzer import MarketAnalyzer
from core.backtest import run_backtest
from core.demo import seed_demo
from core.jobs import build_scheduler, in_19h_window
from core.learner import learn_patterns
from core.signals import Signal
from database import db
from scrapers.watchlist import load_watchlist


def _sig(pid, action="ACHAT", conf=8, score=0.5):
    return Signal(action=action, rule="T", score=score, confidence=conf, player_id=pid, player_name=pid, price=1000)


def test_notifier_filter_and_cooldown():
    sigs = [_sig("a"), _sig("b", conf=5), _sig("c", action="HOLD"), _sig("d", conf=9)]
    assert [s.player_id for s in notifier.select(sigs)] == ["d", "a"]
    # sans canal configuré : sauvegardé non envoyé -> pas de cooldown
    notifier.dispatch(sigs)
    assert len(db.recent_alerts()) == 2
    db.save_alert("ACHAT", "a", 8, "T", "x", sent=True)
    assert [s.player_id for s in notifier.select(sigs)] == ["d"]


def test_split_message():
    parts = split_message("\n\n".join(["x" * 1500] * 5), 4000)
    assert all(len(p) <= 4000 for p in parts) and len(parts) == 3


def test_tax_downgrades_small_rebound(monkeypatch):
    seed_demo(days=20)
    rules = {"Barcola_84": {"player_id": "demo-1", "avg_recovery_value": 0.06, "confidence": 0.9,
                            "profile": [0.0] * 168}}
    an = MarketAnalyzer(load_watchlist(), rules=rules)
    neutral = {"score": 0.0, "confidence": 0.9, "deviation": 0.0, "text": ""}
    monkeypatch.setattr(an, "habit", lambda *a, **k: neutral)
    s = an.build_signal(db.get_player("demo-1"), "T", 0.9, "test")
    # +6% de rebond - 5% de taxe < 4% de marge nette -> pas d'achat
    assert s.action == "HOLD" and "taxe" in s.instant


def test_backtest_and_charts():
    seed_demo(days=35)
    learn_patterns(days=30)
    res = run_backtest(load_watchlist(), days=7, step_hours=12)
    assert res["trades"] >= 1 and "by_rule" in res
    data = real_vs_predicted("demo-1")
    assert len(data["real"]) > 100 and len(data["forecast"]) == 48
    assert chart_png("demo-1")[:4] == b"\x89PNG"


def test_scheduler_and_window():
    ids = {j.id for j in build_scheduler().get_jobs()}
    assert {"snapshot", "watchlist", "latest", "pre19", "post19", "recap", "learn"} <= ids
    assert in_19h_window(datetime(2026, 10, 30, 19, 0))
    assert not in_19h_window(datetime(2026, 10, 30, 20, 31))


def test_dashboard_api(monkeypatch):
    seed_demo(days=10)
    from dashboard import app

    c = TestClient(app)
    assert c.get("/health").json() == {"ok": True}
    assert "FC27 Sniper" in c.get("/").text
    assert c.get("/static/chart.umd.js").status_code == 200
    rows = c.get("/api/players").json()
    assert len(rows) == 12 and {"price", "action", "confidence", "habit_dev", "rarity"} <= set(rows[0])
    wirtz = next(r for r in rows if r["name"] == "Wirtz")
    assert wirtz["rarity"]["label"] == "Trailblazers" and wirtz["rarity"]["special"]
    assert c.get("/api/status").json()["demo"] is True
    assert c.get("/api/player/demo-1/chart").json()["real"]

    monkeypatch.setattr(config, "DASHBOARD_USER", "moi")
    monkeypatch.setattr(config, "DASHBOARD_PASSWORD", "secret")
    assert c.get("/api/status").status_code == 401
    assert c.get("/api/status", auth=("moi", "secret")).status_code == 200
    assert c.get("/health").status_code == 200


def test_price_report():
    seed_demo(days=3)
    msgs = notifier.price_report(load_watchlist())
    assert "💰 PRIX" in msgs[0] and "joueurs" in msgs[0]
    assert all(len(m) < 2000 for m in msgs)  # limite Discord
    body = "\n".join(msgs[1:])
    assert body.startswith("```") and "Koné" in body and "%" in body
    assert "Plus fortes hausses" in msgs[0]  # Koné +35 % en 24h (scénario démo)
    assert "price_report" in {j.id for j in build_scheduler().get_jobs()}
