"""Détection des HABITUDES du marché à partir de price_snapshots.

Idée clé : on travaille en prix RELATIF (prix / moyenne mobile 7 jours - 1) pour pouvoir
comparer un joueur à 30k et un joueur à 300k, et isoler le cycle hebdo de la tendance.

Fenêtres connues (heure de Paris) :
  PATTERN A  Jeudi 18h-20h          -> crash Rivals
             Dimanche 20h-Lundi 04h -> GROS crash FUT Champions (meilleur moment d'ACHAT)
             Lundi 18h-Jeudi 17h    -> remontée
  PATTERN B  Jeu-Ven prix haut (Week-end League), Dim-Lun bas, Mar-Mer spécial SBC fodders
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import config
from database import db
from utils.helpers import utcnow

DAYS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
DAYS_FR_LONG = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# (jour_debut, heure_debut, jour_fin, heure_fin) — lundi=0 ; fin exclusive
WINDOWS = {
    "FUT_CHAMPS_CRASH": (6, 20, 0, 4),
    "RIVALS_CRASH": (3, 18, 3, 20),
    "RECOVERY": (0, 18, 3, 17),
    "WL_HIGH": (3, 20, 5, 0),
    "SBC_FODDER": (1, 0, 3, 0),
}
PHASE_LABELS = {
    "FUT_CHAMPS_CRASH": "crash FUT Champions (Dim 20h-Lun 04h)",
    "RIVALS_CRASH": "crash récompenses Rivals (Jeu 18h-20h)",
    "RECOVERY": "phase de remontée (Lun 18h-Jeu 17h)",
    "WL_HIGH": "prix hauts Week-end League (Jeu-Ven)",
    "SBC_FODDER": "Mar-Mer : spécial SBC fodders",
}


def how(dt: pd.Timestamp | datetime) -> int:
    """Hour-of-week (0 = lundi 00h, 167 = dimanche 23h)."""
    return dt.weekday() * 24 + dt.hour


def in_window(h: int, window: str) -> bool:
    d0, h0, d1, h1 = WINDOWS[window]
    start, end = d0 * 24 + h0, d1 * 24 + h1
    return start <= h < end if start < end else (h >= start or h < end)


def current_phases(dt: datetime) -> list[str]:
    h = how(dt)
    return [w for w in WINDOWS if in_window(h, w)]


def window_label(start_how: int, length: int) -> str:
    end = (start_how + length) % 168
    d0, h0 = divmod(start_how, 24)
    d1, h1 = divmod(end, 24)
    if d0 == d1:
        return f"{DAYS_FR[d0]} {h0}h-{h1}h"
    return f"{DAYS_FR[d0]}-{DAYS_FR[d1]} {h0}h-{h1:02d}h"


# --------------------------------------------------------------------------- données
def load_frame(days: int = 30, player_ids=None, now: datetime | None = None) -> pd.DataFrame:
    now = now or utcnow()
    rows = db.get_snapshots(player_ids, since=now - timedelta(days=days))
    if not rows:
        return pd.DataFrame(columns=["player_id", "ts", "price"])
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(config.TZ)
    df = df.drop(columns=["timestamp"])
    df = df[df["ts"] <= pd.Timestamp(now).tz_convert(config.TZ)]
    return df


def hourly_series(df: pd.DataFrame, player_id: str) -> pd.Series:
    s = df.loc[df["player_id"] == str(player_id)].set_index("ts")["price"].sort_index()
    if s.empty:
        return s
    s = s[~s.index.duplicated(keep="last")]
    return s.resample("1h").mean().interpolate(limit=6)


def relative(s: pd.Series, centered: bool = True) -> pd.Series:
    """Prix relatif à la moyenne mobile 7j (centrée pour l'apprentissage, glissante pour le live)."""
    base = s.rolling(168, center=centered, min_periods=48).mean()
    return s / base - 1


def profile_from_rel(rel: pd.Series) -> np.ndarray | None:
    rel = rel.dropna()
    if len(rel) < 72:
        return None
    by_how = rel.groupby([rel.index.weekday * 24 + rel.index.hour]).median()
    prof = np.full(168, np.nan)
    prof[by_how.index.values.astype(int)] = by_how.values
    s = pd.Series(np.concatenate([prof, prof, prof])).interpolate(limit_direction="both")
    s = s.rolling(3, center=True, min_periods=1).mean()  # lissage circulaire
    out = s.values[168:336]
    return out - np.nanmean(out)


def best_window(profile: np.ndarray, length: int = 4, lowest: bool = True) -> tuple[int, float]:
    ext = np.concatenate([profile, profile[:length]])
    means = np.array([ext[i:i + length].mean() for i in range(168)])
    i = int(np.argmin(means) if lowest else np.argmax(means))
    return i, float(means[i])


@dataclass
class WeeklyStats:
    sunday_crash: list[float]
    rivals_crash: list[float]
    recovery: list[float]

    @staticmethod
    def _summ(vals: list[float], negative: bool) -> dict:
        if not vals:
            return {"avg": None, "hit_rate": 0.0, "n": 0, "std": None}
        arr = np.array(vals)
        hits = (arr < -0.03) if negative else (arr > 0.03)
        return {"avg": float(arr.mean()), "hit_rate": float(hits.mean()), "n": len(arr), "std": float(arr.std())}

    def summary(self) -> dict:
        return {"sunday_crash": self._summ(self.sunday_crash, True),
                "rivals_crash": self._summ(self.rivals_crash, True),
                "recovery": self._summ(self.recovery, False)}


def weekly_stats(s: pd.Series) -> WeeklyStats:
    """Mesure semaine par semaine : crash du dimanche, crash Rivals, remontée jusqu'au jeudi."""
    out = WeeklyStats([], [], [])
    if s.empty:
        return out
    days = pd.date_range(s.index.min().normalize(), s.index.max().normalize(), freq="D")
    for d in days:
        if d.weekday() == 6:  # dimanche
            thu, fri_end = d - pd.Timedelta(days=3), d - pd.Timedelta(days=1)
            ref = s[(s.index >= thu + pd.Timedelta(hours=8)) & (s.index < fri_end)]
            crash = s[(s.index >= d + pd.Timedelta(hours=20)) & (s.index < d + pd.Timedelta(hours=28))]
            if len(ref) >= 12 and len(crash) >= 4:
                low = crash.min()
                out.sunday_crash.append(float(low / ref.mean() - 1))
                rec = s[(s.index >= d + pd.Timedelta(days=4, hours=12)) & (s.index < d + pd.Timedelta(days=4, hours=17))]
                if len(rec) >= 2:
                    out.recovery.append(float(rec.mean() / low - 1))
        if d.weekday() == 3:  # jeudi
            before = s[(s.index >= d + pd.Timedelta(hours=10)) & (s.index < d + pd.Timedelta(hours=17))]
            during = s[(s.index >= d + pd.Timedelta(hours=18)) & (s.index < d + pd.Timedelta(hours=21))]
            if len(before) >= 3 and len(during) >= 2:
                out.rivals_crash.append(float(during.min() / before.mean() - 1))
    return out


def cycle_by_weekday(rel: pd.Series) -> dict[str, float]:
    rel = rel.dropna()
    if rel.empty:
        return {}
    g = rel.groupby(rel.index.weekday).mean()
    return {DAYS_FR_LONG[int(k)]: round(float(v), 4) for k, v in g.items()}


def habit_assessment(price: float, s_live: pd.Series, rule: dict | None, now_local: pd.Timestamp) -> dict:
    """Compare le prix actuel à l'habitude apprise (profil hebdo) et projette la suite.

    Renvoie score in [-1, 1] (positif = acheter), écart vs habitude, texte FR.
    """
    res = {"score": 0.0, "confidence": 0.0, "expected_rel": None, "current_rel": None,
           "deviation": None, "upside": None, "downside": None, "text": "Pas assez d'historique.",
           "phases": current_phases(now_local)}
    if not rule or not rule.get("profile") or s_live.empty:
        return res
    prof = np.array(rule["profile"], dtype=float)
    base = s_live[s_live.index > now_local - pd.Timedelta(days=7)].mean()
    if not base or np.isnan(base):
        return res
    cur_rel = price / base - 1
    h = how(now_local)
    exp_rel = float(prof[h])
    nxt96 = prof[[(h + i) % 168 for i in range(1, 97)]]
    nxt48 = prof[[(h + i) % 168 for i in range(1, 49)]]
    upside, downside = float(nxt96.max() - cur_rel), float(nxt48.min() - cur_rel)
    score = float(np.clip((0.6 * upside + 0.4 * downside) / 0.10, -1, 1))
    conf = float(rule.get("confidence", 0.0))
    res.update(score=score, confidence=conf, expected_rel=exp_rel, current_rel=float(cur_rel),
               deviation=float(cur_rel - exp_rel), upside=upside, downside=downside)

    weeks = rule.get("weeks_observed", 0)
    crash = rule.get("avg_sunday_crash_value")
    rec = rule.get("avg_recovery_value")
    parts = []
    if crash is not None:
        parts.append(f"Perd {crash * 100:+.1f}% le Dimanche soir en moyenne")
        # drawdown actuel vs le dernier Jeu-Ven
        wl = s_live[(s_live.index.weekday.isin([3, 4])) & (s_live.index > now_local - pd.Timedelta(days=7))]
        if len(wl) >= 6:
            dd = price / wl.mean() - 1
            if dd < -0.02:
                state = "fond proche" if dd <= crash * 0.8 else "fond pas encore atteint"
                parts.append(f"On est à {dd * 100:+.1f}% vs Jeu-Ven, {state}")
    if rec is not None and upside > 0.02:
        parts.append(f"Remonte {rec * 100:+.1f}% d'ici Jeudi en moyenne")
    if not parts:
        parts.append(f"Écart vs habitude {res['deviation'] * 100:+.1f}%")
    res["text"] = f"Habitude ({weeks * 7}j) : " + ". ".join(parts) + f". Confiance {conf * 100:.0f}%."
    return res


def prior_profile() -> np.ndarray:
    """Profil hebdo "expert" (connaissance FUT) utilisé tant que le bot n'a pas assez appris."""
    prof = np.zeros(168)
    for h in range(168):
        d, hr = divmod(h, 24)
        if (d == 6 and hr >= 20) or (d == 0 and hr < 4):
            v = -0.12  # crash FUT Champions
        elif d == 0 and hr < 18:
            v = -0.10 + 0.02 * (hr - 4) / 14
        elif d == 3 and 18 <= hr < 20:
            v = -0.01  # crash Rivals
        elif (d == 3 and hr >= 20) or d == 4:
            v = 0.06  # WL : prix hauts
        elif d == 5:
            v = 0.03
        elif d == 6:
            v = -0.02 - 0.04 * hr / 20
        else:  # lundi 18h -> jeudi 17h : remontée linéaire
            start, end = 0 * 24 + 18, 3 * 24 + 17
            v = -0.08 + 0.12 * (h - start) / (end - start)
        prof[h] = v
    return prof - prof.mean()
