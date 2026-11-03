"""Étape 1 : moteur v2 (qualité des données, 4 décisions, prix explicites) + journal des décisions."""
from __future__ import annotations

from datetime import timedelta

import config
from alerts import notifier
from core import decision_journal as dj
from core.signals import format_alert
from database import db
from tests.test_characterization import NOW, PLAYER, analyzer, flat_then, seed
from utils.helpers import round_tier

MARKET = [{**PLAYER, "player_id": f"mk-{i}", "name": f"Marche{i}", "position": "CB"} for i in range(6)]


def seed_market(move: float = 0.0, hours: int = 48) -> list[dict]:
    """6 autres joueurs suivis : marché stable (move=0) ou en baisse/hausse de `move` sur `hours` heures."""
    for p in MARKET:
        seed(flat_then(hours, 30000, round(30000 * (1 + move))), pid=p["player_id"], player=p)
    return [PLAYER, *MARKET]


def test_ea_tiers():
    assert [round_tier(p) for p in (987, 9_999, 10_049, 36_333, 52_400, 150_999)] == \
        [950, 9_900, 10_000, 36_250, 52_000, 150_000]
    assert [round_tier(p, "up") for p in (951, 36_251, 99_501)] == [1_000, 36_500, 100_000]


def test_v2_buy_has_justified_target_tiers_and_theoretical_wording():
    seed(flat_then(48, 50000, 40000))  # -20 % en 48 h, 10 jours d'historique, marché stable
    s = analyzer(seed_market(), habit=False, version="v2").rule4_technical(PLAYER)
    x = s.extra
    assert s.action == "ACHAT" and x["engine"] == "v2" and x["reason"] == ""
    assert x["buy_max"] == 40000 and x["sell_min"] == round_tier(x["target_price"])  # paliers EA
    assert x["target_price"] == x["avg_7d"]  # cible = moyenne 7 j observée, pas une valeur par défaut
    assert x["net_profit"] == round(x["sell_min"] * 0.95 - 40000) and x["executable_price"] is None
    assert x["probability"] is None and x["data_quality"] == 100
    txt = format_alert(s)
    assert "théorique, non garanti" in txt and "Fiabilité : pas encore de bilan" in txt
    assert "Achète ≤ 40\u202f000" in txt and "Gain visé" in txt and "Risque : " in txt
    assert "/100" not in txt and "Confiance" not in txt  # plus de score abstrait
    assert x["risk_level"] in ("FAIBLE", "MOYEN", "ÉLEVÉ") and x["net_pct"] == round(x["net_profit"] / 40000, 4)


def test_v2_margin_too_small_becomes_surveillance():
    seed(flat_then(48, 50000, 42000) | {h: 43500 for h in range(240, 49, -1)})  # moyenne proche du prix
    s = analyzer(seed_market(), habit=False, version="v2").rule4_technical(PLAYER)
    assert s.action == "SURVEILLANCE" and "marge nette théorique" in s.extra["reason"]
    trig = s.extra["buy_trigger"]  # prix sous lequel ce serait un achat : marge nette ≥ 4 % vers la moyenne 7 j
    assert trig and trig < s.price and round_tier(s.extra["avg_7d"], "down") * 0.95 - trig >= 0.04 * trig
    assert "Achat si ≤" in format_alert(s)


def test_v2_sell_never_below_observed_and_no_duplicate_crash_signal():
    seed(flat_then(24, 40000, 52000))
    an = analyzer(seed_market(), habit=False, version="v2")
    s = an.rule4_technical(PLAYER)
    assert s.action == "VENTE" and "VENDRE vers 52 000" in s.action_text.replace(" ", " ")
    assert an.instant_crashes(24) == []


def test_v2_stale_player_is_logged_as_abstention():
    seed({h + 30: 50000 for h in range(200)})  # plus aucun relevé depuis 30 h
    sigs = analyzer(habit=False, version="v2").full_scan()
    assert [(s.rule, s.action) for s in sigs] == [("QUALITE_DONNEES", "AUCUNE ACTION")]
    assert "il y a 30 h" in sigs[0].extra["reason"]


