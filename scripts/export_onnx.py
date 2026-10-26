"""Exporte un modèle YOLO Ultralytics (.pt) en ONNX.

Modèle de départ (avant d'avoir entraîné le tien) — YOLO COCO nano :
    pip install ultralytics onnx
    python scripts/export_onnx.py --weights yolo11n.pt --out models/fc_yolo_n.onnx

Le logiciel reconnaît un modèle COCO et passe en mode repli
(person -> player, sports ball -> ball).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", default="yolo11n.pt")
    ap.add_argument("--out", default="models/fc_yolo_n.onnx")
    ap.add_argument("--imgsz", type=int, default=640, help="640 = tuiles ; 1920 = entrée native dynamique")
    ap.add_argument("--half", action="store_true", help="FP16 (GPU Nvidia uniquement)")
    args = ap.parse_args()

    from ultralytics import YOLO

    path = YOLO(args.weights).export(format="onnx", imgsz=args.imgsz, dynamic=args.imgsz != 640,
                                     simplify=True, opset=17, half=args.half)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, args.out)
    print(f"Exporté : {args.out}")


if __name__ == "__main__":
    main()
