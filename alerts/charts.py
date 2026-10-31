"""Graphiques : prix réel 7 jours vs prix PRÉDIT par l'habitude (profil hebdo appris)."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

import config
from core import learner
from core import pattern_detector as pdt
from database import db


def real_vs_predicted(player_id: str, days: int = 7, forecast_hours: int = 48) -> dict:
    """Séries pour le dashboard / matplotlib.

    Prédiction = moyenne glissante 7 jours (niveau) x (1 + profil hebdo à cette heure).
    Le futur (48h) est projeté avec le dernier niveau connu.
    """
    player = db.get_player(player_id) or {"player_id": player_id, "name": player_id}
    df = pdt.load_frame(days + 7, [player_id])
    s = pdt.hourly_series(df, player_id).dropna() if not df.empty else pd.Series(dtype=float)
    out = {"player": {k: player.get(k) for k in ("player_id", "name", "rating", "position")},
           "real": [], "predicted": [], "forecast": []}
    if s.empty:
        return out
    rule = learner.rule_for(learner.load_rules(), player)
    prof = np.nan_to_num(np.array(rule.get("profile") or [0.0] * 168, dtype=float))
    # moins de 24 relevés : pas encore de moyenne glissante -> moyenne des relevés disponibles
    base = s.rolling(168, min_periods=24).mean().bfill().fillna(float(s.mean()))
    view = s[s.index >= s.index[-1] - pd.Timedelta(days=days)]
    for ts, price in view.items():
        out["real"].append({"t": ts.isoformat(), "p": round(float(price))})
        out["predicted"].append({"t": ts.isoformat(), "p": round(float(base[ts] * (1 + prof[pdt.how(ts)])))})
    last_base, last_ts = float(base.iloc[-1]), s.index[-1]
    for h in range(1, forecast_hours + 1):
        ts = last_ts + pd.Timedelta(hours=h)
        out["forecast"].append({"t": ts.isoformat(), "p": round(last_base * (1 + prof[pdt.how(ts)]))})
    out["confidence"] = rule.get("confidence")
    return out


def chart_png(player_id: str) -> bytes | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = real_vs_predicted(player_id)
    if not data["real"]:
        return None
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=110)
    for key, label, style in (("real", "Prix réel", "-"), ("predicted", "Habitude", "--"), ("forecast", "Prévision 48h", ":")):
        pts = data[key]
        if pts:
            ax.plot(pd.to_datetime([p["t"] for p in pts], utc=True).tz_convert(config.TZ), [p["p"] for p in pts], style, label=label, linewidth=1.6)
    p = data["player"]
    ax.set_title(f"{p.get('name')} {p.get('rating') or ''} — 7 jours ({config.TZ})")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
