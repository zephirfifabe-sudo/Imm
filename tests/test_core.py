import numpy as np

from fccoach.capture.ring_buffer import Frame, FrameRingBuffer
from fccoach.core.config import load_config
from fccoach.core.hardware import AdaptiveCadence, detect_hardware, recommend_cadence
from fccoach.vision.detector import tile_grid


def test_config_loads():
    cfg = load_config("config/config.yaml")
    assert cfg.live_coaching is True
    assert cfg.capture.buffer_seconds == 30
    assert cfg.teams.min_confidence == 0.70


def test_recommend_cadence():
    assert recommend_cadence(0.005, [60, 30, 15, 10]) == 60
    assert recommend_cadence(0.020, [60, 30, 15, 10]) == 30
    assert recommend_cadence(0.050, [60, 30, 15, 10]) == 15
    assert recommend_cadence(0.500, [60, 30, 15, 10]) == 10


def test_adaptive_cadence_steps_down():
    c = AdaptiveCadence([60, 30, 15, 10])
    c.calibrate(0.010)
    assert c.current == 60
    for _ in range(12):
        c.update(0.030)   # la machine ralentit
    assert c.current == 30


def test_hardware_detection_always_has_cpu():
    hw = detect_hardware()
    assert hw.providers[-1] == "CPUExecutionProvider"


def test_ring_buffer_keeps_last_30s():
    buf = FrameRingBuffer(seconds=1, fps=10)
    img = np.zeros((2, 2, 3), np.uint8)
    for i in range(25):
        buf.push(Frame(i, i * 0.1, 0.0, img))
    assert len(buf) == 10
    assert buf.latest().index == 24
    assert [f.index for f in buf.range(2.0, 2.25)] == [20, 21, 22]


def test_tiles_cover_1080p_without_resize():
    tiles = tile_grid(1920, 1080, 640, 96)
    covered = np.zeros((1080, 1920), bool)
    for x, y in tiles:
        covered[y:y + 640, x:x + 640] = True
    assert covered.all()
