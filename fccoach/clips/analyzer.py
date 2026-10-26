"""Analyse hors ligne d'un clip vidéo téléchargé (PS5, réseaux sociaux, enregistrement OBS…).

Même chaîne que le direct (détection, suivi, équipes, curseurs, OCR), mais
pilotée par le TEMPS DE LA VIDÉO et non par l'horloge : le clip est lu aussi
vite que la machine le permet, sans jamais sauter une analyse prévue.

Sorties dans data/clips/<id>/ :
  report.json    résumé + événements horodatés (temps du clip)
  annotated.webm vidéo avec l'overlay debug (optionnel, lisible dans le navigateur)
  events/*.jpg   image clé de chaque événement (changement de joueur, but, pause…)
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from fccoach.analysis.session import Session
from fccoach.capture.clip_buffer import write_clip
from fccoach.core.config import Config, resolve_path
from fccoach.core.state import SharedState
from fccoach.ocr.engines import OcrEngine
from fccoach.ocr.worker import OcrWorker
from fccoach.ocr.zones import load_zones
from fccoach.vision.cursor import SIDE_LABEL, CursorSystem
from fccoach.vision.debug_overlay import draw_debug
from fccoach.vision.detector import YoloOnnxDetector
from fccoach.vision.kits_db import KitsDB
from fccoach.vision.teams import TeamAssignmentSummary, TeamClassifier
from fccoach.vision.types import Detection

log = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts"}
TARGET = (1920, 1080)

ProgressFn = Callable[[float], None]


def fmt_t(t: float) -> str:
    """Temps du clip lisible : 83.4 -> '01:23.4'."""
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def to_1080p(img: np.ndarray) -> np.ndarray:
    """Ramène l'image au 1080p 16:9 attendu (zones OCR, seuils curseurs).

    Clip en 720p : agrandi (jamais réduit si déjà 1080p). Format non 16:9
    (vertical, recadré) : bandes noires pour garder les proportions.
    """
    h, w = img.shape[:2]
    if (w, h) == TARGET:
        return img
    target_ratio = TARGET[0] / TARGET[1]
    if abs(w / h - target_ratio) > 0.02:
        if w / h < target_ratio:
            pad = int(round(h * target_ratio)) - w
            img = cv2.copyMakeBorder(img, 0, 0, pad // 2, pad - pad // 2, cv2.BORDER_CONSTANT)
        else:
            pad = int(round(w / target_ratio)) - h
            img = cv2.copyMakeBorder(img, pad // 2, pad - pad // 2, 0, 0, cv2.BORDER_CONSTANT)
    interp = cv2.INTER_CUBIC if img.shape[1] < TARGET[0] else cv2.INTER_AREA
    return cv2.resize(img, TARGET, interpolation=interp)


def probe(path: str | Path) -> dict[str, Any]:
    """Infos de base du clip ; lève ValueError si illisible."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("vidéo illisible (format ou codec non supporté)")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok, _ = cap.read()
    cap.release()
    if not ok:
        raise ValueError("aucune image lisible dans la vidéo")
    fps = fps if 1 <= fps <= 240 else 30.0
    return {"fps": round(fps, 2), "frames": n, "width": w, "height": h,
            "duration_s": round(n / fps, 2) if n else None}


def extract_segment(src: str | Path, t0: float, t1: float, dest: Path, fps: float,
                    size: tuple[int, int] = (960, 540)) -> bool:
    """Extrait [t0, t1] du clip source (« ce que j'aurais dû faire »)."""
    cap = cv2.VideoCapture(str(src))
    cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000)
    frames = []
    while True:
        ok, img = cap.read()
        if not ok or cap.get(cv2.CAP_PROP_POS_MSEC) / 1000 > t1 + 1 / fps:
            break
        ok, buf = cv2.imencode(".jpg", cv2.resize(img, size, interpolation=cv2.INTER_AREA))
        if ok:
            frames.append(buf.tobytes())
    cap.release()
    return bool(frames) and write_clip(frames, dest, fps, size)


