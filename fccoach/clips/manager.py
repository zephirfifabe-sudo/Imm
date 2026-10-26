"""File d'attente des clips : dépôt, analyse en arrière-plan (un clip à la fois), résultats.

L'analyse tourne dans son propre thread : la capture en direct n'est jamais
bloquée. Chaque clip a son dossier data/clips/<id>/ (source, job.json, report.json…),
rechargé au redémarrage.
"""

from __future__ import annotations

import json
import logging
import queue
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from fccoach.clips.analyzer import VIDEO_EXTENSIONS, ClipAnalyzer, probe
from fccoach.core.config import Config, resolve_path
from fccoach.ocr.engines import OcrEngine
from fccoach.vision.detector import YoloOnnxDetector

log = logging.getLogger(__name__)

STATUS_LABEL = {"queued": "en attente", "running": "analyse en cours", "done": "terminé",
                "error": "erreur", "cancelled": "annulé"}


@dataclass
class ClipJob:
    id: str
    name: str
    source: str                  # nom du fichier source dans le dossier du clip
    status: str = "queued"       # queued | running | done | error | cancelled
    progress: float = 0.0
    created: float = field(default_factory=time.time)
    finished: float | None = None
    error: str | None = None
    info: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d["status_label"] = STATUS_LABEL.get(self.status, self.status)
        d["progress"] = round(self.progress, 3)
        return d


class ClipManager:
    def __init__(self, cfg: Config, detector: YoloOnnxDetector | None, ocr_engine: OcrEngine,
                 cursor_cfg: dict[str, Any], start_worker: bool = True) -> None:
        self.cfg = cfg
        self.detector = detector
        self.ocr_engine = ocr_engine
        self.cursor_cfg = cursor_cfg
        self.root = resolve_path(cfg.clips.dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, ClipJob] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._cancel: set[str] = set()
        self._load_existing()
        self._worker: threading.Thread | None = None
        if start_worker:
            self._worker = threading.Thread(target=self._run, name="clips", daemon=True)
            self._worker.start()

    # ------------------------------------------------------------- dépôt
    def add_file(self, src: str | Path, name: str | None = None, move: bool = False) -> ClipJob:
        """Ajoute un clip déjà présent sur le disque (copie ou déplacement)."""
        src = Path(src)
        ext = src.suffix.lower()
        if ext not in VIDEO_EXTENSIONS:
            raise ValueError(f"format {ext or '?'} non pris en charge ({', '.join(sorted(VIDEO_EXTENSIONS))})")
        info = probe(src)  # refuse tout de suite un fichier illisible
        job = ClipJob(id=uuid.uuid4().hex[:10], name=name or src.name, source=f"source{ext}", info=info)
        d = self.dir(job.id)
        d.mkdir(parents=True)
        (shutil.move if move else shutil.copy2)(str(src), str(d / job.source))
        self._save(job)
        with self._lock:
            self._jobs[job.id] = job
        self._queue.put(job.id)
        log.info("Clip ajouté : %s (%s, %sx%s, %s s)", job.name, job.id, info["width"], info["height"],
                 info["duration_s"])
        return job

    def dir(self, job_id: str) -> Path:
        return self.root / job_id

    # ---------------------------------------------------------- lecture
    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)
            return [j.public() for j in jobs]

    def get(self, job_id: str) -> ClipJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def report(self, job_id: str) -> dict[str, Any] | None:
        p = self.dir(job_id) / "report.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in ("queued", "running"):
                self._cancel.add(job_id)
            del self._jobs[job_id]
        if job.status != "running":
            shutil.rmtree(self.dir(job_id), ignore_errors=True)
        return True

    # ---------------------------------------------------------- analyse
    def run_job(self, job: ClipJob, progress: Callable[[float], None] | None = None) -> None:
        """Analyse synchrone (utilisée par le thread et par la ligne de commande)."""
        d = self.dir(job.id)
        job.status, job.progress, job.error = "running", 0.0, None
        self._save(job)
        try:
            analyzer = ClipAnalyzer(self.cfg, self.detector, self.ocr_engine, self.cursor_cfg)

            def on_progress(p: float) -> None:
                job.progress = p
                if progress:
                    progress(p)

            report = analyzer.analyze(d / job.source, d, on_progress, lambda: job.id in self._cancel)
            report["name"] = job.name
            (d / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
            job.summary = {**report["summary"], "duration_s": report["duration_s"], "speed_x": report["speed_x"],
                           "warnings": report["warnings"]}
            job.status = "cancelled" if job.id in self._cancel else "done"
            job.progress = 1.0
            log.info("Clip analysé : %s en %.1f s (x%.1f vitesse réelle)", job.name, report["processing_s"],
                     report["speed_x"] or 0)
        except Exception as exc:
            log.exception("Analyse du clip %s impossible", job.name)
            job.status, job.error = "error", str(exc)
        job.finished = time.time()
        if job.id in self._cancel:
            shutil.rmtree(d, ignore_errors=True)
            self._cancel.discard(job.id)
        else:
            self._save(job)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.get(job_id)
            if job is None or job.status != "queued":
                continue
            self.run_job(job)

    # ------------------------------------------------------- persistance
    def _save(self, job: ClipJob) -> None:
        d = self.dir(job.id)
        if d.exists():
            (d / "job.json").write_text(json.dumps(asdict(job), ensure_ascii=False), encoding="utf-8")

    def _load_existing(self) -> None:
        for p in sorted(self.root.glob("*/job.json")):
            try:
                job = ClipJob(**json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
            if job.status in ("queued", "running"):   # interrompu par un arrêt du logiciel
                job.status, job.progress = "queued", 0.0
                self._queue.put(job.id)
            self._jobs[job.id] = job


def create_clip_manager(cfg: Config, detector: YoloOnnxDetector | None = None, ocr_engine: OcrEngine | None = None,
                        start_worker: bool = True, load_detector: bool = True) -> ClipManager:
    """Construit le gestionnaire ; réutilise le détecteur et l'OCR du direct s'ils sont fournis."""
    from fccoach.app import build_detector
    from fccoach.core.config import load_yaml
    from fccoach.core.hardware import detect_hardware
    from fccoach.ocr.engines import create_engine

    hw = None
    if detector is None and load_detector:
        hw = detect_hardware(cfg.hardware.accelerator)
        detector, _ = build_detector(cfg, hw)
    if ocr_engine is None:
        hw = hw or detect_hardware(cfg.hardware.accelerator)
        ocr_engine = create_engine(cfg.ocr.engine, hw.is_gpu, cfg.ocr.tesseract_cmd)
    return ClipManager(cfg, detector, ocr_engine, load_yaml(cfg.cursor.config_file), start_worker)
