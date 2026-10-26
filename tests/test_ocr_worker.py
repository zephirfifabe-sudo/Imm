import numpy as np

from fccoach.core.state import SharedState
from fccoach.ocr.worker import OcrWorker
from fccoach.ocr.zones import OcrZone


class FakeEngine:
    name = "fake"

    def __init__(self, text):
        self.text = text

    def read(self, image, whitelist=""):
        return self.text


def test_worker_reads_clock_and_respects_rate():
    zone = OcrZone("clock", "periodic", "clock", rate_hz=2, box=[0.1, 0.03, 0.06, 0.04])
    st = SharedState()
    w = OcrWorker({"clock": zone}, FakeEngine("12:34"), buffer=None, state=st)
    img = np.zeros((1080, 1920, 3), np.uint8)
    w.step(img, 0.0)
    assert st.get("ocr")["clock"] == "12:34"
    w.engine = FakeEngine("12:40")
    w.step(img, 0.2)                      # avant 0,5 s : pas de nouvelle lecture
    assert st.get("ocr")["clock"] == "12:34"
    w.step(img, 0.6)
    assert st.get("ocr")["clock"] == "12:40"
