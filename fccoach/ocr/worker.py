"""Thread OCR : chaque zone a sa propre cadence, sans jamais bloquer capture ni détection.

Cadences (config/ocr_zones.json) :
  - chrono           : 1 à 2 lectures/s
  - score            : 1 lecture/s + lecture forcée à chaque but détecté (request("score"))
  - nom sélectionné  : 2 à 5 lectures/s, zone relative au curseur
  - pause / écrans   : à la demande, quand l'image s'assombrit (overlay)

Les éléments rapides (curseurs, joueurs, balle) ne passent JAMAIS par l'OCR.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from typing import Callable

from fccoach.capture.ring_buffer import FrameRingBuffer
from fccoach.core.state import SharedState
from fccoach.ocr.engines import OcrEngine
from fccoach.ocr.validators import ClockValidator, ScoreValidator, TextVoteValidator
from fccoach.ocr.zones import OcrZone, dark_overlay_score, preprocess

log = logging.getLogger(__name__)

AnchorFn = Callable[[str], "tuple[float, float] | None"]
EventFn = Callable[[dict], None]

_PAUSE_RE = re.compile(r"(?:pause\s+demand[ée]e\s+par|paused\s+by)\s*[:\-]?\s*(.+)", re.IGNORECASE)
_SCREEN_KEYWORDS = {
    "halftime": ("MI-TEMPS", "MI TEMPS", "HALF TIME", "HALF-TIME"),
    "fulltime": ("FIN DU MATCH", "TEMPS RÉGLEMENTAIRE", "FULL TIME", "FULL-TIME"),
}


class OcrWorker(threading.Thread):
    def __init__(self, zones: dict[str, OcrZone], engine: OcrEngine, buffer: FrameRingBuffer,
                 state: SharedState, anchor_fn: AnchorFn | None = None,
                 on_event: EventFn | None = None) -> None:
        super().__init__(name="ocr", daemon=True)
        self.zones = zones
        self.engine = engine
        self.buffer = buffer
        self.state = state
        self.anchor_fn = anchor_fn or (lambda side: None)
        self.on_event = on_event or (lambda e: None)
        self._stop_evt = threading.Event()
        self._requests: set[str] = set()
        self._req_lock = threading.Lock()
        self._next_due: dict[str, float] = {n: 0.0 for n in zones}
        self.clock = ClockValidator()
        self.score = ScoreValidator()
        self.names: dict[str, TextVoteValidator] = {n: TextVoteValidator() for n, z in zones.items() if z.kind == "name"}
        self.opponent_pseudo: str | None = None
        self._lum_hist: deque[float] = deque(maxlen=60)
        self._overlay_active = False
        self._overlay_reads = 0
        self._last_lum_check = 0.0
        self.read_ms: dict[str, float] = {}
        self._now: float | None = None

    # --- API publique -----------------------------------------------------
    def request(self, zone: str) -> None:
        """Demande une lecture immédiate (ex. score à chaque but détecté)."""
        with self._req_lock:
            self._requests.add(zone)

    def stop(self) -> None:
        self._stop_evt.set()

    # --- boucle -----------------------------------------------------------
    def run(self) -> None:
        if self.engine.name == "aucun":
            log.warning("OCR désactivé (aucun moteur)")
        while not self._stop_evt.is_set():
            frame = self.buffer.latest()
            if frame is None:
                time.sleep(0.05)
                continue
            self.step(frame.image, time.monotonic())
            time.sleep(0.02)

    def step(self, image, now: float) -> None:
        """Lit les zones dues à l'instant `now` (horloge monotone en direct,
        temps de la vidéo pour un clip analysé hors ligne)."""
        self._now = now
        if now - self._last_lum_check >= 0.5:
            self._check_overlay(image)
            self._last_lum_check = now
        with self._req_lock:
            requested, self._requests = self._requests, set()
        for name, zone in self.zones.items():
            due = name in requested
            if zone.mode in ("periodic", "relative"):
                due = due or now >= self._next_due[name]
            elif zone.mode == "on_demand":
                due = due or (self._overlay_active and self._overlay_reads < 3 and now >= self._next_due[name])
            if not due:
                continue
            self._next_due[name] = now + 1.0 / max(zone.rate_hz, 0.1)
            self._read_zone(zone, image)
        if self._overlay_active:
            self._overlay_reads += 1

    def _check_overlay(self, image) -> None:
        lum = dark_overlay_score(image)
        baseline = sorted(self._lum_hist)[len(self._lum_hist) // 2] if len(self._lum_hist) >= 10 else None
        active = baseline is not None and lum < 0.6 * baseline
        if active and not self._overlay_active:
            self._overlay_reads = 0
            log.info("Écran assombri détecté (pause / mi-temps ?) : lecture OCR à la demande")
        self._overlay_active = active
        if not active:
            self._lum_hist.append(lum)

    def _read_zone(self, zone: OcrZone, image) -> None:
        anchor = None
        if zone.mode == "relative":
            anchor = self.anchor_fn(zone.relative_to or "")
            if anchor is None:
                return
        crop = zone.crop(image, anchor)
        if crop is None:
            return
        t0 = time.perf_counter()
        try:
            text = self.engine.read(preprocess(crop, zone.preprocess), zone.whitelist)
        except Exception as exc:  # un moteur OCR qui plante ne doit rien bloquer
            log.debug("OCR %s : %s", zone.name, exc)
            return
        self.read_ms[zone.name] = (time.perf_counter() - t0) * 1000
        self._handle_text(zone, text)

    def _handle_text(self, zone: OcrZone, text: str) -> None:
        if zone.kind == "clock":
            before, period_before = self.clock.value, self.clock.period_started
            self.clock.feed(text, self._now)
            if self.clock.period_started != period_before:
                log.info("Reprise de période détectée au chrono (%s)", self.clock.text)
                self.on_event({"type": "period_start", "clock_s": self.clock.value, "ts": time.time()})
            self.state.update("ocr", {"clock": self.clock.text, "clock_s": self.clock.value,
                                      "clock_rejected": self.clock.rejected})
            if self.clock.value is not None and before != self.clock.value:
                self.on_event({"type": "clock", "value": self.clock.value, "text": self.clock.text})
        elif zone.kind == "score":
            value, goal = self.score.feed(text)
            if self.score.initialized:  # pas de « 0-0 » affiché tant que rien n'a été lu
                self.state.update("ocr", {"score": list(value), "score_rejected": self.score.rejected})
            if goal:
                log.info("But détecté par l'OCR : score %d-%d", *value)
                self.on_event({"type": "goal", "score": list(value), "ts": time.time()})
        elif zone.kind == "name":
            val = self.names[zone.name].feed(text)
            self.state.update("ocr", {zone.name: val})
        elif zone.kind == "pause":
            m = _PAUSE_RE.search(text)
            if m:
                pseudo = m.group(1).strip()[:32]
                if pseudo and pseudo != self.opponent_pseudo:
                    self.opponent_pseudo = pseudo
                    log.info("Pseudo lu sur l'overlay de pause : %s", pseudo)
                    self.state.update("ocr", {"pause_by": pseudo})
                    self.on_event({"type": "pause", "by": pseudo, "ts": time.time()})
        elif zone.kind == "screen_title":
            up = text.upper()
            for screen, keys in _SCREEN_KEYWORDS.items():
                if any(k in up for k in keys):
                    self.state.update("ocr", {"screen": screen})
                    self.on_event({"type": screen, "ts": time.time()})
                    break
