"""Zones OCR fixes (JSON) et pré-traitement des recadrages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class OcrZone:
    name: str
    mode: str                       # periodic | on_demand | relative
    kind: str                       # clock | score | name | pause | screen_title
    rate_hz: float = 1.0
    box: list[float] | None = None  # relatif [x, y, w, h]
    relative_to: str | None = None  # cursor_me | cursor_opp
    offset_px: list[int] | None = None  # [dx, dy, w, h] par rapport à la pointe du curseur
    trigger: str | None = None
    whitelist: str = ""
    preprocess: dict[str, Any] = field(default_factory=dict)

    def crop(self, image: np.ndarray, anchor: tuple[float, float] | None = None) -> np.ndarray | None:
        h, w = image.shape[:2]
        if self.mode == "relative":
            if anchor is None or self.offset_px is None:
                return None
            dx, dy, cw, ch = self.offset_px
            x0, y0 = int(anchor[0] + dx), int(anchor[1] + dy)
            x1, y1 = x0 + cw, y0 + ch
        else:
            assert self.box is not None
            bx, by, bw, bh = self.box
            x0, y0 = int(bx * w), int(by * h)
            x1, y1 = int((bx + bw) * w), int((by + bh) * h)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        return image[y0:y1, x0:x1]


def load_zones(path: str | Path) -> dict[str, OcrZone]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    zones = {}
    for name, z in raw.get("zones", {}).items():
        zones[name] = OcrZone(name=name, **z)
    return zones


def preprocess(crop: np.ndarray, opts: dict[str, Any]) -> np.ndarray:
    """Gris, agrandissement, inversion auto (texte clair sur fond sombre), seuillage."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    scale = float(opts.get("scale", 2))
    if scale != 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    inv = opts.get("invert", "auto")
    if inv == "auto":
        inv = float(gray.mean()) < 127  # Tesseract préfère du texte sombre sur fond clair
    if inv:
        gray = 255 - gray
    if opts.get("threshold") == "otsu":
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.copyMakeBorder(gray, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)


def dark_overlay_score(image: np.ndarray) -> float:
    """Luminance moyenne réduite : un menu pause / écran de mi-temps assombrit l'image."""
    small = cv2.resize(image, (96, 54), interpolation=cv2.INTER_AREA)
    return float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).mean())
