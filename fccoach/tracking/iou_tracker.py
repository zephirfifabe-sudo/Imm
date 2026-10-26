"""Suivi léger par recouvrement (IoU) — suffisant pour le vote d'équipe en Phase 1.

Phase 2 le remplacera par un suivi plus robuste (ByteTrack + homographie)
avec la même interface : update(detections) -> detections avec track_id.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fccoach.vision.types import Detection


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-6)


@dataclass
class _Track:
    tid: int
    box: np.ndarray
    cls: str
    missed: int = 0
    age: int = 0


class IouTracker:
    def __init__(self, iou_match: float = 0.3, max_missed: int = 15) -> None:
        self.iou_match = iou_match
        self.max_missed = max_missed
        self._tracks: list[_Track] = []
        self._next = 1

    def update(self, dets: list[Detection]) -> list[Detection]:
        people = [d for d in dets if d.cls != "ball"]
        boxes = np.array([d.as_list() for d in people]) if people else np.zeros((0, 4))
        tboxes = np.array([t.box for t in self._tracks]) if self._tracks else np.zeros((0, 4))
        ious = iou_matrix(tboxes, boxes)
        matched_t, matched_d = set(), set()
        # Appariement glouton par IoU décroissant
        for flat in np.argsort(-ious, axis=None):
            ti, di = divmod(int(flat), max(1, ious.shape[1]))
            if ious.size == 0 or ious[ti, di] < self.iou_match:
                break
            if ti in matched_t or di in matched_d:
                continue
            matched_t.add(ti)
            matched_d.add(di)
            tr = self._tracks[ti]
            tr.box, tr.missed, tr.age = boxes[di], 0, tr.age + 1
            people[di].track_id = tr.tid
        for di, d in enumerate(people):
            if di not in matched_d:
                tr = _Track(self._next, boxes[di], d.cls)
                self._next += 1
                self._tracks.append(tr)
                d.track_id = tr.tid
        for ti, tr in enumerate(self._tracks):
            if ti < len(tboxes) and ti not in matched_t:
                tr.missed += 1
        self._tracks = [t for t in self._tracks if t.missed <= self.max_missed]
        return dets

    def reset(self) -> None:
        self._tracks.clear()
