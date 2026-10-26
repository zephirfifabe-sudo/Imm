"""État du monde à un instant : joueurs et balle en mètres, repère normalisé.

Repère normalisé : MON équipe attaque vers +x (but adverse en x = +52,5),
y de -34 à +34. Construit à chaque pas d'analyse à partir des détections
(équipes + tracks), de l'homographie et des curseurs.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from fccoach.tracking.homography import HomographyTracker
from fccoach.tracking.pitch import inside
from fccoach.tracking.tracker import BallState
from fccoach.vision.types import Detection


@dataclass
class PlayerState:
    tid: int
    team: str                 # me | opp
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    role: str | None = None   # DC, LAT, MDC, MC, MOC, AIL, BU (formation)
    selected: str | None = None   # me | opp : sous un curseur
    conf: float = 0.0

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def dist(self, x: float, y: float) -> float:
        return math.hypot(self.x - x, self.y - y)


@dataclass
class World:
    t: float
    players: list[PlayerState] = field(default_factory=list)
    ball: tuple[float, float] | None = None
    ball_v: tuple[float, float] = (0.0, 0.0)
    ball_visible: bool = False
    pitch_ok: bool = False
    attack_known: bool = False
    team_conf: float = 0.0
    team_reliable: bool = False
    view: np.ndarray | None = None      # zone du terrain visible à l'image (polygone, repère normalisé)

    def visible(self, x: float, y: float, margin: float = 0.0) -> bool:
        """Le point est-il dans le champ de la caméra ? (absence ≠ hors champ)"""
        if self.view is None:
            return False
        return cv2.pointPolygonTest(self.view.astype(np.float32), (float(x), float(y)), True) >= margin

    def team(self, team: str) -> list[PlayerState]:
        return [p for p in self.players if p.team == team]

    def selected(self, side: str) -> PlayerState | None:
        for p in self.players:
            if p.selected == side:
                return p
        return None

    def by_tid(self, tid: int) -> PlayerState | None:
        for p in self.players:
            if p.tid == tid:
                return p
        return None

    @property
    def ball_speed(self) -> float:
        return math.hypot(*self.ball_v)


class AttackDirection:
    """Sens d'attaque : donné par la calibration au coup d'envoi, sinon déduit.

    Déduction : sur la durée, le bloc de mon équipe est en moyenne plus près
    de mon propre but que celui de l'adversaire.
    """

    def __init__(self, window: int = 300) -> None:
        self._diff: deque[float] = deque(maxlen=window)

    def feed(self, my_mean_x: float, opp_mean_x: float) -> None:
        self._diff.append(my_mean_x - opp_mean_x)

    def infer(self) -> bool | None:
        if len(self._diff) < 60:
            return None
        m = float(np.mean(self._diff))
        if abs(m) < 2.0:
            return None
        return m < 0   # mon bloc plus à gauche -> je défends à gauche -> j'attaque à droite

    def reset(self) -> None:
        self._diff.clear()


class WorldBuilder:
    def __init__(self) -> None:
        self._prev: dict[int, tuple[float, float, float]] = {}   # tid -> (t, x, y)
        self._vel: dict[int, tuple[float, float]] = {}
        self._ball_prev: tuple[float, float, float] | None = None
        self._ball_v = (0.0, 0.0)
        self.direction = AttackDirection()

    def build(self, t: float, dets: list[Detection], homo: HomographyTracker, ball: BallState | None,
              selected_tids: dict[str, int | None], my_attack_dir: str | None, team_conf: float,
              team_reliable: bool) -> World:
        w = World(t=t, pitch_ok=homo.ok, team_conf=team_conf, team_reliable=team_reliable)
        if not homo.ok:
            return w
        players = [d for d in dets if d.cls == "player" and d.team in ("me", "opp") and d.track_id is not None]
        if players:
            pts = homo.to_pitch(np.array([d.foot for d in players]))
        else:
            pts = np.zeros((0, 2))
        raw = [(d, float(p[0]), float(p[1])) for d, p in zip(players, pts) if inside(p[0], p[1])]
        # Sens d'attaque
        if my_attack_dir in ("droite", "gauche"):
            right = my_attack_dir == "droite"
            w.attack_known = True
        else:
            me_x = [x for d, x, _ in raw if d.team == "me"]
            op_x = [x for d, x, _ in raw if d.team == "opp"]
            if len(me_x) >= 3 and len(op_x) >= 3:
                self.direction.feed(float(np.mean(me_x)), float(np.mean(op_x)))
            inferred = self.direction.infer()
            right = True if inferred is None else inferred
            w.attack_known = inferred is not None
        sgn = 1.0 if right else -1.0
        corners = homo.to_pitch(np.array([[0, 160], [1920, 160], [1920, 1080], [0, 1080]], float))
        if corners is not None and np.all(np.isfinite(corners)):
            w.view = sgn * corners
        sel = {tid: side for side, tid in selected_tids.items() if tid is not None}
        for d, x, y in raw:
            x, y = sgn * x, sgn * y
            vx, vy = self._velocity(d.track_id, t, x, y)  # type: ignore[arg-type]
            w.players.append(PlayerState(d.track_id, d.team, x, y, vx, vy, selected=sel.get(d.track_id),  # type: ignore[arg-type]
                                         conf=d.team_conf))
        if ball is not None:
            bp = homo.to_pitch(np.array([[ball.x, ball.y]]))
            if bp is not None and inside(bp[0, 0], bp[0, 1], 5):
                bx, by = sgn * float(bp[0, 0]), sgn * float(bp[0, 1])
                if self._ball_prev is not None and t > self._ball_prev[0]:
                    dt = t - self._ball_prev[0]
                    v = ((bx - self._ball_prev[1]) / dt, (by - self._ball_prev[2]) / dt)
                    self._ball_v = (0.5 * self._ball_v[0] + 0.5 * v[0], 0.5 * self._ball_v[1] + 0.5 * v[1])
                self._ball_prev = (t, bx, by)
                w.ball, w.ball_v, w.ball_visible = (bx, by), self._ball_v, ball.visible
        return w

    def _velocity(self, tid: int, t: float, x: float, y: float) -> tuple[float, float]:
        prev = self._prev.get(tid)
        self._prev[tid] = (t, x, y)
        if prev is None or t <= prev[0] or t - prev[0] > 1.0:
            self._vel[tid] = (0.0, 0.0)
            return 0.0, 0.0
        dt = t - prev[0]
        v = ((x - prev[1]) / dt, (y - prev[2]) / dt)
        old = self._vel.get(tid, v)
        nv = (0.6 * old[0] + 0.4 * v[0], 0.6 * old[1] + 0.4 * v[1])
        self._vel[tid] = nv
        if len(self._prev) > 400:
            for k in [k for k, p in self._prev.items() if t - p[0] > 5]:
                self._prev.pop(k, None)
                self._vel.pop(k, None)
        return nv

    def new_half(self) -> None:
        self.direction.reset()
        self._prev.clear()
        self._vel.clear()
