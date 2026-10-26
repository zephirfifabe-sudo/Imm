"""Base des matchs (SQLite) : progression semaine après semaine.

Tables : matches, events, advice (conseils affichés), occurrences (règles
déclenchées = « ce que j'aurais dû faire », avec extrait vidéo).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started REAL NOT NULL, ended REAL,
    source TEXT,                       -- live | clip
    opponent TEXT,
    score_me INTEGER, score_opp INTEGER,
    my_formation TEXT, opp_formation TEXT,
    summary TEXT                       -- JSON (stats, bilan)
);
CREATE TABLE IF NOT EXISTS events (
    match_id INTEGER NOT NULL, t REAL NOT NULL, clock TEXT, type TEXT NOT NULL, team TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS advice (
    match_id INTEGER NOT NULL, t REAL NOT NULL, clock TEXT, rule_id TEXT NOT NULL, text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS occurrences (
    match_id INTEGER NOT NULL, t REAL NOT NULL, clock TEXT, rule_id TEXT NOT NULL, half INTEGER, clip TEXT
);
CREATE INDEX IF NOT EXISTS idx_occ_match ON occurrences(match_id);
CREATE INDEX IF NOT EXISTS idx_ev_match ON events(match_id);
"""


class MatchDB:
    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _query(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def start_match(self, source: str, started: float | None = None) -> int:
        return int(self._exec("INSERT INTO matches (started, source) VALUES (?, ?)",
                              (started or time.time(), source)).lastrowid or 0)

    def update_match(self, match_id: int, **fields: Any) -> None:
        if not fields:
            return
        if "summary" in fields and not isinstance(fields["summary"], str):
            fields["summary"] = json.dumps(fields["summary"], ensure_ascii=False)
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE matches SET {cols} WHERE id=?", (*fields.values(), match_id))

    def add_event(self, match_id: int, t: float, clock: str | None, type_: str, team: str | None, data: dict) -> None:
        self._exec("INSERT INTO events VALUES (?,?,?,?,?,?)",
                   (match_id, t, clock, type_, team, json.dumps(data, ensure_ascii=False)))

    def add_advice(self, match_id: int, t: float, clock: str | None, rule_id: str, text: str) -> None:
        self._exec("INSERT INTO advice VALUES (?,?,?,?,?)", (match_id, t, clock, rule_id, text))

    def add_occurrence(self, match_id: int, t: float, clock: str | None, rule_id: str, half: int, clip: str | None) -> None:
        self._exec("INSERT INTO occurrences VALUES (?,?,?,?,?,?)", (match_id, t, clock, rule_id, half, clip))

    def match(self, match_id: int) -> dict[str, Any] | None:
        rows = self._query("SELECT id, started, ended, source, opponent, score_me, score_opp, my_formation, "
                           "opp_formation, summary FROM matches WHERE id=?", (match_id,))
        if not rows:
            return None
        r = rows[0]
        return {"id": r[0], "started": r[1], "ended": r[2], "source": r[3], "opponent": r[4], "score_me": r[5],
                "score_opp": r[6], "my_formation": r[7], "opp_formation": r[8],
                "summary": json.loads(r[9]) if r[9] else {}}

    def matches(self, limit: int = 100) -> list[dict[str, Any]]:
        ids = [r[0] for r in self._query("SELECT id FROM matches ORDER BY started DESC LIMIT ?", (limit,))]
        return [m for m in (self.match(i) for i in ids) if m]

    def occurrences(self, match_id: int) -> list[dict[str, Any]]:
        return [{"t": r[0], "clock": r[1], "rule_id": r[2], "half": r[3], "clip": r[4]} for r in
                self._query("SELECT t, clock, rule_id, half, clip FROM occurrences WHERE match_id=? ORDER BY t",
                            (match_id,))]

    def rule_rates(self, last_n_matches: int = 10) -> dict[str, float]:
        """Occurrences moyennes par match des règles, sur les derniers matchs (conseils personnalisés)."""
        ids = [r[0] for r in self._query("SELECT id FROM matches WHERE ended IS NOT NULL ORDER BY started DESC LIMIT ?",
                                         (last_n_matches,))]
        if not ids:
            return {}
        q = ",".join("?" * len(ids))
        rows = self._query(f"SELECT rule_id, COUNT(*) FROM occurrences WHERE match_id IN ({q}) GROUP BY rule_id", tuple(ids))
        return {rid: n / len(ids) for rid, n in rows}

    def weekly(self) -> list[dict[str, Any]]:
        """Progression par semaine : matchs, bilan V/N/D, occurrences par match et par règle."""
        weeks: dict[str, dict[str, Any]] = defaultdict(lambda: {"matches": 0, "w": 0, "d": 0, "l": 0, "occ": defaultdict(int)})
        for m in self.matches(1000):
            if m["ended"] is None:
                continue
            y, wk, _ = dt.date.fromtimestamp(m["started"]).isocalendar()
            key = f"{y}-S{wk:02d}"
            wkd = weeks[key]
            wkd["matches"] += 1
            if m["score_me"] is not None and m["score_opp"] is not None:
                wkd["w" if m["score_me"] > m["score_opp"] else "d" if m["score_me"] == m["score_opp"] else "l"] += 1
            for o in self.occurrences(m["id"]):
                wkd["occ"][o["rule_id"]] += 1
        out = []
        for key in sorted(weeks):
            w = weeks[key]
            per_match = {k: round(v / w["matches"], 2) for k, v in w["occ"].items()}
            out.append({"week": key, "matches": w["matches"], "wins": w["w"], "draws": w["d"], "losses": w["l"],
                        "occurrences_per_match": round(sum(w["occ"].values()) / w["matches"], 2),
                        "top_rules": sorted(per_match.items(), key=lambda kv: -kv[1])[:5]})
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
