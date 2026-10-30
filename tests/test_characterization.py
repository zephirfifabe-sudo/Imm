"""ÉTAPE 0 : caractérisation du cerveau actuel (aucune règle modifiée).

- Les tests `test_carac_*` FIGENT le comportement actuel : s'ils cassent, c'est qu'une modification
  a changé une décision, volontairement ou non.
- Les tests `xfail(strict=True)` REPRODUISENT les problèmes de docs/AUDIT_CERVEAU.md : ils décrivent le
  comportement attendu et échouent aujourd'hui. Quand l'étape 1 corrigera un problème, le test passera
  et pytest le signalera (XPASS strict) : on retirera alors le marqueur.

Toutes les séries sont synthétiques et horodatées à une date FIXE (pas de dépendance à l'heure réelle).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import config
from alerts import notifier
from core.analyzer import MarketAnalyzer, similarity
from core.pattern_detector import prior_profile
from core.signals import score_to_action
from database import db

NOW = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)  # vendredi 21h à Paris
PLAYER = {"player_id": "c-1", "name": "Testeur", "rating": 85, "position": "ST",
          "league": "Premier League", "nation": "France"}
NO_HABIT = {"score": 0.0, "confidence": 0.0, "deviation": None, "text": "neutre"}


def seed(prices: dict[int, int], pid: str = "c-1", player: dict | None = None) -> None:
    """prices = {heures avant NOW: prix}."""
    db.upsert_player({**(player or PLAYER), "player_id": pid})
    for h, p in prices.items():
        db.insert_snapshot(pid, p, NOW - timedelta(hours=h), source="test")


def flat_then(drop_from_h: int, start: int, end: int, total_h: int = 240) -> dict[int, int]:
    """Prix stable `start` puis variation linéaire jusqu'à `end` sur les `drop_from_h` dernières heures."""
    out = {}
    for h in range(total_h, -1, -1):
        out[h] = start if h > drop_from_h else round(start + (end - start) * (drop_from_h - h) / drop_from_h)
    return out


def analyzer(players=None, rules=None, habit=True, now=NOW, version="v1") -> MarketAnalyzer:
    an = MarketAnalyzer(players or [PLAYER], rules=rules if rules is not None else {}, now=now, version=version)
    if not habit:
        an.habit = lambda *a, **k: NO_HABIT
    return an


# =========================================================================== caractérisation
def test_carac_score_to_action_thresholds():
    assert [score_to_action(s) for s in (0.6, 0.59, 0.3, 0.29, 0, -0.29, -0.3, -0.59, -0.6)] == \
        ["ACHAT FORT", "ACHAT", "ACHAT", "HOLD", "HOLD", "HOLD", "VENTE", "VENTE", "VENTE URGENTE"]


def test_carac_r4_drop_48h_buy():
    seed(flat_then(48, 50000, 40000))  # -20 % en 48 h
    s = analyzer(habit=False).rule4_technical(PLAYER)
    assert (s.rule, s.action, s.confidence, s.price) == ("R4_CHUTE_48H", "ACHAT", 7, 40000)
    assert round(s.score, 3) == 0.52  # 0,65 × min(1, 0,20/0,25)
    assert s.action_text.startswith("ACHETER 38k-40.4k. Revente 44k+")
    assert s.extra["net_profit"] == 1800  # 40000 × 1,10 × 0,95 − 40000 (rebond par défaut 10 %)


def test_carac_r4_drop_just_below_threshold_is_ignored():
    seed(flat_then(48, 50000, 43000))  # -14 %
    assert analyzer(habit=False).rule4_technical(PLAYER) is None


def test_carac_r4_pump_24h_sell():
    seed(flat_then(24, 40000, 52000))  # +30 % en 24 h
    s = analyzer(habit=False).rule4_technical(PLAYER)
    assert (s.rule, s.action, s.confidence) == ("R4_HYPE_24H", "VENTE", 6)
    assert s.action_text == "VENDRE maintenant ≥ 52k. Rachat possible Dim-Lun."  # B4 corrigé (était 51k)


def test_carac_confidence_formula():
    seed(flat_then(48, 50000, 50000))
    an = analyzer()
    an.habit = lambda *a, **k: {"score": 0.5, "confidence": 0.6, "deviation": 0.0, "text": ""}
    s = an.build_signal(PLAYER, "T", 0.8, "x", rule_conf=0.7)
    # score = 0,65×0,8 + 0,35×0,5 = 0,695 ; conf = 10×(0,30 + 0,35×0,869 + 0,20×0,7 + 0,15×0,6)
    assert (round(s.score, 3), s.confidence, s.action, s.risk) == (0.695, 8, "ACHAT FORT", "Faible")
    habit_only = an.build_signal(PLAYER, "HABITUDE", None, "")
    assert (habit_only.action, habit_only.confidence) == ("ACHAT", 7)  # plafonné à ACHAT et 8/10


