"""PHASE 1 — Porte de validation : curseurs et équipes fiables sur >= 10 combinaisons ?

Jeu d'évaluation = un projet Roboflow SÉPARÉ (« fc-eval »), annoté avec des
classes d'évaluation uniquement (le détecteur, lui, n'a jamais de classe équipe) :
    0 player_me   1 player_opp   2 goalkeeper   3 referee   4 ball
    5 cursor_me   6 cursor_opp          (curseurs : boîte autour du triangle)
Images nommées <combo>__h<1|2>__<n>.jpg (phase0_capture_frames.py), de
préférence capturées serrées (--interval 0.2) pour que le vote temporel joue.

    python scripts/eval_phase1.py --export data/eval_export

Pour chaque combinaison, les boîtes de vérité terrain sont données au module
d'équipes (l'erreur du détecteur est mesurée à part, train_yolo.py) :
  - curseurs : rappel et précision (pointe dans la boîte vérité), confusion rouge/blanc
  - équipes  : taux d'erreur d'attribution, couverture (joueurs attribués)
Rapport : reports/phase1_eval.json — verdict PASS / FAIL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fccoach.core.config import TeamsConfig, load_yaml  # noqa: E402
from fccoach.tracking.iou_tracker import IouTracker  # noqa: E402
from fccoach.vision.cursor import CursorSystem  # noqa: E402
from fccoach.vision.teams import TeamClassifier  # noqa: E402
from fccoach.vision.types import Detection  # noqa: E402

EVAL_CLASSES = ["player_me", "player_opp", "goalkeeper", "referee", "ball", "cursor_me", "cursor_opp"]
_RE = re.compile(r"^(.+?)__h([12])__(\d+)")


def load_gt(lbl: Path, W: int, H: int) -> list[tuple[str, tuple[float, float, float, float]]]:
    out = []
    if not lbl.exists():
        return out
    for ln in lbl.read_text().splitlines():
        p = ln.split()
        if len(p) < 5:
            continue
        c, cx, cy, w, h = int(p[0]), *map(float, p[1:5])
        out.append((EVAL_CLASSES[c], ((cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H)))
    return out


def inside(pt: tuple[float, float], box: tuple[float, float, float, float], pad: float = 6) -> bool:
    return box[0] - pad <= pt[0] <= box[2] + pad and box[1] - pad <= pt[1] <= box[3] + pad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True)
    ap.add_argument("--cursor-config", default="config/cursor.yaml")
    ap.add_argument("--min-combos", type=int, default=10)
    ap.add_argument("--max-team-error", type=float, default=0.05)
    ap.add_argument("--min-team-coverage", type=float, default=0.85)
    ap.add_argument("--min-cursor-recall", type=float, default=0.90)
    ap.add_argument("--min-cursor-precision", type=float, default=0.97)
    args = ap.parse_args()

    frames: dict[str, list[tuple[int, int, Path, Path]]] = defaultdict(list)
    for img in Path(args.export).rglob("*.jpg"):
        m = _RE.match(img.name)
        if m and img.parent.name == "images":
            frames[m.group(1)].append((int(m.group(2)), int(m.group(3)), img,
                                       img.parent.parent / "labels" / (img.stem + ".txt")))
    if not frames:
        raise SystemExit("Aucune image d'évaluation trouvée")
    cursor_cfg = load_yaml(args.cursor_config)
    report: dict = {"combos": {}}
    for combo, items in sorted(frames.items()):
        items.sort()
        cursors = CursorSystem(cursor_cfg)
        teams = TeamClassifier(TeamsConfig())
        tracker = IouTracker()
        c = defaultdict(int)
        half = 1
        ts = 0.0
        for h, _, img_p, lbl_p in items:
            if h != half:
                teams.new_half()
                half = h
            img = cv2.imread(str(img_p))
            H, W = img.shape[:2]
            gt = load_gt(lbl_p, W, H)
            dets, truth = [], {}
            for cls, b in gt:
                if cls in ("player_me", "player_opp", "goalkeeper", "referee"):
                    d = Detection(*b, score=1.0, cls="player" if cls.startswith("player") else cls)
                    dets.append(d)
                    truth[id(d)] = {"player_me": "me", "player_opp": "opp"}.get(cls)
            tracker.update(dets)
            ts += 0.2
            cursors.process(img, ts, [d for d in dets if d.cls in ("player", "goalkeeper")])
            # Curseurs : la pointe détectée tombe-t-elle dans la boîte vérité ?
            for side in ("me", "opp"):
                gt_boxes = [b for cls, b in gt if cls == f"cursor_{side}"]
                other = [b for cls, b in gt if cls == f"cursor_{'opp' if side == 'me' else 'me'}"]
                cands = cursors.last_candidates.get(side, [])
                best = cands[0] if cands else None
                c[f"{side}_gt"] += len(gt_boxes)
                if best is not None:
                    c[f"{side}_pred"] += 1
                    if any(inside(best.tip, b) or inside(best.center, b) for b in gt_boxes):
                        c[f"{side}_tp"] += 1
                    elif any(inside(best.center, b) for b in other):
                        c["side_confusion"] += 1
            cursor_players = {s: cursors.selected_player(s) for s in ("me", "opp")}
            teams.process(img, dets, cursor_players, None)
            for d in dets:
                t = truth.get(id(d))
                if t is None:
                    continue
                c["players"] += 1
                if d.team is None or d.team_conf < teams.cfg.min_confidence:
                    continue
                c["assigned"] += 1
                c["team_wrong"] += int(d.team != t)
        rec = {
            "frames": len(items),
            "halves": sorted({i[0] for i in items}),
            "cursor_recall": {s: round(c[f"{s}_tp"] / c[f"{s}_gt"], 3) if c[f"{s}_gt"] else None for s in ("me", "opp")},
            "cursor_precision": {s: round(c[f"{s}_tp"] / c[f"{s}_pred"], 3) if c[f"{s}_pred"] else None for s in ("me", "opp")},
            "cursor_side_confusion": c["side_confusion"],
            "team_error": round(c["team_wrong"] / c["assigned"], 4) if c["assigned"] else None,
            "team_coverage": round(c["assigned"] / c["players"], 3) if c["players"] else None,
            "clash": teams.status.clash,
            "kit_delta_e": None if teams.status.kit_delta_e is None else round(teams.status.kit_delta_e, 1),
        }
        fails = []
        for s in ("me", "opp"):
            if rec["cursor_recall"][s] is not None and rec["cursor_recall"][s] < args.min_cursor_recall:
                fails.append(f"rappel curseur {s}")
            if rec["cursor_precision"][s] is not None and rec["cursor_precision"][s] < args.min_cursor_precision:
                fails.append(f"précision curseur {s}")
        if rec["cursor_side_confusion"]:
            fails.append("confusion rouge/blanc")
        if rec["team_error"] is None or rec["team_error"] > args.max_team_error:
            fails.append("erreur équipe")
        if rec["team_coverage"] is None or rec["team_coverage"] < args.min_team_coverage:
            fails.append("couverture équipe")
        rec["verdict"] = "PASS" if not fails else "FAIL: " + ", ".join(fails)
        report["combos"][combo] = rec
        print(f"{combo:<40} curseurs R={rec['cursor_recall']} P={rec['cursor_precision']} | "
              f"équipe err={rec['team_error']} couv={rec['team_coverage']} clash={rec['clash']} -> {rec['verdict']}")

    combos = report["combos"]
    n_pass = sum(1 for r in combos.values() if r["verdict"] == "PASS")
    n_clash = sum(1 for r in combos.values() if r["clash"])
    both_halves = sum(1 for r in combos.values() if r["halves"] == [1, 2])
    ok = n_pass >= args.min_combos and n_pass == len(combos) and n_clash >= 1 and both_halves >= args.min_combos
    report["summary"] = {"combos": len(combos), "pass": n_pass, "clash_combos": n_clash,
                         "combos_with_both_halves": both_halves, "phase1_gate": "PASS" if ok else "FAIL"}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/phase1_eval.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n{n_pass}/{len(combos)} combinaisons OK, {n_clash} clash, {both_halves} avec les deux mi-temps")
    print(f"PORTE PHASE 1 : {report['summary']['phase1_gate']} (reports/phase1_eval.json)")
    if not ok:
        print("Tant que la porte n'est pas PASS, on ne passe pas à la Phase 2 : ajuste config/cursor.yaml "
              "et config.yaml > teams, ou ajoute des combinaisons.")


if __name__ == "__main__":
    main()
