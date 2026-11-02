"""Signal de trading + formatage de l'alerte (Telegram / Discord / dashboard)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from utils.helpers import fmt_price, to_local

ACTION_EMOJI = {"ACHAT FORT": "🚨🟢", "ACHAT": "🟢", "VENTE URGENTE": "🚨🔴", "VENTE": "🔴", "HOLD": "⏸️",
                "SURVEILLANCE": "👀", "AUCUNE ACTION": "⏸️", "INFO": "ℹ️"}


@dataclass
class Signal:
    action: str
    rule: str
    score: float  # [-1, 1] positif = acheter
    confidence: int  # 1..10
    player_id: str | None = None
    player_name: str = ""
    rating: int | None = None
    card_type: str | None = None
    position: str | None = None
    price: int | None = None
    change_24h: float | None = None
    instant: str = ""
    habit: str = ""
    action_text: str = ""
    risk: str = "Moyen"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def title(self) -> str:
        bits = [self.player_name]
        if self.rating:
            bits.append(str(self.rating))
        if self.card_type:
            bits.append(str(self.card_type))
        t = " ".join(bits)
        return f"{t} - {self.position}" if self.position else t


def score_to_action(score: float) -> str:
    if score >= 0.6:
        return "ACHAT FORT"
    if score >= 0.3:
        return "ACHAT"
    if score <= -0.6:
        return "VENTE URGENTE"
    if score <= -0.3:
        return "VENTE"
    return "HOLD"


def probability_text(x: dict) -> str:
    p = x.get("probability")
    if not p:
        return "Probabilité de réussite : non disponible (pas assez de résultats évalués)"
    return (f"Fréquence historique favorable à {p['horizon_h']} h : {p['rate'] * 100:.0f} % "
            f"(n={p['n']}, IC95 {p['low'] * 100:.0f}-{p['high'] * 100:.0f} %, théorique)")


def format_alert(s: Signal) -> str:
    emoji = ACTION_EMOJI.get(s.action, "🚨")
    x = s.extra or {}
    if x.get("engine") == "v2":
        return format_alert_v2(s, emoji, x)
    lines = [f"{emoji} [{s.action}] - Confiance {s.confidence}/10"]
    if s.player_name:
        lines.append(f"Joueur : {s.title}")
    if s.price:
        chg = f" ({s.change_24h * 100:+.0f}% / 24h)" if s.change_24h is not None else ""
        lines.append(f"Prix : {fmt_price(s.price)}{chg}")
        x = s.extra or {}
        if x.get("avg_7d"):
            vs = f", actuel {x['vs_avg'] * 100:+.0f} % vs moyenne" if x.get("vs_avg") is not None else ""
            lines.append(f"Moy. 7j : {fmt_price(x['avg_7d'])} (min {fmt_price(x.get('min_7d'))} – "
                         f"max {fmt_price(x.get('max_7d'))}){vs}")
    if s.instant:
        lines.append(f"> Instantané : {s.instant}")
    if (s.extra or {}).get("explain"):
        lines.append(f"> Contexte : {s.extra['explain']}")
    if s.habit:
        lines.append(f"> {s.habit}")
    if s.action_text:
        lines.append(f"Action : {s.action_text}")
    lines.append(f"Risque : {s.risk}.")
    lines.append(f"Règle : {s.rule}")
    return "\n".join(lines)


def coins(v) -> str:
    return f"{int(v):,}".replace(",", "\u202f") if v is not None else "?"


def reliability_text(x: dict) -> str:
    """Bilan RÉEL de la règle (décisions passées vérifiées 24 h après), à la place d'un score inventé."""
    p = x.get("probability")
    if not p:
        return "📊 Fiabilité : pas encore de bilan pour cette règle (affiché après 100 cas vérifiés)"
    return (f"📊 Fiabilité : {p['rate'] * 100:.0f} % gagnants à {p['horizon_h']} h sur {p['n']} cas passés "
            f"(fourchette {p['low'] * 100:.0f}-{p['high'] * 100:.0f} %)")


def risk_text(x: dict) -> str:
    lvl = x.get("risk_level") or "?"
    why = x.get("risk_why") or []
    return f"⚠️ Risque : {lvl}" + (" — " + " ; ".join(why) if why else "")


def format_alert_v2(s: Signal, emoji: str, x: dict) -> str:
    """Alerte v2 : ce qu'un trader veut savoir — combien gagner, pourquoi, quel risque, quelle fiabilité réelle."""
    lines = [f"{emoji} **{s.action}** — {s.title}"]
    if s.action == "ACHAT" and x.get("buy_max"):
        lines.append(f"Achète ≤ {coins(x['buy_max'])} → revends ≥ {coins(x['sell_min'])}")
        if x.get("net_profit") is not None:
            pct = f" ({x['net_pct'] * 100:+.1f} %)" if x.get("net_pct") is not None else ""
            sign = "+" if x["net_profit"] >= 0 else "−"
            lines.append(f"💰 Gain visé : {sign}{coins(abs(x['net_profit']))} net par carte après taxe{pct} "
                         f"(théorique, non garanti)")
    elif s.action == "VENTE" and s.price:
        lines.append(f"Vends vers {coins(s.price)} (prix réellement obtenu non garanti)")
    elif s.action == "SURVEILLANCE":
        lines.append(f"👀 Achat si ≤ {coins(x['buy_trigger'])} (aujourd'hui {coins(s.price)})" if x.get("buy_trigger")
                     else f"👀 Pas encore : {x.get('reason') or 'condition manquante'}")
    if s.instant:
        lines.append(f"📉 Pourquoi : {s.instant}")
    if x.get("explain"):
        lines.append(f"> Contexte : {x['explain']}")
    if x.get("reason") and s.action not in ("SURVEILLANCE",):
        lines.append(f"> Raison : {x['reason']}")
    lines.append(risk_text(x))
    lines.append(reliability_text(x))
    if s.price:
        chg = f", {s.change_24h * 100:+.0f} % / 24 h" if s.change_24h is not None else ""
        avg = (f" · moy. 7 j {fmt_price(x['avg_7d'])} (min {fmt_price(x.get('min_7d'))} – max {fmt_price(x.get('max_7d'))})"
               if x.get("avg_7d") else "")
        when = ""
        if x.get("observed_at"):
            when = " à " + to_local(datetime.fromisoformat(str(x["observed_at"]))).strftime("%Hh%M")
        lines.append(f"Prix observé {fmt_price(s.price)}{when}{chg}{avg}")
    if x.get("calendar"):
        lines.append("📅 " + " · ".join(x["calendar"][:2]))
    lines.append(f"_Règle {s.rule} · moteur v2 · le bot n'achète jamais à ta place_")
    return "\n".join(lines)
