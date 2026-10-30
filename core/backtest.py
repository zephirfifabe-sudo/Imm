"""BACKTEST : rejoue le passé pour savoir si les signaux auraient RAPPORTÉ des crédits.

Méthode honnête (pas de triche sur le futur) :
- les règles sont apprises UNIQUEMENT sur les données antérieures au début du test ;
- toutes les `step_hours`, l'analyseur ne voit que les prix <= t ;
- ACHAT (confiance >= min_conf) -> on achète 1 carte au prix courant ;
  revente au 1er prix >= cible, sinon au prix du marché après `max_hold_hours` ;
- chaque vente paie la taxe EA de 5 %.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import pandas as pd

import config
from core import pattern_detector as pdt
from core.analyzer import MarketAnalyzer
from core.learner import learn_patterns
from utils.helpers import fmt_price, utcnow
from utils.logger import get_logger

log = get_logger("backtest")


def run_backtest(watchlist: list[dict], days: int = 14, learn_days: int = 30, step_hours: int = 6,
                 min_conf: int = 7, max_hold_hours: int = 120) -> dict:
    end = utcnow().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    rules = learn_patterns(days=learn_days, now=start, save=False)
    full = pdt.load_frame(days + 10, [p["player_id"] for p in watchlist], now=end)
    series = {pid: pdt.hourly_series(full, pid).dropna() for pid in full["player_id"].unique()} if not full.empty else {}

    trades, open_until = [], {}
    t = start
    while t < end - timedelta(hours=step_hours):
        an = MarketAnalyzer(watchlist, rules=rules, now=t)
        for sig in an.full_scan():
            pid = sig.player_id
            if not sig.action.startswith("ACHAT") or sig.confidence < min_conf or not sig.price:
                continue
            if open_until.get(pid) and open_until[pid] > t:  # déjà en position sur ce joueur
                continue
            s = series.get(pid)
            if s is None:
                continue
            t_loc = pd.Timestamp(t).tz_convert(config.TZ)
            future = s[(s.index > t_loc) & (s.index <= t_loc + pd.Timedelta(hours=max_hold_hours))]
            if future.empty:
                continue
            buy = sig.price
            target = buy * (1 + config.MIN_NET_MARGIN) / (1 - config.EA_TAX)
            hit = future[future >= target]
            sell_ts, sell = (hit.index[0], float(hit.iloc[0])) if len(hit) else (future.index[-1], float(future.iloc[-1]))
            profit = sell * (1 - config.EA_TAX) - buy
            trades.append({"player": sig.player_name, "rule": sig.rule, "conf": sig.confidence, "buy_ts": str(t_loc),
                           "buy": buy, "sell_ts": str(sell_ts), "sell": round(sell), "profit": round(profit),
                           "roi": profit / buy, "target_hit": bool(len(hit))})
            open_until[pid] = sell_ts.tz_convert("UTC").to_pydatetime()
        t += timedelta(hours=step_hours)

    by_rule = defaultdict(lambda: {"trades": 0, "profit": 0, "wins": 0})
    for tr in trades:
        r = by_rule[tr["rule"]]
        r["trades"] += 1
        r["profit"] += tr["profit"]
        r["wins"] += tr["profit"] > 0
    summary = {
        "period": f"{start:%Y-%m-%d} -> {end:%Y-%m-%d}",
        "trades": len(trades),
        "total_profit": sum(t["profit"] for t in trades),
        "win_rate": round(sum(t["profit"] > 0 for t in trades) / len(trades), 2) if trades else None,
        "avg_roi": round(sum(t["roi"] for t in trades) / len(trades), 4) if trades else None,
        "by_rule": {k: {**v, "win_rate": round(v["wins"] / v["trades"], 2)} for k, v in by_rule.items()},
        "trades_detail": trades,
    }
    log.info("Backtest %s : %d trades, profit %s, win rate %s", summary["period"], len(trades),
             fmt_price(summary["total_profit"]), summary["win_rate"])
    return summary
