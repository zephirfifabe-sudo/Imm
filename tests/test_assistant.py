"""Assistant Discord : recherche de joueurs, textes des commandes, contexte IA, limites, appel IA (simulé)."""
from __future__ import annotations

import json

import httpx
import pytest

import config
from assistant import data, llm
from core.demo import seed_demo


@pytest.fixture(autouse=True)
def fresh_cache():
    data._CACHE.clear()
    llm._MODEL.clear()
    llm._LAST_ASK.clear()


def test_find_players_ignores_accents_and_case():
    seed_demo(days=10)
    assert [p["name"] for p in data.find_players("gyokeres")] == ["Gyökeres"]
    assert data.find_players("hernandez")[0]["name"] == "Theo Hernández"
    assert data.find_players("") == [] and data.find_players("zzzz") == []


def test_command_texts():
    seed_demo(days=10)
    card = data.player_card(data.find_players("doue")[0])
    txt = data.player_text(card)
    assert "Doué" in txt and "Prix :" in txt and "Décision du bot" in txt
    assert "Opportunités du moment" in data.top_text()
    assert data.calendar_text().startswith("📅")
    assert "résumé" in data.summary_text().lower()


def test_llm_context_contains_market_knowledge_and_requested_player():
    seed_demo(days=10)
    ctx = data.llm_context("Je vends Barcola maintenant ?")
    assert "Marché suivi" in ctx and "Base de connaissances" in ctx and "KB-S-001" in ctx
    assert "Fiche demandée" in ctx and "Barcola" in ctx
    assert len(ctx) < 20000  # contexte raisonnable (quota / coût)


def test_daily_limit_and_user_cooldown(monkeypatch):
    monkeypatch.setattr(config, "LLM_DAILY_LIMIT", 2)
    monkeypatch.setattr(config, "LLM_USER_COOLDOWN_S", 15)
    llm.check_limits("a", now=1_000)
    with pytest.raises(llm.LimitReached, match="Attends"):
        llm.check_limits("a", now=1_005)
    llm.check_limits("b", now=1_006)
    with pytest.raises(llm.LimitReached, match="Limite de 2"):
        llm.check_limits("c", now=1_007)


def _fake_provider(status=200, models=("llama-3.1-8b-instant", "llama-3.3-70b-versatile")):
    seen = {}

    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers.get("authorization")
        if status != 200:
            return httpx.Response(status, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Garde tes crédits jusqu'à dimanche."}}]})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_ask_picks_best_model_and_sends_grounded_prompt(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODEL", "")
    client, seen = _fake_provider()
    out = llm.ask("Je fais quoi ce week-end ?", "Marché suivi : -3 %", client=client)
    assert out == "Garde tes crédits jusqu'à dimanche."
    assert seen["body"]["model"] == "llama-3.3-70b-versatile" and seen["auth"] == "Bearer test-key"
    msgs = seen["body"]["messages"]
    assert msgs[0]["role"] == "system" and "UNIQUEMENT sur les données" in msgs[0]["content"]
    assert "DONNÉES DU BOT" in msgs[1]["content"] and "Marché suivi" in msgs[1]["content"]


@pytest.mark.parametrize("status,expected", [(429, "quota"), (401, "Clé IA refusée"), (500, "ne répond pas")])
def test_ask_errors_are_readable(monkeypatch, status, expected):
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    monkeypatch.setattr(config, "LLM_MODEL", "un-modele")
    client, _ = _fake_provider(status=status)
    assert expected in llm.ask("q", "ctx", client=client)


def test_answer_without_key_explains_commands(monkeypatch):
    import asyncio

    from assistant.bot import answer

    monkeypatch.setattr(config, "LLM_API_KEY", "")
    assert "/prix" in asyncio.run(answer("u", "salut"))


def test_discord_client_builds():
    pytest.importorskip("discord")
    from assistant.bot import build_client

    client = build_client()
    assert client.intents.message_content


def _web_provider(web_ok: bool):
    seen = []

    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama-3.3-70b-versatile"}]})
        body = json.loads(req.content)
        seen.append(body["model"])
        if body["model"] == "groq/compound" and not web_ok:
            return httpx.Response(404, json={"error": {"message": "model not found"}})
        txt = "FUT Sheriff annonce Olise 92 (non confirmé)." if body["model"] == "groq/compound" else "Réponse données."
        return httpx.Response(200, json={"choices": [{"message": {"content": txt}}]})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_web_search_used_and_sources_rules(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    monkeypatch.setattr(config, "LLM_WEB_MODEL", "groq/compound")
    client, seen = _web_provider(web_ok=True)
    out = llm.ask("Quels sont les derniers leaks ?", "ctx", client=client, web=True)
    assert out.startswith("🌐") and "non confirmé" in out and seen == ["groq/compound"]


def test_web_search_unavailable_falls_back_to_bot_data(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    monkeypatch.setattr(config, "LLM_MODEL", "")
    monkeypatch.setattr(config, "LLM_WEB_MODEL", "groq/compound")
    client, seen = _web_provider(web_ok=False)
    out = llm.ask("Les leaks de la TOTW ?", "ctx", client=client, web=True)
    assert "recherche web indisponible" in out and "Réponse données." in out
    assert seen == ["groq/compound", "llama-3.3-70b-versatile"]


def test_needs_web_detection(monkeypatch):
    monkeypatch.setattr(config, "LLM_WEB_MODEL", "groq/compound")
    assert llm.needs_web("Quels sont les derniers leaks de FUT Sheriff ?")
    assert llm.needs_web("Y aura-t-il un changement quand GTA va sortir ?")
    assert not llm.needs_web("Je vends Barcola maintenant ?")
    monkeypatch.setattr(config, "LLM_WEB_MODEL", "")
    assert not llm.needs_web("les leaks ?")
