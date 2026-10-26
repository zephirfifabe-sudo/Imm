import numpy as np
import pytest

from fccoach.vision.color import bgr_to_lab, ciede2000, dominant_lab, lab_to_bgr


# Paires de référence Sharma, Wu, Dalal (2005)
@pytest.mark.parametrize("l1,l2,expected", [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, -1.0, 2.0), (50.0, 0.0, 0.0), 2.3669),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
])
def test_ciede2000_reference(l1, l2, expected):
    assert float(ciede2000(np.array(l1), np.array(l2))) == pytest.approx(expected, abs=1e-3)


def test_lab_roundtrip():
    bgr = np.array([[30, 30, 200], [250, 250, 250], [200, 60, 20]], np.uint8)
    back = lab_to_bgr(bgr_to_lab(bgr))
    assert np.abs(back.astype(int) - bgr.astype(int)).max() <= 4  # quantification 8 bits du Lab OpenCV


def test_dominant_ignores_grass_and_skin():
    crop = np.zeros((40, 30, 3), np.uint8)
    crop[:] = (50, 140, 60)            # pelouse
    crop[5:35, 5:25] = (200, 60, 20)   # maillot bleu
    lab, frac = dominant_lab(crop)
    target = bgr_to_lab(np.array([[200, 60, 20]], np.uint8))[0]
    assert float(ciede2000(lab, target)) < 3