def test_notifier_never_sends_abstentions(monkeypatch):
    seed({h + 30: 50000 for h in range(200)})
    s = analyzer(habit=False, version="v2").full_scan()[0]
    s.confidence = 10  # même avec une note forcée
    monkeypatch.setattr(notifier, "send_text", lambda *a, **k: True)
    assert notifier.dispatch([s]) == []


def test_journal_logs_every_decision_and_evaluates_outcomes():
    seed(flat_then(48, 50000, 40000))
    sigs = analyzer(habit=False, version="v2", now=NOW - timedelta(hours=24)).full_scan()
    assert dj.log_decisions(sigs, "v2", NOW - timedelta(hours=24)) == 1
    # à NOW-24 h : -10 % seulement -> AUCUNE ACTION (abstention), au prix observé de 45 000
    assert sigs[0].action == "AUCUNE ACTION" and sigs[0].price == 45000
    assert dj.evaluate_outcomes(now=NOW + timedelta(hours=2)) == 2  # horizons 6 h et 24 h échus ; 48 h / 7 j pas encore
    assert dj.evaluate_outcomes(now=NOW + timedelta(hours=2)) == 0  # jamais évalué deux fois
    with db.get_conn() as c:
        rows = c.execute("SELECT horizon_h, price, verdict FROM decision_outcomes ORDER BY horizon_h").fetchall()
    assert [tuple(r) for r in rows] == [(6, 43750, "abstention_ok"), (24, 40000, "abstention_ok")]  # la baisse a continué
    perf = dj.performance(now=NOW + timedelta(hours=2))
    assert {(r["action"], r["horizon_h"], r["n"]) for r in perf} == {("AUCUNE ACTION", 6, 1), ("AUCUNE ACTION", 24, 1)}
    assert all(r["enough_data"] is False for r in perf)


def test_verdicts():
    assert dj.verdict("ACHAT", 40000, 44000) == ("favorable", 1800)
    assert dj.verdict("ACHAT", 40000, 41000)[0] == "defavorable"  # +2,5 % ne couvre pas la taxe
    assert dj.verdict("VENTE", 40000, 38000)[0] == "favorable"
    assert dj.verdict("SURVEILLANCE", 40000, 44000)[0] == "occasion_manquee"
    assert dj.verdict("AUCUNE ACTION", 40000, 39000)[0] == "abstention_ok"


def test_track_record_only_after_enough_samples(monkeypatch):
    monkeypatch.setattr(config, "PROBA_MIN_SAMPLES", 3)
    db.upsert_player(PLAYER)
    with db.get_conn() as c:
        for i in range(3):
            c.execute("INSERT INTO decision_log (id, timestamp, engine, player_id, action, rule, observed_price) "
                      "VALUES (?,?,?,?,?,?,?)", (i + 1, "2026-10-28T10:00:00+00:00", "v2", "c-1", "ACHAT", "R4_CHUTE_48H", 100))
            c.execute("INSERT INTO decision_outcomes VALUES (?,?,?,?,?,?,?,?)",
                      (i + 1, 24, "2026-10-29T11:00:00+00:00", 110, None, 0.1, 4, "favorable" if i else "defavorable"))
    an = analyzer(version="v2")
    r = an.track_record("R4_CHUTE_48H", "ACHAT")
    assert r["n"] == 3 and r["rate"] == 0.667 and 0 < r["low"] < r["rate"] < r["high"] <= 1


def test_job_snapshot_logs_active_and_shadow_engines(monkeypatch):
    from core import jobs
    from scrapers import price_provider

    seed(flat_then(48, 50000, 40000))
    monkeypatch.setattr(jobs, "_watchlist", lambda: [PLAYER])
    monkeypatch.setattr(price_provider, "snapshot_watchlist", lambda wl: {"ok": 1})
    monkeypatch.setattr(jobs, "utcnow", lambda: NOW.replace(minute=4))  # relevé de début d'heure -> journal
    monkeypatch.setattr(notifier, "send_text", lambda *a, **k: True)
    monkeypatch.setattr(notifier, "send_photo", lambda *a, **k: True, raising=False)
    monkeypatch.setattr(config, "BRAIN_VERSION", "v1")
    monkeypatch.setattr(config, "BRAIN_SHADOW", "v2")
    jobs.job_snapshot()
    with db.get_conn() as c:
        engines = sorted(r[0] for r in c.execute("SELECT engine FROM decision_log"))
    assert engines == ["v1", "v2"]
    assert all(a["action"].startswith(("ACHAT", "VENTE")) for a in db.recent_alerts())  # v2 jamais envoyé


