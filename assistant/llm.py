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

WEB_EXTRA = """
Tu peux faire une recherche web pour cette question (leaks, annonces, actualité). Dans ce cas :
- cite brièvement tes sources (nom du site ou du compte) ;
- présente tout leak ou toute prédiction comme NON CONFIRMÉ tant qu'EA ne l'a pas annoncé ;
- n'invente aucun nom, note ou date que tu n'as pas trouvé."""

# questions qui demandent des infos absentes des données du bot (actualité, leaks, annonces)
WEB_HINTS = ("leak", "fuite", "prédi", "predi", "rumeur", "annonc", "news", "actu", "twitter", " x ", "sheriff",
             "futsheriff", "asy", "dernier", "nouvelle promo", "prochaine promo", "qui sera", "qui va", "sortie de",
             "gta", "patch", "mise à jour d'ea", "roadmap", "aujourd'hui sur", "officiel")


def needs_web(question: str) -> bool:
    q = f" {question.lower()} "
    return bool(config.LLM_WEB_MODEL) and any(h in q for h in WEB_HINTS)


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


def ask(question: str, context: str, client: httpx.Client | None = None, web: bool = False) -> str:
    """Envoie la question et le contexte ; renvoie la réponse (ou un message d'erreur lisible).

    `web=True` : utilise le modèle qui sait chercher sur internet ; s'il est indisponible (non inclus dans
    l'offre, supprimé...), répond quand même avec les seules données du bot en le signalant.
    """
    c = client or httpx.Client(timeout=90)
    try:
        if web:
            out = _complete(c, config.LLM_WEB_MODEL, SYSTEM + WEB_EXTRA, question, context)
            if out is not None:
                return ("🌐 " + out)[:1900]
            log.warning("Recherche web indisponible (%s) : réponse avec les données du bot", config.LLM_WEB_MODEL)
            note = "_(recherche web indisponible : réponse basée uniquement sur les données du bot)_\n"
        else:
            note = ""
        r = _post(c, model(c), SYSTEM, question, context)
        if r.status_code == 429:
            return "🛑 Le fournisseur d'IA limite les requêtes pour le moment (quota gratuit). Réessaie dans un moment."
        if r.status_code in (401, 403):
            return "🔑 Clé IA refusée : vérifie LLM_API_KEY dans le .env du serveur."
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        return (note + text)[:1900]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        log.error("IA en erreur : %s", e)
        return "⚠️ L'IA ne répond pas pour le moment. Réessaie plus tard."
    finally:
        if client is None:
            c.close()


def _post(c: httpx.Client, model_id: str, system: str, question: str, context: str) -> httpx.Response:
    body = {"model": model_id, "temperature": 0.3, "max_tokens": 700,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": f"DONNÉES DU BOT :\n{context}\n\nQUESTION : {question}"}]}
    return c.post(f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions", headers=_headers(), json=body)


def _complete(c: httpx.Client, model_id: str, system: str, question: str, context: str) -> str | None:
    """Réponse du modèle, ou None s'il n'est pas utilisable (modèle absent, payant, quota...)."""
    try:
        r = _post(c, model_id, system, question, context)
        if r.status_code != 200:
            log.warning("Modèle %s refusé par le fournisseur : HTTP %s %s", model_id, r.status_code, r.text[:200])
            return None
        return r.json()["choices"][0]["message"]["content"].strip() or None
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
