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
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from fccoach.core.state import SharedState

if TYPE_CHECKING:
    from fccoach.clips.manager import ClipManager

STATIC = Path(__file__).parent / "static"
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


def create_app(state: SharedState, mjpeg_fps: int = 10, jpeg_quality: int = 70,
               clips: "ClipManager | None" = None, max_upload_mb: int = 4096) -> FastAPI:
    app = FastAPI(title="Coach EA FC 27", docs_url=None, redoc_url=None)

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

    return app
