"""Buffer circulaire de frames horodatées (30 s par défaut).

Écriture par le seul thread de capture, lectures concurrentes par les
analyses. Les lecteurs ne bloquent jamais l'écrivain plus que le temps
d'une copie de référence (pas de copie d'image sous le verrou).
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Frame:
    index: int          # numéro de frame depuis le démarrage
    ts: float           # horloge monotone (s) — pour les délais / la latence
    wall: float         # horodatage réel (epoch) — pour les extraits et la base
    image: np.ndarray   # BGR, 1080p natif

    @property
    def shape(self) -> tuple[int, ...]:
        return self.image.shape


class FrameRingBuffer:
    def __init__(self, seconds: float, fps: float) -> None:
        self.capacity = max(1, int(round(seconds * fps)))
        self._frames: deque[Frame] = deque(maxlen=self.capacity)
        self._lock = threading.Lock()
        self._new = threading.Condition(self._lock)

    def push(self, frame: Frame) -> None:
        with self._new:
            self._frames.append(frame)
            self._new.notify_all()

    def latest(self) -> Frame | None:
        with self._lock:
            return self._frames[-1] if self._frames else None

    def wait_newer(self, index: int, timeout: float = 1.0) -> Frame | None:
        """Attend une frame d'index > index (utile aux consommateurs)."""
        with self._new:
            if not self._frames or self._frames[-1].index <= index:
                self._new.wait(timeout)
            if self._frames and self._frames[-1].index > index:
                return self._frames[-1]
            return None

    def range(self, t0: float, t1: float) -> list[Frame]:
        """Frames dont le timestamp monotone est dans [t0, t1] (extraits vidéo)."""
        with self._lock:
            return [f for f in self._frames if t0 <= f.ts <= t1]

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)

    def duration(self) -> float:
        with self._lock:
            if len(self._frames) < 2:
                return 0.0
            return self._frames[-1].ts - self._frames[0].ts
