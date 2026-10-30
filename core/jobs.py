"""Scheduler complet (heure de Paris).

  toutes les heures :02   snapshot prix (MÉMOIRE) + alerte instantanée crash >15% / R4
  08:00                   watchlist du jour (150 joueurs populaires 20k-400k)
  toutes les 20 min       leaks (alerte immédiate si un joueur de la watchlist est cité)
  :20 chaque heure        SBC + Evos (toutes les 15 min entre 18h et 21h)
  18:45                   rapport PRÉ-19H (leaks + ventes à sécuriser)
  18:55-20:30 / 3 min     surveillance nouvelles cartes -> analyse d'impact immédiate (R1/R5)
  19:15                   rapport POST-19H
  23:00                   récap du jour
  10:10 et 22:10          rapport des prix + variations 24h/12h (PRICE_REPORT_HOURS)
  lundi 05:00             learn_patterns() (auto-apprentissage sur 30 jours)
"""
from __future__ import annotations

import functools
import json
import traceback
from datetime import time as dtime
from datetime import timedelta

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

import config
from alerts import notifier
from core.analyzer import MarketAnalyzer
from core.learner import learn_patterns, load_rules
from database import db
from utils.helpers import iso, to_local, utcnow
from utils.logger import get_logger

log = get_logger("jobs")


