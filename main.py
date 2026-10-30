"""FC27 SNIPER ANALYST V4 FINAL — point d'entrée.

  python main.py                      # = run : bot H24 (scheduler complet + alertes)
  python main.py init                 # crée la BDD
  python main.py watchlist            # scrape les 150 joueurs populaires 20k-400k
  python main.py snapshot             # enregistre les prix de la watchlist (job horaire)
  python main.py logger               # boucle : snapshot toutes les heures 24/7
  python main.py latest               # détecte les nouvelles cartes + analyse d'impact (R1/R5)
  python main.py evos | sbc | leaks   # sources secondaires (R3 / R2 / leaks)
  python main.py backfill             # importe l'historique de prix FUT.GG (mémoire dès le 1er jour)
  python main.py learn                # learn_patterns() -> data/market_rules.json
  python main.py backtest --days 14   # les signaux auraient-ils rapporté ? (taxe 5% incluse)
  python main.py test-alert           # envoie une alerte de test sur Telegram/Discord
  python main.py diagnose             # que renvoient vraiment FUT.GG / FUTBIN ? (pages dans data/debug/)
  python main.py analyze              # scan complet : signaux ACHAT/VENTE/HOLD
  python main.py demo-seed|demo-reset # données synthétiques pour tester sans attendre 30 jours
"""
from __future__ import annotations

import argparse
import json
import sys

from database import db
from utils.logger import get_logger

log = get_logger("main")


def cmd_watchlist(_):
    from scrapers.watchlist import build_watchlist

    wl = build_watchlist()
    print(f"{len(wl)} joueurs dans la watchlist")


def cmd_snapshot(_):
    from scrapers.price_provider import snapshot_watchlist
    from scrapers.watchlist import load_watchlist

    wl = load_watchlist()
    if not wl:
        print("Watchlist vide : lance d'abord `python main.py watchlist`")
        return
    print(snapshot_watchlist(wl))


def cmd_logger(_):
    from apscheduler.schedulers.blocking import BlockingScheduler

    import config

    sched = BlockingScheduler(timezone=config.TZ)
    sched.add_job(cmd_snapshot, "cron", minute=2, args=[None], id="hourly_snapshot", max_instances=1, coalesce=True)
    log.info("Logger horaire démarré (minute 02 de chaque heure)")
    cmd_snapshot(None)
    sched.start()


def _print_signals(signals):
    from core.signals import format_alert

    for s in signals:
        print(format_alert(s))
        print("-" * 50)
    if not signals:
        print("Aucun signal.")


def cmd_latest(_):
    from core.analyzer import MarketAnalyzer
    from scrapers.latest_players import check_new_cards
    from scrapers.watchlist import load_watchlist

    cards = check_new_cards()
    print(f"{len(cards)} nouvelles cartes")
    if cards:
        _print_signals(MarketAnalyzer(load_watchlist()).analyze_new_cards(cards))


def cmd_evos(_):
    from core.analyzer import MarketAnalyzer
    from scrapers.evolutions import scrape_evolutions
    from scrapers.watchlist import load_watchlist

    an = MarketAnalyzer(load_watchlist())
    for evo in scrape_evolutions():
        print(f"Evo : {evo['name']} -> {json.dumps(evo['requirements'], ensure_ascii=False)}")
        _print_signals(an.rule3_evo(evo))


def cmd_sbc(_):
    from core.analyzer import MarketAnalyzer
    from scrapers.sbc import scrape_new_sbcs
    from scrapers.watchlist import load_watchlist

    an = MarketAnalyzer(load_watchlist())
    for sbc in scrape_new_sbcs():
        print(f"SBC : {sbc['name']}")
        _print_signals(an.rule2_sbc(sbc))


def cmd_leaks(_):
    from scrapers.leak_watcher import fetch_leaks
    from scrapers.watchlist import load_watchlist

    for leak in fetch_leaks([p["name"] for p in load_watchlist()]):
        print(f"[{leak['timestamp']}] {leak['tags']} {leak['text'][:200]}")


