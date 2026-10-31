"""Couche SQLite : market_history.db (la MÉMOIRE du bot).

Tables principales :
- players          : fiche joueur (ID EA, nom, note, poste, ligue, nation, club...)
- price_snapshots  : (player_id, timestamp, price) + min/max 24h, volume -> 1 ligne / joueur / heure
- market_events    : (timestamp, event_type, ...) nouvelles cartes, SBC, evos, leaks, crash...
- seen_cards       : cartes déjà vues sur "Latest Players" (détection des nouveautés)
- evolutions, leaks, alerts, source_map, bot_status
- decision_log / decision_outcomes : TOUTES les décisions du cerveau (y compris abstentions) et leur
  évaluation théorique à 6 h / 24 h / 48 h / 7 j (prix observés, jamais des ventes réelles)
- price_snapshots_duplicates : archive des relevés en double (jamais supprimés, voir migrate())
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

import config
from utils.helpers import iso, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    player_id    TEXT PRIMARY KEY,
    base_id      TEXT,
    name         TEXT NOT NULL,
    rating       INTEGER,
    position     TEXT,
    alt_positions TEXT,
    league       TEXT,
    nation       TEXT,
    club         TEXT,
    card_type    TEXT,
    playstyles   TEXT,
    url          TEXT,
    source       TEXT,
    popularity_rank INTEGER,
    updated_at   TEXT
);
CREATE TABLE IF NOT EXISTS price_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id  TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    price      INTEGER NOT NULL,
    min_24h    INTEGER,
    max_24h    INTEGER,
    volume     INTEGER,
    source     TEXT
);
CREATE INDEX IF NOT EXISTS idx_snap_player_ts ON price_snapshots(player_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON price_snapshots(timestamp);

CREATE TABLE IF NOT EXISTS price_history (
    player_id TEXT NOT NULL,
    date      TEXT NOT NULL,
    price     INTEGER NOT NULL,
    PRIMARY KEY (player_id, date)
);

CREATE TABLE IF NOT EXISTS market_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title      TEXT,
    player_id  TEXT,
    position   TEXT,
    payload    TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON market_events(timestamp, event_type);

CREATE TABLE IF NOT EXISTS seen_cards (
    player_id   TEXT PRIMARY KEY,
    first_seen  TEXT NOT NULL,
    payload     TEXT
);
CREATE TABLE IF NOT EXISTS evolutions (
    evo_id      TEXT PRIMARY KEY,
    name        TEXT,
    requirements TEXT,
    upgrades    TEXT,
    url         TEXT,
    first_seen  TEXT
);
CREATE TABLE IF NOT EXISTS leaks (
    leak_id     TEXT PRIMARY KEY,
    timestamp   TEXT,
    source      TEXT,
    text        TEXT,
    tags        TEXT,
    first_seen  TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    action      TEXT,
    player_id   TEXT,
    confidence  INTEGER,
    rule        TEXT,
    message     TEXT,
    sent        INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS source_map (
    player_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    external_id TEXT NOT NULL,
    PRIMARY KEY (player_id, source)
);
CREATE TABLE IF NOT EXISTS bot_status (
    key   TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    note       TEXT
);
CREATE TABLE IF NOT EXISTS decision_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    engine         TEXT NOT NULL,
    player_id      TEXT,
    action         TEXT NOT NULL,
    rule           TEXT,
    score          REAL,
    opportunity    INTEGER,
    data_quality   INTEGER,
    observed_price INTEGER,
    observed_at    TEXT,
    target_price   INTEGER,
    reason         TEXT,
    payload        TEXT
);
CREATE INDEX IF NOT EXISTS idx_decision_ts ON decision_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_decision_player ON decision_log(player_id, timestamp);
CREATE TABLE IF NOT EXISTS decision_outcomes (
    decision_id    INTEGER NOT NULL,
    horizon_h      INTEGER NOT NULL,
    evaluated_at   TEXT NOT NULL,
    price          INTEGER,
    price_at       TEXT,
    change         REAL,
    theoretical_net INTEGER,
    verdict        TEXT,
    PRIMARY KEY (decision_id, horizon_h)
);
"""

# Migrations versionnées : chacune dans une transaction, précédée d'une sauvegarde si la base contient des données.
SCHEMA_VERSION = 2


