"""Envoi Discord via webhook (DISCORD_WEBHOOK_URL ; leaks : DISCORD_LEAKS_WEBHOOK_URL si défini)."""
from __future__ import annotations

import httpx

import config
from alerts.telegram import split_message
from utils.logger import get_logger

log = get_logger("discord")


def enabled() -> bool:
    return bool(config.DISCORD_WEBHOOK_URL)


def send_message(text: str, webhook: str | None = None) -> bool:
    url = webhook or config.DISCORD_WEBHOOK_URL
    if not url:
        return False
    ok = True
    for chunk in split_message(text, 1900):  # limite Discord 2000
        try:
            r = httpx.post(url, json={"content": chunk}, timeout=20)
            ok &= r.status_code in (200, 204)
            if r.status_code not in (200, 204):
                log.error("Discord HTTP %s : %s", r.status_code, r.text[:200])
        except httpx.HTTPError as e:
            log.error("Discord KO : %s", e)
            ok = False
    return ok


def send_photo(png: bytes, caption: str = "") -> bool:
    if not enabled():
        return False
    try:
        r = httpx.post(config.DISCORD_WEBHOOK_URL, data={"content": caption[:1900]},
                       files={"file": ("chart.png", png, "image/png")}, timeout=30)
        return r.status_code in (200, 204)
    except httpx.HTTPError as e:
        log.error("Discord photo KO : %s", e)
        return False
