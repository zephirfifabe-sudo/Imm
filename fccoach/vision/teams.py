"""Attribution des équipes, sans aucune couleur codée en dur.

1. Extraction : torse (20-55 % de la boîte), short (60-80 %), chaussettes
   (85-97 %). Pelouse et peau masquées, K-means (k=2) en Lab.
2. Ancrage par les curseurs : joueur sous curseur ROUGE = mon équipe,
   sous curseur BLANC = adversaire. Ces échantillons sûrs alimentent les
   prototypes en continu (moyenne mobile).
3. Calibration au coup d'envoi : chrono 00:00 (ou 45:00) + deux groupes de
   couleurs séparés par la ligne médiane -> un prototype par moitié.
   Gardiens et arbitre exclus (classes du détecteur + rejet des aberrants).
4. Classification : CIEDE2000 aux deux prototypes, vote majoritaire par
   track (15 images), score de confiance.
5. Clash (maillots trop proches) : poids sur short/chaussettes, vote plus
   long, confiance réduite. Sous 70 % : aucun conseil dépendant de l'équipe.
6. Mi-temps : prototypes recalculés au coup d'envoi de la 2e, sens d'attaque inversé.
7. kits.sqlite : maillots déjà vus pour démarrer plus vite.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fccoach.core.config import TeamsConfig
from fccoach.vision.color import ciede2000, dominant_lab, lab_to_bgr
from fccoach.vision.kits_db import KitsDB
from fccoach.vision.types import Detection

log = logging.getLogger(__name__)

TEAMS = ("me", "opp")
TEAM_LABEL = {"me": "Moi", "opp": "Adversaire"}

# Bandes verticales de la boîte joueur (fraction de la hauteur)
TORSO = (0.20, 0.55)
SHORTS = (0.60, 0.80)
SOCKS = (0.85, 0.97)


@dataclass
class KitSample:
    shirt: np.ndarray
    shorts: np.ndarray | None = None
    socks: np.ndarray | None = None


def _band(image: np.ndarray, det: Detection, band: tuple[float, float], width: float = 0.5) -> np.ndarray:
    H, W = image.shape[:2]
    y0 = int(det.y1 + band[0] * det.h)
    y1 = int(det.y1 + band[1] * det.h)
    half = det.w * width / 2
    x0, x1 = int(det.cx - half), int(det.cx + half)
    return image[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]


def extract_kit(image: np.ndarray, det: Detection) -> KitSample | None:
    """Couleurs dominantes maillot / short / chaussettes d'un joueur."""
    if det.h < 24 or det.w < 8:
        return None
    shirt = dominant_lab(_band(image, det, TORSO, 0.6))
    if shirt is None:
        return None
    shorts = dominant_lab(_band(image, det, SHORTS, 0.6), min_pixels=15)
    socks = dominant_lab(_band(image, det, SOCKS, 0.5), min_pixels=10)
    return KitSample(shirt[0], shorts[0] if shorts else None, socks[0] if socks else None)


@dataclass
class TeamPrototype:
    shirt: np.ndarray
    shorts: np.ndarray | None = None
    socks: np.ndarray | None = None
    n: int = 0

    def update(self, s: KitSample, alpha: float) -> None:
        # Démarrage : moyenne cumulée (rapide), ensuite moyenne mobile (stable)
        a = max(alpha, 1.0 / (self.n + 1))
        self.shirt = (1 - a) * self.shirt + a * s.shirt
        if s.shorts is not None:
            self.shorts = s.shorts if self.shorts is None else (1 - a) * self.shorts + a * s.shorts
        if s.socks is not None:
            self.socks = s.socks if self.socks is None else (1 - a) * self.socks + a * s.socks
        self.n += 1

    @staticmethod
    def from_samples(samples: list[KitSample]) -> "TeamPrototype":
        def med(vals: list[np.ndarray | None]) -> np.ndarray | None:
            v = [x for x in vals if x is not None]
            return np.median(np.stack(v), axis=0).astype(np.float32) if v else None
        shirt = med([s.shirt for s in samples])
        assert shirt is not None
        return TeamPrototype(shirt, med([s.shorts for s in samples]), med([s.socks for s in samples]), len(samples))

    def as_dict(self) -> dict[str, Any]:
        def hexc(lab: np.ndarray | None) -> str | None:
            if lab is None:
                return None
            b, g, r = lab_to_bgr(lab)[0]
            return f"#{r:02x}{g:02x}{b:02x}"
        return {"shirt": hexc(self.shirt), "shorts": hexc(self.shorts), "socks": hexc(self.socks), "samples": self.n}