def test_carac_crash_instant_and_full_scan():
    seed(flat_then(24, 50000, 41000))  # -18 % en 24 h
    an = analyzer(habit=False)
    crash = an.instant_crashes(24)
    assert [(s.rule, s.action) for s in crash] == [("CRASH_INSTANT", "ACHAT")]
    assert [(s.rule, s.action) for s in an.full_scan()] == [("R4_CHUTE_48H", "ACHAT")]


def test_carac_similarity_uses_plus_minus_two():
    ref = {"position": "ST", "league": "Premier League", "nation": "France", "rating": 85}
    assert similarity({**ref, "rating": 87}, ref) == 0.91  # ±2 compte encore (docstring : « ±2 »)
    assert similarity({**ref, "rating": 88}, ref) == 0.70


def test_carac_select_filters_hold_threshold_and_cooldown(monkeypatch):
    seed(flat_then(48, 50000, 40000))
    s = analyzer(habit=False).rule4_technical(PLAYER)
    monkeypatch.setattr(notifier, "send_text", lambda *a, **k: True)
    assert notifier.dispatch([s]) == [s]
    assert notifier.dispatch([s]) == []  # même joueur + même action < 6 h


def test_carac_market_change_needs_five_players():
    players = [{**PLAYER, "player_id": f"m-{i}", "name": f"M{i}"} for i in range(4)]
    for p in players:
        seed(flat_then(24, 10000, 11000), pid=p["player_id"], player=p)
    assert analyzer(players, habit=False).market_change(24) is None


# =========================================================================== migration SQLite
def test_migration_init_db_is_idempotent_and_keeps_rows():
    seed(flat_then(10, 1000, 1000, total_h=10))
    before = db.get_snapshots(["c-1"])
    db.init_db()
    db.init_db()
    assert db.get_snapshots(["c-1"]) == before


def test_migration_adds_trend_column_without_losing_history(tmp_path):
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as c:  # schéma d'avant la colonne trend_7d
        c.execute("CREATE TABLE price_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT NOT NULL, "
                  "timestamp TEXT NOT NULL, price INTEGER NOT NULL, min_24h INTEGER, max_24h INTEGER, "
                  "volume INTEGER, source TEXT)")
        c.executemany("INSERT INTO price_snapshots (player_id, timestamp, price, source) VALUES (?,?,?,?)",
                      [("p", f"2026-10-0{d}T10:00:00+00:00", 1000 + d, "futgenie") for d in range(1, 8)])
    db.init_db(old)
    with sqlite3.connect(old) as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(price_snapshots)")}
        rows = c.execute("SELECT player_id, timestamp, price FROM price_snapshots ORDER BY id").fetchall()
    assert "trend_7d" in cols and len(rows) == 7 and rows[0] == ("p", "2026-10-01T10:00:00+00:00", 1001)


def test_backup_procedure_under_wal_is_complete(tmp_path):
    """Méthode de sauvegarde prévue avant toute migration : API backup de SQLite (cohérente en WAL)."""
    seed(flat_then(100, 1000, 900, total_h=100))
    dest = tmp_path / "backup.db"
    with sqlite3.connect(config.DB_PATH) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
    with sqlite3.connect(dest) as c:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0] == 101


