"""PHASE 1 — Benchmark de TA machine : vitesse de la détection, des curseurs et de l'OCR.

    python scripts/benchmark.py                       # image de la carte de capture
    python scripts/benchmark.py --image data/raw/x/h1/x__h1__00000.jpg
    python scripts/benchmark.py --source match.mp4 --frames 60

Affiche l'accélérateur choisi (CUDA > DirectML/ROCm > OpenVINO > CPU), la
latence de chaque étage et la cadence de détection recommandée (60/30/15/10).
Rapport : reports/benchmark.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fccoach.capture.source import open_source  # noqa: E402
from fccoach.core.config import load_config, load_yaml, resolve_path  # noqa: E402
from fccoach.core.hardware import choose_model, detect_hardware, recommend_cadence  # noqa: E402
from fccoach.core.logging_setup import setup_logging  # noqa: E402
from fccoach.ocr.engines import create_engine  # noqa: E402
from fccoach.ocr.zones import load_zones, preprocess  # noqa: E402
from fccoach.vision.cursor import CursorDetector  # noqa: E402


def grab_frame(args, cfg) -> np.ndarray:
    if args.image:
        img = cv2.imread(args.image)
        if img is None:
            raise SystemExit(f"Image illisible : {args.image}")
        return img
    try:
        cap, _ = open_source(args.source if args.source is not None else cfg.capture.source)
        for _ in range(10):  # laisser la carte se stabiliser
            ok, img = cap.read()
        cap.release()
        if ok:
            return img
    except Exception as exc:
        print(f"Source vidéo indisponible ({exc}) : image synthétique 1080p")
    rng = np.random.default_rng(0)
    img = np.full((1080, 1920, 3), (40, 130, 50), np.uint8)
    img += rng.integers(0, 20, img.shape, dtype=np.uint8)
    return img


def timeit(fn, n: int) -> float:
    fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) / n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--source")
    ap.add_argument("--image")
    ap.add_argument("--frames", type=int, default=30)
    args = ap.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging)
    hw = detect_hardware(cfg.hardware.accelerator)
    img = grab_frame(args, cfg)
    print(f"\nImage de test : {img.shape[1]}x{img.shape[0]}")
    report: dict = {"accelerator": hw.accelerator, "description": hw.description, "providers": hw.available}

    # Détection
    from fccoach.vision.detector import YoloOnnxDetector

    model = choose_model(hw, cfg.detector.model, cfg.detector.model_precision, cfg.detector.precision_mode)
    try:
        d = cfg.detector
        det = YoloOnnxDetector(resolve_path(model), hw.providers, d.mode, d.tile_size, d.tile_overlap,
                               d.conf_threshold, d.iou_threshold, d.roi)
        lat = det.benchmark(img, args.frames)
        rec = recommend_cadence(lat, cfg.hardware.cadence_steps, cfg.hardware.budget_ratio)
        report["detector"] = {"model": model, "mode": det.mode, "latency_ms": round(lat * 1000, 1),
                              "max_fps": round(1 / lat, 1), "recommended_fps": rec,
                              "detections_on_test_image": len(det.detect(img))}
        print(f"Détection : {lat * 1000:.1f} ms/image ({1 / lat:.1f} i/s max) -> cadence recommandée {rec} i/s")
        if rec <= 15:
            print("  Conseil : modèle nano, mode tuiles, ou entraînement sur Colab + GPU. "
                  "Les conseils en direct restent possibles (ils n'ont pas besoin de 60 analyses/s).")
    except Exception as exc:
        print(f"Détection non mesurée : {exc}")
        report["detector"] = {"error": str(exc)}

    # Curseurs (sur CPU, toujours)
    cur = CursorDetector(load_yaml(cfg.cursor.config_file))
    lat_c = timeit(lambda: cur.detect(img, None), args.frames)
    report["cursor_ms"] = round(lat_c * 1000, 2)
    print(f"Curseurs  : {lat_c * 1000:.1f} ms/image ({1 / lat_c:.0f} i/s max)")

    # OCR
    engine = create_engine(cfg.ocr.engine, hw.is_gpu, cfg.ocr.tesseract_cmd)
    report["ocr_engine"] = engine.name
    report["ocr_ms"] = {}
    zones = load_zones(resolve_path(cfg.ocr.zones_file)) if engine.name != "aucun" else {}
    if not zones:
        print("OCR       : aucun moteur installé (voir README > Tesseract)")
    for name, z in zones.items():
        if z.mode == "relative":
            continue
        crop = z.crop(img)
        if crop is None:
            continue
        pre = preprocess(crop, z.preprocess)
        lat_o = timeit(lambda: engine.read(pre, z.whitelist), 3)
        report["ocr_ms"][name] = round(lat_o * 1000, 1)
        print(f"OCR {name:<16}: {lat_o * 1000:.1f} ms -> « {engine.read(pre, z.whitelist)} »")

    Path("reports").mkdir(exist_ok=True)
    Path("reports/benchmark.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nRapport : reports/benchmark.json")


if __name__ == "__main__":
    main()
