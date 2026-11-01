"""CERVEAU : 5 règles d'analyse instantanée + fusion avec les HABITUDES apprises.

R1 Concurrence directe   : nouvelle carte similaire (>85%) à un joueur de la watchlist -> VENTE
R2 SBC / objectif         : SBC qui demande L1 / 85+ ... -> ACHAT des fodders / joueurs concernés
R3 Evo sniping            : joueurs < 20k éligibles à une evo qui les rend meta -> ACHAT MASSIF
R4 Analyse technique      : -15% en 48h sans concurrent -> ACHAT ; +30% en 24h -> VENTE
R5 Saturation             : >= 3 nouvelles cartes même poste dans la semaine -> poste baissier

Deux moteurs (config.BRAIN_VERSION) :
  v1 : moteur historique, conservé à l'identique pour comparaison et retour arrière.
  v2 : même détection, mais décision fiabilisée -> ACHAT / VENTE / SURVEILLANCE / AUCUNE ACTION :
       - pas de décision sur des données trop anciennes ou trop rares (qualité des données) ;
       - variations calculées uniquement sur des relevés RÉELS (aucun point interpolé) ;
       - l'habitude ne décide que si elle est validée (confiance + semaines observées), sinon SURVEILLANCE ;
       - ACHAT seulement avec une cible de revente justifiée par les données et une marge nette suffisante ;
       - prix observé / théorique / exécutable distingués, paliers EA respectés ;
       - « opportunité » et « qualité des données » séparées ; probabilité « non disponible » sans résultats.
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
from utils.helpers import POSITION_GROUP, fmt_coins, fmt_price, position_distance_score, round_tier, to_local, utcnow
from utils.helpers import iso
from utils.logger import get_logger
from utils.rarity import classify

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
                 history_days: int = 10, version: str | None = None):
        self.version = version or config.BRAIN_VERSION
        self.now = now or utcnow()
        self.now_local = pd.Timestamp(self.now).tz_convert(config.TZ)
        self.watchlist = watchlist
        self.by_id = {str(p["player_id"]): p for p in watchlist}
        self.rules = rules if rules is not None else learner.load_rules()
        self.df = pdt.load_frame(history_days, list(self.by_id), now=self.now)
        self._series: dict[str, pd.Series] = {}
        self._raw: dict[str, pd.Series] = {}
        self._market: dict[int, float | None] = {}
        self._track: dict | None = None
        self._ages: dict | None = None

    # ------------------------------------------------------------------ données
    def series(self, pid: str) -> pd.Series:
        if pid not in self._series:
            self._series[pid] = pdt.hourly_series(self.df, pid) if not self.df.empty else pd.Series(dtype=float)
        return self._series[pid]

    def price_now(self, pid: str) -> float | None:
        s = self.series(pid).dropna()
        return float(s.iloc[-1]) if len(s) else (self.by_id.get(pid) or {}).get("price")

    def raw(self, pid: str) -> pd.Series:
        """Relevés RÉELS uniquement (aucune interpolation), index heure locale."""
        if pid not in self._raw:
            d = self.df.loc[self.df["player_id"] == str(pid)] if not self.df.empty else self.df
            s = d.set_index("ts")["price"].sort_index() if len(d) else pd.Series(dtype=float)
            self._raw[pid] = s[~s.index.duplicated(keep="last")]
        return self._raw[pid]

    def change_real(self, pid: str, hours: int) -> float | None:
        """Variation entre le dernier relevé et un relevé réel situé à `hours` (± tolérance) ; sinon None."""
        s = self.raw(pid)
        if len(s) < 2:
            return None
        target = s.index[-1] - pd.Timedelta(hours=hours)
        tol = pd.Timedelta(hours=config.REAL_POINT_TOLERANCE_H)
        near = s[(s.index >= target - tol) & (s.index <= target + tol)]
        if near.empty:
            return None
        ref = near.iloc[int(np.argmin(np.abs((near.index - target).total_seconds())))]
        return float(s.iloc[-1] / ref - 1)

    def quality(self, pid: str) -> dict:
        """Qualité des données (0-100) : fraîcheur du dernier relevé + couverture réelle sur 48 h."""
        s = self.raw(pid)
        now_l = pd.Timestamp(self.now).tz_convert(config.TZ)
        if s.empty:
            return {"score": 0, "ok": False, "age_h": None, "n_48h": 0, "n_7d": 0, "reason": "aucun relevé"}
        age = (now_l - s.index[-1]).total_seconds() / 3600
        n48 = int((s.index > now_l - pd.Timedelta(hours=48)).sum())
        n7 = int((s.index > now_l - pd.Timedelta(days=7)).sum())
        fresh = float(np.clip(1 - (age - 1.5) / 22.5, 0, 1))
        score = int(round(100 * (0.5 * fresh + 0.5 * min(1.0, n48 / 48))))
        reason = ""
        if age > config.MAX_PRICE_AGE_H:
            reason = f"dernier prix relevé il y a {age:.0f} h (max {config.MAX_PRICE_AGE_H:g} h)"
        elif n48 < config.MIN_POINTS_48H:
            reason = f"seulement {n48} relevés sur 48 h (min {config.MIN_POINTS_48H})"
        return {"score": score, "ok": not reason, "age_h": round(age, 1), "n_48h": n48, "n_7d": n7,
                "observed_at": s.index[-1].isoformat(), "reason": reason}

    def change(self, pid: str, hours: int) -> float | None:
        if self.version == "v2":
            return self.change_real(pid, hours)
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
        st = db.price_stats(pid, days=7, now=self.now)
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
                     rule_conf: float = 0.7, extra: dict | None = None, hold_reason: str = "") -> Signal:
        if self.version == "v2":
            return self._build_v2(player, rule, instant_score, instant_txt, rule_conf, extra, hold_reason)
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
            act = f"VENDRE maintenant ≥ {fmt_price(round_tier(price))}. Rachat possible {rule_d.get('best_buy', 'Dim-Lun')}."
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


    # ------------------------------------------------------------------ moteur v2
    def track_record(self, rule: str, action: str) -> dict | None:
        """Fréquence historique favorable à 24 h pour (règle, action), seulement si assez de résultats évalués."""
        if self._track is None:
            from core.decision_journal import track_records

            self._track = track_records(engine="v2", horizon_h=24, now=self.now)
        r = self._track.get((rule, action))
        return r if r and r["n"] >= config.PROBA_MIN_SAMPLES else None

    def card_age(self, player: dict) -> dict | None:
        """Âge d'une carte NEUVE (apparue alors que le bot tournait déjà) et sa phase de découverte du prix.

        Une carte déjà présente au démarrage du bot n'a pas d'âge connu -> None (jamais considérée comme neuve).
        """
        if self._ages is None:
            until = iso(self.now)
            with db.get_conn() as c:
                rows = c.execute("SELECT player_id, MIN(timestamp) FROM price_snapshots WHERE source != 'demo' "
                                 "AND timestamp <= ? GROUP BY player_id", (until,)).fetchall()
            first = {pid: datetime.fromisoformat(t) for pid, t in rows}
            start = min(first.values()) if first else None
            self._ages = {"start": start, "first": first}
        pid = str(player["player_id"])
        first, start = self._ages["first"].get(pid), self._ages["start"]
        if first is None or start is None or first - start < timedelta(hours=12):
            return None
        special = classify(player.get("card_type")).get("special", False)
        days = (self.now - first).total_seconds() / 86400
        limit = config.NEW_CARD_DAYS_SPECIAL if special else config.NEW_CARD_DAYS_BASE
        return {"days": round(days, 1), "special": special, "discovery": days < limit, "limit": limit}

    def calendar(self) -> list[str]:
        """Événements proches tirés de la base de connaissances : contexte affiché, n'influence pas la décision."""
        if not hasattr(self, "_calendar"):
            from knowledge.service import get_service

            self._calendar = get_service().upcoming_text(self.now_local, days=7)
        return self._calendar

    def _build_v2(self, player: dict, rule: str, instant_score: float | None, instant_txt: str,
                  rule_conf: float = 0.7, extra: dict | None = None, hold_reason: str = "") -> Signal:
        """`hold_reason` : une condition du déclencheur n'est pas remplie -> SURVEILLANCE au lieu d'ACHAT/VENTE."""
        pid = str(player["player_id"])
        price = self.price_now(pid)
        q = self.quality(pid)
        hab = self.habit(player, price)
        hs, hc = hab["score"], hab["confidence"]
        rule_d = learner.rule_for(self.rules, player)
        weeks = rule_d.get("weeks_observed") or 0
        habit_ok = hc >= config.HABIT_MIN_CONFIDENCE and weeks >= config.HABIT_MIN_WEEKS
        hs_used = hs if habit_ok else 0.0

        if instant_score is None:
            score = float(np.clip(hs_used, -0.59, 0.59))
        else:
            score = 0.65 * instant_score + 0.35 * hs_used
            if abs(instant_score) >= 0.5 and (np.sign(score) != np.sign(instant_score) or abs(score) < 0.3):
                score = 0.3 * float(np.sign(instant_score))
        action = "ACHAT" if score >= 0.3 else "VENTE" if score <= -0.3 else "AUCUNE ACTION"
        reason = "" if action != "AUCUNE ACTION" else "aucun signal net"
        lean = score if action != "AUCUNE ACTION" else (hs if instant_score is None else score)
        if action == "AUCUNE ACTION" and instant_score is None and not habit_ok and abs(hs) >= 0.3:
            action = "SURVEILLANCE"
            reason = (f"l'habitude suggère {'un achat' if hs > 0 else 'une vente'} mais n'est pas validée "
                      f"(confiance {hc * 100:.0f} %, {weeks} semaine(s) observée(s))")

        observed_at = q.get("observed_at")
        buy_max = target = sell_min = net = None
        if price and action == "ACHAT":
            st = db.price_stats(pid, days=7, now=self.now)
            rec = rule_d.get("avg_recovery_value")
            if instant_score is not None and st.get("avg") and (st.get("n") or 0) >= config.TARGET_MIN_POINTS:
                target = float(st["avg"])  # retour vers la moyenne 7 j (prix observés)
            elif habit_ok and rec and st.get("max"):
                target = min(price * (1 + float(np.clip(rec, 0, 0.35))), float(st["max"]))
            if target is None:
                action, reason = "SURVEILLANCE", "aucune cible de revente justifiée par les données (historique trop court)"
            else:
                buy_max, sell_min = round_tier(price, "down"), round_tier(target, "down")
                net = sell_min * (1 - config.EA_TAX) - buy_max
                if net / buy_max < config.MIN_NET_MARGIN:
                    action = "SURVEILLANCE"
                    reason = (f"marge nette théorique {net / buy_max * 100:+.1f} % après taxe "
                              f"(min {config.MIN_NET_MARGIN * 100:.0f} %)")
        if hold_reason and action in ("ACHAT", "VENTE"):
            action, reason = "SURVEILLANCE", hold_reason
        age = self.card_age(player)
        # carte neuve : la « découverte du prix » prime sur les autres raisons dès qu'un déclencheur existe
        if age and age["discovery"] and (action in ("ACHAT", "VENTE") or (action == "SURVEILLANCE" and instant_score is not None)):
            kind = "spéciale" if age["special"] else "nouvelle"
            action, reason = "SURVEILLANCE", (f"carte {kind} sortie il y a {age['days']:.1f} j : prix encore en "
                                              f"découverte (stabilisation attendue après ~{age['limit']:g} j, KB-S-012)")
        if not q["ok"]:
            action, reason = "AUCUNE ACTION", f"données insuffisantes : {q['reason']}"
        if not price:
            action, reason = "AUCUNE ACTION", "aucun prix observé"

        opportunity = int(round(min(1.0, abs(lean) / 0.8) * 100))
        conf = int(np.clip(round(opportunity * q["score"] / 1000), 1, 10))
        if action not in ("ACHAT", "VENTE"):
            conf = min(conf, 4)  # jamais envoyé sur Discord
        track = self.track_record(rule, action)
        when = to_local(pd.Timestamp(observed_at).to_pydatetime()).strftime("%Hh%M") if observed_at else "?"
        if action == "ACHAT":
            act = (f"ACHETER ≤ {fmt_coins(buy_max)} (prix observé {fmt_coins(price)} à {when}). Revente théorique "
                   f"≥ {fmt_coins(sell_min)} = {fmt_coins(net)} net/carte après taxe (théorique, non garanti).")
        elif action == "VENTE":
            act = (f"VENDRE vers {fmt_coins(round_tier(price, 'nearest'))} (prix observé à {when} ; "
                   f"prix réellement obtenu non garanti).")
        elif action == "SURVEILLANCE":
            act = f"Surveiller, ne pas agir pour l'instant : {reason}."
        else:
            act = f"Ne rien faire : {reason}."
        return Signal(
            action=action, rule=rule, score=round(float(score), 3), confidence=conf, player_id=pid,
            player_name=player.get("name", ""), rating=player.get("rating"), card_type=player.get("card_type"),
            position=player.get("position"), price=int(price) if price else None, change_24h=self.change(pid, 24),
            instant=instant_txt, habit=hab["text"] + ("" if habit_ok else " (habitude non validée : n'influence pas la décision)"),
            action_text=act, risk="Élevé" if q["score"] < 70 else "Moyen",
            extra={**(extra or {}), "engine": "v2", "reason": reason, "calendar": self.calendar(), "card_age": age, "opportunity": opportunity,
                   "data_quality": q["score"], "quality": q, "probability": track, "habit_validated": habit_ok,
                   "habit_deviation": hab["deviation"], "habit_score": round(hs, 3),
                   "observed_price": int(price) if price else None, "observed_at": observed_at,
                   "buy_max": buy_max, "target_price": round(target) if target else None, "sell_min": sell_min,
                   "executable_price": None, "net_profit": round(net) if net is not None else None,
                   **self.context(pid)},
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
        if self.version == "v2":
            return self._rule4_relative(player)
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

    def _rule4_relative(self, player: dict) -> Signal | None:
        """R4 v2 : chute / hausse comparée au marché suivi (force relative) + stabilisation avant tout achat.

        Une chute que tout le marché subit n'est pas une affaire (piège observé sur v1 : 92 % d'achats perdants
        à 24 h en marché baissier). On n'achète que l'écart propre au joueur, une fois la chute calmée.
        """
        pid = str(player["player_id"])
        c48, c24 = self.change(pid, 48), self.change(pid, 24)
        m48, m24 = self.market_change(48), self.market_change(24)
        pct = lambda v: f"{v * 100:+.0f} %"  # noqa: E731
        if c48 is not None and c48 <= config.DROP_48H_BUY and not self.recent_competitor(player):
            extra = {"change_48h": c48, "market_48h": m48}
            if m48 is None:
                return self.build_signal(player, "R4_CHUTE_48H", min(1.0, abs(c48) / 0.25),
                                         f"{pct(c48)} en 48 h.", rule_conf=0.6, extra=extra,
                                         hold_reason="mouvement du marché inconnu (trop peu de joueurs relevés)")
            excess = c48 - m48
            txt = f"{pct(c48)} en 48 h contre {pct(m48)} pour le marché (écart {excess * 100:+.0f} pts)."
            extra["excess_48h"] = excess
            if excess > config.R4_EXCESS_BUY:
                return self.build_signal(player, "R4_CHUTE_48H", min(1.0, abs(c48) / 0.25), txt, rule_conf=0.6,
                                         extra=extra, hold_reason=f"chute alignée sur le marché ({pct(m48)} en 48 h) : "
                                                                  f"pas une baisse propre au joueur")
            c3 = self.change(pid, 3)
            extra["change_3h"] = c3
            hold = ""
            if c3 is None:
                hold = "stabilisation non vérifiable (pas de relevé il y a 3 h)"
            elif c3 < config.R4_STABLE_3H:
                hold = f"chute encore en cours ({pct(c3)} sur 3 h) : attendre la stabilisation"
            else:
                txt += f" Chute stabilisée ({pct(c3)} sur 3 h)."
            return self.build_signal(player, "R4_CHUTE_48H", min(1.0, abs(excess) / 0.25), txt, rule_conf=0.7,
                                     extra=extra, hold_reason=hold)
        if c24 is not None and c24 >= config.PUMP_24H_SELL:
            extra = {"change_24h": c24, "market_24h": m24}
            excess = c24 - m24 if m24 is not None else None
            txt = f"{pct(c24)} en 24 h" + (f" contre {pct(m24)} pour le marché." if m24 is not None else ".")
            hold = "" if excess is not None and excess >= config.R4_EXCESS_SELL else \
                ("mouvement du marché inconnu" if excess is None else
                 f"hausse partagée par le marché ({pct(m24)} en 24 h) : pas une hype propre au joueur")
            return self.build_signal(player, "R4_HYPE_24H", -min(1.0, c24 / 0.45), txt, rule_conf=0.7,
                                     extra={**extra, "excess_24h": excess}, hold_reason=hold)
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
            if self.version == "v2" and not self.quality(pid)["ok"]:
                sigs.append(self.build_signal(p, "QUALITE_DONNEES", None, ""))  # abstention tracée
                continue
            s = self.rule4_technical(p)
            if s is None:
                s = self.build_signal(p, "HABITUDE", None, "Pas de signal technique particulier.")
            sigs.append(s)
        return sigs

    def instant_crashes(self, hours: int = 24) -> list[Signal]:
        if self.version == "v2":
            return []  # v2 : la chute est traitée par R4 uniquement (plus de double signal)
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
