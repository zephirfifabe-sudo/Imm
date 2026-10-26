"""Homographie image -> terrain 2D, recalculée automatiquement quand la caméra bouge.

1. Calibration initiale : au moins 4 points nommés du terrain cliqués une fois
   dans le dashboard (page « Calibration »). Elle est enregistrée avec le
   masque des lignes de l'image de référence et resservira aux matchs
   suivants tant que le réglage de caméra ne change pas.
2. Suivi automatique : à chaque mise à jour, le masque des lignes blanches
   de l'image courante est aligné (ECC, mouvement homographique) sur une
   image clé dont l'homographie est connue. Panoramique, zoom ou caméra qui
   suit le ballon : l'homographie est recalculée à partir des lignes, et
   l'image clé est renouvelée quand le recouvrement baisse.
3. Perte (ralenti, plan serré, menu) : statut « perdue », plus aucune
   position terrain ; on revient dès que les lignes s'alignent de nouveau
   sur l'image clé ou sur la référence de calibration.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from fccoach.tracking.pitch import HL, HW, KEYPOINTS
from fccoach.vision.color import grass_mask

log = logging.getLogger(__name__)

SMALL = (480, 270)  # résolution de travail de l'alignement (le 1080p sert au reste)


def line_mask(image: np.ndarray, size: tuple[int, int] = SMALL) -> np.ndarray:
    """Lignes blanches du terrain (blanc entouré de pelouse), flouté pour l'ECC."""
    small = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    white = (hsv[..., 1] < 70) & (hsv[..., 2] > 150)
    near_grass = cv2.dilate(grass_mask(small).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    m = (white & near_grass).astype(np.float32)
    return cv2.GaussianBlur(m, (0, 0), 1.5)


def homography_from_points(img_pts: np.ndarray, pitch_pts: np.ndarray) -> tuple[np.ndarray, float]:
    """H (image -> terrain) et erreur moyenne de reprojection (mètres)."""
    img_pts = np.asarray(img_pts, np.float32)
    pitch_pts = np.asarray(pitch_pts, np.float32)
    if len(img_pts) < 4:
        raise ValueError("au moins 4 points sont nécessaires")
    H, _ = cv2.findHomography(img_pts, pitch_pts, cv2.RANSAC if len(img_pts) > 4 else 0, 2.0)
    if H is None:
        raise ValueError("points incohérents (alignés ou mal placés)")
    proj = cv2.perspectiveTransform(img_pts[None], H)[0]
    return H, float(np.linalg.norm(proj - pitch_pts, axis=1).mean())


def project(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, np.float64).reshape(-1, 1, 2)
    if len(pts) == 0:
        return np.zeros((0, 2))
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


@dataclass
class Calibration:
    points: list[dict] = field(default_factory=list)   # [{"name": ..., "px": [x, y]}]
    H: np.ndarray | None = None
    error_m: float | None = None
    ref_mask: np.ndarray | None = None
    created: float = 0.0

    @staticmethod
    def from_points(points: list[dict], image: np.ndarray | None) -> "Calibration":
        names = [p["name"] for p in points]
        unknown = [n for n in names if n not in KEYPOINTS]
        if unknown:
            raise ValueError(f"points inconnus : {unknown}")
        if len(set(names)) != len(names):
            raise ValueError("chaque point ne doit être utilisé qu'une fois")
        H, err = homography_from_points([p["px"] for p in points], [KEYPOINTS[n] for n in names])
        if err > 2.5:
            raise ValueError(f"calibration imprécise ({err:.1f} m d'erreur) : vérifie les points cliqués")
        return Calibration(points, H, err, line_mask(image) if image is not None else None, time.time())

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"points": self.points, "error_m": self.error_m, "created": self.created},
                                   indent=1, ensure_ascii=False), encoding="utf-8")
        if self.ref_mask is not None:
            cv2.imwrite(str(path.with_suffix(".png")), (np.clip(self.ref_mask, 0, 1) * 255).astype(np.uint8))

    @staticmethod
    def load(path: str | Path) -> "Calibration | None":
        path = Path(path)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        cal = Calibration.from_points(data["points"], None)
        cal.created = data.get("created", 0.0)
        png = path.with_suffix(".png")
        if png.exists():
            m = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
            if m is not None:
                cal.ref_mask = cv2.resize(m, SMALL).astype(np.float32) / 255.0
        return cal


