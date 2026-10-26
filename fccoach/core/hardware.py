"""Détection de l'accélérateur et cadence adaptative de la détection.

Ordre de préférence (ONNX Runtime) :
    CUDA  >  DirectML (Windows, AMD/Intel/Nvidia) / ROCm (Linux AMD)  >  OpenVINO  >  CPU

Le paquet onnxruntime installé décide des fournisseurs disponibles :
    - onnxruntime-gpu        -> CUDA (Nvidia)
    - onnxruntime-directml   -> DirectML (toute carte DirectX 12 sous Windows)
    - onnxruntime-openvino   -> OpenVINO (Intel CPU / iGPU / Arc)
    - onnxruntime            -> CPU seul
Un seul de ces paquets doit être installé à la fois (voir README).

La cadence adaptative ne touche QUE la détection YOLO : la capture tourne
toujours à pleine vitesse, curseurs et OCR gardent leurs propres cadences.
"""

from __future__ import annotations

import logging
import platform
import time
from collections import deque
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# (nom lisible, fournisseur ONNX Runtime) dans l'ordre de préférence
PROVIDER_PRIORITY: list[tuple[str, str]] = [
    ("cuda", "CUDAExecutionProvider"),
    ("directml", "DmlExecutionProvider"),
    ("rocm", "ROCMExecutionProvider"),
    ("openvino", "OpenVINOExecutionProvider"),
    ("cpu", "CPUExecutionProvider"),
]


@dataclass
class HardwareInfo:
    accelerator: str                 # cuda | directml | rocm | openvino | cpu
    providers: list[str]             # liste passée à onnxruntime.InferenceSession
    available: list[str]             # tous les fournisseurs détectés
    is_gpu: bool
    powerful_gpu: bool               # autorise l'option « précision »
    description: str = ""

    def summary(self) -> str:
        return f"{self.accelerator.upper()} ({self.description})"


def _available_providers() -> list[str]:
    try:
        import onnxruntime as ort

        return list(ort.get_available_providers())
    except Exception as exc:  # onnxruntime absent ou cassé
        log.warning("ONNX Runtime indisponible (%s) : détection impossible, CPU par défaut", exc)
        return ["CPUExecutionProvider"]


def _gpu_description(accel: str) -> tuple[str, bool]:
    """Nom du GPU et estimation « GPU puissant » (>= 8 Go VRAM Nvidia)."""
    if accel == "cuda":
        try:
            import subprocess

            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, check=False,
            ).stdout.strip().splitlines()
            if out:
                name, mem = [x.strip() for x in out[0].split(",")]
                return f"{name}, {int(mem) // 1024} Go", int(mem) >= 8000
        except Exception:
            pass
        return "GPU Nvidia", False
    if accel in ("directml", "rocm"):
        return "GPU DirectX12/ROCm", False
    if accel == "openvino":
        return "Intel OpenVINO", False
    return f"CPU {platform.processor() or platform.machine()}", False


def detect_hardware(preference: str = "auto") -> HardwareInfo:
    """Choisit le meilleur accélérateur disponible et l'affiche dans les logs."""
    available = _available_providers()
    chosen: tuple[str, str] | None = None
    if preference != "auto":
        for name, prov in PROVIDER_PRIORITY:
            if name == preference and prov in available:
                chosen = (name, prov)
        if chosen is None:
            log.warning("Accélérateur « %s » demandé mais indisponible : sélection automatique", preference)
    if chosen is None:
        for name, prov in PROVIDER_PRIORITY:
            if prov in available:
                chosen = (name, prov)
                break
    assert chosen is not None  # CPUExecutionProvider est toujours présent
    accel, prov = chosen
    providers = [prov] if prov == "CPUExecutionProvider" else [prov, "CPUExecutionProvider"]
    desc, powerful = _gpu_description(accel)
    info = HardwareInfo(
        accelerator=accel,
        providers=providers,
        available=available,
        is_gpu=accel != "cpu",
        powerful_gpu=powerful,
        description=desc,
    )
    log.info("Accélérateur détecté : %s | fournisseurs ONNX disponibles : %s",
             info.summary(), ", ".join(available))
    if not info.is_gpu:
        log.info("Mode CPU : terrain 2D moins fluide, conseils en direct toujours actifs")
    return info


def choose_model(info: HardwareInfo, model: str, model_precision: str, precision_mode: bool) -> str:
    """Modèle nano/small par défaut ; « précision » seulement sur GPU puissant."""
    if precision_mode and info.powerful_gpu:
        log.info("Option « précision » activée : %s", model_precision)
        return model_precision
    if precision_mode:
        log.warning("Option « précision » ignorée : GPU puissant non détecté (modèle léger conservé)")
    return model


def recommend_cadence(latency_s: float, steps: list[int], budget_ratio: float = 0.8) -> int:
    """Plus grande cadence (images/s) telle que latence × cadence <= budget.

    Ex. : 20 ms par image, budget 0,8 -> 0,02 × 30 = 0,6 <= 0,8 -> 30 i/s
    (60 i/s demanderait 1,2 s de calcul par seconde : impossible).
    """
    for fps in sorted(steps, reverse=True):
        if latency_s * fps <= budget_ratio:
            return fps
    return min(steps)


@dataclass
class AdaptiveCadence:
    """Ajuste en continu la cadence de la détection (60 -> 30 -> 15 -> 10).

    - Descend dès que la latence moyenne dépasse le budget.
    - Remonte prudemment (hystérésis) si la marge est large pendant 5 s.
    """

    steps: list[int]
    budget_ratio: float = 0.8
    current: int = 10
    window: int = 30
    _lat: deque[float] = field(default_factory=lambda: deque(maxlen=30))
    _last_change: float = 0.0

    def __post_init__(self) -> None:
        self.steps = sorted(set(self.steps), reverse=True)
        self._lat = deque(maxlen=self.window)

    def calibrate(self, latency_s: float) -> int:
        self.current = recommend_cadence(latency_s, self.steps, self.budget_ratio)
        self._lat.clear()
        self._last_change = time.monotonic()
        log.info("Cadence de détection initiale : %d images/s (latence mesurée %.1f ms)",
                 self.current, latency_s * 1000)
        return self.current

    @property
    def period(self) -> float:
        return 1.0 / self.current

    def update(self, latency_s: float) -> int:
        self._lat.append(latency_s)
        if len(self._lat) < 10:
            return self.current
        mean = sum(self._lat) / len(self._lat)
        now = time.monotonic()
        idx = self.steps.index(self.current)
        load = mean * self.current
        if load > self.budget_ratio and idx < len(self.steps) - 1:
            self._set(self.steps[idx + 1], mean, now)
        elif idx > 0 and mean * self.steps[idx - 1] < self.budget_ratio * 0.7 and now - self._last_change > 5.0:
            self._set(self.steps[idx - 1], mean, now)
        return self.current

    def _set(self, fps: int, mean: float, now: float) -> None:
        log.info("Cadence de détection : %d -> %d images/s (latence moyenne %.1f ms)",
                 self.current, fps, mean * 1000)
        self.current = fps
        self._last_change = now
        self._lat.clear()
