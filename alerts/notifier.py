"""Dispatcher des alertes : filtre anti-spam, Telegram + Discord, historique en BDD, rapports.

Anti-spam :
- confiance >= ALERT_MIN_CONFIDENCE (7 par défaut), pas de HOLD ;
- même joueur + même action déjà envoyés il y a < ALERT_COOLDOWN_HOURS -> ignoré ;
- au plus ALERT_MAX_PER_REPORT alertes par envoi (les plus fortes d'abord).
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np

import config
from alerts import discord, telegram
from core.signals import Signal, format_alert
from database import db
from utils.helpers import fmt_price, iso, to_local, utcnow
from utils.logger import get_logger

log = get_logger("notifier")
SEP = "\n\n"


def send_text(text: str) -> bool:
    sent_tg = telegram.send_message(text)
    sent_dc = discord.send_message(text)
    if not (telegram.enabled() or discord.enabled()):
        log.info("[aucun canal configuré] %s", text[:300].replace("\n", " | "))
    return sent_tg or sent_dc


def send_photo(png: bytes, caption: str = "") -> None:
    telegram.send_photo(png, caption)
    discord.send_photo(png, caption)


def _in_cooldown(sig: Signal) -> bool:
    since = iso(utcnow() - timedelta(hours=config.ALERT_COOLDOWN_HOURS))
    if sig.player_id:
        cond, arg = "player_id=?", sig.player_id
    else:  # signaux sans joueur (ex: fodders SBC) : on compare le nom affiché
        cond, arg = "player_id IS NULL AND message LIKE ?", f"%{sig.player_name}%"
    with db.get_conn() as c:
        r = c.execute(f"SELECT 1 FROM alerts WHERE {cond} AND action=? AND sent=1 AND timestamp>=? LIMIT 1",
                      (arg, sig.action, since)).fetchone()
    return r is not None


def select(signals: list[Signal], min_conf: int | None = None, limit: int | None = None,
           respect_cooldown: bool = True) -> list[Signal]:
    min_conf = config.ALERT_MIN_CONFIDENCE if min_conf is None else min_conf
    limit = config.ALERT_MAX_PER_REPORT if limit is None else limit
    keep = [s for s in signals if s.action != "HOLD" and s.confidence >= min_conf]
    if respect_cooldown:
        keep = [s for s in keep if not _in_cooldown(s)]
    keep.sort(key=lambda s: (-s.confidence, -abs(s.score)))
    return keep[:limit]


def dispatch(signals: list[Signal], header: str = "", min_conf: int | None = None, limit: int | None = None,
             with_chart: bool = False) -> list[Signal]:
    chosen = select(signals, min_conf, limit)
    if not chosen:
        return []
    text = (header + SEP if header else "") + SEP.join(format_alert(s) for s in chosen)
    ok = send_text(text)
    for s in chosen:
        db.save_alert(s.action, s.player_id, s.confidence, s.rule, format_alert(s), sent=ok)
    if with_chart and ok and chosen[0].player_id:
        from alerts.charts import chart_png

        png = chart_png(chosen[0].player_id)
        if png:
            send_photo(png, f"{chosen[0].title} : réel vs habitude")
    log.info("%d alerte(s) envoyée(s) (%s)", len(chosen), "OK" if ok else "non envoyées")
    return chosen


# --------------------------------------------------------------------------- rapports planifiés
def _now_label() -> str:
    return to_local(utcnow()).strftime("%a %d/%m %H:%M")


def report_pre19(analyzer, leaks: list[dict]) -> str:
    """18h45 : leaks récents + ventes à sécuriser AVANT les nouveautés de 19h."""
    lines = [f"🕡 PRÉ-19H — {_now_label()}"]
    recent = [l for l in leaks if l.get("tags")][:6]
    if recent:
        lines.append("🔮 Leaks des dernières heures :")
        lines += [f"• {l['text'][:180]}" for l in recent]
    else:
        lines.append("🔮 Aucun leak notable.")
    sells = [s for s in analyzer.full_scan() if s.action.startswith("VENTE")]
    exposed = []
    for l in recent:
        exposed += [t.split(":", 1)[1] for t in l["tags"] if t.startswith("player:")]
    if exposed:
        lines.append("⚠️ Joueurs de ta watchlist cités dans les leaks : " + ", ".join(sorted(set(exposed))))
    chosen = select(sells, limit=5)
    if chosen:
        lines.append("🔴 À sécuriser avant 19h :")
        lines += [f"• {s.title} @ {fmt_price(s.price)} (conf {s.confidence}/10) — {s.instant or s.habit[:80]}"
                  for s in chosen]
    return "\n".join(lines)


def report_post19(new_cards: list[dict], signals: list[Signal], sbcs: list[dict], evos: list[dict]) -> str:
    lines = [f"🕖 POST-19H — {_now_label()}"]
    lines.append(f"🆕 {len(new_cards)} nouvelle(s) carte(s) aujourd'hui"
                 + (" : " + ", ".join(f"{c['name']} {c.get('rating')} {c.get('position') or ''}" for c in new_cards[:12])
                    if new_cards else "."))
    if sbcs:
        lines.append("🧩 SBC : " + ", ".join(s["name"] for s in sbcs[:8]))
    if evos:
        lines.append("🧬 Evos : " + ", ".join(e["name"] for e in evos[:8]))
    chosen = select(signals, limit=6, respect_cooldown=False)
    if chosen:
        lines.append("📊 Impact :")
        lines += [f"• [{s.action}] {s.title} ({s.confidence}/10) — {s.instant[:110]}" for s in chosen]
    else:
        lines.append("📊 Aucun impact fort détecté sur ta watchlist.")
    return "\n".join(lines)


def report_recap(analyzer, rules: dict) -> str:
    """23h00 : état du marché, meilleurs achats/ventes, ce que le bot a appris."""
    sigs = analyzer.full_scan()
    changes = [s.change_24h for s in sigs if s.change_24h is not None]
    mood = np.mean(changes) if changes else None
    lines = [f"🌙 RÉCAP 23H — {_now_label()}"]
    if mood is not None:
        trend = "📈 haussier" if mood > 0.02 else "📉 baissier" if mood < -0.02 else "➡️ stable"
        lines.append(f"Marché watchlist (24h) : {mood * 100:+.1f}% {trend} sur {len(changes)} joueurs")
    buys = sorted([s for s in sigs if s.action.startswith("ACHAT")], key=lambda s: -s.score)[:5]
    sells = sorted([s for s in sigs if s.action.startswith("VENTE")], key=lambda s: s.score)[:5]
    if buys:
        lines.append("🟢 Top achats :")
        lines += [f"• {s.title} @ {fmt_price(s.price)} ({s.confidence}/10) {s.action_text}" for s in buys]
    if sells:
        lines.append("🔴 Top ventes :")
        lines += [f"• {s.title} @ {fmt_price(s.price)} ({s.confidence}/10)" for s in sells]
    g = rules.get("GLOBAL", {})
    if g:
        lines.append(f"🧠 Habitudes : meilleur achat {g.get('best_buy')}, meilleure vente {g.get('best_sell')}, "
                     f"crash FUT Champions moyen {g.get('wl_crash_avg')}, confiance {g.get('confidence')}")
    since = iso(utcnow() - timedelta(hours=24))
    with db.get_conn() as c:
        n = c.execute("SELECT COUNT(*) FROM alerts WHERE timestamp>=? AND sent=1", (since,)).fetchone()[0]
    lines.append(f"📨 {n} alerte(s) envoyée(s) aujourd'hui.")
    return "\n".join(lines)
