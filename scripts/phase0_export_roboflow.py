"""PHASE 0 — Export des frames vers Roboflow.

Deux usages :
  1. Préparer un dossier d'upload (glisser-déposer dans Roboflow) :
       python scripts/phase0_export_roboflow.py --out data/roboflow_upload
  2. Upload direct des images via l'API Roboflow (pip install roboflow),
     avec tags combinaison / mi-temps / clash :
       set ROBOFLOW_API_KEY=xxxx
       python scripts/phase0_export_roboflow.py --upload --workspace moi --project fc-coach

Option --preannotate models/yolo11n.onnx : pré-annotations YOLO (person ->
player, sports ball -> ball) pour gagner du temps ; à CORRIGER dans
Roboflow (gardiens, arbitre, balle masquée).

Classes à annoter (ordre fixe) : player, goalkeeper, referee, ball.
AUCUNE classe d'équipe.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fccoach.vision.types import CLASSES  # noqa: E402


def collect(raw: Path) -> list[dict]:
    items = []
    for meta in sorted(raw.glob("*/h*/metadata.jsonl")):
        for line in meta.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            m = json.loads(line)
            img = meta.parent / m["file"]
            if img.exists():
                m["path"] = img
                items.append(m)
    return items


def preannotate(items: list[dict], model: str, labels_dir: Path) -> None:
    from fccoach.core.hardware import detect_hardware
    from fccoach.vision.detector import YoloOnnxDetector

    hw = detect_hardware()
    det = YoloOnnxDetector(model, hw.providers, mode="tiles", conf=0.35)
    labels_dir.mkdir(parents=True, exist_ok=True)
    for i, m in enumerate(items):
        img = cv2.imread(str(m["path"]))
        H, W = img.shape[:2]
        lines = []
        for d in det.detect(img):
            c = CLASSES.index(d.cls)
            lines.append(f"{c} {d.cx / W:.6f} {((d.y1 + d.y2) / 2) / H:.6f} {d.w / W:.6f} {d.h / H:.6f}")
        (labels_dir / (Path(m["file"]).stem + ".txt")).write_text("\n".join(lines), encoding="utf-8")
        if i % 50 == 0:
            print(f"  pré-annotation {i}/{len(items)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/roboflow_upload")
    ap.add_argument("--preannotate", help="modèle ONNX pour pré-annoter (optionnel)")
    ap.add_argument("--upload", action="store_true", help="envoyer via l'API Roboflow")
    ap.add_argument("--workspace")
    ap.add_argument("--project")
    args = ap.parse_args()

    items = collect(Path(args.raw))
    if not items:
        raise SystemExit(f"Aucune image dans {args.raw} : lance d'abord phase0_capture_frames.py")
    combos = sorted({m["combo"] for m in items})
    print(f"{len(items)} images, {len(combos)} combinaisons de maillots : {', '.join(combos)}")
    if len(combos) < 10:
        print(f"ATTENTION : {len(combos)} combinaisons < 10 requises (dont des clashs et les deux mi-temps)")
    halves = {(m["combo"], m["half"]) for m in items}
    for c in combos:
        missing = [h for h in (1, 2) if (c, h) not in halves]
        if missing:
            print(f"  {c} : mi-temps manquante(s) {missing}")
    if not any(m.get("clash") for m in items):
        print("ATTENTION : aucun cas de clash capturé (--clash)")

    out = Path(args.out)
    img_dir, lbl_dir = out / "images", out / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    for m in items:
        shutil.copy2(m["path"], img_dir / m["file"])
    if args.preannotate:
        preannotate(items, args.preannotate, lbl_dir)
    (out / "classes.txt").write_text("\n".join(CLASSES), encoding="utf-8")
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "combo", "half", "clash"])
        for m in items:
            w.writerow([m["file"], m["combo"], m["half"], int(bool(m.get("clash")))])
    print(f"Dossier prêt : {out} (images/, labels/ si pré-annoté, classes.txt, manifest.csv)")

    if args.upload:
        key = os.environ.get("ROBOFLOW_API_KEY")
        if not (key and args.workspace and args.project):
            raise SystemExit("--upload demande ROBOFLOW_API_KEY, --workspace et --project")
        from roboflow import Roboflow

        project = Roboflow(api_key=key).workspace(args.workspace).project(args.project)
        for i, m in enumerate(items):
            tags = [f"combo:{m['combo']}", f"half:{m['half']}"] + (["clash"] if m.get("clash") else [])
            project.upload(image_path=str(img_dir / m["file"]), tag_names=tags, batch_name=m["combo"])
            if i % 25 == 0:
                print(f"  upload {i}/{len(items)}")
        print("Upload Roboflow terminé (images + tags).")
        if args.preannotate:
            print("Pré-annotations : glisse-dépose le dossier images/ + labels/ + classes.txt dans Roboflow "
                  "(l'API n'importe pas les .txt YOLO sans labelmap).")


if __name__ == "__main__":
    main()
