"""État partagé thread-safe, lu par le dashboard.

Chaque module publie sa section (capture, ocr, curseurs, équipes, alertes) ;
le dashboard lit un instantané JSON. Aucune opération lourde sous le verrou.
"""

from __future__ import annotations

import copy
import threading
import time
from collections import deque
from typing import Any


class SharedState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {"started_at": time.time()}
        self._events: deque[dict[str, Any]] = deque(maxlen=200)
        self._overlay: Any = None  # dernière image debug (numpy BGR)

    def update(self, section: str, values: dict[str, Any]) -> None:
        with self._lock:
            cur = self._data.setdefault(section, {})
            cur.update(values)

    def set(self, section: str, value: Any) -> None:
        with self._lock:
            self._data[section] = value

    def get(self, section: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(self._data.get(section, default))

    def push_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snap = copy.deepcopy(self._data)
            snap["events"] = list(self._events)[-30:]
        snap["now"] = time.time()
        return snap

    def set_overlay(self, image: Any) -> None:
        with self._lock:
            self._overlay = image

    def get_overlay(self) -> Any:
        with self._lock:
            return self._overlay