def test_migration_v2_archives_duplicates_and_backs_up(tmp_path):
    """Base existante avec doublons : sauvegarde complète, doublons archivés (rien de perdu), unicité posée."""
    vps = tmp_path / "vps"
    vps.mkdir()
    old = vps / "market_history.db"
    with sqlite3.connect(old) as c:
        c.execute("CREATE TABLE price_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT NOT NULL, "
                  "timestamp TEXT NOT NULL, price INTEGER NOT NULL, min_24h INTEGER, max_24h INTEGER, "
                  "volume INTEGER, source TEXT)")
        rows = [("p", f"2026-10-0{d}T10:00:00+00:00", 1000 + d, "futgenie") for d in range(1, 8)]
        rows += [("p", "2026-10-07T10:00:00+00:00", 2000, "futgenie")]  # doublon (même heure)
        c.executemany("INSERT INTO price_snapshots (player_id, timestamp, price, source) VALUES (?,?,?,?)", rows)
    db.init_db(old)
    with sqlite3.connect(old) as c:
        assert c.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0] == 7
        assert c.execute("SELECT price FROM price_snapshots WHERE timestamp LIKE '2026-10-07%'").fetchone()[0] == 2000
        assert c.execute("SELECT price FROM price_snapshots_duplicates").fetchall() == [(1007,)]
        assert c.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 2
    backups = list((vps / "backups").glob("market_history-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as c:
        assert c.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0] == 8  # copie d'avant migration
    db.init_db(old)  # relancer ne refait rien
    assert len(list((vps / "backups").glob("*.db"))) == 1


# =========================================================================== problèmes de l'audit
def test_audit_b1_one_alert_per_player(monkeypatch):
    from core import jobs
    from scrapers import price_provider

    seed(flat_then(24, 50000, 35000))  # -30 % en 24 h -> CRASH_INSTANT et R4_CHUTE_48H (confiance >= 7)
    monkeypatch.setattr(jobs, "_watchlist", lambda: [PLAYER])
    monkeypatch.setattr(price_provider, "snapshot_watchlist", lambda wl: {"ok": 1})
    def make(wl):  # habitude favorable (ex. dimanche soir) : les deux signaux dépassent 7/10
        an = analyzer(wl)
        an.habit = lambda *a, **k: {"score": 0.6, "confidence": 0.8, "deviation": -0.1, "text": ""}
        return an

    monkeypatch.setattr(jobs, "MarketAnalyzer", make)
    monkeypatch.setattr(notifier, "send_text", lambda *a, **k: True)
    monkeypatch.setattr(notifier, "send_photo", lambda *a, **k: True, raising=False)
    jobs.job_snapshot()
    assert len([a for a in db.recent_alerts(50) if a["player_id"] == "c-1"]) == 1


def test_audit_b2_duplicate_snapshot_counted_once():
    db.upsert_player(PLAYER)
    ts = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    db.insert_snapshot("c-1", 1000, ts, source="test")
    db.insert_snapshot("c-1", 1000, ts, source="test")
    assert db.price_stats("c-1")["n"] == 1


def test_audit_b3_context_does_not_read_the_future():
    past = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(days=3)
    db.upsert_player(PLAYER)
    for h in range(48):
        db.insert_snapshot("c-1", 1000, past - timedelta(hours=h), source="test")
    for h in range(1, 48):
        db.insert_snapshot("c-1", 9000, past + timedelta(hours=h), source="test")  # « futur » du backtest
    ctx = MarketAnalyzer([PLAYER], rules={}, now=past).context("c-1")
    assert ctx["avg_7d"] == 1000 and ctx["max_7d"] == 1000


def test_audit_b4_sell_advice_not_below_observed_price():
    seed(flat_then(24, 40000, 52000))
    s = analyzer(habit=False).rule4_technical(PLAYER)
    assert "≥ 52k" in s.action_text


@pytest.mark.parametrize("version", [pytest.param("v1", marks=pytest.mark.xfail(strict=True, reason="v1 conservé tel quel (retour arrière)")), "v2"])
def test_audit_s1_unproven_habit_does_not_trigger_trades(version):
    thursday = datetime(2026, 10, 29, 20, 0, tzinfo=timezone.utc)  # jeudi 21h Paris
    db.upsert_player(PLAYER)
    for h in range(120):  # 5 jours, prix parfaitement stable
        db.insert_snapshot("c-1", 50000, thursday - timedelta(hours=h), source="test")
    rules = {"GLOBAL": {"profile": list(prior_profile()), "confidence": 0.0, "weeks_observed": 0}}
    s = analyzer(rules=rules, now=thursday, version=version).build_signal(PLAYER, "HABITUDE", None, "")
    assert s.action in ("HOLD", "SURVEILLANCE")


@pytest.mark.parametrize("version", [pytest.param("v1", marks=pytest.mark.xfail(strict=True, reason="v1 conservé tel quel (retour arrière)")), "v2"])
def test_audit_s3_no_buy_without_justified_target(version):
    db.upsert_player(PLAYER)
    for h in range(60):  # 2,5 jours seulement : pas de moyenne 7 j fiable -> pas de cible justifiable
        db.insert_snapshot("c-1", 50000, NOW - timedelta(hours=h), source="test")
    s = analyzer(habit=False, version=version).build_signal(PLAYER, "T", 0.9, "x")
    assert not s.action.startswith("ACHAT")


@pytest.mark.parametrize("version", [pytest.param("v1", marks=pytest.mark.xfail(strict=True, reason="v1 conservé tel quel (retour arrière)")), "v2"])
def test_audit_s5_no_signal_on_stale_price(version):
    seed({h + 72: p for h, p in flat_then(48, 50000, 40000).items()})  # dernier relevé il y a 72 h
    s = analyzer(habit=False, version=version).rule4_technical(PLAYER)
    assert s is None or s.action == "AUCUNE ACTION"


@pytest.mark.parametrize("version", [pytest.param("v1", marks=pytest.mark.xfail(strict=True, reason="v1 conservé tel quel (retour arrière)")), "v2"])
def test_audit_s5_change_not_computed_on_interpolated_point(version):
    prices = {h: 100000 for h in range(100, 59, -1)}  # relevés jusqu'à -60 h
    prices.update({h: 60000 for h in range(36, -1, -1)})  # trou de -59 h à -37 h, puis 60k
    seed(prices)
    assert analyzer(habit=False, version=version).change("c-1", 48) is None  # point « -48 h » jamais relevé



def test_baseline_report_is_read_only():
    from core.baseline import brain_report, data_report

    seed(flat_then(10, 1000, 1000, total_h=10))
    db.insert_snapshot("c-1", 1000, NOW, source="test")  # 2e relevé de la même heure : remplace (étape 1-A)
    before = db.get_snapshots(["c-1"])
    d = data_report()
    assert (d["snapshots"], d["duplicate_keys"], d["duplicate_rows"]) == (11, 0, 0)
    assert brain_report()["watchlist"] == 0
    assert db.get_snapshots(["c-1"]) == before
