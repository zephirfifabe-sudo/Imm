import numpy as np

from fccoach.tracking.homography import Calibration, HomographyTracker, project
from fccoach.tracking.pitch import KEYPOINTS
from tests.synth_pitch import camera, render


def calibrate(H_cam, image, names=("milieu_haut", "milieu_bas", "surface_gauche_haut", "surface_gauche_bas", "centre")):
    pts = [{"name": n, "px": project(H_cam, np.array([KEYPOINTS[n]]))[0].tolist()} for n in names]
    return Calibration.from_points(pts, image)


def test_calibration_precise():
    H_cam = camera(-20)
    cal = calibrate(H_cam, render(H_cam))
    assert cal.error_m < 0.05
    p = project(H_cam, np.array([[-30.0, 10.0]]))
    assert np.allclose(project(cal.H, p), [[-30, 10]], atol=0.1)


def test_tracks_camera_pan_and_zoom():
    H0 = camera(-20)
    tr = HomographyTracker(calibrate(H0, render(H0)))
    for i, (cx, zoom) in enumerate([(-18, 1.0), (-15, 1.0), (-12, 1.05), (-9, 1.1), (-6, 1.1)]):
        Hc = camera(cx, zoom)
        assert tr.update(render(Hc), now=float(i)) == "ok", (cx, zoom)
        truth = np.array([[cx, 0.0], [cx - 10, 20.0], [cx + 8, -15.0]])
        px = project(Hc, truth)
        assert np.abs(tr.to_pitch(px) - truth).max() < 1.5, (cx, tr.to_pitch(px), truth)


def test_lost_on_close_up_then_recovers():
    H0 = camera(-20)
    tr = HomographyTracker(calibrate(H0, render(H0)))
    close_up = np.full((1080, 1920, 3), (60, 60, 60), np.uint8)   # gros plan sans pelouse
    tr.update(close_up, now=0.0)
    assert tr.update(close_up, now=2.0) == "perdue" and tr.to_pitch(np.zeros((1, 2))) is None
    assert tr.update(render(camera(-19)), now=3.0) == "ok"
