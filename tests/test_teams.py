from fccoach.core.config import TeamsConfig
from fccoach.vision.kits_db import KitsDB
from fccoach.vision.teams import TeamClassifier
from tests.synth import draw_player, pitch

BLUE, WHITE, BLACK, RED = (200, 60, 20), (240, 240, 240), (30, 30, 30), (40, 40, 210)


def kickoff_scene(me_shirt, me_shorts, opp_shirt, opp_shorts, me_socks=None, opp_socks=None):
    img = pitch()
    players = []
    for i in range(5):
        players.append(draw_player(img, 200 + i * 140, 300 + (i % 3) * 150, me_shirt, me_shorts, me_socks))
        players.append(draw_player(img, 1100 + i * 140, 300 + (i % 3) * 150, opp_shirt, opp_shorts, opp_socks))
    for i, p in enumerate(players):
        p.track_id = i + 1
    return img, players


def test_kickoff_calibration_and_classification():
    img, players = kickoff_scene(BLUE, WHITE, RED, BLACK)
    tc = TeamClassifier(TeamsConfig())
    me_selected = players[0]  # curseur rouge sur un joueur de gauche
    for _ in range(5):
        tc.process(img, players, {"me": me_selected, "opp": None}, clock_s=0)
    assert tc.status.calibrated_by == "coup d'envoi"
    assert tc.status.my_attack_dir == "droite"
    assert all(p.team == ("me" if p.cx < 960 else "opp") for p in players)
    assert tc.status.reliable and not tc.status.clash


def test_cursor_fallback_without_kickoff(tmp_path):
    img, players = kickoff_scene(BLUE, WHITE, RED, BLACK)
    db = KitsDB(tmp_path / "kits.sqlite")
    tc = TeamClassifier(TeamsConfig(), db)
    for _ in range(6):
        tc.process(img, players, {"me": players[2], "opp": players[3]}, clock_s=None)
    assert tc.status.calibrated_by == "curseurs"
    assert sum(p.team == "me" for p in players) == 5
    assert len(db.all()) == 2
    # Match suivant : maillot reconnu dans la base
    tc2 = TeamClassifier(TeamsConfig(), db)
    tc2.process(img, players, {"me": players[0], "opp": None}, clock_s=None)
    assert tc2.status.calibrated_by == "base kits"


def test_clash_mode_uses_shorts_and_lowers_confidence():
    near_red = (50, 45, 200)
    img, players = kickoff_scene(RED, WHITE, near_red, BLACK, WHITE, BLACK)
    tc = TeamClassifier(TeamsConfig())
    for _ in range(10):
        tc.process(img, players, {"me": players[0], "opp": players[1]}, clock_s=0)
    assert tc.status.clash
    assert all(p.team == ("me" if p.cx < 960 else "opp") for p in players)
    assert tc.status.confidence <= 0.85 + 1e-6


def test_half_time_flips_direction():
    img, players = kickoff_scene(BLUE, WHITE, RED, BLACK)
    tc = TeamClassifier(TeamsConfig())
    tc.process(img, players, {"me": players[0], "opp": None}, clock_s=0)
    assert tc.status.my_attack_dir == "droite"
    # Temps additionnel : le chrono dépasse 45:00 sans changer de mi-temps
    tc.process(img, players, {"me": players[0], "opp": None}, clock_s=45 * 60)
    tc.process(img, players, {"me": players[0], "opp": None}, clock_s=46 * 60 + 30)
    assert tc.status.half == 1 and tc.status.my_attack_dir == "droite"
    # 2e mi-temps : les équipes ont changé de côté, recalibration au coup d'envoi
    img2, players2 = kickoff_scene(RED, BLACK, BLUE, WHITE)
    tc.process(img2, players2, {"me": players2[1], "opp": None}, clock_s=45 * 60)
    assert tc.status.half == 2
    assert tc.status.my_attack_dir == "gauche"
    assert players2[1].team == "me" and players2[0].team == "opp"
