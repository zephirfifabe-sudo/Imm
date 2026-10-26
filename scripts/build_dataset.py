"""Construit le dataset d'entraînement à partir d'un export Roboflow (format YOLOv8/YOLO11).

- Regroupe les images par COMBINAISON DE MAILLOTS (préfixe du nom de fichier,
  conservé par Roboflow : psg-dom_vs_om-ext__h1__00012_jpg.rf.<hash>.jpg).
- Découpage train/validation PAR COMBINAISON (jamais par image) : les
  maillots de validation n'ont jamais été vus à l'entraînement.
- Augmentation hors ligne (train seulement) : variations de teinte et de
  saturation appliquées aux boîtes joueurs (nouveaux maillots simulés).

    python scripts/build_dataset.py --export data/roboflow_export --out data/dataset --val-combos 2
    python scripts/build_dataset.py ... --val psg-dom_vs_om-ext,real-dom_vs_barca-ext
"""

from __future__ import annotations

import argparse
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml

CLASSES = ["player", "goalkeeper", "referee", "ball"]
_COMBO_RE = re.compile(r"^(.+?)__h([12])__")


def combo_of(name: str) -> tuple[str, int] | None:
    m = _COMBO_RE.match(name)
    return (m.group(1), int(m.group(2))) if m else None


def read_labels(path: Path) -> list[list[float]]:
    if not path.exists():
        return []
    return [[float(x) for x in ln.split()] for ln in path.read_text().splitlines() if ln.strip()]


def jersey_hue_shift(img: np.ndarray, labels: list[list[float]], rng: random.Random) -> np.ndarray:
    """Décale teinte/saturation dans les boîtes de joueurs (pas la pelouse autour)."""
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
    dh = rng.randint(-60, 60)           # H OpenCV 0-179 : ± 120°
    ds = rng.uniform(0.6, 1.4)
    for c, cx, cy, w, h in labels:
        if int(c) not in (0, 1):        # joueurs et gardiens seulement
            continue
        x0, x1 = int((cx - w / 2) * W), int((cx + w / 2) * W)
        y0, y1 = int((cy - h / 2) * H), int((cy + h / 2) * H)
        roi = hsv[max(0, y0):y1, max(0, x0):x1]
        green = (roi[..., 0] >= 32) & (roi[..., 0] <= 90) & (roi[..., 1] >= 50)
        sel = ~green
        roi[..., 0][sel] = (roi[..., 0][sel] + dh) % 180
        roi[..., 1][sel] = np.clip(roi[..., 1][sel] * ds, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True, help="dossier d'export Roboflow (train/ valid/ test/ …)")
    ap.add_argument("--out", default="data/dataset")
    ap.add_argument("--val", help="combinaisons de validation, séparées par des virgules")
    ap.add_argument("--val-combos", type=int, default=2, help="nombre de combinaisons tirées pour la validation")
    ap.add_argument("--aug", type=int, default=2, help="copies augmentées par image d'entraînement")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    export = Path(args.export)
    groups: dict[str, list[tuple[Path, Path]]] = defaultdict(list)
    unknown = 0
    for img in export.rglob("*.jpg"):
        if img.parent.name != "images":
            continue
        c = combo_of(img.name)
        if c is None:
            unknown += 1
            continue
        groups[c[0]].append((img, img.parent.parent / "labels" / (img.stem + ".txt")))
    if unknown:
        print(f"{unknown} images sans préfixe de combinaison ignorées")
    combos = sorted(groups)
    print(f"{len(combos)} combinaisons : {', '.join(f'{c} ({len(groups[c])})' for c in combos)}")
    if len(combos) < 3:
        raise SystemExit("Il faut au moins 3 combinaisons (10 recommandées) pour un découpage par combinaison")

    val = [v.strip() for v in args.val.split(",")] if args.val else rng.sample(combos, min(args.val_combos, len(combos) - 1))
    print(f"Validation (maillots jamais vus à l'entraînement) : {', '.join(val)}")

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    for split in ("train", "val"):
        (out / split / "images").mkdir(parents=True)
        (out / split / "labels").mkdir(parents=True)
    n = {"train": 0, "val": 0, "aug": 0}
    for combo, pairs in groups.items():
        split = "val" if combo in val else "train"
        for img_p, lbl_p in pairs:
            shutil.copy2(img_p, out / split / "images" / img_p.name)
            labels = read_labels(lbl_p)
            (out / split / "labels" / (img_p.stem + ".txt")).write_text(
                "\n".join(" ".join(f"{v:g}" for v in ln) for ln in labels))
            n[split] += 1
            if split == "train" and args.aug:
                img = cv2.imread(str(img_p))
                for k in range(args.aug):
                    aug = jersey_hue_shift(img, labels, rng)
                    stem = f"{img_p.stem}__aug{k}"
                    cv2.imwrite(str(out / "train" / "images" / f"{stem}.jpg"), aug, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    shutil.copy2(out / "train" / "labels" / (img_p.stem + ".txt"), out / "train" / "labels" / f"{stem}.txt")
                    n["aug"] += 1
    (out / "data.yaml").write_text(yaml.safe_dump({
        "path": str(out.resolve()), "train": "train/images", "val": "val/images",
        "names": dict(enumerate(CLASSES)),
    }, allow_unicode=True))
    (out / "split.yaml").write_text(yaml.safe_dump({"val_combos": val, "train_combos": [c for c in combos if c not in val]}))
    print(f"Dataset prêt : {out} | train {n['train']} (+{n['aug']} augmentées) | val {n['val']}")


if __name__ == "__main__":
    main()
