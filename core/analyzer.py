"""CERVEAU : 5 règles d'analyse instantanée + fusion avec les HABITUDES apprises.

R1 Concurrence directe   : nouvelle carte similaire (>85%) à un joueur de la watchlist -> VENTE
R2 SBC / objectif         : SBC qui demande L1 / 85+ ... -> ACHAT des fodders / joueurs concernés
R3 Evo sniping            : joueurs < 20k éligibles à une evo qui les rend meta -> ACHAT MASSIF
R4 Analyse technique      : -15% en 48h sans concurrent -> ACHAT ; +30% en 24h -> VENTE
R5 Saturation             : >= 3 nouvelles cartes même poste dans la semaine -> poste baissier
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import config
from core import learner
from core import pattern_detector as pdt
from core.context import explain_move
from core.signals import Signal, score_to_action
from database import db
from scrapers.requirements_parser import META_PLAYSTYLES
from utils.helpers import POSITION_GROUP, fmt_price, position_distance_score, utcnow
from utils.logger import get_logger

log = get_logger("analyzer")


# --------------------------------------------------------------------------- R1 : similarité
def similarity(new: dict, ref: dict) -> float:
    """Score 0..1 : poste (40%), lien ligue/nation (30%), note ±2 (30%)."""
    pos = position_distance_score(new.get("position"), ref.get("position"))
    for alt in new.get("alt_positions") or []:  # poste secondaire = concurrence un peu moindre
        pos = max(pos, 0.75 * position_distance_score(alt, ref.get("position")))
    same_league = bool(new.get("league")) and new.get("league") == ref.get("league")
    same_nation = bool(new.get("nation")) and new.get("nation") == ref.get("nation")
    link = 1.0 if (same_league and same_nation) else 0.6 if same_league else 0.4 if same_nation else 0.0
    if new.get("rating") and ref.get("rating"):
        d = abs(int(new["rating"]) - int(ref["rating"]))
        rating = max(0.0, 1 - 0.15 * d) if d <= 2 else 0.0
    else:
        rating = 0.0
    return round(0.40 * pos + 0.30 * link + 0.30 * rating, 3)


class MarketAnalyzer:
    def __init__(self, watchlist: list[dict], rules: dict | None = None, now: datetime | None = None,
                 history_days: int = 10):
        self.now = now or utcnow()
        self.now_local = pd.Timestamp(self.now).tz_convert(config.TZ)
        self.watchlist = watchlist
        self.by_id = {str(p["player_id"]): p for p in watchlist}
        self.rules = rules if rules is not None else learner.load_rules()
        self.df = pdt.load_frame(history_days, list(self.by_id), now=self.now)
        self._series: dict[str, pd.Series] = {}
        self._market: dict[int, float | None] = {}

    # ------------------------------------------------------------------ données
    def series(self, pid: str) -> pd.Series:
        if pid not in self._series:
            self._series[pid] = pdt.hourly_series(self.df, pid) if not self.df.empty else pd.Series(dtype=float)
        return self._series[pid]

    def price_now(self, pid: str) -> float | None:
        s = self.series(pid).dropna()
        return float(s.iloc[-1]) if len(s) else (self.by_id.get(pid) or {}).get("price")

    def change(self, pid: str, hours: int) -> float | None:
        s = self.series(pid).dropna()
        if len(s) < 2:
            return None
        past = s[s.index <= s.index[-1] - pd.Timedelta(hours=hours)]
        if past.empty:
            return None
        return float(s.iloc[-1] / past.iloc[-1] - 1)

    def market_change(self, hours: int = 24) -> float | None:
        """Variation médiane de toute la watchlist : sert à dire si un mouvement est général ou individuel."""
        if hours not in self._market:
            vals = [c for c in (self.change(str(p["player_id"]), hours) for p in self.watchlist) if c is not None]
            self._market[hours] = float(np.median(vals)) if len(vals) >= 5 else None
        return self._market[hours]

    def context(self, pid: str) -> dict:
        """Prix moyen/min/max 7j, tendance 7j et explication du mouvement en clair."""
        st = db.price_stats(pid, days=7)
        trend = self.change(pid, 168)
        if trend is None:
            trend = st.get("trend_7d")  # pas encore 7 jours de relevés : tendance affichée par la source
        price = self.price_now(pid)
        vs_avg = (price / st["avg"] - 1) if price and st.get("avg") else None
        return {"avg_7d": st.get("avg"), "min_7d": st.get("min"), "max_7d": st.get("max"), "vs_avg": vs_avg,
                "trend_7d": trend, "explain": explain_move(self.change(pid, 24), self.market_change(24), trend)}

    def habit(self, player: dict, price: float | None = None) -> dict:
        pid = str(player["player_id"])
        price = price or self.price_now(pid)
        rule = learner.rule_for(self.rules, player)
        if not price:
            return pdt.habit_assessment(0, pd.Series(dtype=float), None, self.now_local)
        return pdt.habit_assessment(price, self.series(pid), rule, self.now_local)

    # ------------------------------------------------------------------ fusion
    def build_signal(self, player: dict, rule: str, instant_score: float | None, instant_txt: str,
                     rule_conf: float = 0.7, extra: dict | None = None) -> Signal:
        pid = str(player["player_id"])
        price = self.price_now(pid)
        hab = self.habit(player, price)
        hs, hc = hab["score"], hab["confidence"]
        if instant_score is None:
            # Habitude seule : jamais "FORT"/"URGENTE" ni 9-10/10 sans déclencheur instantané
            score, base_conf = float(np.clip(hs, -0.59, 0.59)), hc
        else:
            score = 0.65 * instant_score + 0.35 * hs
            base_conf = rule_conf
            # Une règle instantanée forte garde sa direction : l'habitude module la force, pas le sens
            if abs(instant_score) >= 0.5 and (np.sign(score) != np.sign(instant_score) or abs(score) < 0.3):
                score = 0.3 * float(np.sign(instant_score))
        agree = 1.0 if (instant_score is None or np.sign(instant_score) == np.sign(hs) or abs(hs) < 0.1) else 0.4
        conf = 10 * (0.30 + 0.35 * min(1, abs(score) / 0.8) + 0.20 * base_conf + 0.15 * hc * agree)
        conf = int(np.clip(round(conf), 1, 8 if instant_score is None else 10))
        action = score_to_action(score)
        rule_d = learner.rule_for(self.rules, player)
        rec = rule_d.get("avg_recovery_value") or 0.10
        net = None
        if price and action.startswith("ACHAT"):
            # Taxe EA 5% : la revente doit couvrir la taxe + une marge nette minimale
            expected = price * (1 + float(np.clip(rec, 0, 0.35)))
            net = expected * (1 - config.EA_TAX) - price
            if net / price < config.MIN_NET_MARGIN:
                action = "HOLD"
                instant_txt = (instant_txt + " " if instant_txt else "") + \
                    f"(Rebond attendu {rec * 100:+.0f}% : marge nette après taxe 5% insuffisante.)"
        if price and action.startswith("ACHAT"):
            act = (f"ACHETER {fmt_price(price * 0.95)}-{fmt_price(price * 1.01)}. "
                   f"Revente {fmt_price(expected)}+ ({rule_d.get('best_sell', 'Jeu-Ven')}) "
                   f"= {fmt_price(net)} net/carte après taxe.")
        elif price and action.startswith("VENTE"):
            act = f"VENDRE maintenant ≥ {fmt_price(price * 0.98)}. Rachat possible {rule_d.get('best_buy', 'Dim-Lun')}."
        else:
            act = "Ne rien faire, attendre un meilleur point d'entrée/sortie."
        risk = "Faible" if conf >= 8 and agree == 1.0 else "Élevé" if conf <= 4 or agree < 1 else "Moyen"
        return Signal(
            action=action, rule=rule, score=round(float(score), 3), confidence=conf, player_id=pid,
            player_name=player.get("name", ""), rating=player.get("rating"), card_type=player.get("card_type"),
            position=player.get("position"), price=int(price) if price else None, change_24h=self.change(pid, 24),
            instant=instant_txt, habit=hab["text"], action_text=act, risk=risk,
            extra={**(extra or {}), "habit_deviation": hab["deviation"], "habit_score": round(hs, 3),
                   "net_profit": round(net) if net is not None else None, **self.context(pid)},
        )

    # ------------------------------------------------------------------ R1
    def rule1_competition(self, new_card: dict) -> list[Signal]:
        out = []
        for p in self.watchlist:
            if str(p["player_id"]) == str(new_card.get("player_id")):
                continue
            sim = similarity(new_card, p)
            if sim > config.SIMILARITY_ALERT:
                txt = (f"Nouvelle carte concurrente {new_card.get('name')} {new_card.get('rating')} "
                       f"({new_card.get('position')}, {new_card.get('league') or '?'}) — similarité {sim * 100:.0f}%.")
                out.append(self.build_signal(p, "R1_CONCURRENCE", -0.85, txt, rule_conf=sim,
                                             extra={"similarity": sim, "new_card": new_card.get("player_id")}))
        return out

    # ------------------------------------------------------------------ R2
    def rule2_sbc(self, sbc: dict) -> list[Signal]:
        req = sbc.get("requirements") or {}
        name = sbc.get("name", "SBC")
        out: list[Signal] = []
        ratings = sorted({r for r in [req.get("min_team_rating"), req.get("min_player_rating"), *req.get("squads", [])] if r})
        if ratings:
            fodder = ", ".join(f"{r}" for r in ratings)
            txt = (f"SBC « {name} » demande des notes {fodder} : la demande en fodders va exploser "
                   f"(acheter les {fodder} les moins chers, revente dans 24-48h).")
            out.append(Signal(action="ACHAT", rule="R2_SBC_FODDER", score=0.6, confidence=7, instant=txt,
                              player_name=f"Fodders {fodder}", action_text=f"ACHETER des {fodder} au prix plancher (discard +10-15%).",
                              risk="Faible", extra={"sbc": name, "ratings": ratings}))
        leagues, nations = set(req.get("leagues") or []), set(req.get("nations") or [])
        min_r = max(ratings) if ratings else 0
        if leagues or nations:
            for p in self.watchlist:
                if (p.get("league") in leagues or p.get("nation") in nations) and (p.get("rating") or 0) >= min_r - 1:
                    link = p.get("league") if p.get("league") in leagues else p.get("nation")
                    txt = f"SBC « {name} » demande des joueurs {link}{f' {min_r}+' if min_r else ''} : demande en hausse."
                    out.append(self.build_signal(p, "R2_SBC_LIEN", 0.55, txt, rule_conf=0.65, extra={"sbc": name}))
        return out

    # ------------------------------------------------------------------ R3
    @staticmethod
    def evo_eligible(player: dict, req: dict) -> bool:
        mx, mn = req.get("max", {}), req.get("min", {})
        stats = {"OVR": player.get("rating"), **(player.get("stats") or {})}
        for k, v in mx.items():
            if stats.get(k) is not None and stats[k] > v:
                return False
        for k, v in mn.items():
            if stats.get(k) is not None and stats[k] < v:
                return False
        if "OVR" in mx and player.get("rating") is None:
            return False
        pos = req.get("positions") or []
        if pos and player.get("position") not in pos and not set(player.get("alt_positions") or []) & set(pos):
            return False
        return True

    def rule3_evo(self, evo: dict, pool: list[dict] | None = None) -> list[Signal]:
        req, up = evo.get("requirements") or {}, evo.get("upgrades") or {}
        pool = pool if pool is not None else db.get_players()
        latest = db.latest_prices()
        gained_meta = [ps for ps in up.get("playstyles_plus", []) + up.get("playstyles", []) if ps.lower() in META_PLAYSTYLES]
        ovr_gain = up.get("stats", {}).get("OVR", 0)
        cands = []
        for p in pool:
            price = (latest.get(str(p["player_id"])) or {}).get("price") or p.get("price")
            if not price or price > config.EVO_CHEAP_MAX or not self.evo_eligible(p, req):
                continue
            final_ovr = (p.get("rating") or 0) + ovr_gain
            meta = len(set(x.lower() for x in (p.get("playstyles") or []) + gained_meta) & META_PLAYSTYLES)
            score = final_ovr + 2.5 * meta - price / 10000
            cands.append((score, p, price, final_ovr, meta))
        cands.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, p, price, final_ovr, meta in cands[:10]:
            if meta < 2 and ovr_gain < 3:
                continue
            txt = (f"Evo « {evo.get('name')} » : {p['name']} ({fmt_price(price)}) éligible -> {final_ovr} OVR "
                   f"avec {meta} playstyles meta. Les joueurs vont acheter pour l'evo.")
            out.append(Signal(action="ACHAT FORT", rule="R3_EVO", score=0.75, confidence=7 if meta >= 3 else 6,
                              player_id=str(p["player_id"]), player_name=p["name"], rating=p.get("rating"),
                              position=p.get("position"), price=int(price), instant=txt,
                              action_text=f"ACHAT MASSIF ≤ {fmt_price(price * 1.1)}, revente +30-80% dans 2-12h.",
                              risk="Moyen", extra={"evo": evo.get("name"), "final_ovr": final_ovr}))
        return out

    # ------------------------------------------------------------------ R4
    def recent_competitor(self, player: dict, hours: int = 48) -> bool:
        for ev in db.get_events("new_card", since=self.now - timedelta(hours=hours)):
            # backtest : ignorer le futur (tolérance 5 min pour les cartes détectées juste après la création)
            if pd.Timestamp(ev["timestamp"]) > pd.Timestamp(self.now) + pd.Timedelta(minutes=5):
                continue
            if similarity(ev.get("payload") or {}, player) > config.SIMILARITY_ALERT:
                return True
        return False

    def rule4_technical(self, player: dict) -> Signal | None:
        pid = str(player["player_id"])
        c48, c24 = self.change(pid, 48), self.change(pid, 24)
        if c48 is not None and c48 <= config.DROP_48H_BUY and not self.recent_competitor(player):
            txt = f"{c48 * 100:+.0f}% en 48h sans nouvelle carte concurrente : panic sell / sur-réaction."
            return self.build_signal(player, "R4_CHUTE_48H", min(1.0, abs(c48) / 0.25), txt, rule_conf=0.7,
                                     extra={"change_48h": c48})
        if c24 is not None and c24 >= config.PUMP_24H_SELL:
            txt = f"{c24 * 100:+.0f}% en 24h sur la hype : prendre les bénéfices avant le retour à la moyenne."
            return self.build_signal(player, "R4_HYPE_24H", -min(1.0, c24 / 0.45), txt, rule_conf=0.7,
                                     extra={"change_24h": c24})
        return None

    # ------------------------------------------------------------------ R5
    def rule5_saturation(self, days: int = 7) -> list[Signal]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for ev in db.new_cards_since(days):
            g = POSITION_GROUP.get(ev.get("position") or "")
            if g:
                groups[g].append(ev)
        out = []
        for g, evs in groups.items():
            if len(evs) < config.SATURATION_COUNT:
                continue
            names = ", ".join(e.get("title") or "?" for e in evs[:5])
            for p in self.watchlist:
                if POSITION_GROUP.get(p.get("position") or "") == g:
                    txt = f"Saturation poste {g} : {len(evs)} nouvelles cartes cette semaine ({names}). Tout le poste va baisser."
                    out.append(self.build_signal(p, "R5_SATURATION", -0.5, txt, rule_conf=0.6,
                                                 extra={"group": g, "count": len(evs)}))
        return out

    # ------------------------------------------------------------------ scans
    def analyze_new_cards(self, cards: list[dict]) -> list[Signal]:
        sigs: list[Signal] = []
        for c in cards:
            sigs += self.rule1_competition(c)
        sigs += self.rule5_saturation()
        return dedupe(sigs)

    def full_scan(self) -> list[Signal]:
        """Un signal par joueur de la watchlist : R4 si déclenchée, sinon habitude seule."""
        sigs = []
        for p in self.watchlist:
            pid = str(p["player_id"])
            if not self.price_now(pid):
                continue
            s = self.rule4_technical(p)
            if s is None:
                s = self.build_signal(p, "HABITUDE", None, "Pas de signal technique particulier.")
            sigs.append(s)
        return sigs

    def instant_crashes(self, hours: int = 24) -> list[Signal]:
        out = []
        for p in self.watchlist:
            c = self.change(str(p["player_id"]), hours)
            if c is not None and c <= config.INSTANT_CRASH_ALERT:
                txt = f"CRASH {c * 100:+.0f}% en {hours}h."
                inst = 0.7 if not self.recent_competitor(p) else -0.3
                out.append(self.build_signal(p, "CRASH_INSTANT", inst, txt, rule_conf=0.6, extra={"change": c}))
        return out


def dedupe(signals: list[Signal]) -> list[Signal]:
    """Un seul signal par joueur : on garde le plus fort (|score| x confiance)."""
    best: dict[str, Signal] = {}
    for s in signals:
        key = s.player_id or s.player_name
        if key not in best or abs(s.score) * s.confidence > abs(best[key].score) * best[key].confidence:
            best[key] = s
    return sorted(best.values(), key=lambda s: (-s.confidence, -abs(s.score)))
