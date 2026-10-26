"""Base kits.sqlite : maillots déjà vus, pour accélérer le départ d'un match.

Quand un échantillon sûr (joueur sous curseur) ressemble à un kit connu
(ΔE00 < seuil), le prototype complet (maillot + short + chaussettes) est
pré-chargé sans attendre le coup d'envoi.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fccoach.vision.color import ciede2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS kits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shirt TEXT NOT NULL,      -- Lab JSON [L, a, b]
    shorts TEXT,
    socks TEXT,
    seen_count INTEGER NOT NULL DEFAULT 1,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    label TEXT
);
"""


@dataclass
class Kit:
    id: int
    shirt: np.ndarray
    shorts: np.ndarray | None
    socks: np.ndarray | None
    seen_count: int
    label: str | None


def _dump(v: np.ndarray | None) -> str | None:
    return None if v is None else json.dumps([round(float(x), 2) for x in v])


def _load(s: str | None) -> np.ndarray | None:
    return None if s is None else np.array(json.loads(s), np.float32)


class KitsDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.executescript(SCHEMA)

    def all(self) -> list[Kit]:
        with self._lock:
            rows = self._conn.execute("SELECT id, shirt, shorts, socks, seen_count, label FROM kits").fetchall()
        return [Kit(r[0], _load(r[1]), _load(r[2]), _load(r[3]), r[4], r[5]) for r in rows]  # type: ignore[arg-type]

    def match(self, shirt: np.ndarray, shorts: np.ndarray | None = None, max_de: float = 8.0) -> Kit | None:
        best, best_d = None, max_de
        for kit in self.all():
            d = float(ciede2000(shirt, kit.shirt))
            if shorts is not None and kit.shorts is not None:
                d = 0.7 * d + 0.3 * float(ciede2000(shorts, kit.shorts))
            if d < best_d:
                best, best_d = kit, d
        return best

    def upsert(self, shirt: np.ndarray, shorts: np.ndarray | None, socks: np.ndarray | None,
               max_de: float = 6.0) -> int:
        now = time.time()
        kit = self.match(shirt, shorts, max_de)
        with self._lock:
            if kit is not None:
                self._conn.execute(
                    "UPDATE kits SET shirt=?, shorts=COALESCE(?, shorts), socks=COALESCE(?, socks), "
                    "seen_count=seen_count+1, last_seen=? WHERE id=?",
                    (_dump(shirt), _dump(shorts), _dump(socks), now, kit.id))
                self._conn.commit()
                return kit.id
            cur = self._conn.execute(
                "INSERT INTO kits (shirt, shorts, socks, first_seen, last_seen) VALUES (?,?,?,?,?)",
                (_dump(shirt), _dump(shorts), _dump(socks), now, now))
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
