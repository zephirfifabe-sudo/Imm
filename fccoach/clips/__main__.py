"""Analyse de clips en ligne de commande.

    python -m fccoach.clips mon_clip.mp4 [autre.mp4 …] [--no-video]

Résultats dans data/clips/<id>/ (report.json, annotated.webm, events/), visibles
aussi dans le dashboard (section « Clips »).
"""

from __future__ import annotations

import argparse
import sys

from fccoach.core.config import load_config
from fccoach.core.logging_setup import setup_logging


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--no-video", action="store_true", help="sans vidéo annotée (plus rapide)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.no_video:
        cfg.clips.annotated_video = False
    setup_logging(cfg.logging)
    from fccoach.clips.manager import create_clip_manager

    mgr = create_clip_manager(cfg, start_worker=False)
    failed = 0
    for path in args.videos:
        try:
            job = mgr.add_file(path)
        except Exception as exc:
            print(f"{path} : refusé — {exc}")
            failed += 1
            continue
        print(f"Analyse de {job.name} ({job.info['duration_s']} s)…")
        mgr.run_job(job, lambda p: print(f"\r  {p:5.0%}", end="", flush=True))
        print()
        if job.status != "done":
            print(f"  échec : {job.error}")
            failed += 1
            continue
        s = job.summary
        print(f"  durée {s['duration_s']} s, analysé à x{s['speed_x']} la vitesse réelle")
        print(f"  changements de joueur : moi {s['selection_changes']['me']}, adversaire {s['selection_changes']['opp']}")
        print(f"  équipes : {'fiables' if s['teams_reliable'] else 'NON fiables'} ({s['teams_confidence']:.0%})"
              + (" — clash" if s["clash"] else ""))
        for w in s["warnings"]:
            print(f"  attention : {w}")
        print(f"  rapport : {mgr.dir(job.id) / 'report.json'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
