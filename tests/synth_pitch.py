"""Vue « télé » synthétique du terrain (lignes blanches) pour tester l'homographie."""

from __future__ import annotations

import cv2
import numpy as np

from fccoach.tracking.pitch import PitchCanvas

CANVAS = PitchCanvas(scale=10, margin=0)


def camera(center_x: float, zoom: float = 1.0) -> np.ndarray:
    """Homographie terrain (m) -> image 1920x1080 : vue en perspective centrée sur center_x."""
    half = 30 / zoom
    src = np.float32([[center_x - half, -34], [center_x + half, -34], [center_x + half * 1.25, 34], [center_x - half * 1.25, 34]])
    dst = np.float32([[300, 120], [1620, 120], [1920, 1060], [0, 1060]])
    return cv2.getPerspectiveTransform(src, dst)


def render(H_pitch_to_img: np.ndarray) -> np.ndarray:
    top = CANVAS.base((40, 140, 55))
    # pixels canevas -> mètres -> image
    s = CANVAS.scale
    C = np.array([[1 / s, 0, -52.5], [0, 1 / s, -34], [0, 0, 1]])
    img = cv2.warpPerspective(top, H_pitch_to_img @ C, (1920, 1080), borderValue=(40, 140, 55))
    noise = np.random.default_rng(0).integers(-6, 6, img.shape)
    return np.clip(img.astype(int) + noise, 0, 255).astype(np.uint8)