def connect(path=None) -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(str(path or config.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_conn(path=None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path=None) -> None:
    with get_conn(path) as c:
        c.executescript(SCHEMA)
        # migration : tendance 7 jours fournie par la source (futgenie) pour chaque relevé
        cols = {r[1] for r in c.execute("PRAGMA table_info(price_snapshots)")}
        if "trend_7d" not in cols:
            c.execute("ALTER TABLE price_snapshots ADD COLUMN trend_7d REAL")
    migrate(path)


def backup_db(path=None, keep_days: int = 14) -> str | None:
    """Copie cohérente (API backup de SQLite, sûre en WAL) dans data/backups/ + vérification d'intégrité.

    Renvoie le chemin de la sauvegarde, ou None si la base est vide. Lève une erreur si la copie est corrompue.
    """
    src_path = Path(path or config.DB_PATH)
    if not src_path.exists():
        return None
    with sqlite3.connect(src_path) as src:
        has_data = src.execute("SELECT name FROM sqlite_master WHERE name='price_snapshots'").fetchone() and \
            src.execute("SELECT 1 FROM price_snapshots LIMIT 1").fetchone()
        if not has_data:
            return None
        out_dir = src_path.parent / "backups"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{src_path.stem}-{utcnow():%Y%m%d-%H%M%S}.db"
        with sqlite3.connect(dest) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError(f"Sauvegarde corrompue : {dest}")
    limit = utcnow().timestamp() - keep_days * 86400
    for old in out_dir.glob(f"{src_path.stem}-*.db"):
        if old != dest and old.stat().st_mtime < limit:
            old.unlink()
    return str(dest)


def schema_version(conn: sqlite3.Connection) -> int:
    r = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return r[0] or 1


def migrate(path=None) -> None:
    """v2 : unicité (joueur, heure) sur price_snapshots. Les doublons sont ARCHIVÉS, jamais perdus."""
    with get_conn(path) as c:
        if schema_version(c) >= SCHEMA_VERSION:
            return
    backup = backup_db(path)  # avant toute modification ; une erreur ici annule la migration
    with get_conn(path) as c:
        c.execute("BEGIN IMMEDIATE")  # verrou d'écriture : le bot et le dashboard démarrent en même temps
        if schema_version(c) >= SCHEMA_VERSION:
            return  # l'autre processus a déjà migré
        c.execute("CREATE TABLE IF NOT EXISTS price_snapshots_duplicates AS SELECT *, '' AS archived_at "
                  "FROM price_snapshots WHERE 0")
        keep = "SELECT MAX(id) FROM price_snapshots GROUP BY player_id, timestamp"  # garde le relevé le plus récent
        n = c.execute(f"SELECT COUNT(*) FROM price_snapshots WHERE id NOT IN ({keep})").fetchone()[0]
        c.execute(f"INSERT INTO price_snapshots_duplicates SELECT *, ? FROM price_snapshots WHERE id NOT IN ({keep})",
                  (iso(utcnow()),))
        c.execute(f"DELETE FROM price_snapshots WHERE id NOT IN ({keep})")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_snap_player_ts ON price_snapshots(player_id, timestamp)")
        c.execute("INSERT INTO schema_version VALUES (?,?,?)",
                  (2, iso(utcnow()), f"unicité (joueur, heure) ; {n} doublon(s) archivé(s) ; sauvegarde {backup}"))


# ---------------------------------------------------------------- players
PLAYER_FIELDS = (
    "player_id", "base_id", "name", "rating", "position", "alt_positions", "league", "nation",
    "club", "card_type", "playstyles", "url", "source", "popularity_rank",
)


def upsert_player(p: dict, conn: sqlite3.Connection | None = None) -> None:
    row = {k: p.get(k) for k in PLAYER_FIELDS}
    row["player_id"] = str(row["player_id"])
    for k in ("alt_positions", "playstyles"):
        if isinstance(row[k], (list, tuple)):
            row[k] = json.dumps(list(row[k]))
    row["updated_at"] = iso(utcnow())
    cols = ", ".join(row)
    ph = ", ".join(f":{k}" for k in row)
    # COALESCE : ne jamais écraser une info connue par un NULL
    upd = ", ".join(f"{k}=COALESCE(excluded.{k}, players.{k})" for k in row if k != "player_id")
    sql = f"INSERT INTO players ({cols}) VALUES ({ph}) ON CONFLICT(player_id) DO UPDATE SET {upd}"
    if conn is not None:
        conn.execute(sql, row)
    else:
        with get_conn() as c:
            c.execute(sql, row)


def get_player(player_id: str) -> dict | None:
    with get_conn() as c:
        r = c.execute("SELECT * FROM players WHERE player_id=?", (str(player_id),)).fetchone()
    return _player_row(r) if r else None


def get_players(ids: Iterable[str] | None = None) -> list[dict]:
    with get_conn() as c:
        if ids is None:
            rows = c.execute("SELECT * FROM players").fetchall()
        else:
            ids = [str(i) for i in ids]
            if not ids:
                return []
            q = ",".join("?" * len(ids))
            rows = c.execute(f"SELECT * FROM players WHERE player_id IN ({q})", ids).fetchall()
    return [_player_row(r) for r in rows]


def _player_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("alt_positions", "playstyles"):
        try:
            d[k] = json.loads(d[k]) if d.get(k) else []
        except (TypeError, ValueError):
            d[k] = []
    return d


# ---------------------------------------------------------------- prices
def insert_snapshot(player_id: str, price: int, ts: datetime | None = None, min_24h=None, max_24h=None,
                    volume=None, source: str = "futgg", conn: sqlite3.Connection | None = None,
                    trend_7d: float | None = None) -> None:
    args = (str(player_id), iso(ts or utcnow()), int(price), min_24h, max_24h, volume, source, trend_7d)
    # un seul relevé par (joueur, heure) : un 2e relevé dans la même heure remplace le premier
    sql = ("INSERT INTO price_snapshots (player_id, timestamp, price, min_24h, max_24h, volume, source, trend_7d) "
           "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(player_id, timestamp) DO UPDATE SET price=excluded.price, "
           "source=excluded.source, trend_7d=COALESCE(excluded.trend_7d, price_snapshots.trend_7d)")
    if conn is not None:
        conn.execute(sql, args)
    else:
        with get_conn() as c:
            c.execute(sql, args)


def price_stats(player_id: str, days: int = 7, conn: sqlite3.Connection | None = None,
                now: datetime | None = None) -> dict:
    """Prix moyen / min / max sur `days` jours avant `now` + dernière tendance 7j connue de la source.

    `now` : en backtest, l'heure simulée (jamais de prix postérieurs).
    """
    now = now or utcnow()
    since, until = iso(now - timedelta(days=days)), iso(now)
    q = ("SELECT AVG(price), MIN(price), MAX(price), COUNT(*) FROM price_snapshots "
         "WHERE player_id=? AND timestamp>=? AND timestamp<=?")
    qt = ("SELECT trend_7d FROM price_snapshots WHERE player_id=? AND trend_7d IS NOT NULL AND timestamp<=? "
          "ORDER BY timestamp DESC LIMIT 1")

    def run(c):
        avg, lo, hi, n = c.execute(q, (str(player_id), since, until)).fetchone()
        t = c.execute(qt, (str(player_id), until)).fetchone()
        return {"avg": round(avg) if avg else None, "min": lo, "max": hi, "n": n, "trend_7d": t[0] if t else None}

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def insert_history(player_id: str, points: list[tuple[str, int]], conn: sqlite3.Connection | None = None) -> None:
    """Courbe 7j / historique journalier renvoyé par la source (date ISO, prix)."""
    rows = [(str(player_id), d, int(p)) for d, p in points if p]
    sql = "INSERT OR REPLACE INTO price_history (player_id, date, price) VALUES (?,?,?)"
    if conn is not None:
        conn.executemany(sql, rows)
    else:
        with get_conn() as c:
            c.executemany(sql, rows)


def latest_prices() -> dict[str, dict]:
    sql = """
    SELECT s.* FROM price_snapshots s
    JOIN (SELECT player_id, MAX(timestamp) ts FROM price_snapshots GROUP BY player_id) m
      ON m.player_id = s.player_id AND m.ts = s.timestamp
    """
    with get_conn() as c:
        return {r["player_id"]: dict(r) for r in c.execute(sql).fetchall()}


def last_scan_times() -> dict[str, str]:
    """{player_id: timestamp du dernier prix relevé}."""
    with get_conn() as c:
        return {r[0]: r[1] for r in c.execute("SELECT player_id, MAX(timestamp) FROM price_snapshots GROUP BY player_id")}


def sparklines(days: int = 7, step_h: int = 3, now: datetime | None = None) -> dict[str, list[list]]:
    """{player_id: [[timestamp, prix], ...]} : un relevé réel par tranche de `step_h` heures (mini-courbes)."""
    now = now or utcnow()
    out: dict[str, dict[int, list]] = {}
    with get_conn() as c:
        rows = c.execute("SELECT player_id, timestamp, price FROM price_snapshots WHERE timestamp >= ? AND timestamp <= ? "
                         "ORDER BY timestamp", (iso(now - timedelta(days=days)), iso(now))).fetchall()
    for pid, ts, price in rows:
        bucket = int(datetime.fromisoformat(ts).timestamp() // (step_h * 3600))
        out.setdefault(pid, {})[bucket] = [ts, price]  # le dernier relevé de la tranche
    return {pid: list(b.values()) for pid, b in out.items()}


def price_at(player_id: str, ts: datetime, conn: sqlite3.Connection | None = None) -> int | None:
    """Dernier prix connu à/avant `ts`."""
    sql = "SELECT price FROM price_snapshots WHERE player_id=? AND timestamp<=? ORDER BY timestamp DESC LIMIT 1"
    if conn is not None:
        r = conn.execute(sql, (str(player_id), iso(ts))).fetchone()
    else:
        with get_conn() as c:
            r = c.execute(sql, (str(player_id), iso(ts))).fetchone()
    return r["price"] if r else None


def get_snapshots(player_ids: Iterable[str] | None = None, since: datetime | None = None) -> list[dict]:
    sql = "SELECT player_id, timestamp, price FROM price_snapshots WHERE 1=1"
    args: list[Any] = []
    if since is not None:
        sql += " AND timestamp >= ?"
        args.append(iso(since))
    if player_ids is not None:
        ids = [str(i) for i in player_ids]
        if not ids:
            return []
        sql += f" AND player_id IN ({','.join('?' * len(ids))})"
        args += ids
    sql += " ORDER BY timestamp"
    with get_conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


# ---------------------------------------------------------------- events
def add_event(event_type: str, title: str = "", player_id: str | None = None, position: str | None = None,
              payload: dict | None = None, ts: datetime | None = None) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT INTO market_events (timestamp, event_type, title, player_id, position, payload) VALUES (?,?,?,?,?,?)",
            (iso(ts or utcnow()), event_type, title, player_id, position, json.dumps(payload or {}, ensure_ascii=False)),
        )


def get_events(event_type: str | None = None, since: datetime | None = None) -> list[dict]:
    sql = "SELECT * FROM market_events WHERE 1=1"
    args: list[Any] = []
    if event_type:
        sql += " AND event_type=?"
        args.append(event_type)
    if since:
        sql += " AND timestamp>=?"
        args.append(iso(since))
    sql += " ORDER BY timestamp"
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
    for r in rows:
        try:
            r["payload"] = json.loads(r["payload"] or "{}")
        except ValueError:
            r["payload"] = {}
    return rows


def new_cards_since(days: int = 7) -> list[dict]:
    return get_events("new_card", since=utcnow() - timedelta(days=days))


# ---------------------------------------------------------------- seen cards / evos / leaks
def mark_seen(player_id: str, payload: dict) -> bool:
    """True si la carte est NOUVELLE (jamais vue)."""
    with get_conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO seen_cards (player_id, first_seen, payload) VALUES (?,?,?)",
            (str(player_id), iso(utcnow()), json.dumps(payload, ensure_ascii=False)),
        )
        return cur.rowcount == 1


def seen_count() -> int:
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM seen_cards").fetchone()[0]


def save_evolution(evo: dict) -> bool:
    with get_conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO evolutions (evo_id, name, requirements, upgrades, url, first_seen) VALUES (?,?,?,?,?,?)",
            (evo["evo_id"], evo.get("name"), json.dumps(evo.get("requirements", {})),
             json.dumps(evo.get("upgrades", {})), evo.get("url"), iso(utcnow())),
        )
        return cur.rowcount == 1


