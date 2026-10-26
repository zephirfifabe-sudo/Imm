"""Validation par cohérence des lectures OCR.

- Le chrono ne recule jamais (et ne saute pas de façon absurde).
- Le score ne monte que de 1 à la fois, d'un seul côté.
- Une valeur incohérente est ignorée : on garde la dernière valeur valide.
- Les noms sont stabilisés par vote sur les dernières lectures.
"""

from __future__ import annotations

import re
import time
from collections import Counter, deque
from dataclasses import dataclass, field

_CLOCK_RE = re.compile(r"(\d{1,3})\s*[:.]\s*(\d{2})")
_SCORE_RE = re.compile(r"(\d{1,2})\s*[-–:]\s*(\d{1,2})")

# Corrections usuelles de l'OCR sur des chiffres
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "|": "1",
                            "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "g": "9"})


def parse_clock(text: str) -> int | None:
    """'45:07' -> 2707 secondes de jeu. None si illisible."""
    m = _CLOCK_RE.search(text.translate(_DIGIT_FIX))
    if not m:
        return None
    mm, ss = int(m.group(1)), int(m.group(2))
    if ss >= 60 or mm > 130:
        return None
    return mm * 60 + ss


def format_clock(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def parse_score(text: str) -> tuple[int, int] | None:
    m = _SCORE_RE.search(text.translate(_DIGIT_FIX))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


@dataclass
class ClockValidator:
    """Chrono de jeu : monotone, avance plausible.

    En EA FC, une mi-temps de 6 min réelles = 45 min de jeu, soit 7,5 s de
    jeu par seconde réelle. On tolère jusqu'à `max_game_per_real` s/s (+ marge).
    """

    max_game_per_real: float = 12.0
    slack_s: float = 20.0
    # Seul « recul » permis : le chrono continue pendant le temps additionnel
    # (45:00 -> 46:30) puis repart de 45:00 au coup d'envoi de la période suivante.
    period_starts: tuple[int, ...] = (45 * 60, 90 * 60, 105 * 60)
    value: int | None = None
    _last_wall: float = 0.0
    rejected: int = 0
    period_started: int | None = None   # dernière reprise de période détectée (s de jeu)

    def feed(self, text: str, now: float | None = None) -> int | None:
        now = time.monotonic() if now is None else now
        sec = parse_clock(text)
        if sec is None:
            return self.value
        if self.value is None:
            self.value, self._last_wall = sec, now
            return sec
        if sec < self.value:
            if sec in self.period_starts and self.value >= sec and sec != self.period_started:
                self.value, self._last_wall, self.period_started = sec, now, sec
                return sec
            self.rejected += 1          # recul : interdit
            return self.value
        elapsed = max(0.0, now - self._last_wall)
        if sec - self.value > elapsed * self.max_game_per_real + self.slack_s:
            self.rejected += 1          # saut absurde : mauvaise lecture
            return self.value
        self.value, self._last_wall = sec, now
        return sec

    def reset(self) -> None:
        self.value = None

    @property
    def text(self) -> str | None:
        return None if self.value is None else format_clock(self.value)


@dataclass
class ScoreValidator:
    """Score : +1 d'un seul côté à la fois, confirmé par `confirm` lectures."""

    confirm: int = 2
    value: tuple[int, int] = (0, 0)
    _pending: tuple[int, int] | None = None
    _pending_count: int = 0
    rejected: int = 0
    initialized: bool = False

    def feed(self, text: str) -> tuple[tuple[int, int], bool]:
        """Retourne (score valide, but_détecté)."""
        sc = parse_score(text)
        if sc is None:
            return self.value, False
        if not self.initialized:
            # Première lecture : on n'accepte qu'un score de début plausible
            if sum(sc) <= 1:
                self.value, self.initialized = sc, True
            else:
                self._pending_or_reject(sc)
                if self._pending_count >= self.confirm + 1:  # reprise en cours de match
                    self.value, self.initialized = sc, True
                    self._pending, self._pending_count = None, 0
            return self.value, False
        if sc == self.value:
            self._pending, self._pending_count = None, 0
            return self.value, False
        dh, da = sc[0] - self.value[0], sc[1] - self.value[1]
        if sorted((dh, da)) != [0, 1]:
            self.rejected += 1
            return self.value, False
        self._pending_or_reject(sc)
        if self._pending_count >= self.confirm:
            self.value = sc
            self._pending, self._pending_count = None, 0
            return self.value, True
        return self.value, False

    def _pending_or_reject(self, sc: tuple[int, int]) -> None:
        if self._pending == sc:
            self._pending_count += 1
        else:
            self._pending, self._pending_count = sc, 1


@dataclass
class TextVoteValidator:
    """Stabilise un texte (nom de joueur, pseudo) par vote majoritaire."""

    window: int = 5
    min_len: int = 2
    min_votes: int = 2
    _hist: deque[str] = field(default_factory=lambda: deque(maxlen=5))

    def __post_init__(self) -> None:
        self._hist = deque(maxlen=self.window)

    def feed(self, text: str) -> str | None:
        clean = re.sub(r"[^\w .'\-À-ÿ]", "", text, flags=re.UNICODE).strip()
        clean = re.sub(r"\s+", " ", clean)
        if len(clean) >= self.min_len:
            self._hist.append(clean.upper())
        return self.value

    @property
    def value(self) -> str | None:
        if not self._hist:
            return None
        txt, n = Counter(self._hist).most_common(1)[0]
        return txt if n >= self.min_votes else None

    def reset(self) -> None:
        self._hist.clear()
