"""Moteurs OCR interchangeables : PaddleOCR (GPU ou CPU costaud) ou Tesseract.

Sélection « auto » : PaddleOCR si installé ET un GPU est détecté, sinon
Tesseract, sinon moteur nul (le logiciel tourne quand même, sans OCR).
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class OcrEngine(Protocol):
    name: str

    def read(self, image: np.ndarray, whitelist: str = "") -> str: ...


class NullEngine:
    name = "aucun"

    def read(self, image: np.ndarray, whitelist: str = "") -> str:
        return ""


class TesseractEngine:
    name = "tesseract"

    def __init__(self, cmd: str = "") -> None:
        import pytesseract

        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        pytesseract.get_tesseract_version()  # lève une erreur si absent
        self._tess = pytesseract

    def read(self, image: np.ndarray, whitelist: str = "") -> str:
        # psm 7 = une seule ligne de texte (chrono, score, nom)
        cfg = "--psm 7 --oem 1"
        if whitelist:
            cfg += f" -c tessedit_char_whitelist={whitelist}"
        return self._tess.image_to_string(image, config=cfg).strip()


class PaddleEngine:
    name = "paddleocr"

    def __init__(self, use_gpu: bool) -> None:
        from paddleocr import PaddleOCR

        try:
            self._ocr = PaddleOCR(use_angle_cls=False, lang="fr", use_gpu=use_gpu, show_log=False)
        except TypeError:  # PaddleOCR >= 3 : API simplifiée
            self._ocr = PaddleOCR(lang="fr")

    def read(self, image: np.ndarray, whitelist: str = "") -> str:
        if image.ndim == 2:
            image = np.stack([image] * 3, axis=-1)
        try:
            res = self._ocr.ocr(image, det=False, cls=False)
            texts = [r[0] for line in (res or []) for r in (line or [])]
        except TypeError:
            res = self._ocr.predict(image)
            texts = [t for r in (res or []) for t in r.get("rec_texts", [])]
        text = " ".join(str(t) for t in texts).strip()
        if whitelist:
            text = "".join(c for c in text if c in whitelist or c == " ")
        return text


def create_engine(kind: str, is_gpu: bool, tesseract_cmd: str = "") -> OcrEngine:
    order: list[str]
    if kind == "auto":
        order = ["paddle", "tesseract"] if is_gpu else ["tesseract", "paddle"]
    else:
        order = [kind]
    for k in order:
        try:
            if k == "paddle":
                eng: OcrEngine = PaddleEngine(use_gpu=is_gpu)
            elif k == "tesseract":
                eng = TesseractEngine(tesseract_cmd)
            elif k == "none":
                return NullEngine()
            else:
                continue
            log.info("Moteur OCR : %s", eng.name)
            return eng
        except Exception as exc:
            log.info("OCR %s indisponible : %s", k, exc)
    log.warning("Aucun moteur OCR disponible : chrono/score non lus (installe Tesseract, voir README)")
    return NullEngine()
