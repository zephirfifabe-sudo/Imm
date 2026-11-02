"""futgenie.gg : formats réels observés (liste et fiche, oct. 2026)."""
from urllib.parse import unquote

from scrapers import futgenie
from scrapers.base import FetchResult

CARD = ('<a class="no-underline block" href="/player-items/{id}"><img src="/coin.png">'
        '<span>{k}</span><span>{p}</span><span>8.30k</span><span>93</span>'
        '<span>Price {p} · SBC points 8,300 · Genie Grade 93</span><span>{chg}%</span><span>7d</span></a>')


def page(cards):
    return "<html><body>" + "".join(CARD.format(**c) for c in cards) + "</body></html>"


FICHE = ("<html><head><title>Achraf Hakimi 88: Price &amp; Stats (FC 27) | FUTGenie</title></head><body>"
         "<h1>Achraf Hakimi</h1><span>99.5k</span><span>Price 99,500 · SBC points 8,300 · Genie Grade 93</span>"
         "<span>Achraf Hakimi</span><span>Common</span><span>Paris SG</span><span>Ligue 1</span>"
         "<span>Morocco</span><span>RB</span></body></html>")


def test_list_url_format():
    url = futgenie.list_url(20000, 250000)
    assert unquote(url.split("f=")[1]) == '{"sort":"grade-desc","minPrice":20000,"maxPrice":250000}'
    assert '"page":3' in unquote(futgenie.list_url(20000, 250000, 3))


def test_parse_cards():
    cards = futgenie.parse_cards(page([{"id": 949520, "k": "98.0k", "p": "98,000", "chg": "-15.4"},
                                       {"id": 949899, "k": "53.0k", "p": "53,000", "chg": "-18.0"}]))
    assert [c["player_id"] for c in cards] == ["fgn-949520", "fgn-949899"]
    assert cards[0]["price"] == 98000 and cards[0]["grade"] == 93 and abs(cards[0]["change_7d"] + 0.154) < 1e-9


def test_parse_fiche():
    p = futgenie.parse_fiche(FICHE, "fgn-949520", "u")
    assert (p["name"], p["rating"], p["price"]) == ("Achraf Hakimi", 88, 99500)
    assert (p["card_type"], p["club"], p["league"], p["nation"], p["position"]) == (
        "Or non rare", "Paris SG", "Ligue 1", "Morocco", "RB")
    p2 = futgenie.parse_fiche(FICHE.replace("<span>Ligue 1</span>", "<span>Ligue 1 McDonald's</span>"), "x", "u")
    assert p2["league"] == "Ligue 1"


class FakeFetcher:
    """Simule futgenie : 30 cartes réparties sur 2 pages, puis la page 3 répète la 2 (fin de liste)."""

    def __init__(self):
        self.calls = []

    def get(self, url, retries=0):
        self.calls.append(url)
        if "/player-items/" in url:
            return FetchResult(url, 200, FICHE, "httpx")
        n = 3 if '"page":3' in unquote(url) else 2 if '"page":2' in unquote(url) else 1
        # page 1 : 23 cartes seulement (une carte sans prix sur le vrai site) ; page 2 : la suite
        ids = range(1, 24) if n == 1 else range(25, 31) if n == 2 else range(25, 31)
        return FetchResult(url, 200, page([{"id": i, "k": "x", "p": f"{20000 + i * 1000:,}", "chg": "1.0"}
                                           for i in ids]), "httpx")

    def close(self):
        pass


def test_watchlist_and_prices():
    fg = futgenie.FutGenie(FakeFetcher())
    players = fg.build_watchlist([(20000, 100000, 28)], max_new=5)
    assert len(players) == 28  # 23 (page 1) + 5 (page 2) : la page « incomplète » n'arrête plus la lecture and players[0]["name"] == "Achraf Hakimi"  # fiche lue pour les nouveaux
    assert sum(1 for p in players if p.get("rating")) == 5  # limite de fiches par passe respectée
    prices = fg.current_prices(players, [(20000, 100000, 28)])
    assert prices["fgn-1"] == 21000 and len(prices) >= 28


def test_fill_missing_names():
    from database import db

    db.upsert_player({"player_id": "fgn-7", "name": "fgn-7", "url": "https://www.futgenie.gg/player-items/7",
                      "source": "futgenie"})
    fg = futgenie.FutGenie(FakeFetcher())
    assert fg.fill_missing([{"player_id": "fgn-7", "url": "https://www.futgenie.gg/player-items/7"}]) == 1
    p = db.get_player("fgn-7")
    assert p["name"] == "Achraf Hakimi" and p["rating"] == 88


