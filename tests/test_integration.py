"""Intégration complète sur un clip « vue télé » synthétique : calibration du terrain,
homographie qui suit la caméra, équipes, formation, passes, coach, bilan, heatmaps."""

from fastapi.testclient import TestClient

from fccoach.clips.manager import ClipManager
from fccoach.core.config import load_config, load_yaml
from fccoach.core.state import SharedState
from fccoach.ocr.engines import NullEngine
from fccoach.ui.server import create_app
from tests.synth_match import SynthMatch, TruthDetector
from tests.synth_pitch import render
from tests.test_homography import calibrate


def test_full_clip_analysis(tmp_path):
    sim = SynthMatch(n=150)
    sim.write(tmp_path / "match.avi")
    cfg = load_config()
    cfg.clips.dir = str(tmp_path / "clips")
    cfg.clips.annotated_video = False
    cfg.teams.kits_db = str(tmp_path / "kits.sqlite")
    cfg.pitch.calibration_file = str(tmp_path / "cal.json")
    H0 = sim.state(0)[0]
    calibrate(H0, render(H0)).save(cfg.pitch.calibration_file)
    mgr = ClipManager(cfg, TruthDetector(sim), NullEngine(), load_yaml("config/cursor.yaml"), False)
    job = mgr.add_file(tmp_path / "match.avi")
    mgr.run_job(job)
    assert job.status == "done", job.error
    rep = mgr.report(job.id)
    m = rep["match"]
    assert rep["teams"]["reliable"]
    assert m["formations"]["me"]["name"] == "41212" and m["formations"]["me"]["confidence"] >= 0.7
    assert m["stats"]["passes_me"] >= 3
    assert "heatmap_me.png" in m["heatmaps"]["me"]
    assert not any("terrain" in w for w in rep["warnings"])
    for r in m["rules"]:                                   # tout conseil cite sa fiche
        assert 1 <= r["source"] <= 11 and r["fiche"]
    # Les fichiers d'analyse sont servis par le dashboard
    client = TestClient(create_app(SharedState(), clips=mgr, cfg=cfg))
    url = f"/api/clips/{job.id}/files/{m['dir']}/{m['heatmaps']['me']}"
    assert client.get(url).status_code == 200
    assert client.get(f"/api/clips/{job.id}/files/../../etc/passwd").status_code == 404