def save_leak(leak: dict) -> bool:
    with get_conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO leaks (leak_id, timestamp, source, text, tags, first_seen) VALUES (?,?,?,?,?,?)",
            (leak["leak_id"], leak.get("timestamp"), leak.get("source"), leak.get("text"),
             json.dumps(leak.get("tags", [])), iso(utcnow())),
        )
        return cur.rowcount == 1


def get_source_id(player_id: str, source: str) -> str | None:
    with get_conn() as c:
        r = c.execute("SELECT external_id FROM source_map WHERE player_id=? AND source=?", (str(player_id), source)).fetchone()
    return r[0] if r else None


def set_source_id(player_id: str, source: str, external_id: str) -> None:
    with get_conn() as c:
        c.execute("INSERT OR REPLACE INTO source_map VALUES (?,?,?)", (str(player_id), source, str(external_id)))


# ---------------------------------------------------------------- alerts / status
def save_alert(action: str, player_id: str | None, confidence: int, rule: str, message: str, sent: bool = False) -> int:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO alerts (timestamp, action, player_id, confidence, rule, message, sent) VALUES (?,?,?,?,?,?,?)",
            (iso(utcnow()), action, player_id, confidence, rule, message, int(sent)),
        )
        return cur.lastrowid


def recent_alerts(limit: int = 30) -> list[dict]:
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def set_status(key: str, value: Any) -> None:
    with get_conn() as c:
        c.execute("INSERT OR REPLACE INTO bot_status VALUES (?,?,?)",
                  (key, json.dumps(value, ensure_ascii=False, default=str), iso(utcnow())))


def get_status() -> dict:
    with get_conn() as c:
        rows = c.execute("SELECT * FROM bot_status").fetchall()
    out = {}
    for r in rows:
        try:
            out[r["key"]] = {"value": json.loads(r["value"]), "updated_at": r["updated_at"]}
        except ValueError:
            out[r["key"]] = {"value": r["value"], "updated_at": r["updated_at"]}
    return out
