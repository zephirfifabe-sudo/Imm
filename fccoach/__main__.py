"""Point d'entrée : python -m fccoach [--config config/config.yaml] [--source 0|video.mp4]"""

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
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.source is not None:
        cfg.capture.source = args.source
    setup_logging(cfg.logging)
    log = logging.getLogger("fccoach")
    log.info("Coach EA FC 27 — Phase 1 (lecture vidéo uniquement, aucune interaction console/réseau/manette)")

    from fccoach.app import Pipeline

    pipe = Pipeline(cfg)
    pipe.start()
    try:
        if args.no_ui:
            pipe.capture.ended.wait()
        else:
            import uvicorn

            from fccoach.ui.server import create_app

            app = create_app(pipe.state, cfg.ui.mjpeg_fps, cfg.ui.jpeg_quality)
            log.info("Dashboard : http://%s:%d", cfg.ui.host, cfg.ui.port)
            uvicorn.run(app, host=cfg.ui.host, port=cfg.ui.port, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        pipe.stop()


if __name__ == "__main__":
    main()
