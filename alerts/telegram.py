"""Envoi Telegram via l'API Bot HTTP (httpx, synchrone).

Choix volontaire : appeler directement https://api.telegram.org plutôt que la boucle asyncio de
python-telegram-bot -> fonctionne depuis n'importe quel thread du scheduler, sans conflit d'event loop.
"""
from __future__ import annotations

import time

import httpx

import config
from utils.logger import get_logger

log = get_logger("telegram")
API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # limite Telegram 4096


def enabled() -> bool:
    return bool(config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID)


def _call(method: str, data: dict, files: dict | None = None, retries: int = 3) -> bool:
    url = API.format(token=config.TELEGRAM_TOKEN, method=method)
    for attempt in range(retries):
        try:
            r = httpx.post(url, data=data, files=files, timeout=30)
            if r.status_code == 429:  # flood control
                wait = r.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
                continue
            if r.status_code == 200 and r.json().get("ok"):
                return True
            log.error("Telegram %s HTTP %s : %s", method, r.status_code, r.text[:300])
            return False
        except httpx.HTTPError as e:
            log.warning("Telegram %s tentative %d : %s", method, attempt + 1, e)
            time.sleep(2 ** attempt)
    return False


def split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    chunks, cur = [], ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 > limit and cur:
            chunks.append(cur)
            cur = ""
        while len(block) > limit:
            chunks.append(block[:limit])
            block = block[limit:]
        cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        chunks.append(cur)
    return chunks


def send_message(text: str) -> bool:
    if not enabled():
        return False
    ok = True
    for chunk in split_message(text):
        ok &= _call("sendMessage", {"chat_id": config.TELEGRAM_CHAT_ID, "text": chunk,
                                    "disable_web_page_preview": "true"})
    return ok


def send_photo(png: bytes, caption: str = "") -> bool:
    if not enabled():
        return False
    return _call("sendPhoto", {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption[:1000]},
                 files={"photo": ("chart.png", png, "image/png")})
