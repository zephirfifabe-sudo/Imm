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


class FakeFetcher:
    """Simule futgenie : 30 cartes réparties sur 2 pages, puis la page 3 répète la 2 (fin de liste)."""

    def __init__(self):
        self.calls = []

    def get(self, url, retries=0):
        self.calls.append(url)
        if "/player-items/" in url:
            return FetchResult(url, 200, FICHE, "httpx")
        n = 3 if '"page":3' in unquote(url) else 2 if '"page":2' in unquote(url) else 1
        ids = range(1, 25) if n == 1 else range(25, 31)
        return FetchResult(url, 200, page([{"id": i, "k": "x", "p": f"{20000 + i * 1000:,}", "chg": "1.0"}
                                           for i in ids]), "httpx")

    def close(self):
        pass


def test_watchlist_and_prices():
    fg = futgenie.FutGenie(FakeFetcher())
    players = fg.build_watchlist([(20000, 100000, 28)], max_new=5)
    assert len(players) == 28 and players[0]["name"] == "Achraf Hakimi"  # fiche lue pour les nouveaux
    assert sum(1 for p in players if p.get("rating")) == 5  # limite de fiches par passe respectée
    prices = fg.current_prices(players, [(20000, 100000, 28)])
    assert prices["fgn-1"] == 21000 and len(prices) >= 28
