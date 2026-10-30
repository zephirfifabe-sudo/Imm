import json
from datetime import timedelta

import config
from core.analyzer import MarketAnalyzer, similarity
from core.demo import seed_demo
from core.learner import learn_patterns, load_rules
from core.signals import format_alert
from database import db
from scrapers.watchlist import load_watchlist
from utils.helpers import utcnow


def test_similarity_rule1():
    ref = {"position": "LW", "league": "Ligue 1", "nation": "France", "rating": 84}
    assert similarity({"position": "LW", "league": "Ligue 1", "nation": "France", "rating": 85}, ref) > 0.85
    assert similarity({"position": "LW", "league": "Ligue 1", "nation": "Spain", "rating": 84}, ref) > 0.85
    assert similarity({"position": "LM", "league": "Ligue 1", "nation": "France", "rating": 84}, ref) > 0.85
    assert similarity({"position": "ST", "league": "Serie A", "nation": "France", "rating": 84}, ref) < 0.85
    assert similarity({"position": "LW", "league": "Ligue 1", "nation": "France", "rating": 88}, ref) < 0.85


def test_learn_patterns_finds_sunday_crash():
    seed_demo(days=35)
    rules = learn_patterns(days=30)
    assert config.RULES_PATH.exists()
    g = rules["GLOBAL"]
    assert g["avg_sunday_crash_value"] < -0.08  # crash du dimanche détecté
    assert g["avg_recovery_value"] > 0.05
    assert g["best_buy"].startswith(("Dim", "Lun"))
    r = rules["Barcola_84"]
    assert r["player_id"] == "demo-1" and len(r["profile"]) == 168 and r["confidence"] > 0.6
    assert load_rules()["_meta"]["players"] == 12


def test_analyzer_rules_end_to_end():
    seed_demo(days=35)
    learn_patterns(days=30)
    an = MarketAnalyzer(load_watchlist())
    by = {s.player_id: s for s in an.full_scan()}
    assert by["demo-2"].rule == "R4_CHUTE_48H" and by["demo-2"].action.startswith("ACHAT")
    assert by["demo-6"].rule == "R4_HYPE_24H" and by["demo-6"].action.startswith("VENTE")
    txt = format_alert(by["demo-2"])
    assert "Confiance" in txt and "Habitude" in txt and "Action : ACHETER" in txt

    # R1 : nouvelle carte qui concurrence Barcola (LW, Ligue 1, France, 84)
    card = {"player_id": "new-1", "name": "Akliouche", "rating": 85, "position": "LW",
            "league": "Ligue 1", "nation": "France"}
    sigs = an.rule1_competition(card)
    assert any(s.player_id == "demo-1" and s.action.startswith("VENTE") for s in sigs)

    # R4 bloquée si une carte concurrente est sortie récemment
    db.add_event("new_card", title="Clone Doué", player_id="x", position="RW",
                 payload={"position": "RW", "league": "Ligue 1", "nation": "France", "rating": 83})
    assert an.rule4_technical(db.get_player("demo-2")) is None

    # R5 : 3 cartes du même groupe de poste en 7 jours
    for i in range(3):
        db.add_event("new_card", title=f"ST {i}", position="ST", payload={"position": "ST"})
    sat = an.rule5_saturation()
    assert {s.player_id for s in sat} >= {"demo-3", "demo-8"}


def test_rule2_sbc_and_rule3_evo():
    seed_demo(days=10)
    an = MarketAnalyzer(load_watchlist())
    sbc = {"name": "Marquee Matchups", "requirements": {"min_team_rating": 84, "leagues": ["Ligue 1"], "squads": []}}
    sigs = an.rule2_sbc(sbc)
    assert sigs[0].rule == "R2_SBC_FODDER"
    assert {"demo-1", "demo-11", "demo-12"} <= {s.player_id for s in sigs}

    cheap = {"player_id": "c1", "name": "Cheap Winger", "rating": 79, "position": "LW", "playstyles": ["Rapid"]}
    db.upsert_player(cheap)
    db.insert_snapshot("c1", 4500, utcnow() - timedelta(hours=1))
    evo = {"name": "Speed Demon", "requirements": {"max": {"OVR": 80}, "positions": ["LW", "RW"]},
           "upgrades": {"stats": {"OVR": 4}, "playstyles_plus": ["Quick Step"], "playstyles": ["Technical"]}}
    out = an.rule3_evo(evo)
    assert out and out[0].player_id == "c1" and out[0].rule == "R3_EVO"
    assert json.dumps(out[0].to_dict())
