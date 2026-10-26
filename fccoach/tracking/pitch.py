"""Modèle du terrain (mètres) et rendu 2D vu du dessus.

Repère du terrain (calibration) : origine au rond central, x vers la DROITE
de l'image (sens de la longueur), y vers le BAS de l'image (ligne de touche
côté caméra). Terrain 105 × 68 m.

Repère « normalisé » (analyses) : mon équipe attaque vers +x. Si j'attaque
vers la gauche de l'image, x et y sont inversés (rotation de 180°).
"""

from __future__ import annotations

import cv2
import numpy as np

LENGTH, WIDTH = 105.0, 68.0
HL, HW = LENGTH / 2, WIDTH / 2
BOX_DEPTH, BOX_HW = 16.5, 20.16
SIX_DEPTH, SIX_HW = 5.5, 9.16
CIRCLE_R = 9.15
PENALTY_SPOT = 11.0
GOAL_HW = 3.66

# Points nommés utilisables pour la calibration (nom -> (x, y) en mètres)
KEYPOINTS: dict[str, tuple[float, float]] = {
    "coin_haut_gauche": (-HL, -HW), "coin_haut_droit": (HL, -HW),
    "coin_bas_gauche": (-HL, HW), "coin_bas_droit": (HL, HW),
    "milieu_haut": (0.0, -HW), "milieu_bas": (0.0, HW), "centre": (0.0, 0.0),
    "cercle_haut": (0.0, -CIRCLE_R), "cercle_bas": (0.0, CIRCLE_R),
    "cercle_gauche": (-CIRCLE_R, 0.0), "cercle_droit": (CIRCLE_R, 0.0),
    "surface_gauche_haut_ligne": (-HL, -BOX_HW), "surface_gauche_bas_ligne": (-HL, BOX_HW),
    "surface_gauche_haut": (-HL + BOX_DEPTH, -BOX_HW), "surface_gauche_bas": (-HL + BOX_DEPTH, BOX_HW),
    "surface_droite_haut_ligne": (HL, -BOX_HW), "surface_droite_bas_ligne": (HL, BOX_HW),
    "surface_droite_haut": (HL - BOX_DEPTH, -BOX_HW), "surface_droite_bas": (HL - BOX_DEPTH, BOX_HW),
    "six_gauche_haut": (-HL + SIX_DEPTH, -SIX_HW), "six_gauche_bas": (-HL + SIX_DEPTH, SIX_HW),
    "six_droit_haut": (HL - SIX_DEPTH, -SIX_HW), "six_droit_bas": (HL - SIX_DEPTH, SIX_HW),
    "penalty_gauche": (-HL + PENALTY_SPOT, 0.0), "penalty_droit": (HL - PENALTY_SPOT, 0.0),
}

KEYPOINT_LABELS: dict[str, str] = {k: k.replace("_", " ") for k in KEYPOINTS}


def pitch_segments() -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Segments des lignes du terrain (pour le rendu et le contrôle de calibration)."""
    s = [((-HL, -HW), (HL, -HW)), ((-HL, HW), (HL, HW)), ((-HL, -HW), (-HL, HW)), ((HL, -HW), (HL, HW)),
         ((0, -HW), (0, HW))]
    for sign in (-1, 1):
        gx = sign * HL
        bx = sign * (HL - BOX_DEPTH)
        sx = sign * (HL - SIX_DEPTH)
        s += [((gx, -BOX_HW), (bx, -BOX_HW)), ((bx, -BOX_HW), (bx, BOX_HW)), ((bx, BOX_HW), (gx, BOX_HW)),
              ((gx, -SIX_HW), (sx, -SIX_HW)), ((sx, -SIX_HW), (sx, SIX_HW)), ((sx, SIX_HW), (gx, SIX_HW))]
    return s


def circle_points(n: int = 48) -> np.ndarray:
    a = np.linspace(0, 2 * np.pi, n)
    return np.stack([CIRCLE_R * np.cos(a), CIRCLE_R * np.sin(a)], 1)


def normalize(x: float, y: float, my_attack_right: bool) -> tuple[float, float]:
    """Repère terrain -> repère normalisé (mon attaque vers +x)."""
    return (x, y) if my_attack_right else (-x, -y)


def inside(x: float, y: float, margin: float = 3.0) -> bool:
    return abs(x) <= HL + margin and abs(y) <= HW + margin


class PitchCanvas:
    """Image du terrain vu du dessus, pour les heatmaps et les exports."""

    def __init__(self, scale: float = 8.0, margin: int = 20) -> None:
        self.scale = scale
        self.margin = margin
        self.w = int(LENGTH * scale) + 2 * margin
        self.h = int(WIDTH * scale) + 2 * margin

    def px(self, x: float, y: float) -> tuple[int, int]:
        return (int(self.margin + (x + HL) * self.scale), int(self.margin + (y + HW) * self.scale))

    def base(self, color: tuple[int, int, int] = (40, 110, 45)) -> np.ndarray:
        img = np.zeros((self.h, self.w, 3), np.uint8)
        img[:] = color
        self.draw_lines(img)
        return img

    def draw_lines(self, img: np.ndarray, color: tuple[int, int, int] = (235, 235, 235)) -> None:
        for a, b in pitch_segments():
            cv2.line(img, self.px(*a), self.px(*b), color, 2, cv2.LINE_AA)
        pts = np.array([self.px(x, y) for x, y in circle_points()], np.int32)
        cv2.polylines(img, [pts], True, color, 2, cv2.LINE_AA)

    def heatmap(self, hist: np.ndarray, title: str = "") -> np.ndarray:
        """hist : grille (ny, nx) couvrant le terrain. Retourne une image BGR."""
        img = self.base((25, 60, 28))
        if hist.max() > 0:
            h = cv2.GaussianBlur(hist.astype(np.float32), (0, 0), 2.0)
            h = (255 * h / h.max()).astype(np.uint8)
            h = cv2.resize(h, (int(LENGTH * self.scale), int(WIDTH * self.scale)), interpolation=cv2.INTER_CUBIC)
            col = cv2.applyColorMap(h, cv2.COLORMAP_INFERNO)
            alpha = (h.astype(np.float32) / 255.0)[..., None] * 0.85
            m = self.margin
            roi = img[m:m + h.shape[0], m:m + h.shape[1]]
            img[m:m + h.shape[0], m:m + h.shape[1]] = (roi * (1 - alpha) + col * alpha).astype(np.uint8)
        self.draw_lines(img)
        if title:
            cv2.putText(img, title, (self.margin, self.margin - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        return img
