"""Détecteur YOLO (Ultralytics) exporté en ONNX, exécuté par ONNX Runtime.

- Classes : player, goalkeeper, referee, ball. AUCUNE classe « équipe ».
- 1080p natif : soit par tuiles (tile_size × tile_size avec recouvrement),
  soit en entrée native (modèle exporté en imgsz=1920, dynamique).
  JAMAIS d'image réduite à 640 px : la balle et les curseurs y disparaissent.
- Repli tant que le modèle maison n'existe pas : un YOLO COCO (yolo11n.onnx)
  fonctionne, « person » -> player et « sports ball » -> ball.
"""

from __future__ import annotations

import ast
import logging
import time
from pathlib import Path

import cv2
import numpy as np

from fccoach.vision.types import CLASSES, Detection

log = logging.getLogger(__name__)

_COCO_MAP = {0: "player", 32: "ball"}  # person, sports ball


def tile_grid(width: int, height: int, tile: int, overlap: int) -> list[tuple[int, int]]:
    """Origines (x, y) des tuiles couvrant toute l'image, sans redimensionnement."""
    def axis(size: int) -> list[int]:
        if size <= tile:
            return [0]
        step = tile - overlap
        pos = list(range(0, size - tile, step))
        pos.append(size - tile)
        return sorted(set(pos))
    return [(x, y) for y in axis(height) for x in axis(width)]