class ClipAnalyzer:
    """Analyse un clip complet. Une instance par clip (états neufs)."""

    def __init__(self, cfg: Config, detector: YoloOnnxDetector | None, ocr_engine: OcrEngine,
                 cursor_cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.detector = detector
        self.cursor_cfg = cursor_cfg
        self.state = SharedState()
        self.cursors = CursorSystem(cursor_cfg)
        self.session: Session | None = None
        self._segments: list[tuple[float, float, Path]] = []
        self.kits = KitsDB(resolve_path(cfg.teams.kits_db))
        self.teams = TeamClassifier(cfg.teams, self.kits)
        self.events: list[dict[str, Any]] = []
        self._t = 0.0
        self._events_dir = Path(".")
        zones = load_zones(resolve_path(cfg.ocr.zones_file))
        # Le worker OCR n'est pas démarré en thread : on appelle step() au temps du clip
        self.ocr = OcrWorker(zones, ocr_engine, buffer=None, state=self.state,  # type: ignore[arg-type]
                             anchor_fn=self.cursors.anchor, on_event=self._on_ocr_event)
        self.ocr_engine_name = ocr_engine.name

    # ------------------------------------------------------------------
    def analyze(self, path: str | Path, out_dir: str | Path, progress: ProgressFn | None = None,
                should_stop: Callable[[], bool] | None = None) -> dict[str, Any]:
        out_dir = Path(out_dir)
        # Analyse du jeu (terrain 2D, événements, coach) : pas d'écriture dans l'historique des matchs
        self.session = Session(self.cfg, self.cursors, self.teams, "clip", out_root=out_dir, use_db=False,
                               clip_request=lambda t0, t1, p: self._segments.append((t0, t1, p)))
        self._events_dir = out_dir / "events"
        self._events_dir.mkdir(parents=True, exist_ok=True)
        info = probe(path)
        fps = info["fps"]
        total = info["frames"] or 0
        warnings = self._warnings(info)
        cap = cv2.VideoCapture(str(path))
        ccfg = self.cfg.clips
        det_period = 1.0 / max(0.5, min(ccfg.analysis_fps, fps))
        cur_period = 1.0 / max(1.0, min(float(self.cursor_cfg.get("rate_hz", 30)), fps))
        writer = self._open_writer(out_dir, fps) if ccfg.annotated_video else None
        next_det = next_cur = 0.0
        dets: list[Detection] = []
        timeline: list[dict[str, Any]] = []
        next_sample = 0.0
        idx = 0
        n_det = 0
        t_start = time.perf_counter()
        try:
            while True:
                if should_stop and should_stop():
                    warnings.append("analyse interrompue")
                    break
                ok, raw = cap.read()
                if not ok:
                    break
                t = idx / fps
                self._t = t
                img = to_1080p(raw)
                if self.detector is not None and t >= next_det:
                    dets = self._detect(img)
                    next_det += det_period
                    n_det += 1
                if t >= next_cur:
                    players = [d for d in dets if d.cls in ("player", "goalkeeper")] if self.detector else None
                    for ev in self.cursors.process(img, t, players):
                        self._add_event({**ev.as_dict(), "t": round(t, 2)}, img, dets)
                        self.session.push_selection(ev)
                    next_cur += cur_period
                self.ocr.step(img, t)
                if t >= next_sample:
                    timeline.append(self._sample(t, dets))
                    next_sample += 1.0
                if writer is not None:
                    over = draw_debug(img, dets, self.cursors, self.teams)
                    cv2.putText(over, fmt_t(t), (20, 1060), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
                    writer.write(cv2.resize(over, (ccfg.annotated_width, ccfg.annotated_width * 9 // 16),
                                            interpolation=cv2.INTER_AREA))
                idx += 1
                if progress and total and idx % 15 == 0:
                    progress(min(0.999, idx / total))
        finally:
            cap.release()
            if writer is not None:
                writer.release()
            self.kits.close()
        match = self.session.match
        bilan = match.finish()
        self.session.close()
        for t0, t1, dest in self._segments:
            extract_segment(path, max(0.0, t0), t1, dest, fps)
        elapsed = time.perf_counter() - t_start
        duration = idx / fps if fps else 0.0
        homo = self.session.homography
        if homo.calibration is None:
            warnings.append("terrain non calibré : pas de terrain 2D, d'événements ni de conseils "
                            "(calibre-le une fois dans le dashboard, page « Calibration »)")
        elif not match.pitch_ok_steps:
            warnings.append("lignes du terrain jamais reconnues sur ce clip (caméra différente de la calibration ?)")
        if self.detector is None:
            warnings.append("aucun détecteur chargé : pas de boîtes joueurs, donc pas d'attribution d'équipes")
        if self.ocr_engine_name == "aucun":
            warnings.append("aucun moteur OCR : chrono, score et pseudo non lus")
        if self.detector is not None and not self.teams.status.reliable:
            warnings.append("équipes non fiables (< 70 %) sur ce clip : à vérifier avec la vidéo annotée")
        report = {
            "source": info,
            "duration_s": round(duration, 2),
            "frames_read": idx,
            "detections_run": n_det,
            "processing_s": round(elapsed, 1),
            "speed_x": round(duration / elapsed, 2) if elapsed else None,
            "detector": None if self.detector is None else self.detector.mode,
            "ocr_engine": self.ocr_engine_name,
            "teams": self.teams.snapshot(),
            "ocr": self.state.get("ocr", {}),
            "summary": self._summary(duration),
            "match": {**bilan, "dir": match.out_dir.relative_to(out_dir).as_posix()},
            "events": self.events,
            "timeline": timeline,
            "annotated_video": "annotated.webm" if writer is not None and (out_dir / "annotated.webm").exists() else None,
            "warnings": warnings,
        }
        if progress:
            progress(1.0)
        return report

    # ------------------------------------------------------------------
    def _detect(self, img: np.ndarray) -> list[Detection]:
        assert self.detector is not None and self.session is not None
        self.session.set_ocr(self.state.get("ocr", {}), self.ocr.overlay_active)
        dets, advice = self.session.step(self._t, img, self.detector.detect(img))
        if advice is not None:
            self._add_event({"type": "advice", "t": round(self._t, 2), "text": advice.text,
                             "rule_id": advice.rule_id}, img, dets)
        return dets

    def _sample(self, t: float, dets: list[Detection]) -> dict[str, Any]:
        s = TeamAssignmentSummary.from_dets(dets)
        return {"t": round(t, 1), "team_conf": round(self.teams.status.confidence, 3),
                "me": s.me, "opp": s.opp, "unknown": s.unknown,
                "cursor_me": self.cursors.tracks["me"].status, "cursor_opp": self.cursors.tracks["opp"].status,
                "clock": self.ocr.clock.text}

    def _add_event(self, ev: dict[str, Any], img: np.ndarray, dets: list[Detection]) -> None:
        ev["t_text"] = fmt_t(ev["t"])
        ev["clock"] = self.ocr.clock.text
        n = len(self.events)
        if n < self.cfg.clips.max_event_snapshots:
            snap = draw_debug(img, dets, self.cursors, self.teams)
            name = f"{n:04d}.jpg"
            cv2.imwrite(str(self._events_dir / name), cv2.resize(snap, (960, 540)), [cv2.IMWRITE_JPEG_QUALITY, 80])
            ev["snapshot"] = name
        if ev["type"] == "selection_change":
            log.debug("Clip %s — %s change de joueur", ev["t_text"], SIDE_LABEL[ev["side"]])
        self.events.append(ev)

    def _on_ocr_event(self, ev: dict[str, Any]) -> None:
        if self.session is not None:
            self.session.push_ocr_event(ev)
        if ev["type"] in ("goal", "pause", "halftime", "fulltime", "period_start"):
            self.events.append({**ev, "t": round(self._t, 2), "t_text": fmt_t(self._t)})

    def _summary(self, duration: float) -> dict[str, Any]:
        sel = [e for e in self.events if e["type"] == "selection_change"]
        by_side = Counter(e["side"] for e in sel)
        minutes = max(duration / 60, 1e-6)
        zones_opp = Counter(e["zone"] for e in sel if e["side"] == "opp")
        return {
            "selection_changes": {"me": by_side.get("me", 0), "opp": by_side.get("opp", 0)},
            # Taux par minute seulement sur un clip d'au moins une minute (sinon extrapolation trompeuse)
            "selection_changes_per_min": ({s: round(by_side.get(s, 0) / minutes, 1) for s in ("me", "opp")}
                                          if duration >= 60 else None),
            "opp_switch_zones": dict(zones_opp.most_common()),
            "goals": [e for e in self.events if e["type"] == "goal"],
            "opponent_pseudo": self.ocr.opponent_pseudo,
            "teams_reliable": self.teams.status.reliable,
            "teams_confidence": round(self.teams.status.confidence, 3),
            "clash": self.teams.status.clash,
        }

    def _warnings(self, info: dict[str, Any]) -> list[str]:
        w = []
        if (info["width"], info["height"]) != TARGET:
            w.append(f"clip en {info['width']}x{info['height']} : ramené en 1920x1080 (précision réduite "
                     "sous 1080p, surtout pour la balle et les curseurs)")
        if info["height"] < 700:
            w.append("résolution très basse : curseurs et OCR peu fiables")
        if not info["frames"]:
            w.append("nombre d'images inconnu : progression approximative")
        return w

    def _open_writer(self, out_dir: Path, fps: float) -> cv2.VideoWriter | None:
        size = (self.cfg.clips.annotated_width, self.cfg.clips.annotated_width * 9 // 16)
        w = cv2.VideoWriter(str(out_dir / "annotated.webm"), cv2.VideoWriter_fourcc(*"VP80"), fps, size)
        if not w.isOpened():
            log.warning("Encodeur WebM indisponible : pas de vidéo annotée (les images clés restent produites)")
            return None
        return w
