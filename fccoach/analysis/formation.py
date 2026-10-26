"""Estimation de formation (4312, 41212, 4213…) et attribution des postes.

Gabarits en mètres, équipe attaquant vers +x. Les joueurs visibles (souvent
une partie seulement : la caméra ne montre pas tout le terrain) sont
appariés aux postes du gabarit (affectation hongroise), avec un décalage
du bloc en x et en y. Les scores s'accumulent dans le temps ; la confiance
est la part du meilleur gabarit, pondérée par la couverture. Aucun conseil
de formation sous 70 %.

Photo d'engagement : au coup d'envoi, les deux équipes sont dans leurs
moitiés et presque tous les joueurs sont visibles : la mesure compte double.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np

from fccoach.analysis.world import PlayerState
from fccoach.core.assignment import linear_sum_assignment

# (x, y, rôle) des 10 joueurs de champ, bloc moyen, attaque vers +x
TEMPLATES: dict[str, list[tuple[float, float, str]]] = {
    "4312": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
             (-20, 0, "MDC"), (-14, -15, "MC"), (-14, 15, "MC"), (-4, 0, "MOC"), (6, -7, "BU"), (6, 7, "BU")],
    "41212": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
              (-22, 0, "MDC"), (-13, -20, "MC"), (-13, 20, "MC"), (-4, 0, "MOC"), (6, -7, "BU"), (6, 7, "BU")],
    "4213": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
             (-20, -8, "MDC"), (-20, 8, "MDC"), (-8, 0, "MOC"), (4, -24, "AIL"), (6, 0, "BU"), (4, 24, "AIL")],
    "433": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
            (-16, -14, "MC"), (-19, 0, "MDC"), (-16, 14, "MC"), (4, -24, "AIL"), (6, 0, "BU"), (4, 24, "AIL")],
    "4231": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
             (-20, -8, "MDC"), (-20, 8, "MDC"), (-6, -22, "AIL"), (-6, 0, "MOC"), (-6, 22, "AIL"), (6, 0, "BU")],
    "442": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
            (-16, -24, "AIL"), (-18, -8, "MC"), (-18, 8, "MC"), (-16, 24, "AIL"), (4, -7, "BU"), (4, 7, "BU")],
    "4321": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
             (-18, -14, "MC"), (-20, 0, "MDC"), (-18, 14, "MC"), (-4, -10, "MOC"), (-4, 10, "MOC"), (6, 0, "BU")],
    "352": [(-34, -14, "DC"), (-35, 0, "DC"), (-34, 14, "DC"), (-14, -28, "LAT"), (-20, -8, "MDC"),
            (-20, 8, "MDC"), (-14, 28, "LAT"), (-6, 0, "MOC"), (6, -7, "BU"), (6, 7, "BU")],
    "343": [(-34, -14, "DC"), (-35, 0, "DC"), (-34, 14, "DC"), (-16, -26, "LAT"), (-18, -8, "MC"),
            (-18, 8, "MC"), (-16, 26, "LAT"), (4, -22, "AIL"), (6, 0, "BU"), (4, 22, "AIL")],
    "4141": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"), (-22, 0, "MDC"),
             (-10, -24, "AIL"), (-12, -8, "MC"), (-12, 8, "MC"), (-10, 24, "AIL"), (6, 0, "BU")],
    "4411": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
             (-16, -24, "AIL"), (-18, -8, "MC"), (-18, 8, "MC"), (-16, 24, "AIL"), (-4, 0, "MOC"), (6, 0, "BU")],
    "4222": [(-32, -24, "LAT"), (-34, -8, "DC"), (-34, 8, "DC"), (-32, 24, "LAT"),
             (-20, -8, "MDC"), (-20, 8, "MDC"), (-6, -17, "MOC"), (-6, 17, "MOC"), (6, -7, "BU"), (6, 7, "BU")],
    "3412": [(-34, -14, "DC"), (-35, 0, "DC"), (-34, 14, "DC"), (-16, -26, "LAT"), (-18, -8, "MC"),
             (-18, 8, "MC"), (-16, 26, "LAT"), (-5, 0, "MOC"), (6, -7, "BU"), (6, 7, "BU")],
    "3421": [(-34, -14, "DC"), (-35, 0, "DC"), (-34, 14, "DC"), (-16, -26, "LAT"), (-18, -8, "MC"),
             (-18, 8, "MC"), (-16, 26, "LAT"), (-3, -13, "MOC"), (-3, 13, "MOC"), (6, 0, "BU")],
    "3142": [(-34, -14, "DC"), (-35, 0, "DC"), (-34, 14, "DC"), (-24, 0, "MDC"), (-12, -26, "LAT"),
             (-13, -9, "MC"), (-13, 9, "MC"), (-12, 26, "LAT"), (6, -7, "BU"), (6, 7, "BU")],
    "5212": [(-28, -28, "LAT"), (-35, -14, "DC"), (-36, 0, "DC"), (-35, 14, "DC"), (-28, 28, "LAT"),
             (-19, -10, "MC"), (-19, 10, "MC"), (-6, 0, "MOC"), (6, -7, "BU"), (6, 7, "BU")],
    "523": [(-28, -28, "LAT"), (-35, -14, "DC"), (-36, 0, "DC"), (-35, 14, "DC"), (-28, 28, "LAT"),
            (-18, -10, "MC"), (-18, 10, "MC"), (4, -22, "AIL"), (6, 0, "BU"), (4, 22, "AIL")],
    "541": [(-30, -28, "LAT"), (-35, -14, "DC"), (-36, 0, "DC"), (-35, 14, "DC"), (-30, 28, "LAT"),
            (-16, -24, "AIL"), (-18, -8, "MC"), (-18, 8, "MC"), (-16, 24, "AIL"), (4, 0, "BU")],
    "532": [(-30, -28, "LAT"), (-35, -14, "DC"), (-36, 0, "DC"), (-35, 14, "DC"), (-30, 28, "LAT"),
            (-18, -12, "MC"), (-20, 0, "MDC"), (-18, 12, "MC"), (4, -7, "BU"), (4, 7, "BU")],
}

MIDFIELD = ("MDC", "MC", "MOC")
DEFENDERS = ("DC", "LAT")


@dataclass
class FormationEstimate:
    name: str | None = None
    confidence: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)
    roles: dict[int, str] = field(default_factory=dict)   # tid -> rôle
    offset: tuple[float, float] = (0.0, 0.0)

    def as_dict(self) -> dict:
        top = sorted(self.scores.items(), key=lambda kv: -kv[1])[:3]
        return {"name": self.name, "confidence": round(self.confidence, 3),
                "top": [[k, round(v, 3)] for k, v in top]}


_OFFSETS = np.array([(ox, oy) for ox in np.arange(-20, 21, 2.0) for oy in (-6.0, -3.0, 0.0, 3.0, 6.0)])


def match_template(pos: np.ndarray, template: list[tuple[float, float, str]]) -> tuple[float, list[int], tuple[float, float]]:
    """Coût moyen (m) de l'appariement joueurs visibles -> postes, avec décalage du bloc.

    Recherche du décalage en deux temps : coût approché vectorisé (plus proche
    poste) sur toute la grille, puis affectation hongroise sur les meilleurs candidats.
    """
    tpl = np.array([(x, y) for x, y, _ in template])
    shifted = tpl[None, :, :] + _OFFSETS[:, None, :]                       # (O, 10, 2)
    d = np.linalg.norm(pos[None, :, None, :] - shifted[:, None, :, :], axis=3)   # (O, k, 10)
    approx = d.min(axis=2).mean(axis=1)
    best = (math.inf, [], (0.0, 0.0))
    for oi in np.argsort(approx)[:4]:
        r, c = linear_sum_assignment(d[oi])
        cost = float(d[oi][r, c].mean())
        if cost < best[0]:
            best = (cost, list(c), (float(_OFFSETS[oi, 0]), float(_OFFSETS[oi, 1])))
    return best


class FormationTracker:
    """Une instance par équipe. Les positions sont données dans le repère où
    l'équipe attaque vers +x (l'adversaire est donc retourné avant l'appel)."""

    def __init__(self, min_players: int = 7, temperature: float = 1.5, memory: int = 120,
                 max_fit_m: float = 6.0) -> None:
        self.min_players = min_players
        self.max_fit_m = max_fit_m
        self.temperature = temperature
        self._evidence: deque[dict[str, float]] = deque(maxlen=memory)
        self._role_votes: dict[int, deque[str]] = defaultdict(lambda: deque(maxlen=20))
        self.estimate = FormationEstimate()

    def observe(self, players: list[PlayerState], kickoff: bool = False) -> FormationEstimate:
        if len(players) < self.min_players:
            return self._finish()
        pos = np.array([(p.x, p.y) for p in players])
        costs, assign = {}, {}
        for name, tpl in TEMPLATES.items():
            cost, cols, off = match_template(pos, tpl)
            costs[name] = cost
            assign[name] = (cols, off)
        cmin = min(costs.values())
        if cmin > self.max_fit_m:
            return self._finish()     # joueurs en transition : pas de forme lisible
        # Log-vraisemblance relative de chaque gabarit, pondérée par la couverture
        coverage = min(1.0, len(players) / 10)
        obs = {k: -coverage * (v - cmin) / self.temperature for k, v in costs.items()}
        for _ in range(2 if kickoff else 1):
            self._evidence.append(obs)
        best = min(costs, key=costs.__getitem__)
        cols, off = assign[best]
        for p, c in zip(players, cols):
            self._role_votes[p.tid].append(TEMPLATES[best][c][2])
        self.estimate.offset = off
        return self._finish()

    def _finish(self) -> FormationEstimate:
        if not self._evidence:
            return self.estimate
        agg: dict[str, float] = defaultdict(float)
        for e in self._evidence:
            for k, v in e.items():
                agg[k] += v
        # Postérieur : les mesures s'accumulent (produit des vraisemblances)
        top = max(agg.values())
        expo = {k: math.exp(v - top) for k, v in agg.items()}
        z = sum(expo.values())
        scores = {k: v / z for k, v in expo.items()}
        name = max(scores, key=scores.__getitem__)
        # Confiance freinée tant qu'il y a peu de mesures
        maturity = min(1.0, len(self._evidence) / 10)
        self.estimate.name = name
        self.estimate.scores = scores
        self.estimate.confidence = scores[name] * maturity
        self.estimate.roles = {tid: max(set(v), key=list(v).count) for tid, v in self._role_votes.items() if v}
        return self.estimate

    def role_of(self, tid: int) -> str | None:
        return self.estimate.roles.get(tid)

    def slot_positions(self) -> list[tuple[float, float, str]]:
        """Positions des postes du gabarit retenu, décalage du bloc compris."""
        if self.estimate.name is None:
            return []
        ox, oy = self.estimate.offset
        return [(x + ox, y + oy, r) for x, y, r in TEMPLATES[self.estimate.name]]

    def reset(self) -> None:
        self._evidence.clear()
        self._role_votes.clear()
        self.estimate = FormationEstimate()
