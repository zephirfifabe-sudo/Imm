"""Point d'entrée : python -m fccoach [--config config/config.yaml] [--source 0|video.mp4] [--clips-only]"""

from __future__ import annotations

import argparse
import logging

from fccoach.core.config import load_config
from fccoach.core.logging_setup import setup_logging


def main() -> None:
    ap = argparse.ArgumentParser(description="Coach EA FC 27 — analyse passive du flux de capture")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--source", help="remplace capture.source (index périphérique ou fichier vidéo)")
    ap.add_argument("--no-ui", action="store_true", help="sans dashboard (logs seulement)")
    ap.add_argument("--clips-only", action="store_true",
                    help="sans carte de capture : dashboard uniquement pour analyser des clips téléchargés")
    args = ap.parse_args()
    if args.clips_only and args.no_ui:
        ap.error("--clips-only a besoin du dashboard ; en ligne de commande : python -m fccoach.clips clip.mp4")

    cfg = load_config(args.config)
    if args.source is not None:
        cfg.capture.source = args.source
    setup_logging(cfg.logging)
    log = logging.getLogger("fccoach")
    log.info("Coach EA FC 27 — Phase 1 (lecture vidéo uniquement, aucune interaction console/réseau/manette)")

    from fccoach.app import Pipeline
    from fccoach.clips.manager import create_clip_manager
    from fccoach.core.state import SharedState

    pipe: Pipeline | None = None
    if args.clips_only:
        state = SharedState()
        state.update("system", {"accelerator": "—", "phase": 1, "mode": "clips"})
        clips = create_clip_manager(cfg)
        log.info("Mode clips seulement : pas de capture en direct")
    else:
        pipe = Pipeline(cfg)
        pipe.start()
        state = pipe.state
        # Les clips réutilisent le détecteur et l'OCR du direct (pas de deuxième modèle en mémoire)
        clips = create_clip_manager(cfg, pipe.detector, pipe.ocr.engine, load_detector=False)
    try:
        if args.no_ui:
            if pipe is not None:
                pipe.capture.ended.wait()
        else:
            import uvicorn

            from fccoach.ui.server import create_app

            app = create_app(state, cfg.ui.mjpeg_fps, cfg.ui.jpeg_quality, clips, cfg.clips.max_upload_mb, pipe, cfg)
            log.info("Dashboard : http://%s:%d", cfg.ui.host, cfg.ui.port)
            uvicorn.run(app, host=cfg.ui.host, port=cfg.ui.port, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        if pipe is not None:
            pipe.stop()

if __name__ == "__main__":
    main()
