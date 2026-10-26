"""Profil de l'adversaire : habitudes défensives comptées dès la 1re minute (fiche 10).

Une habitude est comptée au plus une fois par séquence de possession.
  - 2 occurrences : conseil possible avec la mention « à confirmer » ;
  - 3 occurrences : habitude installée.
Le profil est sauvegardé en SQLite par adversaire (pseudo lu par l'OCR) ; un
adversaire déjà rencontré démarre avec ses habitudes connues signalées.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HABITS: dict[str, str] = {
    "midfield_only": "Ramène ses milieux sans prendre un défenseur",
    "dc_out": "Sort son DC de la ligne",
    "closes_lanes": "Ferme les lignes sans presser",
    "ignores_runs": "Presse au lieu de suivre les appels",
    "rush_carrier": "Fonce sur le porteur",
}
CONFIRMED = 3
TO_CONFIRM = 2


@dataclass
class OpponentProfile:
    pseudo: str | None = None
    counts: dict[str, int] = field(default_factory=lambda: {k: 0 for k in HABITS})
    prior: dict[str, int] = field(default_factory=dict)       # matchs précédents
    line_heights: list[float] = field(default_factory=list)
    _last_seq: dict[str, int] = field(default_factory=dict)

    def count(self, habit: str, sequence_id: int) -> bool:
        """Compte une occurrence (une seule par séquence de possession)."""
        if self._last_seq.get(habit) == sequence_id:
            return False
        self._last_seq[habit] = sequence_id
        self.counts[habit] = self.counts.get(habit, 0) + 1
        return True

    def effective(self, habit: str) -> int:
        """Occurrences du match ; +1 si l'habitude était installée lors d'un match précédent."""
        return self.counts.get(habit, 0) + (1 if self.prior.get(habit, 0) >= CONFIRMED else 0)

    def summary(self) -> list[dict[str, Any]]:
        out = []
        for k, label in HABITS.items():
            n = self.effective(k)
            if n <= 0:
                continue
            status = "installée" if n >= CONFIRMED else ("à confirmer" if n >= TO_CONFIRM else "observée")
            out.append({"habit": k, "label": label, "count": self.counts.get(k, 0), "status": status,
                        "confidence": round(min(1.0, n / CONFIRMED), 2),
                        "known_before": self.prior.get(k, 0) >= CONFIRMED})
        return sorted(out, key=lambda h: -h["count"])

    def mean_line_height(self) -> float | None:
        return round(sum(self.line_heights[-60:]) / len(self.line_heights[-60:]), 1) if self.line_heights else None


class OpponentDB:
    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS opponents (
            pseudo TEXT PRIMARY KEY, counts TEXT NOT NULL, matches INTEGER NOT NULL DEFAULT 0,
            line_height REAL, updated REAL NOT NULL)""")
        self._conn.commit()

    def load(self, pseudo: str) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute("SELECT counts FROM opponents WHERE pseudo=?", (pseudo,)).fetchone()
        return json.loads(row[0]) if row else {}

    def matches(self, pseudo: str) -> int:
        with self._lock:
            row = self._conn.execute("SELECT matches FROM opponents WHERE pseudo=?", (pseudo,)).fetchone()
        return int(row[0]) if row else 0

    def save(self, profile: OpponentProfile) -> None:
        if not profile.pseudo:
            return
        merged = dict(profile.prior)
        for k, v in profile.counts.items():
            merged[k] = max(merged.get(k, 0), v)   # on garde le niveau d'habitude le plus net observé
        with self._lock:
            self._conn.execute(
                "INSERT INTO opponents (pseudo, counts, matches, line_height, updated) VALUES (?,?,1,?,?) "
                "ON CONFLICT(pseudo) DO UPDATE SET counts=excluded.counts, matches=matches+1, "
                "line_height=excluded.line_height, updated=excluded.updated",
                (profile.pseudo, json.dumps(merged), profile.mean_line_height(), time.time()))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
