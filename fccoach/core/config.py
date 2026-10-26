"""Chargement typé de config/config.yaml.

Chaque section devient une dataclass. Les clés inconnues sont ignorées avec
un avertissement, les clés absentes prennent la valeur par défaut : un
config.yaml incomplet ne fait jamais planter le logiciel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

T = TypeVar("T")


@dataclass
class CaptureConfig:
    source: int | str = 0
    backend: str = "auto"
    width: int = 1920
    height: int = 1080
    fps: int = 60
    fourcc: str = "MJPG"
    buffer_seconds: float = 30.0          # extraits vidéo (compressés, 960x540)
    raw_buffer_seconds: float = 1.0       # images 1080p brutes pour l'analyse
    clip_fps: float = 15.0
    realtime_file_playback: bool = True


@dataclass
class HardwareConfig:
    accelerator: str = "auto"
    cadence_steps: list[int] = field(default_factory=lambda: [60, 30, 15, 10])
    benchmark_frames: int = 30
    budget_ratio: float = 0.8


@dataclass
class DetectorConfig:
    model: str = "models/fc_yolo_n.onnx"
    model_precision: str = "models/fc_yolo_s.onnx"
    precision_mode: bool = False
    mode: str = "tiles"
    tile_size: int = 640
    tile_overlap: int = 96
    conf_threshold: float = 0.30
    iou_threshold: float = 0.50
    roi: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0, 1.0])


@dataclass
class OcrConfig:
    engine: str = "auto"
    zones_file: str = "config/ocr_zones.json"
    tesseract_cmd: str = ""


@dataclass
class CursorSection:
    config_file: str = "config/cursor.yaml"


@dataclass
class TeamsConfig:
    vote_window: int = 15
    prototype_ema: float = 0.05
    cursor_sample_weight: float = 1.0
    clash_delta_e: float = 12.0
    min_confidence: float = 0.70
    kits_db: str = "data/kits.sqlite"
    kickoff_clock: list[str] = field(default_factory=lambda: ["00:00", "45:00"])


@dataclass
class TrackingConfig:
    iou_match: float = 0.3
    max_missed: int = 15


@dataclass
class PitchConfig:
    calibration_file: str = "config/pitch_calibration.json"
    homography_hz: float = 10.0


@dataclass
class CoachSection:
    rules_file: str = "knowledge/rules.yaml"
    min_interval_s: float = 20.0
    display_s: float = 30.0
    repeat_after_s: float = 90.0
    min_confidence: float = 0.70
    clip_before_s: float = 6.0
    clip_after_s: float = 3.0
    max_clips_per_rule_half: int = 3


@dataclass
class StorageConfig:
    matches_db: str = "data/matches.sqlite"
    opponents_db: str = "data/opponents.sqlite"
    matches_dir: str = "data/matches"


@dataclass
class ClipsConfig:
    dir: str = "data/clips"
    analysis_fps: float = 15.0          # détections par seconde DE VIDÉO
    annotated_video: bool = True        # vidéo avec l'overlay debug (WebM, lisible dans le navigateur)
    annotated_width: int = 960
    max_upload_mb: int = 4096
    max_event_snapshots: int = 300


@dataclass
class UiConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    debug_overlay: bool = True
    mjpeg_fps: int = 10
    jpeg_quality: int = 70


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/coach.log"


@dataclass
class Config:
    live_coaching: bool = True
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    cursor: CursorSection = field(default_factory=CursorSection)
    teams: TeamsConfig = field(default_factory=TeamsConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    pitch: PitchConfig = field(default_factory=PitchConfig)
    coach: CoachSection = field(default_factory=CoachSection)
    storage: StorageConfig = field(default_factory=StorageConfig)
    clips: ClipsConfig = field(default_factory=ClipsConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _build(cls: type[T], data: dict[str, Any] | None, path: str) -> T:
    """Construit récursivement une dataclass à partir d'un dict YAML."""
    data = data or {}
    kwargs: dict[str, Any] = {}
    known = {f.name: f for f in fields(cls)}  # type: ignore[arg-type]
    for key, value in data.items():
        if key not in known:
            log.warning("Clé de configuration inconnue ignorée : %s.%s", path, key)
            continue
        default = known[key].default_factory() if callable(known[key].default_factory) else None  # type: ignore[misc]
        if default is not None and is_dataclass(default):
            kwargs[key] = _build(type(default), value, f"{path}.{key}")
        else:
            kwargs[key] = value
    return cls(**kwargs)


def resolve_path(p: str | Path) -> Path:
    """Chemin relatif -> relatif à la racine du projet."""
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def load_config(path: str | Path = "config/config.yaml") -> Config:
    path = resolve_path(path)
    if not path.exists():
        log.warning("Fichier %s introuvable : configuration par défaut", path)
        return Config()
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return _build(Config, raw, "config")


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(resolve_path(path), encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
