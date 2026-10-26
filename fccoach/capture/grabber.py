"""Thread de capture : lit la source en continu et remplit le buffer circulaire.

La capture ne ralentit JAMAIS : elle n'attend aucun consommateur. Les
analyses lisent la frame la plus récente ; si elles sont lentes, elles
sautent simplement des images.
"""

from __future__ import annotations

import logging
import threading
import time

import cv2
import numpy as np

from fccoach.capture.ring_buffer import Frame, FrameRingBuffer
from fccoach.capture.source import open_source
from fccoach.core.config import CaptureConfig

log = logging.getLogger(__name__)


class CaptureThread(threading.Thread):
    def __init__(self, cfg: CaptureConfig, buffer: FrameRingBuffer) -> None:
        super().__init__(name="capture", daemon=True)
        self.cfg = cfg
        self.buffer = buffer
        self._stop_evt = threading.Event()
        self.fps_measured = 0.0
        self.frames_total = 0
        self.read_failures = 0
        self.ended = threading.Event()   # fin de fichier
        self.error: str | None = None

    def stop(self) -> None:
        self._stop_evt.set()

    def run(self) -> None:
        try:
            cap, is_file = open_source(self.cfg.source, self.cfg.backend, self.cfg.width,
                                       self.cfg.height, self.cfg.fps, self.cfg.fourcc)
        except Exception as exc:
            self.error = str(exc)
            log.error("Capture : %s", exc)
            self.ended.set()
            return
        file_fps = cap.get(cv2.CAP_PROP_FPS) or self.cfg.fps
        frame_period = 1.0 / file_fps if is_file and self.cfg.realtime_file_playback else 0.0
        t_last_stat = time.monotonic()
        n_stat = 0
        next_due = time.monotonic()
        try:
            while not self._stop_evt.is_set():
                ok, img = cap.read()
                now = time.monotonic()
                if not ok or img is None:
                    if is_file:
                        log.info("Fin de la vidéo")
                        break
                    self.read_failures += 1
                    if self.read_failures % 60 == 1:
                        log.warning("Capture : lecture impossible (%d échecs) — câble/OBS ?", self.read_failures)
                    time.sleep(0.01)
                    continue
                img = np.ascontiguousarray(img)
                self.buffer.push(Frame(self.frames_total, now, time.time(), img))
                self.frames_total += 1
                n_stat += 1
                if now - t_last_stat >= 1.0:
                    self.fps_measured = n_stat / (now - t_last_stat)
                    t_last_stat, n_stat = now, 0
                if frame_period:
                    # Rejouer un fichier à vitesse réelle (sinon il défile trop vite)
                    next_due += frame_period
                    delay = next_due - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    else:
                        next_due = time.monotonic()
        finally:
            cap.release()
            self.ended.set()
