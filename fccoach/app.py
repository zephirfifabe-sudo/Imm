"""Orchestration du direct : capture -> vision / curseurs / OCR -> analyse du match -> dashboard.

Threads indépendants, chacun à sa cadence :
  capture   : pleine vitesse (60 i/s), ne bloque jamais
  extraits  : 30 s compressées pour les extraits vidéo du bilan
  vision    : détection YOLO, puis Session (suivi, équipes, terrain 2D, événements,
              formations, adversaire, coach), cadence adaptative 60/30/15/10
  curseurs  : masque couleur + forme, cadence propre (30 Hz par défaut)
  ocr       : chrono / score / noms / écrans, cadences propres
  ui        : FastAPI (thread principal)
"""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

from fccoach.analysis.session import Session
from fccoach.capture.clip_buffer import ClipBuffer
from fccoach.capture.grabber import CaptureThread
from fccoach.capture.ring_buffer import FrameRingBuffer
from fccoach.core.config import Config, load_yaml, resolve_path
from fccoach.core.hardware import AdaptiveCadence, HardwareInfo, choose_model, detect_hardware
from fccoach.core.state import SharedState
from fccoach.ocr.engines import create_engine
from fccoach.ocr.worker import OcrWorker
from fccoach.ocr.zones import load_zones
from fccoach.vision.cursor import SIDE_LABEL, CursorSystem
from fccoach.vision.debug_overlay import draw_debug
from fccoach.vision.detector import YoloOnnxDetector
from fccoach.vision.kits_db import KitsDB
from fccoach.vision.teams import TeamAssignmentSummary, TeamClassifier
from fccoach.vision.types import Detection

log = logging.getLogger(__name__)


def build_detector(cfg: Config, hw: HardwareInfo) -> tuple[YoloOnnxDetector | None, str]:
    """Charge le détecteur ONNX ; None (mode dégradé) si le modèle est absent."""
    model = choose_model(hw, cfg.detector.model, cfg.detector.model_precision, cfg.detector.precision_mode)
    try:
        d = cfg.detector
        return YoloOnnxDetector(resolve_path(model), hw.providers, d.mode, d.tile_size, d.tile_overlap,
                                d.conf_threshold, d.iou_threshold, d.roi), model
    except Exception as exc:
        log.error("Détecteur indisponible : %s", exc)
        log.warning("Mode dégradé : curseurs + OCR seulement (pas d'attribution d'équipes sans boîtes joueurs)")
        return None, model


