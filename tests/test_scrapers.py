import json

from scrapers.futgg import FutGGScraper
from scrapers.leak_watcher import parse_telegram_page, tag_leak, telegram_url
from scrapers.parsing import extract_players
from scrapers.requirements_parser import parse_evo_requirements, parse_evo_upgrades, parse_sbc_requirements
from tests.conftest import fixture_text
from utils.helpers import parse_price


def test_parse_price():
    assert parse_price("67.5K") == 67500
    assert parse_price("67,5k") == 67500
    assert parse_price("1.2M") == 1_200_000
    assert parse_price("67,500") == 67500
    assert parse_price("45 250") == 45250
    assert parse_price(512000) == 512000
    assert parse_price("abc") is None
    assert parse_price(None) is None


def test_extract_players_json_and_anchors():
    players = extract_players(fixture_text("futgg_list.html"), "https://www.fut.gg")
    by_id = {p["player_id"]: p for p in players}
    assert list(by_id)[:3] == ["50544321", "239085", "256630"]  # ordre de la page conservé
    b = by_id["50544321"]
    assert (b["name"], b["rating"], b["position"], b["price"]) == ("Barcola", 84, "LW", 67500)
    assert b["league"] == "Ligue 1 McDonald's" and b["nation"] == "France"
    assert b["alt_positions"] == ["RW"]
    assert by_id["239085"]["price"] == 512000 and by_id["239085"]["name"] == "Erling Haaland"
    d = by_id["256630"]  # uniquement via l'ancre HTML
    assert (d["rating"], d["position"], d["price"]) == (83, "RW", 45250)


def test_futgg_prices_payload():
    res = FutGGScraper.parse_prices_payload(json.loads(fixture_text("futgg_prices.json")))
    assert res["price"] == 67500
    assert res["volume"] == 3
    assert len(res["history"]) == 3 and res["history"][0][1] == 72000


def test_sbc_requirements():
    txt = """Marquee Matchups
    Min. 1 Players from: Ligue 1
    Min. Team Rating: 84
    Exactly 11 Players in the Squad
    Also needs 2x 85 rated squads"""
    r = parse_sbc_requirements(txt)
    assert r["min_team_rating"] == 84
    assert "Ligue 1" in r["leagues"]
    assert 85 in r["squads"]


def test_evo_parsing():
    req = parse_evo_requirements("Requirements\nOverall Max. 82\nMax Pace 85\nPosition: ST / CF\nMax PlayStyles+ 1")
    assert req["max"]["OVR"] == 82 and req["max"]["PAC"] == 85
    assert req["positions"] == ["ST", "CF"]
    assert req["max_playstyles_plus"] == 1
    up = parse_evo_upgrades("Level 1: +2 Overall, +5 Pace\nLevel 2: +2 Overall, Quick Step+, Finesse Shot")
    assert up["stats"] == {"OVR": 4, "PAC": 5}
    assert "Quick Step" in up["playstyles_plus"] and "Finesse Shot" in up["playstyles"]


def test_telegram_leaks():
    assert telegram_url("@futleaks") == "https://t.me/s/futleaks"
    assert telegram_url("https://t.me/futleaks") == "https://t.me/s/futleaks"
    leaks = parse_telegram_page(fixture_text("telegram.html"), "https://t.me/s/futleaks")
    assert [l["leak_id"] for l in leaks] == ["tg:futleaks/1201", "tg:futleaks/1202"]
    tags = tag_leak(leaks[0]["text"], ["Bradley Barcola", "Isak"])
    assert "totw" in tags and "sbc" in tags and "player:Bradley Barcola" in tags
    assert tag_leak(leaks[1]["text"], ["Isak"]) == []


def test_rarity_classification():
    from utils.rarity import classify, detect_in_text

    assert classify("Team of the Week")["label"] == "TOTW" and classify("IF")["special"]
    assert classify("Gold Rare") == {**classify("Gold Rare"), "label": "Or rare", "special": False}
    assert classify("FUT Heroes")["category"] == "hero" and classify("Icon")["category"] == "icon"
    assert classify("3") is None and classify(None) is None  # ID numérique ignoré
    assert classify("Neon Nights")["label"] == "Neon Nights"  # promo inconnue gardée telle quelle
    assert detect_in_text("Barcola 84 LW 67.5K") is None
    assert detect_in_text("Bradley Barcola Trailblazers 89") == "Trailblazers"


def test_card_type_extracted():
    html = fixture_text("futgg_list.html").replace(
        '<span>83</span><span>RW</span>', '<span>87</span><span>RW</span><span>POTM</span>')
    by_id = {p["player_id"]: p for p in extract_players(html, "https://www.fut.gg")}
    assert by_id["50544321"]["card_type"] == "Or rare"   # depuis le JSON (rarityName)
    assert by_id["256630"]["card_type"] == "POTM"        # depuis le texte de la carte
