"""Suivi des joueurs (style ByteTrack) et de la balle — identités stables.

Joueurs :
  - prédiction à vitesse constante (filtre alpha-bêta sur cx, cy, w, h) ;
  - association en deux temps (affectation hongroise sur 1 - IoU) : d'abord
    les détections sûres, puis les détections faibles pour prolonger les
    tracks existants (joueurs partiellement masqués) ;
  - un track perdu est gardé `max_lost_s` secondes ; s'il réapparaît près de
    sa position prédite, il reprend son identité (re-liaison).
Balle : un seul objet, porte de distance autour de la prédiction, maintien
jusqu'à 0,5 s quand elle est masquée.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fccoach.core.assignment import linear_sum_assignment
from fccoach.tracking.iou_tracker import iou_matrix
from fccoach.vision.types import Detection


@dataclass
class _PTrack:
    tid: int
    state: np.ndarray            # cx, cy, w, h
    vel: np.ndarray = field(default_factory=lambda: np.zeros(4))
    cls: str = "player"
    last_t: float = 0.0
    hits: int = 1
    lost: bool = False

    def predict(self, t: float) -> np.ndarray:
        dt = max(0.0, t - self.last_t)
        return self.state + self.vel * min(dt, 1.0)

    def box(self, t: float) -> np.ndarray:
        cx, cy, w, h = self.predict(t)
        return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])

    def update(self, det: Detection, t: float, alpha: float = 0.7, beta: float = 0.3) -> None:
        z = np.array([det.cx, (det.y1 + det.y2) / 2, det.w, det.h])
        dt = max(1e-3, t - self.last_t)
        pred = self.predict(t)
        resid = z - pred
        self.state = pred + alpha * resid
        self.vel = self.vel + beta * resid / dt
        self.vel[2:] *= 0.5                         # la taille varie peu
        self.last_t = t
        self.hits += 1
        self.lost = False


class PlayerTracker:
    def __init__(self, high: float = 0.5, low: float = 0.15, iou_match: float = 0.25,
                 max_lost_s: float = 1.5, relink_px: float = 80.0) -> None:
        self.high, self.low = high, low
        self.iou_match = iou_match
        self.max_lost_s = max_lost_s
        self.relink_px = relink_px
        self.tracks: list[_PTrack] = []
        self._next = 1

    def _associate(self, tracks: list[_PTrack], dets: list[Detection], t: float) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        if not tracks or not dets:
            return [], list(range(len(tracks))), list(range(len(dets)))
        tb = np.array([tr.box(t) for tr in tracks])
        db = np.array([d.as_list() for d in dets])
        iou = iou_matrix(tb, db)
        rows, cols = linear_sum_assignment(1 - iou)
        pairs = [(r, c) for r, c in zip(rows, cols) if iou[r, c] >= self.iou_match]
        mt = {r for r, _ in pairs}
        md = {c for _, c in pairs}
        return pairs, [i for i in range(len(tracks)) if i not in mt], [j for j in range(len(dets)) if j not in md]

    def update(self, dets: list[Detection], t: float) -> list[Detection]:
        people = [d for d in dets if d.cls != "ball"]
        high = [d for d in people if d.score >= self.high]
        low = [d for d in people if self.low <= d.score < self.high]
        active = [tr for tr in self.tracks if not tr.lost]
        pairs, un_t, un_d = self._associate(active, high, t)
        for r, c in pairs:
            active[r].update(high[c], t)
            high[c].track_id = active[r].tid
        # Deuxième passe : détections faibles pour les tracks restants
        rest = [active[i] for i in un_t]
        pairs2, un_t2, _ = self._associate(rest, low, t)
        for r, c in pairs2:
            rest[r].update(low[c], t)
            low[c].track_id = rest[r].tid
        for i in un_t2:
            rest[i].lost = True
        # Nouvelles détections sûres : re-liaison à un track perdu proche, sinon nouveau track
        lost = [tr for tr in self.tracks if tr.lost]
        for j in un_d:
            d = high[j]
            best, best_d = None, self.relink_px
            for tr in lost:
                cx, cy, _, _ = tr.predict(t)
                dist = float(np.hypot(cx - d.cx, cy - (d.y1 + d.y2) / 2))
                if dist < best_d and tr.cls == d.cls:
                    best, best_d = tr, dist
            if best is not None:
                best.update(d, t)
                lost.remove(best)
                d.track_id = best.tid
            else:
                tr = _PTrack(self._next, np.array([d.cx, (d.y1 + d.y2) / 2, d.w, d.h]), cls=d.cls, last_t=t)
                self._next += 1
                self.tracks.append(tr)
                d.track_id = tr.tid
        self.tracks = [tr for tr in self.tracks if not (tr.lost and t - tr.last_t > self.max_lost_s)]
        # Les détections faibles non associées sont abandonnées (souvent du bruit)
        return [d for d in dets if d.cls == "ball" or d.track_id is not None]

    def reset(self) -> None:
        self.tracks.clear()


@dataclass
class BallState:
    x: float
    y: float
    t: float
    visible: bool
    score: float = 0.0


class BallTracker:
    def __init__(self, gate_px: float = 250.0, hold_s: float = 0.5) -> None:
        self.gate_px = gate_px
        self.hold_s = hold_s
        self.state: BallState | None = None
        self._vel = np.zeros(2)

    def update(self, dets: list[Detection], t: float) -> BallState | None:
        balls = [d for d in dets if d.cls == "ball"]
        pred = None
        if self.state is not None:
            dt = min(1.0, t - self.state.t)
            pred = np.array([self.state.x, self.state.y]) + self._vel * dt
        chosen = None
        if balls:
            if pred is not None and t - self.state.t <= self.hold_s:  # type: ignore[union-attr]
                gate = self.gate_px * max(1.0, (t - self.state.t) / 0.1)  # type: ignore[union-attr]
                cands = [(float(np.hypot(b.cx - pred[0], (b.y1 + b.y2) / 2 - pred[1])), b) for b in balls]
                cands = [c for c in cands if c[0] <= gate]
                if cands:
                    chosen = min(cands, key=lambda c: c[0] - 50 * c[1].score)[1]
            if chosen is None:
                chosen = max(balls, key=lambda b: b.score)
        if chosen is not None:
            pos = np.array([chosen.cx, (chosen.y1 + chosen.y2) / 2])
            if self.state is not None and t > self.state.t:
                v = (pos - np.array([self.state.x, self.state.y])) / (t - self.state.t)
                self._vel = 0.5 * self._vel + 0.5 * v
            self.state = BallState(float(pos[0]), float(pos[1]), t, True, chosen.score)
            return self.state
        if self.state is not None and t - self.state.t <= self.hold_s and pred is not None:
            return BallState(float(pred[0]), float(pred[1]), t, False, 0.0)
        return None
