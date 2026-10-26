"""Entraînement YOLO (Ultralytics) + export ONNX + rapport de précision par classe.

Fonctionne sur le PC (GPU Nvidia conseillé) ou sur Google Colab si le PC est
trop faible :
    !pip install ultralytics onnx
    !python scripts/train_yolo.py --data data/dataset/data.yaml --size n --epochs 120

- Modèle nano (n) par défaut, small (s) ou medium (m) pour l'option « précision ».
- imgsz 640 : le modèle travaille par TUILES de 640 px découpées dans le 1080p
  natif (pas d'image réduite). Avec --imgsz 1920 : mode « native ».
- Augmentation teinte/saturation activée (hsv_h, hsv_s) en plus de build_dataset.py.
- Rapport : précision / rappel / mAP par classe -> reports/detector_<nom>.json
  (le taux d'erreur d'attribution d'équipe est mesuré à part par eval_phase1.py).
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/dataset/data.yaml")
    ap.add_argument("--size", default="n", choices=["n", "s", "m"])
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=-1, help="-1 = automatique selon la VRAM")
    ap.add_argument("--device", default=None, help="0, cpu, mps… (auto par défaut)")
    ap.add_argument("--name", default=None)
    args = ap.parse_args()

    from ultralytics import YOLO

    name = args.name or f"fc_yolo_{args.size}"
    model = YOLO(f"yolo11{args.size}.pt")
    model.train(
        data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device=args.device,
        name=name, project="runs", exist_ok=True,
        hsv_h=0.1, hsv_s=0.7, hsv_v=0.3,   # variations de teinte/saturation (maillots)
        fliplr=0.5, mosaic=1.0, scale=0.3,  # pas de réduction massive : objets petits
        close_mosaic=10, patience=30,
    )
    best = Path("runs") / name / "weights" / "best.pt"
    trained = YOLO(str(best))
    metrics = trained.val(data=args.data, imgsz=args.imgsz, split="val")
    names = trained.names
    report = {"model": name, "imgsz": args.imgsz, "classes": {}}
    p, r, ap50, ap = metrics.box.p, metrics.box.r, metrics.box.ap50, metrics.box.ap
    for i, cls_idx in enumerate(metrics.box.ap_class_index):
        report["classes"][names[int(cls_idx)]] = {
            "precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
            "mAP50": round(float(ap50[i]), 4), "mAP50-95": round(float(ap[i]), 4),
        }
    report["all"] = {"mAP50": round(float(metrics.box.map50), 4), "mAP50-95": round(float(metrics.box.map), 4)}
    Path("reports").mkdir(exist_ok=True)
    out = Path("reports") / f"detector_{name}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nPrécision par classe (validation = maillots jamais vus) :")
    for c, m in report["classes"].items():
        print(f"  {c:<11} P={m['precision']:.3f}  R={m['recall']:.3f}  mAP50={m['mAP50']:.3f}")
    print(f"Rapport : {out}")

    onnx_path = trained.export(format="onnx", imgsz=args.imgsz, dynamic=args.imgsz != 640, simplify=True, opset=17)
    Path("models").mkdir(exist_ok=True)
    dst = Path("models") / f"{name}.onnx"
    shutil.copy2(onnx_path, dst)
    print(f"Modèle ONNX : {dst} (à référencer dans config.yaml > detector.model)")


if __name__ == "__main__":
    main()
