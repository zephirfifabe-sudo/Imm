"""Dashboard web local (FastAPI) — second écran, interface en français.

  GET  /                          page du dashboard (direct + clips)
  GET  /api/state                 état JSON (système, OCR, curseurs, équipes, événements)
  GET  /video/debug.mjpg          flux MJPEG de l'overlay debug
  POST /api/clips                 dépôt d'un clip téléchargé (multipart, champ « file »)
  GET  /api/clips                 liste des clips et progression
  GET  /api/clips/{id}            état + rapport d'un clip
  GET  /api/clips/{id}/video      vidéo annotée (WebM)
  GET  /api/clips/{id}/events/{f} image clé d'un événement
  DELETE /api/clips/{id}          supprime (ou annule) un clip
  GET  /clips/{id}                page de résultat d'un clip
  GET  /api/clips/{id}/files/{p}  fichiers d'analyse d'un clip (extraits, heatmaps)
  Calibration du terrain : GET /calibration, GET /api/calibration, POST /api/calibration/freeze,
       GET /api/calibration/frame.jpg, POST /api/calibration, GET /api/calibration/preview.jpg
  Historique : GET /historique, GET /bilan/{id}, GET /api/matches, GET /api/matches/{id},
       GET /api/weekly, GET /api/matches/{id}/files/{p}
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
from fastapi import Body, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from fccoach.core.config import Config, resolve_path
from fccoach.core.state import SharedState
from fccoach.tracking.homography import Calibration, project
from fccoach.tracking.pitch import KEYPOINTS, circle_points, pitch_segments

if TYPE_CHECKING:
    from fccoach.app import Pipeline
    from fccoach.clips.manager import ClipManager

_MEDIA = {".webm": "video/webm", ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json"}


def safe_file(root: Path, rel: str) -> Path:
    """Fichier sous `root` uniquement (aucune remontée « .. »)."""
    p = (root / rel).resolve()
    if root.resolve() not in p.parents or not p.is_file():
        raise HTTPException(404, "Fichier introuvable")
    return p


def draw_pitch_overlay(image: np.ndarray, H_img_to_pitch: np.ndarray) -> np.ndarray:
    """Lignes du terrain reprojetées sur l'image : contrôle visuel de la calibration."""
    out = image.copy()
    Hinv = np.linalg.inv(H_img_to_pitch)
    for a, b in pitch_segments():
        pts = np.linspace(a, b, 20)
        px = project(Hinv, pts).astype(np.int32)
        cv2.polylines(out, [px], False, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.polylines(out, [project(Hinv, circle_points()).astype(np.int32)], True, (0, 255, 255), 2, cv2.LINE_AA)
    return out


def jpeg(img: np.ndarray, quality: int = 85) -> Response:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise HTTPException(500, "Encodage impossible")
    return Response(buf.tobytes(), media_type="image/jpeg")

STATIC = Path(__file__).parent / "static"
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


def create_app(state: SharedState, mjpeg_fps: int = 10, jpeg_quality: int = 70,
               clips: "ClipManager | None" = None, max_upload_mb: int = 4096,
               pipeline: "Pipeline | None" = None, cfg: Config | None = None) -> FastAPI:
    app = FastAPI(title="Coach EA FC 27", docs_url=None, redoc_url=None)
    cfg = cfg or (pipeline.cfg if pipeline else None) or Config()
    frozen: dict[str, Any] = {"image": None}
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    def api_state() -> JSONResponse:
        return JSONResponse(state.snapshot())

    async def mjpeg():
        period = 1.0 / max(1, mjpeg_fps)
        params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
        last_id = None
        while True:
            img = state.get_overlay()
            if img is not None and id(img) != last_id:
                last_id = id(img)
                small = cv2.resize(img, (960, 540), interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", small, params)
                if ok:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            await asyncio.sleep(period)

    @app.get("/video/debug.mjpg")
    def video() -> StreamingResponse:
        return StreamingResponse(mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

    # ------------------------------------------------------------ clips
    def mgr() -> "ClipManager":
        if clips is None:
            raise HTTPException(503, "Analyse de clips indisponible")
        return clips

    @app.post("/api/clips")
    async def upload_clip(file: UploadFile = File(...)) -> JSONResponse:
        from fccoach.clips.analyzer import VIDEO_EXTENSIONS

        m = mgr()
        name = Path(file.filename or "clip.mp4").name
        ext = Path(name).suffix.lower()
        if ext not in VIDEO_EXTENSIONS:
            raise HTTPException(400, f"Format {ext or '?'} non pris en charge ({', '.join(sorted(VIDEO_EXTENSIONS))})")
        tmp = m.root / f"_upload_{uuid.uuid4().hex}{ext}"
        size, limit = 0, max_upload_mb * 1024 * 1024
        try:
            with open(tmp, "wb") as fh:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, f"Fichier trop gros (> {max_upload_mb} Mo)")
                    fh.write(chunk)
            job = await asyncio.to_thread(m.add_file, tmp, name, True)
        except ValueError as exc:
            raise HTTPException(400, f"Clip refusé : {exc}") from exc
        finally:
            tmp.unlink(missing_ok=True)
        return JSONResponse(job.public())

    @app.get("/api/clips")
    def list_clips() -> JSONResponse:
        return JSONResponse(mgr().list() if clips else [])

    @app.get("/api/clips/{job_id}")
    def get_clip(job_id: str) -> JSONResponse:
        m = mgr()
        job = m.get(job_id)
        if job is None:
            raise HTTPException(404, "Clip introuvable")
        return JSONResponse({"job": job.public(), "report": m.report(job_id) if job.status == "done" else None})

    @app.get("/api/clips/{job_id}/video")
    def clip_video(job_id: str) -> FileResponse:
        m = mgr()
        if m.get(job_id) is None:
            raise HTTPException(404, "Clip introuvable")
        p = m.dir(job_id) / "annotated.webm"
        if not p.exists():
            raise HTTPException(404, "Pas de vidéo annotée pour ce clip")
        return FileResponse(p, media_type="video/webm")

    @app.get("/api/clips/{job_id}/events/{fname}")
    def clip_event(job_id: str, fname: str) -> FileResponse:
        m = mgr()
        if m.get(job_id) is None or not _SAFE.match(fname):
            raise HTTPException(404, "Image introuvable")
        p = m.dir(job_id) / "events" / fname
        if not p.exists():
            raise HTTPException(404, "Image introuvable")
        return FileResponse(p, media_type="image/jpeg")

    @app.delete("/api/clips/{job_id}")
    def delete_clip(job_id: str) -> JSONResponse:
        if not mgr().delete(job_id):
            raise HTTPException(404, "Clip introuvable")
        return JSONResponse({"ok": True})

    @app.get("/clips/{job_id}")
    def clip_page(job_id: str) -> FileResponse:
        return FileResponse(STATIC / "clip.html")

    @app.get("/api/clips/{job_id}/files/{rel:path}")
    def clip_file(job_id: str, rel: str) -> FileResponse:
        m = mgr()
        if m.get(job_id) is None:
            raise HTTPException(404, "Clip introuvable")
        p = safe_file(m.dir(job_id), rel)
        return FileResponse(p, media_type=_MEDIA.get(p.suffix, "application/octet-stream"))

    # ------------------------------------------------------- calibration
    cal_path = resolve_path(cfg.pitch.calibration_file)

    def current_frame(clip: str | None, t: float) -> np.ndarray:
        if clip:
            from fccoach.clips.analyzer import to_1080p

            m = mgr()
            job = m.get(clip)
            if job is None:
                raise HTTPException(404, "Clip introuvable")
            cap = cv2.VideoCapture(str(m.dir(clip) / job.source))
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, img = cap.read()
            cap.release()
            if not ok:
                raise HTTPException(400, "Image du clip illisible à cet instant")
            return to_1080p(img)
        if pipeline is None:
            raise HTTPException(400, "Pas de capture en direct : choisis un clip pour calibrer")
        f = pipeline.buffer.latest()
        if f is None:
            raise HTTPException(400, "Aucune image reçue de la capture")
        return f.image.copy()

    @app.get("/calibration")
    def calibration_page() -> FileResponse:
        return FileResponse(STATIC / "calibration.html")

    @app.get("/api/calibration")
    def calibration_info() -> JSONResponse:
        data = json.loads(cal_path.read_text(encoding="utf-8")) if cal_path.exists() else None
        status = pipeline.session.homography.status if pipeline else ("ok" if data else "non calibré")
        return JSONResponse({"keypoints": {k: list(v) for k, v in KEYPOINTS.items()}, "calibration": data,
                             "status": status, "live": pipeline is not None,
                             "clips": clips.list() if clips else []})

    @app.post("/api/calibration/freeze")
    def calibration_freeze(clip: str | None = None, t: float = 1.0) -> JSONResponse:
        frozen["image"] = current_frame(clip, t)
        return JSONResponse({"ok": True})

    @app.get("/api/calibration/frame.jpg")
    def calibration_frame() -> Response:
        if frozen["image"] is None:
            raise HTTPException(404, "Aucune image figée")
        return jpeg(frozen["image"])

    @app.post("/api/calibration")
    def calibration_save(payload: dict = Body(...)) -> JSONResponse:
        if frozen["image"] is None:
            raise HTTPException(400, "Fige d'abord une image")
        try:
            if pipeline is not None:
                cal = pipeline.session.calibrate(payload.get("points", []), frozen["image"])
            else:
                cal = Calibration.from_points(payload.get("points", []), frozen["image"])
                cal.save(cal_path)
        except ValueError as exc:
            raise HTTPException(400, f"Calibration refusée : {exc}") from exc
        return JSONResponse({"ok": True, "error_m": round(cal.error_m or 0, 2), "points": len(cal.points)})

    @app.get("/api/calibration/preview.jpg")
    def calibration_preview() -> Response:
        if frozen["image"] is None:
            raise HTTPException(404, "Aucune image figée")
        cal = Calibration.load(cal_path) if cal_path.exists() else None
        if cal is None or cal.H is None:
            raise HTTPException(404, "Pas encore calibré")
        return jpeg(draw_pitch_overlay(frozen["image"], cal.H))

    # --------------------------------------------------------- historique
    def db():
        from fccoach.storage.db import MatchDB

        if pipeline is not None and pipeline.session.db is not None:
            return pipeline.session.db
        return MatchDB(resolve_path(cfg.storage.matches_db))

    def match_dir(mid: int) -> Path:
        return resolve_path(cfg.storage.matches_dir) / f"match_{mid:05d}"

    @app.get("/historique")
    def history_page() -> FileResponse:
        return FileResponse(STATIC / "history.html")

    @app.get("/bilan/{mid}")
    def bilan_page(mid: int) -> FileResponse:
        return FileResponse(STATIC / "bilan.html")

    @app.get("/api/matches")
    def api_matches() -> JSONResponse:
        return JSONResponse(db().matches(200))

    @app.get("/api/weekly")
    def api_weekly() -> JSONResponse:
        return JSONResponse(db().weekly())

    @app.get("/api/matches/{mid}")
    def api_match(mid: int) -> JSONResponse:
        m = db().match(mid)
        if m is None:
            raise HTTPException(404, "Match introuvable")
        bilans = {}
        for name in ("mi_temps", "fin"):
            p = match_dir(mid) / f"bilan_{name}.json"
            if p.exists():
                bilans[name] = json.loads(p.read_text(encoding="utf-8"))
        return JSONResponse({"match": m, "bilans": bilans})

    @app.get("/api/matches/{mid}/files/{rel:path}")
    def match_file(mid: int, rel: str) -> FileResponse:
        p = safe_file(match_dir(mid), rel)
        return FileResponse(p, media_type=_MEDIA.get(p.suffix, "application/octet-stream"))

    return app