def robust_subset(samples: list[KitSample], max_de: float = 15.0) -> list[KitSample]:
    """Retire les aberrants (gardien, arbitre) : trop loin de la médiane du groupe."""
    if len(samples) < 3:
        return samples
    med = np.median(np.stack([s.shirt for s in samples]), axis=0)
    d = ciede2000(np.stack([s.shirt for s in samples]), med[None, :])
    return [s for s, di in zip(samples, d) if di <= max_de]


@dataclass
class TeamStatus:
    calibrated_by: str | None = None     # coup d'envoi | curseurs | base kits
    half: int = 1
    my_attack_dir: str | None = None     # droite | gauche (dans l'image)
    clash: bool = False
    kit_delta_e: float | None = None
    confidence: float = 0.0
    reliable: bool = False
    alert: str | None = None


class TeamClassifier:
    def __init__(self, cfg: TeamsConfig, kits_db: KitsDB | None = None) -> None:
        self.cfg = cfg
        self.db = kits_db
        self.protos: dict[str, TeamPrototype | None] = {"me": None, "opp": None}
        self.status = TeamStatus()
        self._votes: dict[int, deque[tuple[str, float]]] = {}
        self._calibrated_half: int | None = None
        self._anchor_counts = {"me": 0, "opp": 0}
        self._last_clock: int | None = None
        self._last_seen_track: dict[int, float] = {}

    # ------------------------------------------------------------------ API
    def process(self, image: np.ndarray, dets: list[Detection], cursor_players: dict[str, Detection | None],
                clock_s: int | None = None) -> None:
        """Remplit det.team / det.team_conf pour chaque joueur de champ."""
        players = [d for d in dets if d.cls == "player"]
        samples: dict[int, KitSample] = {}
        for i, d in enumerate(players):
            s = extract_kit(image, d)
            if s is not None:
                samples[i] = s
        self._detect_half_change(clock_s)
        self._maybe_kickoff(image, players, samples, cursor_players, clock_s)
        self._anchor(image, cursor_players)
        self._bootstrap_other(players, samples, cursor_players)
        if self.protos["me"] is None or self.protos["opp"] is None:
            self.status.reliable = False
            self.status.alert = "Calibration des équipes en cours…"
            return
        self._update_clash()
        confs = []
        now = time.monotonic()
        for i, d in enumerate(players):
            s = samples.get(i)
            if s is None:
                continue
            team, conf = self._classify(s)
            if team is None:
                continue
            if d.track_id is not None:
                team, conf = self._vote(d.track_id, team, conf, now)
            d.team, d.team_conf = team, conf
            confs.append(conf)
        # Le joueur sous un curseur est sûr à 100 %
        for side, p in cursor_players.items():
            if p is not None:
                p.team, p.team_conf = side, 1.0
        self._update_confidence(confs)

    def new_half(self) -> None:
        """Mi-temps : recalibrer au prochain coup d'envoi, inverser le sens d'attaque."""
        if self.status.half >= 2:
            return
        self.status.half = 2
        self._calibrated_half = None
        self._votes.clear()
        if self.status.my_attack_dir:
            self.status.my_attack_dir = "gauche" if self.status.my_attack_dir == "droite" else "droite"
        log.info("Mi-temps : sens d'attaque inversé (%s), prototypes recalculés au coup d'envoi",
                 self.status.my_attack_dir)

    def snapshot(self) -> dict[str, Any]:
        st = self.status
        return {
            "calibrated_by": st.calibrated_by, "half": st.half, "my_attack_dir": st.my_attack_dir,
            "clash": st.clash, "kit_delta_e": None if st.kit_delta_e is None else round(st.kit_delta_e, 1),
            "confidence": round(st.confidence, 3), "reliable": st.reliable, "alert": st.alert,
            "prototypes": {t: (p.as_dict() if p else None) for t, p in self.protos.items()},
        }

    # ------------------------------------------------------------ internes
    def _weights(self) -> tuple[float, float, float]:
        return (0.2, 0.5, 0.3) if self.status.clash else (0.7, 0.3, 0.0)

    def distance(self, s: KitSample, p: TeamPrototype) -> float:
        ws, wsh, wso = self._weights()
        total, wsum = ws * float(ciede2000(s.shirt, p.shirt)), ws
        if wsh and s.shorts is not None and p.shorts is not None:
            total += wsh * float(ciede2000(s.shorts, p.shorts))
            wsum += wsh
        if wso and s.socks is not None and p.socks is not None:
            total += wso * float(ciede2000(s.socks, p.socks))
            wsum += wso
        return total / wsum

    def _classify(self, s: KitSample) -> tuple[str | None, float]:
        pm, po = self.protos["me"], self.protos["opp"]
        assert pm is not None and po is not None
        dm, do = self.distance(s, pm), self.distance(s, po)
        # Loin des deux équipes : gardien / arbitre non distingués par le détecteur (modèle COCO)
        if min(dm, do) > max(25.0, 1.5 * (self.status.kit_delta_e or 0)):
            return None, 0.0
        team = "me" if dm < do else "opp"
        margin = abs(do - dm) / (dm + do + 1e-6)          # 0 = ambigu, 1 = certain
        return team, float(np.clip(0.5 + margin, 0.0, 1.0))

    def _vote(self, tid: int, team: str, conf: float, now: float) -> tuple[str, float]:
        window = self.cfg.vote_window * (2 if self.status.clash else 1)
        q = self._votes.get(tid)
        if q is None or q.maxlen != window:
            q = deque(q or [], maxlen=window)
            self._votes[tid] = q
        q.append((team, conf))
        self._last_seen_track[tid] = now
        counts = {t: sum(1 for v in q if v[0] == t) for t in TEAMS}
        best = max(counts, key=counts.__getitem__)
        frac = counts[best] / len(q)
        mean_conf = float(np.mean([c for t, c in q if t == best]))
        # Un track tout neuf n'a pas encore de vote solide
        maturity = min(1.0, len(q) / max(3, window // 3))
        if len(self._votes) > 200:
            self._gc(now)
        return best, frac * mean_conf * (0.6 + 0.4 * maturity)

    def _gc(self, now: float) -> None:
        for tid in [t for t, ts in self._last_seen_track.items() if now - ts > 10]:
            self._votes.pop(tid, None)
            self._last_seen_track.pop(tid, None)

    def _update_clash(self) -> None:
        pm, po = self.protos["me"], self.protos["opp"]
        assert pm is not None and po is not None
        de = float(ciede2000(pm.shirt, po.shirt))
        clash = de < self.cfg.clash_delta_e
        if clash != self.status.clash:
            log.warning("Maillots %s (ΔE00 = %.1f) : mode %s", "trop proches" if clash else "distincts",
                        de, "CLASH (short, chaussettes, continuité)" if clash else "normal")
            self._votes.clear()
        self.status.clash, self.status.kit_delta_e = clash, de

    def _update_confidence(self, confs: list[float]) -> None:
        if not confs:
            self.status.confidence *= 0.95
        else:
            c = float(np.median(confs))
            if self.status.clash:
                c *= 0.85
            # lissage pour éviter le clignotement de l'alerte
            self.status.confidence = 0.8 * self.status.confidence + 0.2 * c if self.status.confidence else c
        self.status.reliable = self.status.confidence >= self.cfg.min_confidence
        if not self.status.reliable:
            self.status.alert = (f"Équipes incertaines ({self.status.confidence:.0%}) : "
                                 "conseils dépendant de l'équipe suspendus")
        elif self.status.clash:
            self.status.alert = "Maillots proches (clash) : attribution par short/chaussettes"
        else:
            self.status.alert = None

    def _anchor(self, image: np.ndarray, cursor_players: dict[str, Detection | None]) -> None:
        """Échantillons sûrs : joueur sous curseur rouge = moi, blanc = adversaire."""
        for side, det in cursor_players.items():
            if det is None or det.cls != "player":
                continue
            s = extract_kit(image, det)
            if s is None:
                continue
            p = self.protos[side]
            if p is None:
                known = self.db.match(s.shirt, s.shorts) if self.db else None
                if known is not None:
                    self.protos[side] = TeamPrototype(known.shirt, known.shorts, known.socks, n=5)
                    log.info("Maillot %s reconnu dans kits.sqlite (kit #%d)", TEAM_LABEL[side], known.id)
                    self.status.calibrated_by = self.status.calibrated_by or "base kits"
                else:
                    self.protos[side] = TeamPrototype(s.shirt, s.shorts, s.socks, n=1)
            else:
                # Rendu du joueur sélectionné parfois différent : poids configurable
                p.update(s, self.cfg.prototype_ema * self.cfg.cursor_sample_weight)
            self._anchor_counts[side] += 1
        if (self.status.calibrated_by is None and self.protos["me"] is not None and self.protos["opp"] is not None
                and min(self._anchor_counts.values()) >= 5):
            self.status.calibrated_by = "curseurs"
            log.info("Équipes calibrées par les curseurs (coup d'envoi non détecté)")
            self._save_kits()

    def _bootstrap_other(self, players: list[Detection], samples: dict[int, KitSample],
                         cursor_players: dict[str, Detection | None]) -> None:
        """Un seul curseur visible (l'autre hors champ) : l'équipe inconnue est déduite
        des joueurs nettement différents de l'équipe connue (cohérents entre eux)."""
        known = [t for t in TEAMS if self.protos[t] is not None and self._anchor_counts[t] >= 5]
        if len(known) != 1:
            return
        k = known[0]
        other = "opp" if k == "me" else "me"
        if self.protos[other] is not None:
            return
        pk = self.protos[k]
        assert pk is not None
        sel = {id(p) for p in cursor_players.values() if p is not None}
        far = [s for i, s in samples.items() if id(players[i]) not in sel
               and float(ciede2000(s.shirt, pk.shirt)) > self.cfg.clash_delta_e * 1.5]
        far = robust_subset(far, max_de=10.0)
        if len(far) < 4:
            self._boot_hits = 0
            return
        cand = TeamPrototype.from_samples(far)
        prev = getattr(self, "_boot_cand", None)
        same = prev is not None and float(ciede2000(prev.shirt, cand.shirt)) < 6.0
        self._boot_cand = cand
        self._boot_hits = getattr(self, "_boot_hits", 0) + 1 if same else 1
        if self._boot_hits >= 5:      # même couleur sur 5 images d'affilée
            self.protos[other] = cand
            self._anchor_counts[other] = 5
            self.status.calibrated_by = self.status.calibrated_by or f"curseur {'rouge' if k == 'me' else 'blanc'} + couleurs"
            log.info("Équipe %s déduite par contraste de couleur (un seul curseur visible)", TEAM_LABEL[other])
            self._save_kits()

    def _detect_half_change(self, clock_s: int | None) -> None:
        if clock_s is None:
            return
        # Le chrono dépasse 45:00 pendant le temps additionnel, puis repart de 45:00
        if self._last_clock is not None and clock_s == 45 * 60 < self._last_clock and self.status.half == 1:
            self.new_half()
        self._last_clock = clock_s

    def _maybe_kickoff(self, image: np.ndarray, players: list[Detection], samples: dict[int, KitSample],
                       cursor_players: dict[str, Detection | None], clock_s: int | None) -> None:
        if clock_s is None or self._calibrated_half == self.status.half:
            return
        # Coup d'envoi de la mi-temps en cours : 00:00 (1re), 45:00 (2e)
        idx = min(self.status.half, len(self.cfg.kickoff_clock)) - 1
        if clock_s != self._parse(self.cfg.kickoff_clock[idx]):
            return
        W = image.shape[1]
        left = [samples[i] for i, d in enumerate(players) if i in samples and d.cx < W / 2]
        right = [samples[i] for i, d in enumerate(players) if i in samples and d.cx >= W / 2]
        if len(left) < 4 or len(right) < 4:
            return
        left, right = robust_subset(left), robust_subset(right)
        if len(left) < 3 or len(right) < 3:
            return
        pl, pr = TeamPrototype.from_samples(left), TeamPrototype.from_samples(right)
        # Les deux moitiés doivent vraiment être deux équipes différentes
        de = float(ciede2000(pl.shirt, pr.shirt))
        if de < 3.0 and (pl.shorts is None or pr.shorts is None or float(ciede2000(pl.shorts, pr.shorts)) < 3.0):
            return
        # Quelle moitié est la mienne ? Le curseur rouge (ou blanc) tranche.
        me_left: bool | None = None
        for side, det in cursor_players.items():
            if det is not None:
                on_left = det.cx < W / 2
                me_left = on_left if side == "me" else not on_left
                break
        if me_left is None and self.protos["me"] is not None:
            me_left = float(ciede2000(self.protos["me"].shirt, pl.shirt)) < float(ciede2000(self.protos["me"].shirt, pr.shirt))
        if me_left is None:
            return  # on attend un curseur pour savoir qui est qui
        self.protos["me"], self.protos["opp"] = (pl, pr) if me_left else (pr, pl)
        self.status.my_attack_dir = "droite" if me_left else "gauche"
        self.status.calibrated_by = "coup d'envoi"
        self._calibrated_half = self.status.half
        self._votes.clear()
        log.info("Coup d'envoi (%s) : équipes calibrées, j'attaque vers la %s (ΔE00 maillots %.1f)",
                 "1re mi-temps" if self.status.half == 1 else "2e mi-temps", self.status.my_attack_dir, de)
        self._save_kits()

    def _save_kits(self) -> None:
        if self.db is None:
            return
        for p in self.protos.values():
            if p is not None:
                self.db.upsert(p.shirt, p.shorts, p.socks)

    @staticmethod
    def _parse(c: str) -> int:
        mm, ss = c.split(":")
        return int(mm) * 60 + int(ss)


@dataclass
class TeamAssignmentSummary:
    """Compte rendu exposé au dashboard."""

    me: int = 0
    opp: int = 0
    unknown: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dets(dets: list[Detection]) -> "TeamAssignmentSummary":
        s = TeamAssignmentSummary()
        for d in dets:
            if d.cls != "player":
                continue
            if d.team == "me":
                s.me += 1
            elif d.team == "opp":
                s.opp += 1
            else:
                s.unknown += 1
        return s
