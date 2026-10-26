"""Événements de jeu à partir de la suite des états du monde (repère normalisé).

  possession   porteur = joueur le plus proche du ballon (< 1,8 m) ; équipe en possession
  passe        lâcher du porteur puis contrôle par un coéquipier (début, fin, progression)
  perte / récupération   changement d'équipe en possession
  conduite     le même porteur avance de 5 m ou plus
  tir          ballon rapide vers le but adverse (ou le mien pour l'adversaire)
  corner       ballon arrêté près d'un poteau de corner
  pressing     un adversaire fonce sur mon porteur (vitesse de rapprochement)
Les buts viennent de l'OCR (score), les changements de joueur des curseurs.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fccoach.analysis.world import PlayerState, World
from fccoach.tracking.pitch import HL, HW

OWN_RADIUS = 1.8         # m : distance de contrôle
RELEASE_SPEED = 5.0      # m/s : le ballon part
SHOT_SPEED = 17.0


@dataclass
class GameEvent:
    type: str
    t: float
    team: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "t": round(self.t, 2), "team": self.team, **self.data}


class EventDetector:
    def __init__(self) -> None:
        self.owner: PlayerState | None = None
        self.owner_since = 0.0
        self.possession: str | None = None
        self.possession_since = 0.0
        self._release: dict[str, Any] | None = None     # passe en vol
        self._carry_start: tuple[float, float] | None = None
        self._carry_done = False
        self._corner_since: float | None = None
        self._corner_done_t = -1e9
        self._shot_done_t = -1e9
        self._press: dict[int, float] = {}               # tid adverse -> dernier pressing compté
        self.history: deque[GameEvent] = deque(maxlen=2000)
        # Mémoire utile aux signaux
        self.last_loss: GameEvent | None = None
        self.last_recovery: GameEvent | None = None
        self.last_pass_start: GameEvent | None = None
        self.last_reception: GameEvent | None = None
        self.last_opp_corner_t: float | None = None
        self.passes_without_progress = 0
        self._seq_best_x: float | None = None
        self.counts: dict[str, int] = {}

    def _emit(self, ev: GameEvent, out: list[GameEvent]) -> None:
        self.history.append(ev)
        key = f"{ev.type}:{ev.team}"
        self.counts[key] = self.counts.get(key, 0) + 1
        out.append(ev)

    def update(self, w: World) -> list[GameEvent]:
        out: list[GameEvent] = []
        if not w.pitch_ok or w.ball is None:
            return out
        bx, by = w.ball
        near = min(w.players, key=lambda p: p.dist(bx, by), default=None)
        controlled = near is not None and near.dist(bx, by) <= OWN_RADIUS and w.ball_speed < 14
        if controlled:
            assert near is not None
            self._on_control(near, w, out)
        elif self.owner is not None and w.ball_speed >= RELEASE_SPEED and self.owner.dist(bx, by) > OWN_RADIUS:
            self._on_release(w, out)
        self._shot(w, out)
        self._corner(w, out)
        self._pressing(w, out)
        return out

    # ------------------------------------------------------------------
    def _on_control(self, p: PlayerState, w: World, out: list[GameEvent]) -> None:
        t = w.t
        if self.owner is not None and p.tid == self.owner.tid:
            self.owner = p
            if self._carry_start and not self._carry_done:
                dx = p.x - self._carry_start[0] if p.team == "me" else self._carry_start[0] - p.x
                if dx >= 5:
                    self._carry_done = True
                    self._emit(GameEvent("conduite", t, p.team, {"tid": p.tid, "x": round(p.x, 1)}), out)
            return
        prev = self.owner
        rel = self._release
        if prev is not None and prev.team == p.team and rel is not None and p.tid != prev.tid:
            progress = (p.x - rel["x"]) if p.team == "me" else (rel["x"] - p.x)
            self._emit(GameEvent("passe", t, p.team, {
                "from": prev.tid, "to": p.tid, "t_start": rel["t"], "progress_m": round(progress, 1),
                "length_m": round(math.hypot(p.x - rel["x"], p.y - rel["y"]), 1),
                "start": [round(rel["x"], 1), round(rel["y"], 1)], "end": [round(p.x, 1), round(p.y, 1)]}), out)
            if p.team == "me":
                self._sequence_progress(p.x, counted_pass=True)
        self.last_reception = GameEvent("reception", t, p.team, {"tid": p.tid, "vx": p.vx, "vy": p.vy})
        if self.possession != p.team:
            self._change_possession(p, w, out)
        self.owner, self.owner_since = p, t
        self._release = None
        self._carry_start, self._carry_done = (p.x, p.y), False

    def _change_possession(self, p: PlayerState, w: World, out: list[GameEvent]) -> None:
        t = w.t
        if self.possession is not None:
            zone = "opp_half" if p.x > 0 else "own_half"
            if p.team == "opp":
                ev = GameEvent("perte", t, "me", {"x": round(p.x, 1), "loss_zone": zone})
                self.last_loss = ev
            else:
                ev = GameEvent("recuperation", t, "me", {"x": round(p.x, 1)})
                self.last_recovery = ev
            self._emit(ev, out)
        self.possession, self.possession_since = p.team, t
        self.passes_without_progress = 0
        self._seq_best_x = p.x if p.team == "me" else None

    def _sequence_progress(self, x: float, counted_pass: bool) -> None:
        if self._seq_best_x is None or x >= self._seq_best_x + 5:
            self._seq_best_x = x if self._seq_best_x is None else max(x, self._seq_best_x)
            self.passes_without_progress = 0
        elif counted_pass:
            self.passes_without_progress += 1

    def _on_release(self, w: World, out: list[GameEvent]) -> None:
        if self._release is not None or self.owner is None:
            return
        o = self.owner
        vx, vy = w.ball_v
        fwd = vx if o.team == "me" else -vx     # vers le but adverse de l'équipe du porteur
        self._release = {"t": w.t, "x": o.x, "y": o.y, "team": o.team}
        ev = GameEvent("passe_debut", w.t, o.team, {
            "tid": o.tid, "speed": round(w.ball_speed, 1), "forward": fwd > 3, "backward": fwd < -3,
            "axial": abs(o.y) < 14 and abs(vy) < abs(vx), "long": w.ball_speed > 15 and fwd > 3})
        self.last_pass_start = ev
        self._emit(ev, out)

    def _shot(self, w: World, out: list[GameEvent]) -> None:
        if w.ball_speed < SHOT_SPEED or w.t - self._shot_done_t < 2.0 or self.owner is None:
            return
        bx, by = w.ball  # type: ignore[misc]
        vx, vy = w.ball_v
        team = self.owner.team
        goal_x = HL if team == "me" else -HL
        if (goal_x - bx) * vx <= 0 or abs(goal_x - bx) > 35:
            return
        y_at_goal = by + vy * (goal_x - bx) / vx
        if abs(y_at_goal) < 12:
            self._shot_done_t = w.t
            self._emit(GameEvent("tir", w.t, team, {"x": round(bx, 1), "y": round(by, 1)}), out)

    def _corner(self, w: World, out: list[GameEvent]) -> None:
        bx, by = w.ball  # type: ignore[misc]
        at_corner = abs(abs(bx) - HL) < 2.5 and abs(abs(by) - HW) < 2.5 and w.ball_speed < 1.5
        if not at_corner:
            self._corner_since = None
            return
        if self._corner_since is None:
            self._corner_since = w.t
        elif w.t - self._corner_since > 0.6 and w.t - self._corner_done_t > 10:
            self._corner_done_t = w.t
            team = "me" if bx > 0 else "opp"     # corner près du but adverse = pour moi
            if team == "opp":
                self.last_opp_corner_t = w.t
            self._emit(GameEvent("corner", w.t, team, {"side": "droite" if by > 0 else "gauche"}), out)

    def _pressing(self, w: World, out: list[GameEvent]) -> None:
        o = self.owner
        if o is None or o.team != "me" or self.possession != "me":
            return
        for p in w.team("opp"):
            d = p.dist(o.x, o.y)
            if d > 8 or d < 0.5:
                continue
            closing = ((o.x - p.x) * p.vx + (o.y - p.y) * p.vy) / d
            if closing > 4.0 and w.t - self._press.get(p.tid, -1e9) > 4.0:
                self._press[p.tid] = w.t
                self._emit(GameEvent("pressing", w.t, "opp", {"tid": p.tid, "selected": p.selected == "opp",
                                                               "role": p.role}), out)

    def recent(self, type_: str, team: str | None, since: float) -> list[GameEvent]:
        return [e for e in self.history if e.type == type_ and (team is None or e.team == team) and e.t >= since]

    def reset_half(self) -> None:
        self.owner = None
        self.possession = None
        self._release = None
