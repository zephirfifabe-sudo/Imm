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
    assert len(rows) == 12 and {"price", "action", "confidence", "habit_dev", "rarity", "scanned_at"} <= set(rows[0])
    assert rows[0]["scanned_at"].endswith("+00:00")
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


def test_daily_summary_discord_and_dashboard():
    seed_demo(days=3)
    wl = load_watchlist()
    text = notifier.publish_summary(MarketAnalyzer(wl), wl)
    assert "RÉSUMÉ DES 24 DERNIÈRES HEURES" in text and "Consignes" in text and "taxe EA" in text
    assert "Plus fortes hausses" in text and "Koné" in text  # Koné +35 % (scénario démo)
    from dashboard import app

    r = TestClient(app).get("/api/summary").json()
    assert r["text"] == text and r["timestamp"]


def test_consignes_by_weekday():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Paris")
    sunday_night = notifier._consignes(datetime(2026, 11, 1, 21, 0, tzinfo=tz), None)
    assert any("crash FUT Champions" in t and "acheter" in t for t in sunday_night)
    friday = notifier._consignes(datetime(2026, 10, 30, 15, 0, tzinfo=tz), 0.06)
    assert any("Vendredi" in t for t in friday) and any("forte hausse" in t for t in friday)


def test_card_image_url(monkeypatch):
    from dashboard.app import card_image

    assert card_image("fgn-949899") == "https://www.futgenie.gg/api/cards/949899"
    assert card_image("demo-1") is None  # autres sources : carte dessinée
    monkeypatch.setattr(config, "CARD_IMAGES", False)
    assert card_image("fgn-949899") is None


def test_sparklines_and_chart_periods():
    seed_demo(days=10)
    from dashboard import app

    c = TestClient(app)
    sp = c.get("/api/sparklines").json()
    assert set(sp) >= {"demo-1", "demo-12"}
    pts = sp["demo-1"]
    assert 50 <= len(pts) <= 58 and pts[-1][1] > 0  # 7 jours, 1 point / 3 h, relevés réels
    assert len(c.get("/api/player/demo-1/chart?days=1").json()["real"]) <= 25
    assert len(c.get("/api/player/demo-1/chart?days=30").json()["real"]) > 200  # tout l'historique disponible (10 j)


def test_chart_with_few_snapshots_and_nan_profile(monkeypatch):
    """Joueur récent (< 24 relevés) + habitude contenant des NaN : le graphique ne doit pas planter (erreur 500)."""
    from datetime import timedelta

    from alerts import charts
    from database import db
    from utils.helpers import utcnow

    db.upsert_player({"player_id": "fgn-1", "name": "Nouveau"})
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    for h in range(10):
        db.insert_snapshot("fgn-1", 30000 + h * 10, now - timedelta(hours=h), source="futgenie")
    monkeypatch.setattr(charts.learner, "rule_for", lambda *a: {"profile": [float("nan")] * 168})
    from dashboard import app

    r = TestClient(app).get("/api/player/fgn-1/chart?days=7")
    assert r.status_code == 200 and len(r.json()["real"]) == 10


def test_supervision_alerts_on_outage_partial_and_recovery():
    from datetime import timedelta

    from core.jobs import supervision_check
    from database import db
    from utils.helpers import utcnow

    now = utcnow().replace(minute=0, second=0, microsecond=0)
    assert supervision_check(now) is None  # jamais de vraies données : rien à surveiller
    db.upsert_player({"player_id": "s1", "name": "S"})
    db.insert_snapshot("s1", 1000, now - timedelta(hours=1), source="futgenie")
    db.set_status("last_snapshot", {"ok": 150, "failed": 8})
    assert supervision_check(now) is None  # tout va bien, état inchangé
    msg = supervision_check(now + timedelta(hours=3))
    assert msg.startswith("⚠️") and "depuis 4 h" in msg
    assert supervision_check(now + timedelta(hours=4)) is None  # pas de répétition
    db.insert_snapshot("s1", 1000, now + timedelta(hours=5), source="futgenie")
    db.set_status("last_snapshot", {"ok": 40, "failed": 118})
    assert "partiel" in supervision_check(now + timedelta(hours=5)).lower()
    db.set_status("last_snapshot", {"ok": 155, "failed": 3})
    assert supervision_check(now + timedelta(hours=5)).startswith("✅")


def test_snapshot_every_15_minutes_and_hourly_journal(monkeypatch):
    from datetime import datetime, timezone

    from core import jobs
    from scrapers import price_provider

    trig = {j.id: str(j.trigger) for j in build_scheduler().get_jobs()}["snapshot"]
    assert "minute='2,17,32,47'" in trig

    class FG:  # faux futgenie : 1 prix par joueur
        trends = {}

        def __init__(self, *a, **k):
            self.calls = []

        def current_prices(self, players, bands, max_fiches=40):
            FG.max_fiches = max_fiches
            return {p["player_id"]: 1000 for p in players}

        def fill_missing(self, players, limit=20):
            FG.limit = limit

        def close(self):
            pass

    import scrapers.futgenie as fgmod
    monkeypatch.setattr(fgmod, "FutGenie", FG)
    monkeypatch.setattr(price_provider, "utcnow", lambda: datetime(2026, 10, 31, 9, 33, tzinfo=timezone.utc))
    from database import db

    db.upsert_player({"player_id": "q1", "name": "Q"})
    price_provider._snapshot_futgenie([{"player_id": "q1", "name": "Q"}])
    assert db.get_snapshots(["q1"])[0]["timestamp"] == "2026-10-31T09:30:00+00:00"  # grille de 15 min
    assert (FG.max_fiches, FG.limit) == (10, 5)  # budgets de fiches répartis sur l'heure

    logged = []
    monkeypatch.setattr(jobs, "_watchlist", lambda: [{"player_id": "q1", "name": "Q"}])
    monkeypatch.setattr(price_provider, "snapshot_watchlist", lambda wl: {"ok": 1})
    monkeypatch.setattr(jobs, "journal_scan", lambda *a: logged.append(1))
    for minute, expected in ((5, 1), (20, 1), (35, 1), (50, 1)):
        monkeypatch.setattr(jobs, "utcnow", lambda m=minute: datetime(2026, 10, 31, 9, m, tzinfo=timezone.utc))
        jobs.job_snapshot()
    assert len(logged) == 1  # journal seulement au relevé de début d'heure
