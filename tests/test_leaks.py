"""Leaks : analyse (type, notes, postes, impacts estimés), anti-flood au 1er passage, salon Discord dédié."""
from __future__ import annotations

import config
from alerts import notifier
from database import db
from scrapers import leak_watcher as lw
from tests.conftest import fixture_text

WL = [{"player_id": "p1", "name": "Bradley Barcola", "rating": 85, "position": "LW", "league": "Ligue 1"},
      {"player_id": "p2", "name": "Bukayo Saka", "rating": 87, "position": "RW", "league": "Premier League"},
      {"player_id": "p3", "name": "Saliba", "rating": 87, "position": "CB", "league": "Premier League"}]


def test_analyze_sbc_leak_points_to_fodder():
    a = lw.analyze_leak("New SBC tomorrow: Icon upgrade requires 88 and 86 rated players, 1 x 90", WL)
    assert a["kind"] == "sbc" and a["ratings"] == [86, 88, 90]
    assert any("86, 88" in i and "KB-K-001" in i for i in a["impact"])


def test_analyze_promo_leak_flags_competition_and_watchlist_players():
    a = lw.analyze_leak("Thunderstruck Team 2 leak: RW 89 Premier League winger, Barcola LW 88 confirmed", WL)
    assert a["kind"] == "promo" and a["positions"] == ["LW", "RW"] and a["leagues"] == ["Premier League"]
    assert a["players"] == ["Bradley Barcola"]
    assert any("Barcola" in i and "ta liste" in i for i in a["impact"])
    assert any("concurrence possible pour Bukayo Saka" in i for i in a["impact"])
    assert not any("Saliba" in i for i in a["impact"])  # autre poste


def test_rating_extraction_ignores_prices_and_percentages():
    assert lw.analyze_leak("Prices up 85% ! Card at 88k, rated 84", [])["ratings"] == [84]


def _fake_fetch(monkeypatch, html: str):
    class F:
        def get(self, url, **k):
            return type("R", (), {"text": html})()

        def close(self):
            pass

    monkeypatch.setattr(lw, "Fetcher", F)
    monkeypatch.setattr(config, "LEAK_CHANNELS", ["futleaks"])


def test_first_read_of_a_channel_is_not_notified(monkeypatch):
    from core import jobs

    _fake_fetch(monkeypatch, fixture_text("telegram.html"))
    sent = []
    monkeypatch.setattr(jobs, "_watchlist", lambda: WL)
    monkeypatch.setattr(notifier, "send_leaks", lambda t: sent.append(t) or True)
    jobs.job_leaks()
    assert sent == []  # 1re lecture : on mémorise sans alerter
    html = fixture_text("telegram.html").replace("futleaks/1201", "futleaks/1301").replace("futleaks/1202", "futleaks/1302")
    _fake_fetch(monkeypatch, html)
    jobs.job_leaks()
    assert len(sent) == 1 and "LEAK" in sent[0] and "Barcola" in sent[0] and "non confirmé" in sent[0]


def test_leaks_go_to_dedicated_webhook(monkeypatch):
    from alerts import discord

    calls = []
    monkeypatch.setattr(config, "DISCORD_LEAKS_WEBHOOK_URL", "https://discord.test/leaks")
    monkeypatch.setattr(discord, "send_message", lambda text, webhook=None: calls.append(webhook) or True)
    assert notifier.send_leaks("x")
    assert calls == ["https://discord.test/leaks"]


def test_leaks_api():
    from fastapi.testclient import TestClient

    from dashboard import app

    db.save_leak({"leak_id": "tg:futleaks/9", "source": "https://t.me/s/futleaks", "text": "SBC 87 rated tomorrow",
                  "tags": ["sbc"], "timestamp": "2026-10-31T10:00:00+00:00"})
    r = TestClient(app).get("/api/leaks").json()
    assert r["leaks"][0]["kind"] == "sbc" and r["leaks"][0]["url"] == "https://t.me/futleaks/9"