def test_parse_fiche_special_card():
    html = FICHE.replace("Achraf Hakimi 88: Price", "Christopher Nkunku 82 Team of the Week: Price").replace(
        "Achraf Hakimi", "Christopher Nkunku")
    p = futgenie.parse_fiche(html, "fgn-1032160", "u")
    assert (p["name"], p["rating"], p["card_type"]) == ("Christopher Nkunku", 82, "TOTW")


def test_parse_fiche_long_name_and_promo():
    long_name = "Mateus Gonçalo Espanha Fernandes"
    html = FICHE.replace("Achraf Hakimi 88: Price", f"{long_name} 85 Destined for Glory: Price").replace(
        "Achraf Hakimi", long_name)
    p = futgenie.parse_fiche(html, "fgn-1030497", "u")
    assert (p["name"], p["rating"], p["card_type"]) == (long_name, 85, "Destined for Glory")


# --------------------------------------------------------------------------- mode « toutes les cartes »
class CatalogFetcher:
    """futgenie réel (02/11) : une recherche ne renvoie que les 10 meilleures cartes de la tranche, page 2 vide."""

    def __init__(self, prices: dict[int, int], fail_after: int | None = None):
        self.prices, self.calls, self.fail_after = prices, [], fail_after

    def get(self, url, retries=0):
        import json

        from scrapers.base import FetchError

        self.calls.append(url)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise FetchError("site en pause")
        f = json.loads(unquote(url.split("f=")[1]))
        if f.get("page", 1) > 1:
            return FetchResult(url, 200, page([]), "httpx")
        inside = sorted((i for i, p in self.prices.items() if f["minPrice"] <= p <= f["maxPrice"]), key=lambda i: -i)[:10]
        return FetchResult(url, 200, page([{"id": i, "k": "x", "p": f"{self.prices[i]:,}", "chg": "1.0"} for i in inside]),
                           "httpx")

    def close(self):
        pass


def catalog(n=137, lo=20000, hi=250000):
    import random

    rnd = random.Random(7)
    return {1_000_000 + i: rnd.randrange(lo, hi, 50) for i in range(n)}


def test_discover_finds_every_card_despite_10_card_limit():
    prices = catalog()
    fg = futgenie.FutGenie(CatalogFetcher(prices))
    ranges, cards, stats = fg.discover(20000, 250000)
    assert {c["player_id"] for c in cards} == {f"fgn-{i}" for i in prices}  # TOUTES les cartes, pas 10
    assert stats["complete"] and stats["saturated"] == 0
    assert ranges[0][0] == 20000 and ranges[-1][1] == 250000
    assert all(a[1] + 1 == b[0] for a, b in zip(ranges, ranges[1:]))  # tranches contiguës, sans trou
    assert stats["requests"] < len(prices)  # bien moins d'une requête par carte


def test_scan_reads_all_ranges_and_resplits_a_range_that_filled_up():
    from database import db

    prices = catalog(60)
    fg = futgenie.FutGenie(CatalogFetcher(prices))
    players = fg.build_all(20000, 250000, max_new=0)
    assert len(players) == 60
    before = len(db.get_status()["fg_ranges"]["value"]["ranges"])
    last = {p["player_id"]: p["price"] for p in players}
    for i in range(15):  # 15 nouvelles cartes arrivent dans la même zone de prix
        prices[1_000_060 + i] = 120_000 + i * 300
    got = fg.scan_ranges(players, last, max_fiches=0, budget=200)
    assert all(p["player_id"] in got for p in players) and fg.skipped == set()  # aucune carte suivie perdue
    assert {f"fgn-{1_000_060 + i}" for i in range(15)} <= set(got)  # tranche recoupée : toutes les nouvelles vues
    assert len(db.get_status()["fg_ranges"]["value"]["ranges"]) > before  # nouveau découpage mémorisé


def test_rotation_when_too_many_ranges_and_network_failure_is_not_hidden():
    from database import db

    prices = catalog()
    fg = futgenie.FutGenie(CatalogFetcher(prices))
    players = fg.build_all(20000, 250000, max_new=0)
    total = len(db.get_status()["fg_ranges"]["value"]["ranges"])
    last = {p["player_id"]: p["price"] for p in players}
    seen = set()
    for _ in range(-(-total // 5)):  # budget 5 tranches par scan : en quelques tours tout est relu
        got = futgenie.FutGenie(CatalogFetcher(prices)).scan_ranges(players, last, max_fiches=0, budget=5)
        seen |= set(got)
    assert seen == {p["player_id"] for p in players}
    # site en panne : les joueurs prévus ce tour-ci ne sont PAS classés « relus plus tard » (l'échec reste visible)
    fg3 = futgenie.FutGenie(CatalogFetcher(prices, fail_after=0))
    got = fg3.scan_ranges(players, last, max_fiches=0, budget=total)
    assert got == {} and fg3.skipped == set()
