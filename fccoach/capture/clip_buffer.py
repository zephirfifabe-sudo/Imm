"""Buffer d'extraits vidéo : 30 s compressées (JPEG 960x540) + écriture d'extraits.

Le buffer brut (1080p non compressé) ne garde qu'une seconde : 30 s de 1080p
brut à 60 i/s pèseraient ~11 Go de RAM. Ici, ~50 Mo pour 30 s.
Un extrait demandé [t-avant, t+après] est écrit en WebM dès que la fin est
disponible, dans un thread séparé (jamais dans la capture).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from fccoach.capture.ring_buffer import FrameRingBuffer

log = logging.getLogger(__name__)


@dataclass
class _Request:
    t0: float
    t1: float
    path: Path
    label: str


class ClipBuffer(threading.Thread):
    def __init__(self, raw: FrameRingBuffer, seconds: float = 30.0, fps: float = 15.0,
                 size: tuple[int, int] = (960, 540), quality: int = 75) -> None:
        super().__init__(name="extraits", daemon=True)
        self.raw = raw
        self.fps = fps
        self.size = size
        self.quality = quality
        self._frames: deque[tuple[float, bytes]] = deque(maxlen=int(seconds * fps))
        self._lock = threading.Lock()
        self._requests: list[_Request] = []
        self._stop_evt = threading.Event()

    def request(self, t0: float, t1: float, path: str | Path, label: str = "") -> None:
        with self._lock:
            self._requests.append(_Request(t0, t1, Path(path), label))

    def stop(self) -> None:
        self._stop_evt.set()

    def run(self) -> None:
        last = -1
        period = 1.0 / self.fps
        while not self._stop_evt.is_set():
            t_start = time.monotonic()
            f = self.raw.latest()
            if f is not None and f.index != last:
                last = f.index
                small = cv2.resize(f.image, self.size, interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                if ok:
                    with self._lock:
                        self._frames.append((f.ts, buf.tobytes()))
            self._flush()
            time.sleep(max(0.0, period - (time.monotonic() - t_start)))

    def _flush(self) -> None:
        with self._lock:
            if not self._frames:
                return
            newest = self._frames[-1][0]
            ready = [r for r in self._requests if r.t1 <= newest]
            self._requests = [r for r in self._requests if r.t1 > newest]
            frames = list(self._frames) if ready else []
        for r in ready:
            sel = [b for ts, b in frames if r.t0 <= ts <= r.t1]
            if sel:
                write_clip(sel, r.path, self.fps, self.size)


def write_clip(jpegs: list[bytes], path: Path, fps: float, size: tuple[int, int]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"VP80"), fps, size)
    if not w.isOpened():
        log.warning("Encodeur WebM indisponible : extrait %s non écrit", path.name)
        return False
    for b in jpegs:
        img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            w.write(img)
    w.release()
    return True
