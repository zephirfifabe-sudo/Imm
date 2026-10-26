import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from fccoach.clips.analyzer import to_1080p
from fccoach.clips.manager import ClipManager
from fccoach.core.config import load_config, load_yaml
from fccoach.core.state import SharedState
from fccoach.ocr.engines import NullEngine
from fccoach.ui.server import create_app
from fccoach.vision.color import grass_mask
from fccoach.vision.types import Detection
from tests.synth import draw_cursor, draw_player, pitch


class StubDetector:
    """Détecteur de test : tout ce qui n'est pas pelouse et assez haut = joueur."""
    mode = "stub"

    def detect(self, img):
        m = (~grass_mask(img)).astype(np.uint8) * 255
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for c in cs:
            x, y, w, h = cv2.boundingRect(c)
            if h > 50:
                out.append(Detection(x, y, x + w, y + h, 0.9, "player"))
        return out


def make_clip(path, n=45, size=(1280, 720)):
    """Clip 720p : mon curseur fixe, le curseur adverse change de joueur à mi-clip."""
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 15, size)
    for f in range(n):
        img = pitch()
        for i in range(4):
            draw_player(img, 300 + i * 150, 400, (200, 60, 20), (240, 240, 240))
            draw_player(img, 1100 + i * 150, 400, (40, 40, 210), (30, 30, 30))
        draw_cursor(img, 300, 392, (30, 30, 230))
        draw_cursor(img, 1100 if f < n // 2 else 1550, 392, (250, 250, 250))
        out.write(cv2.resize(img, size, interpolation=cv2.INTER_AREA))
    out.release()


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c.clips.dir = str(tmp_path / "clips")
    c.teams.kits_db = str(tmp_path / "kits.sqlite")
    c.clips.analysis_fps = 15
    return c


def manager(cfg, start_worker=False):
    return ClipManager(cfg, StubDetector(), NullEngine(), load_yaml("config/cursor.yaml"), start_worker)


def test_to_1080p_keeps_ratio():
    assert to_1080p(np.zeros((720, 1280, 3), np.uint8)).shape == (1080, 1920, 3)
    vertical = np.full((1920, 1080, 3), 255, np.uint8)
    out = to_1080p(vertical)
    assert out.shape == (1080, 1920, 3)
    assert out[:, :300].max() == 0 and out[:, 960].min() == 255   # bandes noires sur les côtés


def test_analyze_clip(cfg, tmp_path):
    src = tmp_path / "clip.mp4"
    make_clip(src)
    mgr = manager(cfg)
    job = mgr.add_file(src)
    mgr.run_job(job)
    assert job.status == "done", job.error
    rep = mgr.report(job.id)
    sel = [e for e in rep["events"] if e["type"] == "selection_change"]
    assert [e["side"] for e in sel].count("opp") == 2           # sélection initiale + changement
    switch = [e for e in sel if e["side"] == "opp"][1]
    assert 1.4 <= switch["t"] <= 1.8                            # au milieu du clip (temps vidéo)
    assert rep["summary"]["teams_reliable"]
    assert rep["summary"]["selection_changes"] == {"me": 1, "opp": 2}
    assert any("1280x720" in w for w in rep["warnings"])
    d = mgr.dir(job.id)
    assert (d / "events" / switch["snapshot"]).exists()
    assert rep["annotated_video"] is None or (d / "annotated.webm").stat().st_size > 0


def test_rejects_non_video(cfg, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        manager(cfg).add_file(bad)
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"pas une video")
    with pytest.raises(ValueError):
        manager(cfg).add_file(fake)


def test_upload_api(cfg, tmp_path):
    cfg.clips.annotated_video = False
    src = tmp_path / "clip.mp4"
    make_clip(src, n=20)
    mgr = manager(cfg, start_worker=True)
    client = TestClient(create_app(SharedState(), clips=mgr))
    r = client.post("/api/clips", files={"file": ("mon clip.mp4", src.read_bytes(), "video/mp4")})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    for _ in range(100):
        data = client.get(f"/api/clips/{job_id}").json()
        if data["job"]["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert data["job"]["status"] == "done"
    assert data["report"]["name"] == "mon clip.mp4"
    assert client.get(f"/clips/{job_id}").status_code == 200
    assert client.post("/api/clips", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400
    assert client.delete(f"/api/clips/{job_id}").json()["ok"]
    assert client.get("/api/clips").json() == []
