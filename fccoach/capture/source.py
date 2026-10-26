"""Ouverture de la source vidéo (carte de capture, caméra virtuelle OBS, fichier).

Lecture seule : aucune commande n'est jamais envoyée à la console.
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path

import cv2

log = logging.getLogger(__name__)

_BACKENDS = {
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
    "v4l2": cv2.CAP_V4L2,
    "any": cv2.CAP_ANY,
}


def parse_source(source: int | str) -> int | str:
    """'0' -> 0 (périphérique), sinon chemin de fichier/URL."""
    if isinstance(source, int):
        return source
    s = str(source).strip()
    return int(s) if s.isdigit() else s


def open_source(source: int | str, backend: str = "auto", width: int = 1920, height: int = 1080,
                fps: int = 60, fourcc: str = "MJPG") -> tuple[cv2.VideoCapture, bool]:
    """Ouvre la source. Retourne (capture, est_un_fichier)."""
    src = parse_source(source)
    is_file = isinstance(src, str)
    if is_file:
        if not Path(src).exists() and "://" not in src:
            raise FileNotFoundError(f"Vidéo introuvable : {src}")
        cap = cv2.VideoCapture(src)
    else:
        if backend == "auto":
            # Sous Windows, DirectShow expose la caméra virtuelle OBS et la plupart des cartes
            api = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        else:
            api = _BACKENDS.get(backend, cv2.CAP_ANY)
        cap = cv2.VideoCapture(src, api)
        if fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc[:4]))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # toujours l'image la plus récente
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la source vidéo : {source!r}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    f = cap.get(cv2.CAP_PROP_FPS)
    log.info("Source vidéo ouverte : %s | %dx%d @ %.1f i/s", source, w, h, f)
    if (w, h) != (1920, 1080):
        log.warning("Résolution %dx%d (attendu 1920x1080) : vérifie la carte de capture / OBS. "
                    "Les zones OCR et seuils curseurs sont calés sur du 1080p.", w, h)
    return cap, is_file
