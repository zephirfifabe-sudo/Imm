"""PHASE 0 — Capture automatique de frames pour l'annotation.

Lit la carte de capture (ou un fichier vidéo enregistré) et enregistre des
images 1080p natives, en évitant les doublons (scènes quasi identiques) et
les écrans sans terrain (menus, replays très zoomés : optionnel).

Chaque session = UNE combinaison de maillots et UNE mi-temps :
    python scripts/phase0_capture_frames.py --combo psg-dom_vs_om-ext --half 1
    python scripts/phase0_capture_frames.py --source match.mp4 --combo real-dom_vs_barca-ext --half 2 --clash

Sortie : data/raw/<combo>/h<half>/<combo>__h<half>__<n>.jpg + metadata.jsonl
Le nom de fichier porte la combinaison : le découpage train/val par
combinaison (build_dataset.py) s'appuie dessus, même après Roboflow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fccoach.capture.source import open_source  # noqa: E402
from fccoach.vision.color import grass_mask  # noqa: E402


def dhash(img: np.ndarray, size: int = 16) -> np.ndarray:
    """Empreinte perceptuelle (différence de gradients) pour éliminer les doublons."""
    g = cv2.cvtColor(cv2.resize(img, (size + 1, size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return (g[:, 1:] > g[:, :-1]).flatten()


def safe_combo(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()).strip("-")
    if not s:
        raise SystemExit("--combo vide : donne un nom de combinaison de maillots, ex. psg-dom_vs_om-ext")
    return s.replace("__", "_")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="0", help="index du périphérique (0, 1…) ou fichier vidéo")
    ap.add_argument("--combo", required=True, help="combinaison de maillots, ex. psg-dom_vs_om-ext")
    ap.add_argument("--half", type=int, choices=(1, 2), required=True, help="mi-temps (1 ou 2)")
    ap.add_argument("--clash", action="store_true", help="maillots proches (cas de clash)")
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--interval", type=float, default=1.0, help="secondes mini entre deux images")
    ap.add_argument("--min-diff", type=float, default=0.12, help="différence dHash mini (0-1) vs dernière image gardée")
    ap.add_argument("--min-grass", type=float, default=0.25, help="part de pelouse mini (filtre menus) ; 0 = désactivé")
    ap.add_argument("--max-frames", type=int, default=400)
    ap.add_argument("--quality", type=int, default=95)
    ap.add_argument("--preview", action="store_true", help="fenêtre d'aperçu (q pour quitter)")
    args = ap.parse_args()

    combo = safe_combo(args.combo)
    out_dir = Path(args.out) / combo / f"h{args.half}"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "metadata.jsonl"
    start_n = len(list(out_dir.glob("*.jpg")))

    cap, is_file = open_source(args.source)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(args.interval * fps))) if is_file else 1
    print(f"Capture -> {out_dir} (combo={combo}, mi-temps={args.half}, clash={args.clash})")

    kept, seen, last_hash, last_t = start_n, 0, None, 0.0
    with open(meta_path, "a", encoding="utf-8") as meta:
        while kept < args.max_frames:
            ok, img = cap.read()
            if not ok:
                break
            seen += 1
            now = time.monotonic()
            if is_file and seen % step:
                continue
            if not is_file and now - last_t < args.interval:
                continue
            if img.shape[:2] != (1080, 1920):
                print(f"Attention : image {img.shape[1]}x{img.shape[0]} (1080p attendu)")
            if args.min_grass > 0:
                small = cv2.resize(img, (192, 108), interpolation=cv2.INTER_AREA)
                if grass_mask(small).mean() < args.min_grass:
                    continue  # menu, replay, écran de stats
            h = dhash(img)
            if last_hash is not None and (h != last_hash).mean() < args.min_diff:
                continue
            name = f"{combo}__h{args.half}__{kept:05d}.jpg"
            cv2.imwrite(str(out_dir / name), img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
            meta.write(json.dumps({"file": name, "combo": combo, "half": args.half, "clash": args.clash,
                                   "wall": time.time(), "source_frame": seen}) + "\n")
            kept += 1
            last_hash, last_t = h, now
            if kept % 25 == 0:
                print(f"  {kept} images gardées")
            if args.preview:
                cv2.imshow("capture (q = quitter)", cv2.resize(img, (960, 540)))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    cap.release()
    print(f"Terminé : {kept - start_n} nouvelles images ({kept} au total) dans {out_dir}")


if __name__ == "__main__":
    main()
