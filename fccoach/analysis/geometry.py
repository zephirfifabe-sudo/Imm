"""Petits calculs géométriques sur le terrain (repère normalisé, mètres)."""

from __future__ import annotations

import math

from fccoach.analysis.world import PlayerState


def dist_point_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def lane_free(a: PlayerState, b: PlayerState, opponents: list[PlayerState], width: float = 2.0) -> bool:
    """Ligne de passe a -> b libre : aucun adversaire à moins de `width` m du segment."""
    return all(dist_point_segment(o.x, o.y, a.x, a.y, b.x, b.y) > width for o in opponents)


def nearest(players: list[PlayerState], x: float, y: float) -> tuple[PlayerState | None, float]:
    best, bd = None, math.inf
    for p in players:
        d = p.dist(x, y)
        if d < bd:
            best, bd = p, d
    return best, bd


def closing_speed(chaser: PlayerState, target: PlayerState) -> float:
    """Vitesse de rapprochement du poursuivant vers la cible (m/s, > 0 = il fonce)."""
    d = chaser.dist(target.x, target.y)
    if d < 1e-6:
        return 0.0
    rvx, rvy = chaser.vx - target.vx, chaser.vy - target.vy
    return ((target.x - chaser.x) * rvx + (target.y - chaser.y) * rvy) / d
