"""Signal de trading + formatage de l'alerte (Telegram / Discord / dashboard)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from utils.helpers import fmt_price

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


def format_alert_v2(s: Signal, emoji: str, x: dict) -> str:
    """Alerte v2 : opportunité et qualité des données séparées, prix observé daté, base de chaque affirmation."""
    lines = [f"{emoji} [{s.action}] - Opportunité {x.get('opportunity', 0)}/100 · Qualité des données {x.get('data_quality', 0)}/100"]
    if s.player_name:
        lines.append(f"Joueur : {s.title}")
    if s.price:
        chg = f" ({s.change_24h * 100:+.0f}% / 24h)" if s.change_24h is not None else ""
        q = x.get("quality") or {}
        lines.append(f"Prix observé : {fmt_price(s.price)}{chg} · relevé il y a {q.get('age_h', '?')} h "
                     f"({q.get('n_48h', '?')} relevés sur 48 h)")
        if x.get("avg_7d"):
            vs = f", actuel {x['vs_avg'] * 100:+.0f} % vs moyenne" if x.get("vs_avg") is not None else ""
            lines.append(f"Moy. 7j : {fmt_price(x['avg_7d'])} (min {fmt_price(x.get('min_7d'))} – "
                         f"max {fmt_price(x.get('max_7d'))}){vs}")
    if s.instant:
        lines.append(f"> Déclencheur : {s.instant}")
    if x.get("explain"):
        lines.append(f"> Contexte : {x['explain']}")
    if s.habit:
        lines.append(f"> {s.habit}")
    if x.get("reason"):
        lines.append(f"> Raison : {x['reason']}")
    if s.action_text:
        lines.append(f"Action : {s.action_text}")
    lines.append(probability_text(x))
    lines.append(f"Risque : {s.risk}. Règle : {s.rule} · moteur v2")
    return "\n".join(lines)
