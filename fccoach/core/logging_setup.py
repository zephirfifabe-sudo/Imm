"""Logs clairs : console + fichier tournant."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from fccoach.core.config import LoggingConfig, resolve_path

FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"


def setup_logging(cfg: LoggingConfig) -> None:
    root = logging.getLogger()
    root.setLevel(cfg.level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT, "%H:%M:%S"))
    root.addHandler(console)
    if cfg.file:
        path = resolve_path(cfg.file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(fh)
    # Bibliothèques bavardes
    for noisy in ("uvicorn.access", "ppocr", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