def cmd_learn(args):
    from core.learner import learn_patterns

    rules = learn_patterns(days=args.days)
    g = rules.get("GLOBAL", {})
    print(json.dumps({k: v for k, v in g.items() if k != "profile"}, ensure_ascii=False, indent=2))
    for k, v in rules.items():
        if k.startswith("_") or k == "GLOBAL":
            continue
        print(f"{k:28s} best_buy={v['best_buy']:18s} crash_dim={v['avg_sunday_crash']} "
              f"remontée={v['avg_recovery_to_thursday']} conf={v['confidence']}")


def cmd_analyze(args):
    from core.analyzer import MarketAnalyzer
    from scrapers.watchlist import load_watchlist

    an = MarketAnalyzer(load_watchlist())
    sigs = sorted(an.full_scan(), key=lambda s: (-s.confidence, -abs(s.score)))
    if not args.all:
        sigs = [s for s in sigs if s.action != "HOLD"]
    _print_signals(sigs[: args.limit])


def cmd_run(_):
    from core.jobs import run_forever

    run_forever()


def cmd_backfill(_):
    from scrapers.backfill import backfill_history
    from scrapers.watchlist import load_watchlist

    print(backfill_history(load_watchlist()))


def cmd_backtest(args):
    from core.backtest import run_backtest
    from scrapers.watchlist import load_watchlist
    from utils.helpers import fmt_price

    res = run_backtest(load_watchlist(), days=args.days, min_conf=args.min_conf)
    print(f"Période {res['period']} : {res['trades']} trades, profit net {fmt_price(res['total_profit'])} "
          f"(1 carte/trade, taxe 5% incluse), win rate {res['win_rate']}, ROI moyen {res['avg_roi']}")
    for rule, r in res["by_rule"].items():
        print(f"  {rule:16s} {r['trades']:3d} trades  profit {fmt_price(r['profit']):>8s}  win {r['win_rate']}")


def cmd_test_alert(_):
    from alerts import notifier
    from core.analyzer import MarketAnalyzer
    from core.signals import format_alert
    from scrapers.watchlist import load_watchlist

    sigs = sorted(MarketAnalyzer(load_watchlist()).full_scan(), key=lambda s: -s.confidence)
    text = "🧪 TEST FC27 Sniper Analyst\n\n" + (format_alert(sigs[0]) if sigs else "Bot opérationnel.")
    print("Envoyé" if notifier.send_text(text) else "Non envoyé (TELEGRAM_TOKEN/CHAT_ID ou DISCORD_WEBHOOK_URL ?)")


def cmd_diagnose(_):
    from scrapers.diagnose import run_diagnose

    run_diagnose()


def cmd_inspect(_):
    from scrapers.diagnose import run_inspect

    run_inspect()


def cmd_demo_seed(_):
    from core.demo import seed_demo

    n = seed_demo()
    print(f"Démo : {n} joueurs x 35 jours de prix horaires générés")


def cmd_demo_reset(_):
    from core.demo import reset_demo

    reset_demo()
    print("Données de démo supprimées")


def main(argv=None):
    ap = argparse.ArgumentParser(description="FC27 SNIPER ANALYST V4 FINAL")
    sub = ap.add_subparsers(dest="cmd")
    for name, fn in [("run", cmd_run), ("diagnose", cmd_diagnose), ("inspect", cmd_inspect), ("backfill", cmd_backfill), ("test-alert", cmd_test_alert),
                     ("init", lambda a: print("BDD OK")), ("watchlist", cmd_watchlist), ("snapshot", cmd_snapshot),
                     ("logger", cmd_logger), ("latest", cmd_latest), ("evos", cmd_evos), ("sbc", cmd_sbc),
                     ("leaks", cmd_leaks), ("demo-seed", cmd_demo_seed), ("demo-reset", cmd_demo_reset)]:
        sub.add_parser(name).set_defaults(fn=fn)
    p = sub.add_parser("learn")
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(fn=cmd_learn)
    p = sub.add_parser("analyze")
    p.add_argument("--all", action="store_true", help="inclure les HOLD")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("backtest")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--min-conf", type=int, default=7)
    p.set_defaults(fn=cmd_backtest)
    args = ap.parse_args(argv)
    if not args.cmd:  # `python main.py` (Docker) = bot H24
        args.fn = cmd_run
    db.init_db()
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
