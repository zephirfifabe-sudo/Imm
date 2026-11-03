"""futreveal.com : format réel observé le 03/11 (GET /cards -> items / total / has_more, 50 cartes par page)."""
from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import config
from database import db
from scrapers import futreveal, price_provider
from scrapers.base import FetchError, FetchResult
from utils.helpers import iso, utcnow


def item(i, name, rating, ps, pc=None, rarity="Rare", special=False, sbc=False, created_days=40, age_min=1,
         extinct=False):
    now = utcnow()
    return {
        "id": f"uuid-{i}", "ea_id": 50_000_000 + i, "game_version": "27", "rating": rating,
        "is_special": special, "is_sbc": sbc, "is_objective": False, "is_hero": False, "is_icon": False,
        "created_at": iso(now - timedelta(days=created_days)).replace("+00:00", "Z"),
        "player": {"common_name": name}, "rarity": {"name": rarity}, "primary_position": {"short_name": "ST"},
        "club": {"name": "Club"}, "league": {"name": "Ligue 1"}, "nation": {"name": "France"},
        "price": {"PC": pc or ps, "PS": ps, "XB": ps, "updated_at": iso(now - timedelta(minutes=age_min)),
                  "is_extinct_ps": extinct, "is_extinct_pc": False, "is_extinct_xb": False},
    }


class FakeAPI:
    """Comme le vrai site (03/11) : pagination ignorée, 2 cartes max par réponse ici (50 en vrai), total exact,
    filtre sur SON prix (ici le PC), d'où la fourchette élargie côté bot."""

    def __init__(self, items, fail=False, cap=2):
        self.items, self.fail, self.calls, self.cap = items, fail, [], cap

    def get(self, url, expect="html", retries=0):
        self.calls.append(url)
        if self.fail:
            raise FetchError("futreveal en panne")
        q = parse_qs(urlparse(url).query)
        lo, hi = int(q["price_from"][0]), int(q["price_to"][0])
        inside = sorted((x for x in self.items if lo <= x["price"]["PC"] <= hi), key=lambda x: -x["rating"])
        return FetchResult(url, 200, json.dumps({"items": inside[:self.cap], "total": len(inside),
                                                 "has_more": len(inside) > self.cap}), "httpx")

    def close(self):
        pass


def use(monkeypatch, api):
    monkeypatch.setattr(futreveal, "Fetcher", lambda *a, **k: api)


ITEMS = [
    item(1, "Hakimi", 88, 99_500),
    item(2, "Doué", 83, 35_000, pc=19_000),  # PC sous 20k mais PS dans la fourchette : doit être gardée
    item(3, "Cheap", 80, 15_000),  # hors fourchette PS
    item(4, "SBC Guy", 86, 50_000, sbc=True),  # non vendable
    item(5, "Nouveau TOTW", 87, 120_000, rarity="Team of the Week", special=True, created_days=1),
]


def test_parse_card_reads_nested_objects_and_platform_price():
    c = futreveal.parse_card(ITEMS[4])
    assert (c["name"], c["rating"], c["position"], c["club"], c["price"]) == ("Nouveau TOTW", 87, "ST", "Club", 120_000)
    assert c["card_type"] == "TOTW" and c["special"] and c["tradeable"] and c["released_at"]
    assert futreveal.parse_card({"id": "x"}) is None  # sans nom : ignorée


def test_cards_paginates_and_filters_on_ps_price(monkeypatch):
    api = FakeAPI(ITEMS)
    use(monkeypatch, api)
    fr = futreveal.FutReveal()
    names = {c["name"] for c in fr.cards(20_000, 300_000)}
    assert names == {"Hakimi", "Doué", "Nouveau TOTW"}  # SBC et < 20k (PS) exclues, Doué gardée malgré PC 19k
    assert len(api.calls) >= 2 and "price_from=12000" in api.calls[0]  # fourchette élargie (x0,6 / x1,6)
    assert "page=" not in api.calls[0] and fr.incomplete == 0  # découpage par prix, rien de manquant