# --------------------------------------------------------------------------- R4 en force relative (étape 7)
def test_r4_drop_aligned_with_market_is_not_a_buy():
    seed(flat_then(48, 50000, 40000))  # -20 %
    wl = seed_market(move=-0.18)  # tout le marché perd ~18 %
    s = analyzer(wl, habit=False, version="v2").rule4_technical(PLAYER)
    assert s.action == "SURVEILLANCE" and "alignée sur le marché" in s.extra["reason"]
    assert round(s.extra["excess_48h"], 2) == -0.02


def test_r4_player_specific_drop_but_still_falling_waits():
    prices = flat_then(48, 50000, 44000)
    prices.update({h: 44000 - (3 - h) * 2000 for h in range(3, -1, -1)})  # -14 % sur les 3 dernières heures
    seed(prices)
    s = analyzer(seed_market(), habit=False, version="v2").rule4_technical(PLAYER)
    assert s.action == "SURVEILLANCE" and "chute encore en cours" in s.extra["reason"]


def test_r4_player_specific_stabilised_drop_is_a_buy():
    prices = flat_then(48, 50000, 39000)
    prices.update({h: 39000 for h in range(6, -1, -1)})  # palier stable depuis 6 h
    seed(prices)
    s = analyzer(seed_market(move=-0.02), habit=False, version="v2").rule4_technical(PLAYER)
    assert s.action == "ACHAT" and "contre -2 % pour le marché" in s.instant and "stabilisée" in s.instant


def test_r4_pump_shared_by_market_is_not_hype():
    seed(flat_then(24, 40000, 52000))  # +30 %
    wl = seed_market(move=0.25, hours=24)
    s = analyzer(wl, habit=False, version="v2").rule4_technical(PLAYER)
    assert s.action == "SURVEILLANCE" and "partagée par le marché" in s.extra["reason"]


def test_r4_unknown_market_never_trades():
    seed(flat_then(48, 50000, 40000))
    s = analyzer(habit=False, version="v2").rule4_technical(PLAYER)  # un seul joueur suivi
    assert s.action == "SURVEILLANCE" and "marché inconnu" in s.extra["reason"]


# --------------------------------------------------------------------------- nouvelles cartes (découverte du prix)
def test_new_special_card_is_in_price_discovery():
    wl = seed_market()  # le bot tourne depuis 10 jours
    totw = {**PLAYER, "player_id": "totw-1", "name": "Nouveau TOTW", "card_type": "Team of the Week"}
    seed({h: 60000 - (30 - h) * 600 for h in range(30, -1, -1)}, pid="totw-1", player=totw)  # sortie il y a 30 h, chute
    an = analyzer([*wl, totw], habit=False, version="v2")
    age = an.card_age(totw)
    assert age["special"] and age["discovery"] and age["days"] == 1.2 and age["limit"] == 4
    s = an.build_signal(totw, "R4_CHUTE_48H", 0.9, "chute")
    assert s.action == "SURVEILLANCE" and "découverte" in s.extra["reason"] and "KB-S-012" in s.extra["reason"]


def test_card_present_since_bot_start_is_never_new():
    wl = seed_market()
    an = analyzer(wl, habit=False, version="v2")
    assert an.card_age(PLAYER) is None and an.card_age(MARKET[0]) is None


