"""Dashboard web local (FastAPI) — second écran, interface en français.

  GET /                 page du dashboard
  GET /api/state        état JSON (système, OCR, curseurs, équipes, événements)
  GET /video/debug.mjpg flux MJPEG de l'overlay debug
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import cv2
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from fccoach.core.state import SharedState

STATIC = Path(__file__).parent / "static"


def create_app(state: SharedState, mjpeg_fps: int = 10, jpeg_quality: int = 70) -> FastAPI:
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

    return app
