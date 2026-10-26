import cv2

from fccoach.core.config import load_yaml
from fccoach.vision.cursor import CursorSystem, CursorTrack
from tests.synth import draw_cursor, draw_player, pitch

CFG = load_yaml("config/cursor.yaml")
RED = (30, 30, 230)
WHITE = (250, 250, 250)


def scene():
    img = pitch()
    me = draw_player(img, 800, 500, (200, 60, 20), (240, 240, 240))
    opp = draw_player(img, 1200, 520, (240, 240, 240), (30, 30, 30))
    other = draw_player(img, 600, 600, (60, 60, 220), (240, 240, 240))  # maillot rouge, sans curseur
    draw_cursor(img, 800, 492, RED)
    draw_cursor(img, 1200, 512, WHITE)
    return img, [me, opp, other]


def test_detects_both_cursors_and_players():
    img, players = scene()
    sys = CursorSystem(CFG)
    sys.process(img, 0.0, players)
    me, opp = sys.tracks["me"], sys.tracks["opp"]
    assert me.status == "visible" and abs(me.pos[0] - 800) < 5
    assert opp.status == "visible" and abs(opp.pos[0] - 1200) < 5
    assert sys.selected_player("me") is players[0]
    assert sys.selected_player("opp") is players[1]


def test_rejects_red_jersey_and_white_line():
    img, players = scene()
    # Ligne blanche du terrain et maillot rouge : pas des curseurs
    cv2.line(img, (100, 900), (1800, 900), WHITE, 4)
    cands = CursorSystem(CFG).detector.detect(img, players)
    assert len(cands["me"]) == 1
    assert len(cands["opp"]) == 1


def test_needs_player_below_when_detector_present():
    img = pitch()
    draw_cursor(img, 900, 400, RED)
    assert CursorSystem(CFG).detector.detect(img, [])["me"] == []
    # Sans détecteur (players=None) : forme seule
    assert len(CursorSystem(CFG).detector.detect(img, None)["me"]) == 1


def test_upward_triangle_rejected():
    import numpy as np
    img = pitch()
    pts = np.array([[880, 420], [920, 420], [900, 400]], np.int32)  # pointe vers le haut
    cv2.fillPoly(img, [pts], RED)
    assert CursorSystem(CFG).detector.detect(img, None)["me"] == []


def test_interpolation_then_fallback_and_switch_event():
    img, players = scene()
    sys = CursorSystem(CFG)
    ev = sys.process(img, 0.0, players)
    assert [e.side for e in ev] == ["me", "opp"]          # première sélection
    blank = pitch()
    sys.process(blank, 1.0, players)
    assert sys.tracks["me"].status == "interpolé"
    sys.process(blank, 3.5, players)
    assert sys.tracks["me"].status == "repli"
    # Changement de joueur : le curseur rouge saute sur un autre joueur (confirmé sur 2 images)
    img2 = pitch()
    p2 = draw_player(img2, 1500, 300, (200, 60, 20), (240, 240, 240))
    draw_cursor(img2, 1500, 292, RED)
    assert sys.process(img2, 4.0, [p2]) == []
    ev = sys.process(img2, 4.05, [p2])
    assert len(ev) == 1 and ev[0].side == "me" and sys.tracks["me"].changes == 2


def test_reaction_delay():
    t = CursorTrack("opp", switch_confirm_frames=1)
    t.reference_ts = 10.0
    from fccoach.vision.cursor import CursorCandidate
    ev = t.update(CursorCandidate("opp", (100, 100), (100, 90), (90, 80, 20, 20), 1.0), 10.7)
    assert ev is not None and abs(ev.reaction_delay_s - 0.7) < 1e-6
