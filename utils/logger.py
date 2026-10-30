"""Logger avec rotation : data/logs/bot.log (5 Mo x 7 fichiers) + console."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

import config

_CONFIGURED = False


def get_logger(name: str = "sniper") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        config.ensure_dirs()
        fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
        root = logging.getLogger("sniper")
        root.setLevel(logging.INFO)
        fh = RotatingFileHandler(config.LOG_DIR / "bot.log", maxBytes=5_000_000, backupCount=7, encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(fh)
        root.addHandler(sh)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(name if name.startswith("sniper") else f"sniper.{name}")
