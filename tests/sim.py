"""Simulation de match en coordonnées terrain (sans vision) pour tester les Phases 2 à 5."""

from __future__ import annotations

import numpy as np

from fccoach.analysis.formation import TEMPLATES
from fccoach.tracking.tracker import BallState
from fccoach.vision.types import Detection

SCALE = 10.0


def to_px(x: float, y: float) -> tuple[float, float]:
    return (x + 52.5) * SCALE, (y + 34) * SCALE


class FakeHomography:
    """Image = vue de dessus à 10 px/m : px = (x + 52,5) * 10."""

    def __init__(self) -> None:
        self.status = "ok"
        self.calibration = object()
        self.H = np.eye(3)

    ok = True

    def update(self, image, now=None):
        return self.status

    def to_pitch(self, pts):
        return np.asarray(pts, float) / SCALE - [52.5, 34]


class Scene:
    """Moi en `me_form` (j'attaque vers +x), adversaire en `opp_form` (attaque vers -x)."""

    def __init__(self, me_form: str = "41212", opp_form: str = "4213", shift: float = 0.0) -> None:
        self.pos: dict[int, list[float]] = {}
        self.team: dict[int, str] = {}
        for i, (x, y, _) in enumerate(TEMPLATES[me_form]):
            self.pos[i + 1] = [x + shift, y]
            self.team[i + 1] = "me"
        for i, (x, y, _) in enumerate(TEMPLATES[opp_form]):
            self.pos[i + 101] = [-(x - shift), -y]
            self.team[i + 101] = "opp"
        self.ball = list(self.pos[5])

    def dets(self, rng=None) -> list[Detection]:
        out = []
        for tid, (x, y) in self.pos.items():
            if rng is not None:
                x, y = x + rng.normal(0, 0.3), y + rng.normal(0, 0.3)
            px, py = to_px(x, y)
            d = Detection(px - 5, py - 30, px + 5, py, 0.9, "player", track_id=tid, team=self.team[tid], team_conf=0.95)
            out.append(d)
        return out

    def ball_state(self, t: float) -> BallState:
        px, py = to_px(*self.ball)
        return BallState(px, py, t, True, 0.9)

    def move_ball_towards(self, x: float, y: float, step: float) -> bool:
        bx, by = self.ball
        d = float(np.hypot(x - bx, y - by))
        if d <= step:
            self.ball = [x, y]
            return True
        self.ball = [bx + (x - bx) * step / d, by + (y - by) * step / d]
        return False