def safe_job(fn):
    """Une erreur dans un job ne doit JAMAIS tuer le bot."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            db.set_status(f"job:{fn.__name__}", {"state": "running"})
            res = fn(*a, **kw)
            db.set_status(f"job:{fn.__name__}", {"state": "ok"})
            return res
        except Exception as e:  # noqa: BLE001
            log.error("Job %s en erreur : %s\n%s", fn.__name__, e, traceback.format_exc())
            db.set_status(f"job:{fn.__name__}", {"state": "error", "error": str(e)[:300]})
    return wrapper


def _watchlist() -> list[dict]:
    from scrapers.watchlist import build_watchlist, load_watchlist

    wl = load_watchlist()
    return wl or build_watchlist()


# --------------------------------------------------------------------------- jobs
@safe_job
def job_snapshot():
    from scrapers.price_provider import snapshot_watchlist

    wl = _watchlist()
    if not wl:
        return
    summary = snapshot_watchlist(wl)
    if not summary["ok"]:
        _notify_pause()
        return
    an = MarketAnalyzer(wl)
    urgent = an.instant_crashes(24) + [s for s in an.full_scan() if s.rule.startswith("R4")]
    notifier.dispatch(urgent, header="⚡ ALERTE MARCHÉ", with_chart=True)


@safe_job
def job_watchlist():
    from scrapers.watchlist import build_watchlist

    wl = build_watchlist()
    notifier.send_text(f"📋 Watchlist du jour : {len(wl)} joueurs entre "
                       f"{config.PRICE_MIN // 1000}k et {config.PRICE_MAX // 1000}k.")


def in_19h_window(now_local=None) -> bool:
    t = (now_local or to_local(utcnow())).time()
    return dtime(18, 55) <= t <= dtime(20, 30)


@safe_job
def job_latest(force: bool = False):
    from scrapers.latest_players import check_new_cards

    if not force and not in_19h_window():
        return
    cards = check_new_cards()
    if cards:
        sigs = MarketAnalyzer(_watchlist()).analyze_new_cards(cards)
        names = ", ".join(f"{c['name']} {c.get('rating')}" for c in cards[:8])
        notifier.dispatch(sigs, header=f"🆕 NOUVEAUTÉS : {names}", min_conf=6)


@safe_job
def job_sbc_evo():
    from scrapers.evolutions import scrape_evolutions
    from scrapers.sbc import scrape_new_sbcs

    an = MarketAnalyzer(_watchlist())
    sigs = []
    for sbc in scrape_new_sbcs():
        sigs += an.rule2_sbc(sbc)
    for evo in scrape_evolutions():
        sigs += an.rule3_evo(evo)
    notifier.dispatch(sigs, header="🧩 SBC / EVO", min_conf=6)


@safe_job
def job_leaks():
    from scrapers.leak_watcher import fetch_leaks

    wl = _watchlist()
    new = fetch_leaks([p["name"] for p in wl])
    hot = [l for l in new if any(t.startswith("player:") for t in l.get("tags", []))]
    if hot:
        notifier.send_text("🔮 LEAK sur ta watchlist :\n\n" + "\n\n".join(l["text"][:400] for l in hot[:5]))


@safe_job
def job_pre19():
    with db.get_conn() as c:
        rows = c.execute("SELECT * FROM leaks WHERE first_seen>=? ORDER BY first_seen DESC",
                         (iso(utcnow() - timedelta(hours=8)),)).fetchall()
    leaks = [{**dict(r), "tags": json.loads(r["tags"] or "[]")} for r in rows]
    notifier.send_text(notifier.report_pre19(MarketAnalyzer(_watchlist()), leaks))


@safe_job
def job_post19():
    since = utcnow() - timedelta(hours=3)
    cards = [e["payload"] for e in db.get_events("new_card", since=since)]
    sbcs = [e["payload"] for e in db.get_events("sbc", since=since)]
    evos = [e["payload"] for e in db.get_events("evo", since=since)]
    sigs = MarketAnalyzer(_watchlist()).analyze_new_cards(cards) if cards else []
    notifier.send_text(notifier.report_post19(cards, sigs, sbcs, evos))


@safe_job
def job_recap():
    notifier.send_text(notifier.report_recap(MarketAnalyzer(_watchlist()), load_rules()))


@safe_job
def job_learn():
    rules = learn_patterns(days=30)
    g = rules.get("GLOBAL", {})
    notifier.send_text(
        f"🧠 Auto-apprentissage terminé : {rules['_meta']['players']} joueurs.\n"
        f"Meilleur achat : {g.get('best_buy')} | Meilleure vente : {g.get('best_sell')}\n"
        f"Crash FUT Champions moyen : {g.get('wl_crash_avg')} | Remontée : {g.get('recovery_avg')} | "
        f"Confiance : {g.get('confidence')}")


@safe_job
def job_price_report():
    notifier.send_messages(notifier.price_report(_watchlist()))


def _notify_pause() -> None:
    """Prévient UNE fois par pause quand FUT.GG bloque le bot (pas de message à chaque heure)."""
    import time as _time
    from urllib.parse import urlparse

    from scrapers.base import blocked_until

    base = "https://www.futgenie.gg" if config.PRICE_SOURCE == "futgenie" else config.FUTGG_BASE
    until = blocked_until(urlparse(base).netloc)
    if not until or (db.get_status().get("pause_notified") or {}).get("value") == until:
        return
    db.set_status("pause_notified", until)
    notifier.send_text(
        f"⚠️ La source de prix ({urlparse(base).netloc}) bloque temporairement le bot. Pause automatique jusqu'à "
        f"{_time.strftime('%H:%M', _time.localtime(until))}, puis reprise toute seule. "
        "Les prix déjà relevés sont conservés.")


def job_heartbeat():
    db.set_status("heartbeat", {"alive": True})


# --------------------------------------------------------------------------- scheduler
def build_scheduler() -> BlockingScheduler:
    s = BlockingScheduler(timezone=config.TZ, executors={"default": ThreadPoolExecutor(4)},
                          job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300})
    s.add_job(job_snapshot, "cron", minute=2, id="snapshot")
    s.add_job(job_watchlist, "cron", hour=8, minute=0, id="watchlist")
    s.add_job(job_leaks, "cron", minute="*/20", id="leaks")
    s.add_job(job_sbc_evo, "cron", minute=20, hour="0-17,21-23", id="sbc_evo")
    s.add_job(job_sbc_evo, "cron", minute="*/15", hour="18-20", id="sbc_evo_19h")
    s.add_job(job_pre19, "cron", hour=18, minute=45, id="pre19")
    s.add_job(job_latest, "cron", hour="18-20", minute="*/3", id="latest")  # filtré 18:55-20:30
    s.add_job(job_post19, "cron", hour=19, minute=15, id="post19")
    s.add_job(job_recap, "cron", hour=23, minute=0, id="recap")
    # rapport des prix : minute 10, après le relevé horaire (lancé à :02, ~3 min)
    s.add_job(job_price_report, "cron", hour=config.PRICE_REPORT_HOURS, minute=10, id="price_report")
    s.add_job(job_learn, "cron", day_of_week="mon", hour=5, minute=0, id="learn")
    s.add_job(job_heartbeat, "interval", minutes=5, id="heartbeat")
    return s


def run_forever() -> None:
    db.init_db()
    db.set_status("started_at", utcnow().isoformat())
    log.info("🚀 FC27 SNIPER ANALYST démarré (TZ=%s)", config.TZ)
    job_heartbeat()
    wl = _watchlist()
    notifier.send_text(f"✅ FC27 Sniper Analyst en ligne — {len(wl)} joueurs surveillés.")
    if not config.RULES_PATH.exists():
        job_learn()
    if wl and not db.latest_prices():
        job_snapshot()
    build_scheduler().start()
