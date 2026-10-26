"""Couleurs : conversion Lab, CIEDE2000 vectorisé, masques pelouse/peau, K-means."""

from __future__ import annotations

import cv2
import numpy as np


def bgr_to_lab(pixels_bgr: np.ndarray) -> np.ndarray:
    """BGR uint8 (N,3) ou image -> Lab réel (L 0-100, a/b ~ -128..127), float32."""
    arr = np.asarray(pixels_bgr, dtype=np.uint8)
    shape = arr.shape
    lab = cv2.cvtColor(arr.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    lab[:, 0] *= 100.0 / 255.0
    lab[:, 1:] -= 128.0
    return lab.reshape(shape[:-1] + (3,))


def lab_to_bgr(lab: np.ndarray) -> np.ndarray:
    """Lab réel (3,) ou (N,3) -> BGR uint8 (pour l'affichage des prototypes)."""
    arr = np.atleast_2d(np.asarray(lab, dtype=np.float32)).copy()
    arr[:, 0] *= 255.0 / 100.0
    arr[:, 1:] += 128.0
    out = cv2.cvtColor(np.clip(arr, 0, 255).astype(np.uint8).reshape(-1, 1, 3), cv2.COLOR_LAB2BGR)
    return out.reshape(-1, 3)


def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """Distance CIEDE2000 (Sharma et al. 2005), vectorisée. Entrées (...,3)."""
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm**7 / (Cm**7 + 25.0**7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dhp = np.where(C1p * C2p == 0, 0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))
    Lpm = (L1 + L2) / 2
    Cpm = (C1p + C2p) / 2
    hsum = h1p + h2p
    hpm = np.where(np.abs(h1p - h2p) > 180,
                   np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2),
                   hsum / 2)
    hpm = np.where(C1p * C2p == 0, hsum, hpm)
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    dtheta = 30 * np.exp(-(((hpm - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cpm**7 / (Cpm**7 + 25.0**7))
    Sl = 1 + (0.015 * (Lpm - 50) ** 2) / np.sqrt(20 + (Lpm - 50) ** 2)
    Sc = 1 + 0.045 * Cpm
    Sh = 1 + 0.015 * Cpm * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def grass_mask(bgr: np.ndarray, h_range: tuple[int, int] = (32, 90), s_min: int = 50, v_min: int = 40) -> np.ndarray:
    """Masque True = pelouse (vert)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[..., 0] >= h_range[0]) & (hsv[..., 0] <= h_range[1])
            & (hsv[..., 1] >= s_min) & (hsv[..., 2] >= v_min))


def skin_mask(bgr: np.ndarray) -> np.ndarray:
    """Masque True = peau (YCrCb), toutes carnations approximativement."""
    ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    cr, cb = ycc[..., 1], ycc[..., 2]
    return (cr >= 135) & (cr <= 175) & (cb >= 80) & (cb <= 130)


def dominant_lab(bgr_crop: np.ndarray, k: int = 2, min_pixels: int = 30) -> tuple[np.ndarray, float] | None:
    """Couleur dominante (Lab) d'un recadrage, pelouse et peau retirées.

    K-means (k=2) en Lab : le plus gros cluster = maillot (l'autre absorbe
    numéros, ombres, bords). Retourne (lab, part_du_cluster) ou None.
    """
    if bgr_crop is None or bgr_crop.size == 0:
        return None
    mask = ~(grass_mask(bgr_crop) | skin_mask(bgr_crop))
    pix = bgr_crop[mask]
    if len(pix) < min_pixels:
        return None
    lab = bgr_to_lab(pix.reshape(-1, 3)).astype(np.float32)
    if len(lab) > 1500:  # sous-échantillonnage : K-means rapide
        idx = np.random.default_rng(0).choice(len(lab), 1500, replace=False)
        lab = lab[idx]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 15, 0.5)
    k = min(k, len(lab))
    _, labels, centers = cv2.kmeans(lab, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    best = int(np.argmax(counts))
    return centers[best].astype(np.float32), float(counts[best] / counts.sum())