class Pipeline:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.state = SharedState()
        self.hw: HardwareInfo = detect_hardware(cfg.hardware.accelerator)
        # 1 s d'images brutes pour l'analyse ; les 30 s d'extraits sont compressées à part
        self.buffer = FrameRingBuffer(cfg.capture.raw_buffer_seconds, cfg.capture.fps)
        self.clips = ClipBuffer(self.buffer, cfg.capture.buffer_seconds, cfg.capture.clip_fps)
        self.capture = CaptureThread(cfg.capture, self.buffer)
        self.cursor_cfg = load_yaml(cfg.cursor.config_file)
        self.cursors = CursorSystem(self.cursor_cfg)
        self.kits = KitsDB(resolve_path(cfg.teams.kits_db))
        self.teams = TeamClassifier(cfg.teams, self.kits)
        self.session = Session(cfg, self.cursors, self.teams, "live", clip_request=self.clips.request)
        self.cadence = AdaptiveCadence(cfg.hardware.cadence_steps, cfg.hardware.budget_ratio)
        self._dets: list[Detection] = []
        self._dets_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.calibration_frame: np.ndarray | None = None
        self.detector, model = build_detector(cfg, self.hw)
        zones = load_zones(resolve_path(cfg.ocr.zones_file))
        engine = create_engine(cfg.ocr.engine, self.hw.is_gpu, cfg.ocr.tesseract_cmd)
        self.ocr = OcrWorker(zones, engine, self.buffer, self.state, self.cursors.anchor, self._on_ocr_event)
        self.state.update("system", {
            "accelerator": self.hw.summary(), "providers": self.hw.available,
            "detector": None if self.detector is None else model, "ocr_engine": engine.name,
            "live_coaching": cfg.live_coaching, "phase": 5,
        })

    # ------------------------------------------------------------------
    def start(self) -> None:
        self.capture.start()
        self.clips.start()
        log.info("Attente des premières images…")
        t0 = time.monotonic()
        while self.buffer.latest() is None and not self.capture.ended.is_set():
            if time.monotonic() - t0 > 10:
                log.error("Aucune image reçue en 10 s : vérifie la source vidéo (config.yaml > capture.source)")
                break
            time.sleep(0.05)
        self._calibrate_cadence()
        for target, name in ((self._vision_loop, "vision"), (self._cursor_loop, "curseurs")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        self.ocr.start()

    def stop(self) -> None:
        self._stop.set()
        self.capture.stop()
        self.ocr.stop()
        self.clips.stop()
        for t in self._threads:
            t.join(timeout=2)
        self.session.close()       # bilan de fin si le match n'était pas terminé
        self.kits.close()

    def _calibrate_cadence(self) -> None:
        if self.detector is None:
            self.cadence.current = min(self.cadence.steps)
            return
        frame = self.buffer.latest()
        img = frame.image if frame is not None else np.zeros((1080, 1920, 3), np.uint8)
        lat = self.detector.benchmark(img, self.cfg.hardware.benchmark_frames)
        self.cadence.calibrate(lat)
        self.state.update("system", {"detect_latency_ms": round(lat * 1000, 1)})

    # ------------------------------------------------------------------
    def _vision_loop(self) -> None:
        last_index = -1
        overlay_every = 1.0 / max(1, self.cfg.ui.mjpeg_fps)
        last_overlay = 0.0
        while not self._stop.is_set():
            t_start = time.monotonic()
            frame = self.buffer.wait_newer(last_index, timeout=0.5)
            if frame is None:
                continue
            last_index = frame.index
            dets: list[Detection] = []
            if self.detector is not None:
                t0 = time.perf_counter()
                raw = self.detector.detect(frame.image)
                lat = time.perf_counter() - t0
                self.cadence.update(lat)
                self.session.set_ocr(self.state.get("ocr", {}), self.ocr.overlay_active)
                dets, advice = self.session.step(frame.ts, frame.image, raw)
                if advice is not None:
                    self.state.push_event({"type": "advice", "wall": time.time(), "text": advice.text})
                with self._dets_lock:
                    self._dets = dets
                summary = TeamAssignmentSummary.from_dets(dets)
                self.state.set("teams", {**self.teams.snapshot(), "count_me": summary.me,
                                         "count_opp": summary.opp, "count_unknown": summary.unknown})
                self.state.set("match", self.session.snapshot())
                self.state.update("system", {"detect_fps": self.cadence.current,
                                             "detect_latency_ms": round(lat * 1000, 1),
                                             "analysis_ms": round((time.perf_counter() - t0) * 1000, 1),
                                             "players": summary.me + summary.opp + summary.unknown})
            self.state.update("system", {"capture_fps": round(self.capture.fps_measured, 1),
                                         "buffer_s": round(self.buffer.duration(), 1),
                                         "lag_ms": round((time.monotonic() - frame.ts) * 1000)})
            if self.cfg.ui.debug_overlay and time.monotonic() - last_overlay >= overlay_every:
                self.state.set_overlay(draw_debug(frame.image, dets, self.cursors, self.teams))
                last_overlay = time.monotonic()
            # Cadence : la vision dort, la capture continue à pleine vitesse
            sleep = self.cadence.period - (time.monotonic() - t_start)
            if sleep > 0:
                time.sleep(sleep)

    def _cursor_loop(self) -> None:
        period = 1.0 / float(self.cursor_cfg.get("rate_hz", 30))
        last_index = -1
        while not self._stop.is_set():
            t_start = time.monotonic()
            frame = self.buffer.wait_newer(last_index, timeout=0.5)
            if frame is None:
                continue
            last_index = frame.index
            with self._dets_lock:
                dets = self._dets
            players = [d for d in dets if d.cls in ("player", "goalkeeper")] if self.detector else None
            t0 = time.perf_counter()
            for ev in self.cursors.process(frame.image, frame.ts, players):
                log.info("Changement de joueur sélectionné — %s, zone %s", SIDE_LABEL[ev.side], ev.zone)
                self.state.push_event(ev.as_dict())
                self.session.push_selection(ev)
            self.state.update("cursors", {
                side: t.as_dict() for side, t in self.cursors.tracks.items()
            })
            self.state.update("system", {"cursor_ms": round((time.perf_counter() - t0) * 1000, 1)})
            sleep = period - (time.monotonic() - t_start)
            if sleep > 0:
                time.sleep(sleep)

    def _on_ocr_event(self, ev: dict) -> None:
        # Mi-temps et équipes : traitées par la Session, dans le thread de vision
        if ev["type"] in ("goal", "pause", "halftime", "fulltime", "period_start"):
            self.state.push_event(ev)
            self.session.push_ocr_event(ev)
            if ev["type"] == "goal":
                self.ocr.request("score")

    def calibrate(self, points: list[dict]) -> dict:
        """Calibration du terrain sur l'image figée par le dashboard."""
        frame = self.calibration_frame if self.calibration_frame is not None else self.buffer.latest()
        if frame is None:
            raise ValueError("aucune image reçue de la capture")
        img = frame if isinstance(frame, np.ndarray) else frame.image
        cal = self.session.calibrate(points, img)
        return {"error_m": round(cal.error_m or 0, 2), "points": len(cal.points)}

    def freeze_frame(self) -> np.ndarray | None:
        f = self.buffer.latest()
        self.calibration_frame = None if f is None else f.image.copy()
        return self.calibration_frame
