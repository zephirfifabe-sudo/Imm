"""Types partagés par les modules de vision."""

from __future__ import annotations

from dataclasses import dataclass, field

# Classes du détecteur. AUCUNE classe « équipe » : l'équipe est déduite dans teams.py.
CLASSES: tuple[str, ...] = ("player", "goalkeeper", "referee", "ball")


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    cls: str                       # player | goalkeeper | referee | ball
    track_id: int | None = None
    team: str | None = None        # "me" | "opp" | None (déduit par teams.py)
    team_conf: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def w(self) -> float:
        return self.x2 - self.x1

    @property
    def h(self) -> float:
        return self.y2 - self.y1

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def foot(self) -> tuple[float, float]:
        """Point au sol (bas-centre) — utilisé par l'homographie en Phase 2."""
        return (self.cx, self.y2)

    def as_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]
