"""Étape 1 : moteur v2 (qualité des données, 4 décisions, prix explicites) + journal des décisions."""
from __future__ import annotations

from datetime import timedelta

import config
from alerts import notifier
from core import decision_journal as dj
from core.signals import format_alert
from database import db
from tests.test_characterization import NOW, PLAYER, analyzer, flat_then, seed
from utils.helpers import round_tier


def test_ea_tiers():
    assert [round_tier(p) for p in (987, 9_999, 10_049, 36_333, 52_400, 150_999)] == \
        [950, 9_900, 10_000, 36_250, 52_000, 150_000]
    assert [round_tier(p, "up") for p in (951, 36_251, 99_501)] == [1_000, 36_500, 100_000]


def test_v2_buy_has_justified_target_tiers_and_theoretical_wording():
    seed(flat_then(48, 50000, 40000))  # -20 % en 48 h, 10 jours d'historique
    s = analyzer(habit=False, version="v2").rule4_technical(PLAYER)
    x = s.extra
    assert s.action == "ACHAT" and x["engine"] == "v2" and x["reason"] == ""
    assert x["buy_max"] == 40000 and x["sell_min"] == round_tier(x["target_price"])  # paliers EA
    assert x["target_price"] == x["avg_7d"]  # cible = moyenne 7 j observée, pas une valeur par défaut
    assert x["net_profit"] == round(x["sell_min"] * 0.95 - 40000) and x["executable_price"] is None
    assert x["probability"] is None and x["data_quality"] == 100
    txt = format_alert(s)
    assert "théorique, non garanti" in txt and "Probabilité de réussite : non disponible" in txt
    assert "Opportunité" in txt and "Qualité des données 100/100" in txt and "Confiance" not in txt


def test_v2_margin_too_small_becomes_surveillance():
    seed(flat_then(48, 50000, 42000) | {h: 43500 for h in range(240, 49, -1)})  # moyenne proche du prix
    s = analyzer(habit=False, version="v2").rule4_technical(PLAYER)
    assert s.action == "SURVEILLANCE" and "marge nette théorique" in s.extra["reason"]


def test_v2_sell_never_below_observed_and_no_duplicate_crash_signal():
    seed(flat_then(24, 40000, 52000))
    an = analyzer(habit=False, version="v2")
    s = an.rule4_technical(PLAYER)
    assert s.action == "VENTE" and "VENDRE vers 52 000" in s.action_text.replace(" ", " ")
    assert an.instant_crashes(24) == []


def test_v2_stale_player_is_logged_as_abstention():
    seed({h + 30: 50000 for h in range(200)})  # plus aucun relevé depuis 30 h
    sigs = analyzer(habit=False, version="v2").full_scan()
    assert [(s.rule, s.action) for s in sigs] == [("QUALITE_DONNEES", "AUCUNE ACTION")]
    assert "il y a 30 h" in sigs[0].extra["reason"]


def test_notifier_never_sends_abstentions(monkeypatch):
    seed({h + 30: 50000 for h in range(200)})
    s = analyzer(habit=False, version="v2").full_scan()[0]
    s.confidence = 10  # même avec une note forcée
    monkeypatch.setattr(notifier, "send_text", lambda *a, **k: True)
    assert notifier.dispatch([s]) == []


def test_journal_logs_every_decision_and_evaluates_outcomes():
    seed(flat_then(48, 50000, 40000))
    sigs = analyzer(habit=False, version="v2", now=NOW - timedelta(hours=24)).full_scan()
    assert dj.log_decisions(sigs, "v2", NOW - timedelta(hours=24)) == 1
    # à NOW-24 h : -10 % seulement -> AUCUNE ACTION (abstention), au prix observé de 45 000
    assert sigs[0].action == "AUCUNE ACTION" and sigs[0].price == 45000
    assert dj.evaluate_outcomes(now=NOW + timedelta(hours=2)) == 2  # horizons 6 h et 24 h échus ; 48 h / 7 j pas encore
    assert dj.evaluate_outcomes(now=NOW + timedelta(hours=2)) == 0  # jamais évalué deux fois
    with db.get_conn() as c:
        rows = c.execute("SELECT horizon_h, price, verdict FROM decision_outcomes ORDER BY horizon_h").fetchall()
    assert [tuple(r) for r in rows] == [(6, 43750, "abstention_ok"), (24, 40000, "abstention_ok")]  # la baisse a continué
    perf = dj.performance(now=NOW + timedelta(hours=2))
    assert {(r["action"], r["horizon_h"], r["n"]) for r in perf} == {("AUCUNE ACTION", 6, 1), ("AUCUNE ACTION", 24, 1)}
    assert all(r["enough_data"] is False for r in perf)


def test_verdicts():
    assert dj.verdict("ACHAT", 40000, 44000) == ("favorable", 1800)
    assert dj.verdict("ACHAT", 40000, 41000)[0] == "defavorable"  # +2,5 % ne couvre pas la taxe
    assert dj.verdict("VENTE", 40000, 38000)[0] == "favorable"
    assert dj.verdict("SURVEILLANCE", 40000, 44000)[0] == "occasion_manquee"
    assert dj.verdict("AUCUNE ACTION", 40000, 39000)[0] == "abstention_ok"


def test_track_record_only_after_enough_samples(monkeypatch):
    monkeypatch.setattr(config, "PROBA_MIN_SAMPLES", 3)
    db.upsert_player(PLAYER)
    with db.get_conn() as c:
        for i in range(3):
            c.execute("INSERT INTO decision_log (id, timestamp, engine, player_id, action, rule, observed_price) "
                      "VALUES (?,?,?,?,?,?,?)", (i + 1, "2026-10-28T10:00:00+00:00", "v2", "c-1", "ACHAT", "R4_CHUTE_48H", 100))
            c.execute("INSERT INTO decision_outcomes VALUES (?,?,?,?,?,?,?,?)",
                      (i + 1, 24, "2026-10-29T11:00:00+00:00", 110, None, 0.1, 4, "favorable" if i else "defavorable"))
    an = analyzer(version="v2")
    r = an.track_record("R4_CHUTE_48H", "ACHAT")
    assert r["n"] == 3 and r["rate"] == 0.667 and 0 < r["low"] < r["rate"] < r["high"] <= 1


def test_job_snapshot_logs_active_and_shadow_engines(monkeypatch):
    from core import jobs
    from scrapers import price_provider

    seed(flat_then(48, 50000, 40000))
    monkeypatch.setattr(jobs, "_watchlist", lambda: [PLAYER])
    monkeypatch.setattr(price_provider, "snapshot_watchlist", lambda wl: {"ok": 1})
    monkeypatch.setattr(jobs, "utcnow", lambda: NOW.replace(minute=4))  # relevé de début d'heure -> journal
    monkeypatch.setattr(notifier, "send_text", lambda *a, **k: True)
    monkeypatch.setattr(notifier, "send_photo", lambda *a, **k: True, raising=False)
    monkeypatch.setattr(config, "BRAIN_VERSION", "v1")
    monkeypatch.setattr(config, "BRAIN_SHADOW", "v2")
    jobs.job_snapshot()
    with db.get_conn() as c:
        engines = sorted(r[0] for r in c.execute("SELECT engine FROM decision_log"))
    assert engines == ["v1", "v2"]
    assert all(a["action"].startswith(("ACHAT", "VENTE")) for a in db.recent_alerts())  # v2 jamais envoyé
