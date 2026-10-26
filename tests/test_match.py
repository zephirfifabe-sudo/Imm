import json

import numpy as np

from fccoach.analysis.match import MatchAnalyzer
from fccoach.analysis.opponent_profile import OpponentDB
from fccoach.coach.engine import CoachConfig
from fccoach.coach.rules import load_rules
from fccoach.storage.db import MatchDB
from tests.sim import FakeHomography, Scene

RULES = load_rules("knowledge/rules.yaml")
IMG = np.zeros((10, 10, 3), np.uint8)


def run(an, scene, t0, t1, dt=0.1, clock0=600, selected=None, actions=None, rng=None):
    t = t0
    while t < t1 - 1e-9:
        if actions:
            actions(t, scene)
        an.set_ocr(clock0 + int(t * 7.5), None)
        an.step(t, IMG, scene.dets(rng), scene.ball_state(t), selected or {"me": None, "opp": None}, "droite", 0.95, True)
        t = round(t + dt, 3)
    return t


def analyzer(tmp_path, **kw):
    return MatchAnalyzer(RULES, FakeHomography(), tmp_path / "match", MatchDB(tmp_path / "m.sqlite"),
                         OpponentDB(tmp_path / "o.sqlite"), coach_cfg=CoachConfig(min_interval_s=20), **kw)


def test_formations_roles_and_pitch(tmp_path):
    an = analyzer(tmp_path)
    run(an, Scene("41212", "4213"), 0, 15, rng=np.random.default_rng(0))
    f = an.snapshot()["formations"]
    assert f["me"]["name"] == "41212" and f["me"]["confidence"] >= 0.7
    assert f["opp"]["name"] == "4213" and f["opp"]["confidence"] >= 0.7
    roles = {p["tid"]: p["role"] for p in an.snapshot()["pitch"]["players"]}
    assert roles[5] == "MDC" and roles[1] == "LAT" and roles[2] == "DC"


def test_pass_loss_and_counter_press_advice(tmp_path):
    an = analyzer(tmp_path)
    sc = Scene("41212", "4213")
    sc.ball = list(sc.pos[5])
    run(an, sc, 0, 12, rng=np.random.default_rng(1))       # formations + possession de mon MDC
    # Passe MDC (5) -> MC (6)
    target = sc.pos[6]
    def pass_(t, s):
        s.move_ball_towards(target[0] + 0.5, target[1], 2.0)
    t = run(an, sc, 12, 14, actions=pass_)
    assert an.stats.counts.get("passes_me") == 1
    # Perte : un adversaire vient prendre le ballon à mon MC
    thief = 107
    sc.pos[thief] = [target[0] + 1.0, target[1] + 0.5]
    sc.ball = [target[0] + 1.0, target[1] + 0.5]
    sc.pos[6] = [target[0] - 4, target[1]]
    t = run(an, sc, t, t + 6)
    assert an.stats.counts.get("pertes") == 1
    shown = [a.rule_id for a in an.coach.shown]
    assert "perte_quadrille" in shown or "perte_quadrille" in an.coach.occurrence_counts()
    bilan = an.finish()
    assert any(r["rule_id"] == "perte_quadrille" and r["source"] == 9 for r in bilan["rules"])
    assert (tmp_path / "match" / "bilan_fin.json").exists()
    assert (tmp_path / "match" / "heatmaps" / "heatmap_me.png").exists()
    assert an.db.occurrences(an.match_id)


def test_score_mapping_and_history(tmp_path):
    an = analyzer(tmp_path)
    sc = Scene()
    run(an, sc, 0, 3)
    an.events.possession = "me"
    an.on_ocr_event({"type": "goal", "score": [0, 1]})   # je marque, je suis à l'extérieur
    assert an.my_score() == (1, 0)
    an.on_ocr_event({"type": "pause", "by": "Rival_77"})
    an.profile.counts["dc_out"] = 3
    an.finish()
    m = an.db.match(an.match_id)
    assert m["score_me"] == 1 and m["opponent"] == "Rival_77"
    assert an.db.weekly()[0]["matches"] == 1
    # Match suivant contre le même adversaire : habitude connue d'avance
    an2 = analyzer(tmp_path)
    an2.set_opponent("Rival_77")
    assert an2.profile.effective("dc_out") == 1
    assert json.loads((tmp_path / "match" / "bilan_fin.json").read_text())["opponent"]["pseudo"] == "Rival_77"


def test_no_advice_during_kickoff(tmp_path):
    an = analyzer(tmp_path)
    sc = Scene()
    t = 0.0
    for _ in range(50):
        an.set_ocr(0, "00:00")                                # chrono figé : engagement
        an.step(t, IMG, sc.dets(), sc.ball_state(t), {"me": None, "opp": None}, "droite", 0.95, True)
        t += 0.1
    assert not an.play_running(t) and an.coach.shown == []
