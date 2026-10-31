"""Tracker de fodders 85-91 : découverte du filtre futgenie, relevé, analyse, alerte de hausse."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlparse

import config
from database import db
from scrapers import fodder

POINTS = {85: 2100, 86: 4100, 87: 5500, 88: 8300, 89: 11000, 90: 15000, 91: 20000}
BASE_PRICE = {85: 2900, 86: 6000, 87: 7900, 88: 13000, 89: 20750, 90: 35250, 91: 52000}
CARD = ('<a href="/player-items/{id}"><span>Price {p:,} · SBC points {pts:,} · Genie Grade 80</span>'
        '<span>+1.0%</span><span>7d</span></a>')


class FakeFutgenie:
    """Ne comprend que {"sort": "price-asc", "minOvr": r, "maxOvr": r} ; sinon liste par défaut (notes mélangées)."""

    def __init__(self, bump: dict | None = None):
        self.bump, self.calls = bump or {}, 0

    def get(self, url, **k):
        self.calls += 1
        f = json.loads(unquote(parse_qs(urlparse(url).query)["f"][0]))
        if f.get("sort") == "price-asc" and f.get("minOvr") == f.get("maxOvr") in POINTS:
            r = f["minOvr"]
            base = int(BASE_PRICE[r] * self.bump.get(r, 1))
            cards = [{"id": r * 100 + i, "p": base + i * 250, "pts": POINTS[r]} for i in range(12)]
        else:
            cards = [{"id": 9000 + i, "p": 50000 - i * 777, "pts": POINTS[85 + i % 7]} for i in range(12)]
        return type("R", (), {"text": "<html>" + "".join(CARD.format(**c) for c in cards) + "</html>"})()

    def close(self):
        pass


def test_discovery_finds_the_working_filter_and_remembers_it():
    fake = FakeFutgenie()
    done = fodder.snapshot_fodder(fake)
    assert fodder.load_spec()["min"] == "minOvr" and fodder.load_spec()["sort"] == "price-asc"
    assert done[88] == {"min_price": 13000, "avg5": 13500, "sbc_points": 8300, "n": 12}
    calls = fake.calls
    fodder.snapshot_fodder(fake)
    assert fake.calls - calls == len(config.FODDER_RATINGS)  # filtre mémorisé : plus de découverte


def test_no_filter_found_retries_once_a_day(monkeypatch):
    class Never(FakeFutgenie):
        def get(self, url, **k):
            self.calls += 1
            return type("R", (), {"text": "<html></html>"})()

    n = Never()
    assert fodder.snapshot_fodder(n) == {}
    first = n.calls
    assert fodder.snapshot_fodder(n) == {} and n.calls == first  # pas de nouvel essai avant 24 h


def test_status_best_value_and_rising_alert():
    now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
    fake = FakeFutgenie()
    for h in range(48, 0, -1):  # 2 jours de relevés normaux
        fodder.snapshot_fodder(fake, now=now - timedelta(hours=h))
    fake.bump = {88: 1.25}  # le 88 grimpe de 25 % d'un coup (SBC en approche ?)
    fodder.snapshot_fodder(fake, now=now)
    st = {x["rating"]: x for x in fodder.fodder_status(now=now)}
    assert st[88]["price"] == 16250 and round(st[88]["change_24h"], 2) == 0.25
    assert st[85]["per_1k_points"] == round(2900 / 2100 * 1000)
    best = [r for r, x in st.items() if x.get("best_value")]
    assert best == [min(POINTS, key=lambda r: BASE_PRICE[r] / POINTS[r] if r != 88 else 9)]
    alerts = fodder.rising_alerts(list(st.values()), now=now)
    assert [a["rating"] for a in alerts] == [88]
    assert "88" in fodder.format_rising(alerts) and "hypothèse" in fodder.format_rising(alerts)
    assert fodder.rising_alerts(list(st.values()), now=now + timedelta(hours=1)) == []  # pas de répétition (12 h)


def test_fodder_api_and_summary_line():
    from fastapi.testclient import TestClient

    from alerts.notifier import fodder_lines
    from dashboard import app

    fodder.snapshot_fodder(FakeFutgenie())
    r = TestClient(app).get("/api/fodder").json()
    assert r["active"] and {x["rating"] for x in r["rows"]} == set(config.FODDER_RATINGS)
    assert "Fodders" in fodder_lines()[0] and "88" in fodder_lines()[0] and "⭐" not in fodder_lines()[0]


def test_cheapest_card_whatever_its_version():
    """En 90 : la carte or (21 000 pts) est une star à 390k ; le fodder réel est une spéciale moins chère."""
    class Mixed(FakeFutgenie):
        def get(self, url, **k):
            r = super().get(url, **k)
            if '%22minOvr%22%3A90' in url and "price-asc" in url:
                cards = [{"id": 1, "p": 35250, "pts": 26000}, {"id": 2, "p": 39000, "pts": 26000}] + \
                        [{"id": 10 + i, "p": 390000 + i * 1000, "pts": 21000} for i in range(8)]
                r.text = "<html>" + "".join(CARD.format(**c) for c in cards) + "</html>"
            return r

    done = fodder.snapshot_fodder(Mixed())
    assert done[90]["min_price"] == 35250 and done[90]["sbc_points"] == 26000


def test_fodder_report_for_discord():
    fodder.snapshot_fodder(FakeFutgenie())
    txt = fodder.format_report(fodder.fodder_status())
    assert txt.startswith("🧱 **FODDERS") and "**88** : 13" in txt and "pts" not in txt and len(txt) < 1900
