"""Explication d'un mouvement de prix, en clair.

Deux questions :
1) Tout le marché ou juste ce joueur ?  -> on compare sa variation 24h à celle (médiane) de la watchlist.
2) Chute de fond ou creux passager ?   -> on regarde sa tendance sur 7 jours.
"""
from __future__ import annotations


def _pct(v: float) -> str:
    return f"{v * 100:+.0f} %"


def explain_move(change_24h: float | None, market_24h: float | None, trend_7d: float | None) -> str:
    if change_24h is None:
        return ""
    parts = []
    if market_24h is not None:
        gap = change_24h - market_24h
        same_way = change_24h * market_24h > 0
        if abs(market_24h) >= 0.03 and same_way and abs(gap) < 0.04:
            parts.append(f"Mouvement **général du marché** ({_pct(market_24h)} sur 24h en moyenne) : "
                         f"pas propre au joueur")
        elif abs(gap) >= 0.04:
            word = "baisse" if gap < 0 else "hausse"
            parts.append(f"{word.capitalize()} **propre au joueur** ({_pct(change_24h)} contre "
                         f"{_pct(market_24h)} pour le marché)")
        elif abs(change_24h) >= 0.03:
            parts.append(f"Marché calme ({_pct(market_24h)}), le joueur suit à peu près")
    if trend_7d is not None:
        if trend_7d <= -0.10 and change_24h < 0:
            parts.append(f"tendance de fond **baissière** sur 7 jours ({_pct(trend_7d)}) : prudence, ça peut continuer")
        elif change_24h <= -0.05 and trend_7d >= 0:
            parts.append(f"sur 7 jours il reste en hausse ({_pct(trend_7d)}) : **creux passager** probable")
        elif trend_7d >= 0.10 and change_24h > 0:
            parts.append(f"tendance de fond **haussière** sur 7 jours ({_pct(trend_7d)})")
        elif change_24h >= 0.05 and trend_7d < 0:
            parts.append(f"mais en baisse sur 7 jours ({_pct(trend_7d)}) : **rebond** à confirmer")
    if not parts:
        return ""
    text = " ; ".join(parts)
    return text[0].upper() + text[1:] + "."