def test_base_card_entering_price_band_is_never_new():
    """Une carte de base (ex. Bonmatí or non rare) existe depuis la sortie du jeu, même si le bot la découvre tard."""
    wl = seed_market()
    gold = {**PLAYER, "player_id": "gold-1", "name": "Or tombé dans la tranche", "card_type": "Or non rare"}
    seed({h: 249000 for h in range(30, -1, -1)}, pid="gold-1", player=gold)
    assert analyzer([*wl, gold], version="v2").card_age(gold) is None


def test_old_special_card_falling_into_band_is_not_new_but_real_release_is():
    """Cas réel du 02/11 : vieilles cartes spéciales (numéro futgenie ancien) entrées dans la tranche 20k-250k en
    baissant -> pas neuves. Une carte sortie après tout ce que le bot connaissait (numéro plus grand) -> neuve."""
    known = {**PLAYER, "player_id": "fgn-1032400", "name": "Promo déjà suivie", "card_type": "Ultimate Scream"}
    seed({h: 90000 for h in range(240, -1, -1)}, pid=known["player_id"], player=known)
    wl = [*seed_market(), known]
    old = {**PLAYER, "player_id": "fgn-1030455", "name": "Cucurella", "card_type": "Destined for Glory"}
    new = {**PLAYER, "player_id": "fgn-1032528", "name": "Nouvelle promo", "card_type": "Ultimate Scream"}
    for c in (old, new):
        seed({h: 150000 for h in range(30, -1, -1)}, pid=c["player_id"], player=c)
    an = analyzer([*wl, old, new], habit=False, version="v2")
    assert an.card_age(old) is None
    age = an.card_age(new)
    assert age and age["discovery"] and age["limit"] == 4


def test_v2_trades_reach_discord_threshold_and_abstentions_never_do(monkeypatch):
    prices = flat_then(48, 50000, 39000)
    prices.update({h: 39000 for h in range(6, -1, -1)})
    seed(prices)
    an = analyzer(seed_market(move=-0.02), habit=False, version="v2")
    buy = an.rule4_technical(PLAYER)
    assert buy.action == "ACHAT" and buy.confidence >= config.ALERT_MIN_CONFIDENCE
    monkeypatch.setattr(notifier, "send_text", lambda *a, **k: True)
    assert notifier.dispatch([buy]) == [buy]  # l'achat validé part bien sur Discord
    wait = an.build_signal(PLAYER, "HABITUDE", None, "")
    assert wait.action in ("AUCUNE ACTION", "SURVEILLANCE") and wait.confidence <= 4


def test_context_uses_trigger_window_no_contradiction():
    """Cas réel (Jill Scott) : -8 % / 24 h comme le marché, mais -28 % / 48 h contre -11 % : l'explication
    doit dire « propre au joueur » sur 48 h, pas « mouvement général du marché »."""
    from core.context import explain_move

    assert "général" in explain_move(-0.08, -0.05, -0.24)
    txt = explain_move(-0.28, -0.11, -0.24, window="48h")
    assert "propre au joueur" in txt and "48h" in txt and "général" not in txt


def test_context_48h_does_not_call_small_gap_player_specific():
    """-20 % contre -15 % sur 48 h : R4 dit « alignée sur le marché » (écart < 10 pts), le contexte ne doit pas
    dire « propre au joueur »."""
    from core.context import explain_move

    txt = explain_move(-0.20, -0.15, None, window="48h")
    assert "propre au joueur" not in txt.replace("pas assez pour être propre au joueur", "") and "un peu plus forte" in txt


def test_history_requirements_count_hours_not_points():
    """Passage aux relevés toutes les 5 min : 30 relevés en 2 h et demie ne valent pas « 24 h de données »."""
    from datetime import timedelta as td

    for m in range(0, 150, 5):  # 30 relevés (17h35 -> 20h00), mais seulement 4 heures couvertes
        db.insert_snapshot(PLAYER["player_id"], 50000, NOW - td(minutes=m), source="futreveal")
    an = analyzer([PLAYER], habit=False, version="v2")
    q = an.quality(PLAYER["player_id"])
    assert q["n_48h"] == 30 and q["h_48h"] == 4 and not q["ok"] and "heures couvertes" in q["reason"]
    assert db.price_stats(PLAYER["player_id"], now=NOW)["hours"] == 4
