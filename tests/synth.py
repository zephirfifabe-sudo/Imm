"""Images synthétiques pour les tests : pelouse, joueurs, curseurs."""

from __future__ import annotations

import cv2
import numpy as np

from fccoach.vision.types import Detection

GRASS = (50, 140, 60)  # BGR


def pitch(w: int = 1920, h: int = 1080) -> np.ndarray:
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = GRASS
    rng = np.random.default_rng(1)
    noise = rng.integers(-8, 8, img.shape)
    return np.clip(img.astype(int) + noise, 0, 255).astype(np.uint8)


def draw_player(img: np.ndarray, x: int, y: int, shirt: tuple[int, int, int], shorts: tuple[int, int, int],
                socks: tuple[int, int, int] | None = None, w: int = 34, h: int = 90) -> Detection:
    """Joueur rectangulaire : tête (peau), maillot, short, chaussettes."""
    socks = socks or shorts
    x1, y1 = x - w // 2, y
    cv2.rectangle(img, (x - 7, y1), (x + 7, y1 + int(0.15 * h)), (120, 160, 210), -1)        # tête
    cv2.rectangle(img, (x1, y1 + int(0.17 * h)), (x1 + w, y1 + int(0.57 * h)), shirt, -1)    # maillot
    cv2.rectangle(img, (x1 + 2, y1 + int(0.58 * h)), (x1 + w - 2, y1 + int(0.82 * h)), shorts, -1)
    cv2.rectangle(img, (x1 + 4, y1 + int(0.84 * h)), (x1 + w - 4, y1 + h), socks, -1)
    return Detection(float(x1), float(y1), float(x1 + w), float(y1 + h), 0.9, "player")


def draw_cursor(img: np.ndarray, tip_x: int, tip_y: int, color: tuple[int, int, int], size: int = 18) -> None:
    pts = np.array([[tip_x - size // 2, tip_y - size], [tip_x + size // 2, tip_y - size], [tip_x, tip_y]], np.int32)
    cv2.fillPoly(img, [pts], color)
