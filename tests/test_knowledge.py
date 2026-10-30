"""Base de connaissances : format, cohérence avec le code, calendrier, vérification par les données."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import config
from database import db
from knowledge.service import KnowledgeService, get_service
from knowledge.verify import verify_all
from utils.helpers import EA_TIERS


def test_committed_knowledge_is_valid():
    ks = get_service()
    assert ks.validate() == []
    assert len(ks.entries) >= 30 and ks.event("black_friday") and ks.event("toty")
    # le niveau 2 (stratégies) n'est jamais présenté comme confirmé
    assert all(e["statut"] in ("hypothese", "a_verifier") for e in ks.active(niveau=2))


def test_knowledge_matches_code_constants():
    ks = get_service()
    assert ks.data("taxe_ea", "taux") == config.EA_TAX
    tiers = [(lim if lim is not None else float("inf"), step) for lim, step in ks.data("paliers_prix", "paliers")]
    assert tuple(tiers) == EA_TIERS


def test_validation_catches_bad_entries(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "categorie: test\nentrees:\n  - {id: T-1, cle: a, niveau: 1, titre: t, contenu: c, version_jeu: FC27,"
        " sources: [{url: '', type: rumeur}], fiabilite: 2, statut: confirme, verifie_le: 2026-10-30}\n", encoding="utf-8")
    errors = KnowledgeService(tmp_path).validate()
    assert any("type de source inconnu" in e for e in errors)
    assert any("fiabilité >= 4" in e for e in errors)


def test_upcoming_events_and_summary_lines():
    from alerts.notifier import knowledge_lines, knowledge_tips

    ks = get_service()
    names = [e["cle"] for e in ks.upcoming(datetime(2026, 11, 20), days=10)]
    assert "black_friday" in names
    tips = knowledge_tips(datetime(2026, 11, 20))
    assert any("Black Friday" in t and "dans 7 j" in t and "KB-S-004" in t for t in tips)
    assert any("À venir" in line for line in knowledge_lines(datetime(2026, 11, 20)))


def _seed_market(weeks: int, weekly_amp: float, end: datetime) -> None:
    """8 joueurs, prix horaire avec cycle : +amp jeu-ven, -amp dim-lun (heure de Paris approximée)."""
    start = end - timedelta(weeks=weeks)
    for i in range(8):
        db.upsert_player({"player_id": f"k-{i}", "name": f"K{i}"})
    with db.get_conn() as c:
        t = start
        while t <= end:
            d = (t + timedelta(hours=1)).weekday()
            level = 1 + (weekly_amp if d in (3, 4) else -weekly_amp if d in (6, 0) else 0)
            for i in range(8):
                db.insert_snapshot(f"k-{i}", int(10000 * (1 + i / 10) * level), t, source="test", conn=c)
            t += timedelta(hours=1)


def test_verify_confirms_weekly_cycle_on_matching_data():
    end = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    _seed_market(4, 0.06, end)
    r = verify_all(now=end, save=True)
    h = r["hypotheses"]["cycle_hebdo_week_end"]
    assert h["verdict"] == "confirmee" and h["n"] >= 3 and h["mediane"] > 0.05
    assert r["hypotheses"]["crash_black_friday"]["verdict"] == "insuffisant"  # événement pas encore passé
    assert r["profil_jours_observe"]["vendredi"] > 0 > r["profil_jours_observe"]["lundi"]
    assert get_service().observed()["hypotheses"]["cycle_hebdo_week_end"]["verdict"] == "confirmee"


def test_verify_contradicts_when_data_disagree():
    end = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    _seed_market(4, -0.06, end)  # l'inverse : prix bas jeu-ven
    assert verify_all(now=end, save=False)["hypotheses"]["cycle_hebdo_week_end"]["verdict"] == "contredite"


def test_verify_needs_three_weeks():
    end = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    _seed_market(1, 0.06, end)
    assert verify_all(now=end, save=False)["hypotheses"]["cycle_hebdo_week_end"]["verdict"] == "insuffisant"


def test_dashboard_knowledge_api():
    from dashboard import app

    r = TestClient(app).get("/api/knowledge").json()
    assert {"marche", "calendrier", "cartes", "strategies"} <= set(r["categories"])
    e = next(x for x in r["categories"]["marche"] if x["cle"] == "taxe_ea")
    assert e["statut_label"] == "confirmé" and e["sources"][0]["url"].startswith("https://help.ea.com")
