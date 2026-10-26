from fastapi.testclient import TestClient

from fccoach.core.config import load_config
from fccoach.core.state import SharedState
from fccoach.storage.db import MatchDB
from fccoach.ui.server import create_app
from tests.synth_pitch import camera, render
from tests.test_homography import calibrate


def test_pages_and_history(tmp_path):
    cfg = load_config()
    cfg.storage.matches_db = str(tmp_path / "m.sqlite")
    cfg.storage.matches_dir = str(tmp_path / "matches")
    cfg.pitch.calibration_file = str(tmp_path / "cal.json")
    db = MatchDB(cfg.storage.matches_db)
    mid = db.start_match("live")
    db.add_occurrence(mid, 10.0, "12:00", "ramene_ton_dc", 1, None)
    db.update_match(mid, ended=1e9, score_me=2, score_opp=1)
    c = TestClient(create_app(SharedState(), cfg=cfg))
    for page in ("/", "/calibration", "/historique", f"/bilan/{mid}"):
        assert c.get(page).status_code == 200, page
    assert c.get("/static/common.css").status_code == 200
    assert c.get("/api/matches").json()[0]["score_me"] == 2
    assert c.get("/api/weekly").json()[0]["top_rules"][0][0] == "ramene_ton_dc"
    assert c.get(f"/api/matches/{mid}").json()["match"]["id"] == mid
    info = c.get("/api/calibration").json()
    assert "centre" in info["keypoints"] and info["status"] == "non calibré"
    # Sans capture ni clip : impossible de figer une image
    assert c.post("/api/calibration/freeze").status_code == 400


def test_calibration_preview(tmp_path):
    cfg = load_config()
    cfg.pitch.calibration_file = str(tmp_path / "cal.json")
    H = camera(-20)
    img = render(H)
    cal = calibrate(H, img)
    cal.save(cfg.pitch.calibration_file)
    from fccoach.ui import server
    app = server.create_app(SharedState(), cfg=cfg)
    c = TestClient(app)
    # Image figée injectée directement (comme le ferait /freeze depuis la capture)
    frozen = [cell.cell_contents for route in app.routes if getattr(route, "path", "") == "/api/calibration/frame.jpg"
              for cell in route.endpoint.__closure__ if isinstance(cell.cell_contents, dict)][0]
    frozen["image"] = img
    assert c.get("/api/calibration/preview.jpg").headers["content-type"] == "image/jpeg"
    r = c.post("/api/calibration", json={"points": [{"name": p["name"], "px": p["px"]} for p in cal.points]})
    assert r.status_code == 200 and r.json()["error_m"] < 0.1
    bad = c.post("/api/calibration", json={"points": cal.points[:3]})
    assert bad.status_code == 400
