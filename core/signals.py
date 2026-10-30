"""Signal de trading + formatage de l'alerte (Telegram / Discord / dashboard)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from utils.helpers import fmt_price

ACTION_EMOJI = {"ACHAT FORT": "🚨🟢", "ACHAT": "🟢", "VENTE URGENTE": "🚨🔴", "VENTE": "🔴", "HOLD": "⏸️",
                "INFO": "ℹ️"}


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


def format_alert(s: Signal) -> str:
    emoji = ACTION_EMOJI.get(s.action, "🚨")
    lines = [f"{emoji} [{s.action}] - Confiance {s.confidence}/10"]
    if s.player_name:
        lines.append(f"Joueur : {s.title}")
    if s.price:
        chg = f" ({s.change_24h * 100:+.0f}% / 24h)" if s.change_24h is not None else ""
        lines.append(f"Prix : {fmt_price(s.price)}{chg}")
    if s.instant:
        lines.append(f"> Instantané : {s.instant}")
    if s.habit:
        lines.append(f"> {s.habit}")
    if s.action_text:
        lines.append(f"Action : {s.action_text}")
    lines.append(f"Risque : {s.risk}.")
    lines.append(f"Règle : {s.rule}")
    return "\n".join(lines)
