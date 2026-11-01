"""Appel à l'IA (API au format OpenAI : Groq par défaut, OpenRouter, Mistral... selon LLM_BASE_URL).

Garde-fous : limite de questions par jour (tout le serveur), délai minimum entre deux questions d'une même
personne, réponses courtes, et une consigne stricte : n'utiliser que les données du bot, signaler l'incertitude.
"""
from __future__ import annotations

import time
from datetime import datetime

import httpx

import config
from database import db
from utils.helpers import to_local, utcnow
from utils.logger import get_logger

log = get_logger("assistant")

SYSTEM = """Tu es FC27 Sniper, l'assistant d'un petit groupe d'amis qui font du trading sur le marché des transferts \
d'EA SPORTS FC 27 Ultimate Team. Tu réponds en français, de façon claire, concrète et courte (8 lignes maximum), \
comme un pote trader expérimenté.

Règles strictes :
- Appuie-toi UNIQUEMENT sur les données fournies (prix relevés, décisions du bot, base de connaissances, calendrier). \
Si elles ne suffisent pas, dis-le simplement au lieu d'inventer.
- Distingue toujours un fait observé d'une hypothèse ou d'une date non confirmée.
- Les prix sont des prix observés, pas des ventes garanties ; la taxe EA de 5 % s'applique à chaque vente.
- Ne promets jamais de gain. Tu donnes un avis, la décision appartient au joueur. Le bot n'achète jamais rien.
- Ne parle pas de toi comme d'une IA de telle ou telle entreprise ; tu es l'assistant du bot."""

PREFERRED = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-70b-versatile", "qwen/qwen3-32b",
             "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
_MODEL: dict = {}
_LAST_ASK: dict[str, float] = {}


class LimitReached(Exception):
    pass


def enabled() -> bool:
    return bool(config.LLM_API_KEY)


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.LLM_API_KEY}"}


def model(client: httpx.Client | None = None) -> str:
    """Modèle configuré, sinon le meilleur disponible chez le fournisseur (liste lue une fois)."""
    if config.LLM_MODEL:
        return config.LLM_MODEL
    if "id" in _MODEL:
        return _MODEL["id"]
    c = client or httpx.Client(timeout=20)
    try:
        r = c.get(f"{config.LLM_BASE_URL.rstrip('/')}/models", headers=_headers())
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", [])]
    finally:
        if client is None:
            c.close()
    chosen = next((m for m in PREFERRED if m in ids), None) or next((m for m in ids if "70b" in m), None) or ids[0]
    _MODEL["id"] = chosen
    log.info("Modèle IA choisi : %s", chosen)
    return chosen


def check_limits(user_id: str, now: float | None = None) -> None:
    """Lève LimitReached avec un message lisible si la limite du jour ou le délai par personne est dépassé."""
    now = now or time.time()
    last = _LAST_ASK.get(user_id)
    if last and now - last < config.LLM_USER_COOLDOWN_S:
        raise LimitReached(f"⏳ Attends encore {int(config.LLM_USER_COOLDOWN_S - (now - last)) + 1} s avant ta prochaine question.")
    day = to_local(datetime.fromtimestamp(now, tz=utcnow().tzinfo)).strftime("%Y-%m-%d")
    st = (db.get_status().get("llm_usage") or {}).get("value") or {}
    count = st.get("count", 0) if st.get("day") == day else 0
    if count >= config.LLM_DAILY_LIMIT:
        raise LimitReached(f"🛑 Limite de {config.LLM_DAILY_LIMIT} questions par jour atteinte. Reviens demain !")
    db.set_status("llm_usage", {"day": day, "count": count + 1})
    _LAST_ASK[user_id] = now


def ask(question: str, context: str, client: httpx.Client | None = None) -> str:
    """Envoie la question et le contexte ; renvoie la réponse (ou un message d'erreur lisible)."""
    c = client or httpx.Client(timeout=60)
    try:
        body = {"model": model(c), "temperature": 0.3, "max_tokens": 700,
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": f"DONNÉES DU BOT :\n{context}\n\nQUESTION : {question}"}]}
        r = c.post(f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions", headers=_headers(), json=body)
        if r.status_code == 429:
            return "🛑 Le fournisseur d'IA limite les requêtes pour le moment (quota gratuit). Réessaie dans un moment."
        if r.status_code in (401, 403):
            return "🔑 Clé IA refusée : vérifie LLM_API_KEY dans le .env du serveur."
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        return text[:1900]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        log.error("IA en erreur : %s", e)
        return "⚠️ L'IA ne répond pas pour le moment. Réessaie plus tard."
    finally:
        if client is None:
            c.close()