class YoloOnnxDetector:
    def __init__(self, model_path: str | Path, providers: list[str], mode: str = "tiles",
                 tile_size: int = 640, tile_overlap: int = 96, conf: float = 0.3, iou: float = 0.5,
                 roi: list[float] | None = None) -> None:
        import onnxruntime as ort

        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Modèle ONNX introuvable : {model_path}. Exporte-le avec scripts/export_onnx.py "
                "(ou un YOLO COCO en attendant le modèle maison)."
            )
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(model_path), sess_options=so, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.fixed_hw = (shape[2], shape[3]) if isinstance(shape[2], int) and isinstance(shape[3], int) else None
        self.fp16 = "float16" in self.session.get_inputs()[0].type
        self.mode = mode
        self.tile = tile_size if self.fixed_hw is None else int(self.fixed_hw[0])
        self.overlap = tile_overlap
        self.conf = conf
        self.iou = iou
        self.roi = roi or [0.0, 0.0, 1.0, 1.0]
        self.names = self._read_names()
        self.class_map = self._build_class_map()
        log.info("Détecteur chargé : %s | fournisseur %s | mode %s | classes %s",
                 model_path.name, self.session.get_providers()[0], mode, sorted(set(self.class_map.values())))
        if mode == "native" and self.fixed_hw is not None and max(self.fixed_hw) < 1920:
            log.warning("Modèle à entrée fixe %s : mode « native » impossible sans réduire l'image, "
                        "passage en mode tuiles", self.fixed_hw)
            self.mode = "tiles"

    def _read_names(self) -> dict[int, str]:
        meta = self.session.get_modelmeta().custom_metadata_map
        if "names" in meta:
            try:
                return {int(k): str(v) for k, v in ast.literal_eval(meta["names"]).items()}
            except Exception:
                pass
        return {}

    def _build_class_map(self) -> dict[int, str]:
        if self.names and all(n in CLASSES for n in self.names.values()):
            return {i: n for i, n in self.names.items()}
        if self.names.get(0) == "person":
            log.warning("Modèle COCO détecté : mode repli (person -> player, sports ball -> ball). "
                        "Gardiens/arbitre non distingués tant que le modèle maison n'est pas entraîné.")
            return dict(_COCO_MAP)
        if not self.names:
            log.warning("Noms de classes absents du modèle : ordre supposé %s", CLASSES)
            return dict(enumerate(CLASSES))
        # Noms partiellement compatibles : on garde ce qui correspond
        return {i: n for i, n in self.names.items() if n in CLASSES}

    # ------------------------------------------------------------------
    def _prep(self, img: np.ndarray, size_hw: tuple[int, int]) -> np.ndarray:
        """Padding (sans redimensionnement) à size_hw, BGR->RGB, NCHW float."""
        h, w = img.shape[:2]
        th, tw = size_hw
        if (h, w) != (th, tw):
            img = cv2.copyMakeBorder(img, 0, th - h, 0, tw - w, cv2.BORDER_CONSTANT, value=(114, 114, 114))
        blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float16 if self.fp16 else np.float32) / 255.0
        return np.ascontiguousarray(blob)

    def _infer(self, batch: np.ndarray) -> np.ndarray:
        out = self.session.run(None, {self.input_name: batch})[0]
        return out.astype(np.float32)  # (B, 4+nc, N)

    def _decode(self, pred: np.ndarray, ox: int, oy: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pred = pred.T  # (N, 4+nc)
        scores_all = pred[:, 4:]
        cls = scores_all.argmax(1)
        scores = scores_all[np.arange(len(cls)), cls]
        keep = (scores >= self.conf) & np.isin(cls, list(self.class_map))
        pred, cls, scores = pred[keep], cls[keep], scores[keep]
        xywh = pred[:, :4]
        boxes = np.stack([xywh[:, 0] - xywh[:, 2] / 2 + ox, xywh[:, 1] - xywh[:, 3] / 2 + oy,
                          xywh[:, 0] + xywh[:, 2] / 2 + ox, xywh[:, 1] + xywh[:, 3] / 2 + oy], 1)
        return boxes, scores, cls

    def detect(self, image: np.ndarray) -> list[Detection]:
        H, W = image.shape[:2]
        rx0, ry0 = int(self.roi[0] * W), int(self.roi[1] * H)
        rx1, ry1 = int(self.roi[2] * W), int(self.roi[3] * H)
        roi = image[ry0:ry1, rx0:rx1]
        rh, rw = roi.shape[:2]
        all_b, all_s, all_c = [], [], []
        if self.mode == "native":
            th, tw = (int(np.ceil(rh / 32) * 32), int(np.ceil(rw / 32) * 32))
            pred = self._infer(self._prep(roi, (th, tw)))[0]
            b, s, c = self._decode(pred, rx0, ry0)
            all_b.append(b), all_s.append(s), all_c.append(c)
        else:
            origins = tile_grid(rw, rh, self.tile, self.overlap)
            tiles = [roi[y:y + self.tile, x:x + self.tile] for x, y in origins]
            for (x, y), t in zip(origins, tiles):
                pred = self._infer(self._prep(t, (self.tile, self.tile)))[0]
                b, s, c = self._decode(pred, rx0 + x, ry0 + y)
                all_b.append(b), all_s.append(s), all_c.append(c)
        boxes = np.concatenate(all_b) if all_b else np.zeros((0, 4))
        scores = np.concatenate(all_s) if all_s else np.zeros(0)
        cls = np.concatenate(all_c) if all_c else np.zeros(0, int)
        dets: list[Detection] = []
        for c in np.unique(cls):
            m = cls == c
            b, s = boxes[m], scores[m]
            xywh = np.stack([b[:, 0], b[:, 1], b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]], 1)
            idx = cv2.dnn.NMSBoxes(xywh.tolist(), s.tolist(), self.conf, self.iou)
            for i in np.array(idx).reshape(-1):
                x1, y1, x2, y2 = b[i]
                dets.append(Detection(float(max(0, x1)), float(max(0, y1)), float(min(W, x2)),
                                      float(min(H, y2)), float(s[i]), self.class_map[int(c)]))
        return dets

    def benchmark(self, image: np.ndarray, n: int = 30) -> float:
        """Latence moyenne (s) d'une détection complète sur une image 1080p."""
        self.detect(image)  # chauffe (allocation GPU, compilation)
        t0 = time.perf_counter()
        for _ in range(n):
            self.detect(image)
        return (time.perf_counter() - t0) / n
