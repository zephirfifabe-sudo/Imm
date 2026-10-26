"""Clip synthétique « vue télé » : lignes en perspective, caméra qui panote, 2 équipes,
curseurs, ballon qui circule. L'index d'image est codé dans un coin pour le faux détecteur."""

from __future__ import annotations

import cv2
import numpy as np

from fccoach.analysis.formation import TEMPLATES
from fccoach.tracking.homography import project
from fccoach.vision.types import Detection
from tests.synth import draw_cursor, draw_player
from tests.synth_pitch import camera, render

BLUE, WHITE, RED, BLACK = (200, 60, 20), (240, 240, 240), (40, 40, 210), (30, 30, 30)


def encode_index(img: np.ndarray, i: int) -> None:
    for k, v in enumerate((i // 256 % 16, i // 16 % 16, i % 16)):
        img[0:40, 40 * k:40 * k + 40] = v * 16 + 8


def decode_index(img: np.ndarray) -> int:
    d = [int(round((img[5:35, 40 * k + 5:40 * k + 35].mean() - 8) / 16)) for k in range(3)]
    return d[0] * 256 + d[1] * 16 + d[2]


class SynthMatch:
    def __init__(self, n: int = 150, fps: int = 15) -> None:
        self.n, self.fps = n, fps
        self.me = [[x, y] for x, y, _ in TEMPLATES["41212"]]
        self.opp = [[-x, -y] for x, y, _ in TEMPLATES["4213"]]
        self.truth: dict[int, list[Detection]] = {}

    def state(self, i: int) -> tuple[np.ndarray, list, list, list[float], int]:
        t = i / self.fps
        drift = 4 * np.sin(t / 3)
        me = [[x + drift, y] for x, y in self.me]
        opp = [[x + drift, y] for x, y in self.opp]
        # Le ballon passe de mon MDC (4) à mon MC (5) puis à mon MC (6), en boucle
        seq = [4, 5, 6, 7]
        k, frac = divmod(t / 2.0, 1.0)
        a, b = me[seq[int(k) % 4]], me[seq[(int(k) + 1) % 4]]
        f = min(1.0, max(0.0, (frac - 0.6) / 0.3))   # possession puis passe rapide
        ball = [a[0] + (b[0] - a[0]) * f + 0.8, a[1] + (b[1] - a[1]) * f]
        H = camera(-18 + 6 * np.sin(t / 4), 1.0)
        return H, me, opp, ball, seq[int(k) % 4]

    def frame(self, i: int) -> np.ndarray:
        H, me, opp, ball, holder = self.state(i)
        img = render(H)
        dets = []
        for team, pts, shirt, shorts in (("me", me, BLUE, WHITE), ("opp", opp, RED, BLACK)):
            px = project(H, np.array(pts))
            for j, (x, y) in enumerate(px):
                if not (20 < x < 1900 and 120 < y < 1075):
                    continue
                h = int(40 + 50 * (y / 1080))
                d = draw_player(img, int(x), int(y - h), shirt, shorts, w=max(14, h // 3), h=h)
                dets.append(d)
                if team == "me" and j == holder:
                    draw_cursor(img, int(x), int(y - h - 6), (30, 30, 230), size=max(12, h // 5))
        bx, by = project(H, np.array([ball]))[0]
        cv2.circle(img, (int(bx), int(by)), 6, (255, 255, 255), -1)
        dets.append(Detection(bx - 6, by - 6, bx + 6, by + 6, 0.8, "ball"))
        encode_index(img, i)
        self.truth[i] = dets
        return img

    def write(self, path) -> None:
        out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), self.fps, (1920, 1080))
        for i in range(self.n):
            out.write(self.frame(i))
        out.release()


class TruthDetector:
    """Faux détecteur : renvoie les boîtes exactes de l'image (index lu dans le coin)."""
    mode = "vérité"

    def __init__(self, sim: SynthMatch) -> None:
        self.sim = sim

    def detect(self, img):
        i = decode_index(img)
        return [Detection(d.x1, d.y1, d.x2, d.y2, d.score, d.cls) for d in self.sim.truth.get(i, [])]