def test_split_by_price_gets_every_card_despite_50_card_cap(monkeypatch):
    import random

    rnd = random.Random(3)
    many = [item(i, f"J{i}", 80 + i % 10, rnd.randrange(20_000, 300_000, 250)) for i in range(137)]
    use(monkeypatch, FakeAPI(many, cap=50))
    fr = futreveal.FutReveal()
    got = fr.cards(20_000, 300_000)
    assert len(got) == 137 and fr.incomplete == 0 and fr.requests <= 12


def test_existing_players_keep_their_id_and_history():
    db.upsert_player({"player_id": "fgn-949520", "name": "Achraf Hakimi", "rating": 88, "card_type": "Or rare"})
    known = [{"player_id": "fgn-949520", "name": "Achraf Hakimi", "rating": 88, "card_type": "Or rare", "price": 97_000}]
    cards = [futreveal.parse_card(ITEMS[0]), futreveal.parse_card(ITEMS[4])]
    out = {c["name"]: c["player_id"] for c in futreveal.assign_ids(cards, known)}
    assert out["Hakimi"] == "fgn-949520"  # même nom (dernier mot), même note, prix à ±25 % -> même joueur
    assert out["Nouveau TOTW"] == "fr-50000005"
    assert db.source_ids("futreveal") == {"uuid-1": "fgn-949520", "uuid-5": "fr-50000005"}  # mémorisé
    # 2e passage : le rattachement mémorisé est réutilisé tel quel
    again = futreveal.assign_ids(cards, [])
    assert {c["player_id"] for c in again} == {"fgn-949520", "fr-50000005"}


def test_snapshot_uses_futreveal_and_ignores_stale_prices(monkeypatch):
    items = [item(i, f"J{i}", 85, 30_000 + i * 1000) for i in range(10)]
    items[0] = item(0, "J0", 85, 30_000, age_min=500)  # prix vieux de 8 h : ignoré
    use(monkeypatch, FakeAPI(items))
    monkeypatch.setattr(config, "PRICE_SOURCE", "futreveal")
    players = futreveal.assign_ids([futreveal.parse_card(x) for x in items], [])
    summary = price_provider.snapshot_watchlist(players)
    assert summary["source"] == "futreveal" and summary["ok"] == 9 and summary["stale"] == 1
    assert db.latest_prices()["fr-50000003"]["price"] == 33_000


def test_snapshot_falls_back_to_futgenie(monkeypatch):
    called = []
    monkeypatch.setattr(price_provider, "_snapshot_futgenie", lambda pl: called.append(len(pl)) or {"source": "futgenie"})
    monkeypatch.setattr(config, "PRICE_SOURCE", "futreveal")
    players = [{"player_id": "fgn-1", "name": "A"}, {"player_id": "fgn-2", "name": "B"}]
    use(monkeypatch, FakeAPI([], fail=True))  # site en panne
    assert price_provider.snapshot_watchlist(players)["source"] == "futgenie"
    use(monkeypatch, FakeAPI(ITEMS))  # répond, mais aucun joueur suivi n'y est rattaché (watchlist futgenie)
    assert price_provider.snapshot_watchlist(players)["source"] == "futgenie" and called == [2, 2]


def test_real_release_date_decides_new_card():
    from core.analyzer import MarketAnalyzer

    an = MarketAnalyzer([], version="v2")
    totw = {"player_id": "fgn-1032400", "card_type": "TOTW", "released_at": iso(utcnow() - timedelta(days=1.5))}
    old = {"player_id": "fr-9", "card_type": "Ultimate Scream", "released_at": "2026-10-23T17:05:02.927Z"}
    age = an.card_age(totw)
    assert age["discovery"] and age["special"] and age["days"] == 1.5
    assert an.card_age(old) is None  # sortie le 23/10 : pas neuve, même si le bot la découvre aujourd'hui


def test_dry_run_writes_nothing(monkeypatch):
    use(monkeypatch, FakeAPI(ITEMS))
    txt = futreveal.dry_run()
    assert "3 vendables" in txt and "moins de 4 jours : 1" in txt and "Nouveau TOTW" in txt
    assert db.source_ids("futreveal") == {}  # aucun rattachement enregistré pendant un test