class HomographyTracker:
    def __init__(self, calibration: Calibration | None = None, cc_min: float = 0.55,
                 lost_after_s: float = 1.0) -> None:
        self.cc_min = cc_min
        self.lost_after_s = lost_after_s
        sx, sy = SMALL[0] / 1920, SMALL[1] / 1080
        self._S = np.diag([sx, sy, 1.0])
        self._Si = np.linalg.inv(self._S)
        self.calibration: Calibration | None = None
        self.H: np.ndarray | None = None
        self.status = "non calibré"
        self.cc = 0.0
        self._key_mask: np.ndarray | None = None
        self._key_H: np.ndarray | None = None
        self._last_M = np.eye(3)            # dernier mouvement de caméra (image précédente -> courante)
        self._last_ok: float | None = None
        if calibration is not None:
            self.set_calibration(calibration)

    def set_calibration(self, cal: Calibration) -> None:
        self.calibration = cal
        self.H = cal.H
        self._key_mask = cal.ref_mask
        self._key_H = cal.H
        self._last_M = np.eye(3)
        self.status = "ok" if cal.ref_mask is not None else "recherche"
        self._last_ok: float | None = None   # fixé à la première mise à jour (horloge de l'appelant)
        log.info("Calibration du terrain chargée (%d points, erreur %.2f m)", len(cal.points), cal.error_m or 0)

    @property
    def ok(self) -> bool:
        return self.H is not None and self.status == "ok"

    def _ecc(self, template: np.ndarray, current: np.ndarray, init: np.ndarray) -> tuple[float, np.ndarray] | None:
        """ECC en pyramide (grossier -> fin) : supporte les grands panoramiques."""
        crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-6)
        W = init.astype(np.float32).copy()
        cc = 0.0
        for factor, sigma in ((0.25, 2.0), (0.5, 1.5), (1.0, 0.0)):
            D = np.diag([factor, factor, 1.0]).astype(np.float32)
            Wl = D @ W @ np.linalg.inv(D)
            size = (int(SMALL[0] * factor), int(SMALL[1] * factor))
            t = cv2.resize(template, size, interpolation=cv2.INTER_AREA)
            c = cv2.resize(current, size, interpolation=cv2.INTER_AREA)
            if sigma:
                t, c = cv2.GaussianBlur(t, (0, 0), sigma), cv2.GaussianBlur(c, (0, 0), sigma)
            try:
                cc, Wl = cv2.findTransformECC(t, c, Wl.astype(np.float32), cv2.MOTION_HOMOGRAPHY, crit, None, 1)
            except cv2.error:
                return None
            W = np.linalg.inv(D) @ Wl @ D
        return float(cc), W.astype(np.float32)

    def _H_from(self, key_H: np.ndarray, W: np.ndarray) -> np.ndarray:
        # W : coordonnées image clé (réduites) -> image courante (réduites)
        M = self._Si @ W.astype(np.float64) @ self._S
        return key_H @ np.linalg.inv(M)

    @staticmethod
    def _sane(H: np.ndarray) -> bool:
        """Le centre et le bas de l'image doivent tomber sur (ou près du) terrain."""
        pts = project(H, np.array([[960, 540], [960, 1000], [200, 700], [1720, 700]]))
        return bool(np.all(np.isfinite(pts)) and np.all(np.abs(pts[:, 0]) < HL + 25) and np.all(np.abs(pts[:, 1]) < HW + 25))

    def _plausible(self, H: np.ndarray, max_jump_m: float = 15.0) -> bool:
        """La caméra ne saute pas de plus de 15 m entre deux mises à jour."""
        if self._key_H is None:
            return True
        c = np.array([[960.0, 540.0]])
        return float(np.linalg.norm(project(H, c) - project(self._key_H, c))) < max_jump_m

    def update(self, image: np.ndarray, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now
        if self.calibration is None:
            self.status = "non calibré"
            return self.status
        cur = line_mask(image)
        if cur.mean() < 0.002:   # presque aucune ligne : plan serré, menu, ralenti
            return self._fail(now)
        if self._key_mask is None:   # calibration chargée sans masque : l'image courante devient la clé
            self._key_mask, self._key_H = cur, self.calibration.H
        # Image clé = dernière image alignée ; départ = mouvement de caméra précédent
        # (un panoramique continue généralement dans le même sens).
        init = (self._S @ self._last_M @ self._Si).astype(np.float32)
        res = self._ecc(self._key_mask, cur, init)
        if res is not None and res[0] >= self.cc_min:
            H = self._H_from(self._key_H, res[1])
            if self._sane(H) and self._plausible(H):
                self._last_M = self._Si @ res[1].astype(np.float64) @ self._S
                self.cc, self.H = res[0], H
                self._key_mask, self._key_H = cur, H
                return self._ok(now)
        # Repli : retour à la vue de référence de la calibration (après un ralenti, etc.)
        ref = self.calibration.ref_mask
        if ref is not None:
            res = self._ecc(ref, cur, np.eye(3, dtype=np.float32))
            if res is not None and res[0] >= self.cc_min:
                H = self._H_from(self.calibration.H, res[1])
                if self._sane(H):
                    self._key_mask, self._key_H, self._last_M = cur, H, np.eye(3)
                    self.cc, self.H = res[0], H
                    return self._ok(now)
        self._last_M = np.eye(3)
        return self._fail(now)

    def _ok(self, now: float) -> str:
        if self.status != "ok":
            log.info("Homographie retrouvée (corrélation %.2f)", self.cc)
        self.status = "ok"
        self._last_ok = now
        return self.status

    def _fail(self, now: float) -> str:
        if self._last_ok is None:
            self._last_ok = now
        if now - self._last_ok > self.lost_after_s:
            if self.status == "ok":
                log.info("Homographie perdue (ralenti, plan serré ou caméra changée)")
            self.status = "perdue"
            self.H = None
        return self.status

    def to_pitch(self, pts: np.ndarray) -> np.ndarray | None:
        return None if self.H is None else project(self.H, pts)

    def to_image(self, pts: np.ndarray) -> np.ndarray | None:
        return None if self.H is None else project(np.linalg.inv(self.H), pts)
