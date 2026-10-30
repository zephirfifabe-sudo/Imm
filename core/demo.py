"""Données de DÉMO : 35 jours d'historique horaire synthétique (cycle hebdo + bruit + tendance).

Sert à valider tout le pipeline (learner, analyzer, dashboard) sans attendre 4 semaines
de vraies données. Toutes les lignes sont marquées source='demo' et supprimables
avec `python main.py demo-reset`.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np

from core.pattern_detector import prior_profile
from database import db
from scrapers.watchlist import save_watchlist
from utils.helpers import iso, to_local, utcnow

DEMO_PLAYERS = [
    ("demo-1", "Barcola", 84, "LW", "Ligue 1", "France", "Paris SG", 70000),
    ("demo-2", "Doué", 83, "RW", "Ligue 1", "France", "Paris SG", 45000),
    ("demo-3", "Isak", 86, "ST", "Premier League", "Sweden", "Newcastle", 180000),
    ("demo-4", "Rodrygo", 85, "RW", "LALIGA EA SPORTS", "Brazil", "Real Madrid", 95000),
    ("demo-5", "Theo Hernández", 84, "LB", "Serie A", "France", "AC Milan", 38000),
    ("demo-6", "Koné", 82, "CDM", "Serie A", "France", "AS Roma", 25000),
    ("demo-7", "Wirtz", 88, "CAM", "Bundesliga", "Germany", "Leverkusen", 320000),
    ("demo-8", "Gyökeres", 85, "ST", "Premier League", "Sweden", "Arsenal", 120000),
    ("demo-9", "Saliba", 87, "CB", "Premier League", "France", "Arsenal", 150000),
    ("demo-10", "Nico Williams", 85, "LW", "LALIGA EA SPORTS", "Spain", "Athletic Club", 88000),
    ("demo-11", "Dembélé", 88, "RW", "Ligue 1", "France", "Paris SG", 260000),
    ("demo-12", "Hakimi", 86, "RB", "Ligue 1", "Morocco", "Paris SG", 110000),
]


def seed_demo(days: int = 35, seed: int = 27) -> int:
    rng = np.random.default_rng(seed)
    prof = prior_profile()
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)
    players = []
    with db.get_conn() as c:
        for i, (pid, name, rating, pos, league, nation, club, base) in enumerate(DEMO_PLAYERS):
            p = {"player_id": pid, "name": name, "rating": rating, "position": pos, "league": league,
                 "nation": nation, "club": club, "card_type": "Gold Rare", "source": "demo", "popularity_rank": i + 1}
            db.upsert_player(p, conn=c)
            amp = rng.uniform(0.7, 1.4)  # chaque joueur réagit plus ou moins au cycle
            trend = rng.uniform(-0.25, 0.10) / (days * 24)
            level, t = 1.0, start
            price = base
            while t <= now:
                h = to_local(t).weekday() * 24 + to_local(t).hour
                level *= 1 + trend + rng.normal(0, 0.004)
                price = base * level * (1 + amp * prof[h]) * (1 + rng.normal(0, 0.01))
                db.insert_snapshot(pid, int(price), t, source="demo", conn=c)
                t += timedelta(hours=1)
            # Scénarios pour déclencher les règles R4 sur les dernières heures
            if pid in ("demo-2", "demo-6"):
                # demo-2 : chute -20% sur 48h (panic sell) ; demo-6 : hype +35% sur 24h
                hours, move = (48, -0.20) if pid == "demo-2" else (24, 0.35)
                ref = db.price_at(pid, now - timedelta(hours=hours), conn=c)
                for k in range(1, hours + 1):
                    ts = now - timedelta(hours=hours - k)
                    price = ref * (1 + move * k / hours)
                    c.execute("UPDATE price_snapshots SET price=? WHERE player_id=? AND timestamp=?",
                              (int(price), pid, iso(ts)))
            players.append({**p, "price": int(price)})
    save_watchlist(players)
    db.set_status("mode", "demo")
    return len(players)


def reset_demo() -> None:
    with db.get_conn() as c:
        c.execute("DELETE FROM price_snapshots WHERE source='demo'")
        c.execute("DELETE FROM players WHERE source='demo'")
        c.execute("DELETE FROM market_events WHERE player_id LIKE 'demo-%' OR payload LIKE '%\"demo\"%'")
        c.execute("DELETE FROM bot_status WHERE key='mode'")
