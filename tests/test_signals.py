"""Règles adversaire en direct et prudence hors champ, sur match simulé."""

import numpy as np

from fccoach.analysis.match import MatchAnalyzer
from fccoach.coach.engine import CoachConfig
from fccoach.coach.rules import load_rules
from tests.sim import FakeHomography, Scene

RULES = load_rules("knowledge/rules.yaml")
IMG = np.zeros((10, 10, 3), np.uint8)


def run(an, sc, t0, t1, selected, dt=0.1):
    t = t0
    while t < t1:
        an.set_ocr(600 + int(t * 7.5), None)
        an.step(t, IMG, sc.dets(), sc.ball_state(t), selected, "droite", 0.95, True)
        t = round(t + dt, 3)


def test_opp_cursor_on_midfielder_while_ball_at_his_dc(tmp_path):
    an = MatchAnalyzer(RULES, FakeHomography(), tmp_path, coach_cfg=CoachConfig(min_interval_s=0))
    sc = Scene("41212", "4213")
    run(an, sc, 0, 12, {"me": None, "opp": None})            # formations et postes
    # Mon BU (tid 9) reçoit près de son DC ; il a sélectionné son MDC (tid 105)
    bu = sc.pos[9]
    sc.pos[9] = [31.0, -7.0]
    sc.ball = [31.8, -7.0]
    run(an, sc, 12, 15, {"me": 9, "opp": 105})
    assert an.signals["opp_cursor_role"] == "MDC"
    assert an.signals["ball_zone_owner_opp"] == "DC"
    shown = [a.rule_id for a in an.coach.shown]
    assert "curseur_milieu_lache_dc" in shown, (shown, an.coach.occurrence_counts())
    adv = [a for a in an.coach.shown if a.rule_id == "curseur_milieu_lache_dc"][0]
    assert "R2" in adv.text and "fiche 10" in adv.text
    _ = bu


def test_offscreen_is_not_empty():
    from fccoach.analysis.world import World
    w = World(t=0, pitch_ok=True)
    w.view = np.array([[-30, -34], [0, -34], [0, 34], [-30, 34]], float)
    assert w.visible(-10, 0) and not w.visible(20, 0)
