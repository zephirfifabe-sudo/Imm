"""Détection des curseurs de sélection (léger : masque couleur + forme, sans YOLO).

Règle fixe : MON curseur est TOUJOURS ROUGE, celui de l'ADVERSAIRE TOUJOURS BLANC.
Forme : petit triangle pointant vers le bas, au-dessus de la tête du joueur.

Étapes (1080p natif) :
 1. masques HSV rouge / blanc (config/cursor.yaml) ;
 2. filtres de forme : aire, côtés, rapport largeur/hauteur, solidité,
    triangle ajusté (minEnclosingTriangle) pointant vers le bas ;
 3. anti-confusion : saturation moyenne (rouge vs maillots roses/rouges),
    isolement (couronne vide autour : exclut lignes et maillots blancs),
    position au-dessus d'une boîte de joueur, régions HUD exclues ;
 4. suivi : lissage, interpolation jusqu'à 2 s si masqué, puis repli sur
    le joueur le plus proche sans jamais bloquer ;
 5. événement à chaque changement de joueur sélectionné.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from fccoach.vision.types import Detection

log = logging.getLogger(__name__)

SIDES = ("me", "opp")
SIDE_LABEL = {"me": "moi (rouge)", "opp": "adversaire (blanc)"}


@dataclass
class CursorCandidate:
    side: str
    tip: tuple[float, float]        # pointe basse du triangle
    center: tuple[float, float]
    bbox: tuple[int, int, int, int]  # x, y, w, h
    score: float                    # qualité de forme 0-1
    player: Detection | None = None


@dataclass
class SelectionChange:
    side: str                       # me | opp
    ts: float                       # horloge monotone
    wall: float
    tip: tuple[float, float]
    zone: str                       # zone image (ou terrain après homographie, Phase 2)
    track_id: int | None
    poste: str | None               # rempli en Phase 4 (formation)
    reaction_delay_s: float | None  # vs ma dernière passe / conduite (Phase 3)

    def as_dict(self) -> dict[str, Any]:
        return {"type": "selection_change", "side": self.side, "wall": self.wall,
                "tip": [round(self.tip[0]), round(self.tip[1])], "zone": self.zone,
                "track_id": self.track_id, "poste": self.poste,
                "reaction_delay_s": None if self.reaction_delay_s is None else round(self.reaction_delay_s, 2)}


def image_zone(x: float, y: float, w: int = 1920, h: int = 1080) -> str:
    """Zone grossière dans l'image tant que l'homographie (Phase 2) n'existe pas."""
    col = ("gauche", "centre", "droite")[min(2, int(3 * x / w))]
    row = ("haut", "milieu", "bas")[min(2, int(3 * y / h))]
    return f"{row}-{col}"


class CursorDetector:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.shape = cfg.get("shape", {})
        self.pos = cfg.get("position", {})
        self._ranges = {
            side: [(np.array(lo, np.uint8), np.array(hi, np.uint8)) for lo, hi in cfg[side]["hsv_ranges"]]
            for side in SIDES
        }

    def _mask(self, hsv: np.ndarray, side: str) -> np.ndarray:
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in self._ranges[side]:
            mask |= cv2.inRange(hsv, lo, hi)
        return mask

    def _excluded(self, x: float, y: float, w: int, h: int) -> bool:
        for rx, ry, rx2, ry2 in self.pos.get("exclude_regions", []):
            if rx * w <= x <= rx2 * w and ry * h <= y <= ry2 * h:
                return True
        return False

    def _triangle_down(self, cnt: np.ndarray) -> tuple[float, tuple[float, float]] | None:
        """Score de forme et pointe si le contour est un triangle pointant vers le bas."""
        area = cv2.contourArea(cnt)
        ok, tri = cv2.minEnclosingTriangle(cnt.astype(np.float32))
        if not ok or tri is None:
            return None
        tri = tri.reshape(3, 2)
        tri_area = abs(cv2.contourArea(tri))
        if tri_area <= 0:
            return None
        fill = area / tri_area
        if fill < self.shape.get("min_triangle_fill", 0.7):
            return None
        order = np.argsort(tri[:, 1])          # du plus haut au plus bas (y croissant)
        top2, bottom = tri[order[:2]], tri[order[2]]
        height = bottom[1] - top2[:, 1].mean()
        width = abs(top2[0, 0] - top2[1, 0])
        if height <= 0 or width <= 0:
            return None
        # base horizontale en haut, pointe en bas, centrée sous la base
        if abs(top2[0, 1] - top2[1, 1]) > 0.35 * height:
            return None
        if not (min(top2[:, 0]) - 0.15 * width <= bottom[0] <= max(top2[:, 0]) + 0.15 * width):
            return None
        approx = cv2.approxPolyDP(cnt, self.shape.get("approx_epsilon", 0.12) * cv2.arcLength(cnt, True), True)
        vertex_bonus = 1.0 if len(approx) == 3 else 0.8
        return float(min(1.0, fill) * vertex_bonus), (float(bottom[0]), float(bottom[1]))

    def _isolated(self, mask: np.ndarray, x: int, y: int, w: int, h: int, ring: int, max_fill: float) -> bool:
        H, W = mask.shape
        x0, y0, x1, y1 = max(0, x - ring), max(0, y - ring), min(W, x + w + ring), min(H, y + h + ring)
        roi = mask[y0:y1, x0:x1]
        inner = mask[y:y + h, x:x + w]
        ring_area = roi.size - inner.size
        if ring_area <= 0:
            return True
        ring_on = (int(np.count_nonzero(roi)) - int(np.count_nonzero(inner)))
        return ring_on / ring_area <= max_fill

    def detect(self, image: np.ndarray, players: list[Detection] | None = None,
               hsv: np.ndarray | None = None) -> dict[str, list[CursorCandidate]]:
        """Candidats par côté, du meilleur au moins bon."""
        H, W = image.shape[:2]
        if hsv is None:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        boxes = [p for p in (players or []) if p.cls in ("player", "goalkeeper")]
        need_player = bool(self.pos.get("require_player_below", True)) and players is not None
        sh = self.shape
        out: dict[str, list[CursorCandidate]] = {}
        for side in SIDES:
            side_cfg = self.cfg[side]
            mask = self._mask(hsv, side)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cands: list[CursorCandidate] = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if not (sh.get("min_area", 25) <= area <= sh.get("max_area", 900)):
                    continue
                x, y, w, h = cv2.boundingRect(cnt)
                if not (sh.get("min_side_px", 6) <= max(w, h) <= sh.get("max_side_px", 45)):
                    continue
                aspect = w / max(h, 1)
                if not (sh.get("min_aspect", 0.6) <= aspect <= sh.get("max_aspect", 2.2)):
                    continue
                hull_area = cv2.contourArea(cv2.convexHull(cnt))
                if hull_area <= 0 or area / hull_area < sh.get("min_solidity", 0.8):
                    continue
                if self._excluded(x + w / 2, y + h / 2, W, H):
                    continue
                tri = self._triangle_down(cnt)
                if tri is None:
                    continue
                score, tip = tri
                if "min_saturation_mean" in side_cfg:
                    cmask = np.zeros((h, w), np.uint8)
                    cv2.drawContours(cmask, [cnt - [x, y]], -1, 255, -1)
                    sat = cv2.mean(hsv[y:y + h, x:x + w, 1], mask=cmask)[0]
                    if sat < side_cfg["min_saturation_mean"]:
                        continue
                ring = int(side_cfg.get("isolation_ring_px", sh.get("isolation_ring_px", 6)))
                max_fill = float(side_cfg.get("isolation_max_fill", sh.get("isolation_max_fill", 0.25)))
                if not self._isolated(mask, x, y, w, h, ring, max_fill):
                    continue
                player = self.player_below(tip, boxes)
                if need_player and player is None:
                    continue
                cands.append(CursorCandidate(side, tip, (x + w / 2, y + h / 2), (x, y, w, h), score, player))
            cands.sort(key=lambda c: c.score + (0.5 if c.player else 0.0), reverse=True)
            out[side] = cands
        return out

    def player_below(self, tip: tuple[float, float], boxes: list[Detection]) -> Detection | None:
        best, best_d = None, 1e9
        for b in boxes:
            dx = abs(tip[0] - b.cx)
            gap = b.y1 - tip[1]  # >0 : la boîte commence sous la pointe
            if dx <= self.pos.get("max_dx_px", 40) and -self.pos.get("max_overlap_px", 25) <= gap <= self.pos.get("max_gap_px", 60):
                d = dx + abs(gap)
                if d < best_d:
                    best, best_d = b, d
        return best


@dataclass
class CursorTrack:
    side: str
    smoothing: float = 0.5
    interpolate_max_s: float = 2.0
    switch_jump_px: float = 80.0
    switch_confirm_frames: int = 2
    pos: tuple[float, float] | None = None
    vel: tuple[float, float] = (0.0, 0.0)
    last_seen: float = 0.0
    status: str = "absent"          # visible | interpolé | repli | absent
    player: Detection | None = None
    track_id: int | None = None
    _pending: tuple[float, float] | None = None
    _pending_n: int = 0
    _last_ts: float = 0.0
    changes: int = 0
    reference_ts: float | None = None   # dernière passe/conduite (Phase 3)

    def update(self, cand: CursorCandidate | None, ts: float,
               players: list[Detection] | None = None) -> SelectionChange | None:
        dt = max(1e-3, ts - self._last_ts) if self._last_ts else 0.0
        self._last_ts = ts
        if cand is not None:
            return self._observe(cand, ts, dt)
        # Curseur masqué : interpolation puis repli
        if self.pos is None:
            self.status = "absent"
            return None
        age = ts - self.last_seen
        if age <= self.interpolate_max_s:
            self.pos = (self.pos[0] + self.vel[0] * dt, self.pos[1] + self.vel[1] * dt)
            self.vel = (self.vel[0] * 0.9, self.vel[1] * 0.9)
            self.status = "interpolé"
        else:
            self.status = "repli"
            if players:
                near = min(players, key=lambda p: (p.cx - self.pos[0]) ** 2 + (p.y1 - self.pos[1]) ** 2)
                self.player = near
                self.track_id = near.track_id
        return None

    def _observe(self, cand: CursorCandidate, ts: float, dt: float) -> SelectionChange | None:
        tip = cand.tip
        change: SelectionChange | None = None
        if self.pos is None:
            self._accept(tip, ts, dt, reset=True)
            change = self._event(cand, ts)
        else:
            jump = float(np.hypot(tip[0] - self.pos[0], tip[1] - self.pos[1]))
            same_track = cand.player is not None and cand.player.track_id is not None and cand.player.track_id == self.track_id
            if jump > self.switch_jump_px and not same_track:
                # Saut : nouveau joueur sélectionné ? On confirme sur N images.
                if self._pending is not None and np.hypot(tip[0] - self._pending[0], tip[1] - self._pending[1]) < self.switch_jump_px / 2:
                    self._pending_n += 1
                else:
                    self._pending, self._pending_n = tip, 1
                if self._pending_n >= self.switch_confirm_frames:
                    self._accept(tip, ts, dt, reset=True)
                    self._pending, self._pending_n = None, 0
                    change = self._event(cand, ts)
                else:
                    return None
            else:
                self._pending, self._pending_n = None, 0
                self._accept(tip, ts, dt, reset=False)
        self.player = cand.player
        self.track_id = cand.player.track_id if cand.player else None
        self.status = "visible"
        return change

    def _accept(self, tip: tuple[float, float], ts: float, dt: float, reset: bool) -> None:
        if reset or self.pos is None:
            self.vel = (0.0, 0.0)
            self.pos = tip
        else:
            a = self.smoothing
            new = (a * tip[0] + (1 - a) * self.pos[0], a * tip[1] + (1 - a) * self.pos[1])
            if dt > 0:
                self.vel = ((new[0] - self.pos[0]) / dt, (new[1] - self.pos[1]) / dt)
            self.pos = new
        self.last_seen = ts

    def _event(self, cand: CursorCandidate, ts: float) -> SelectionChange:
        self.changes += 1
        delay = None
        if self.reference_ts is not None and 0 <= ts - self.reference_ts <= 3.0:
            delay = ts - self.reference_ts
        return SelectionChange(
            side=self.side, ts=ts, wall=time.time(), tip=cand.tip,
            zone=image_zone(*cand.tip), track_id=cand.player.track_id if cand.player else None,
            poste=None, reaction_delay_s=delay,
        )

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "pos": None if self.pos is None else [round(self.pos[0]), round(self.pos[1])],
                "track_id": self.track_id, "changes": self.changes,
                "seen_ago_s": round(time.monotonic() - self.last_seen, 1) if self.last_seen else None}


class CursorSystem:
    """Détecteur + un suivi par côté. Thread-safe côté lecture (valeurs simples)."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.detector = CursorDetector(cfg)
        tcfg = cfg.get("tracking", {})
        self.tracks = {
            side: CursorTrack(
                side=side,
                smoothing=tcfg.get("smoothing", 0.5),
                interpolate_max_s=tcfg.get("interpolate_max_s", 2.0),
                switch_jump_px=tcfg.get("switch_jump_px", 80),
                switch_confirm_frames=tcfg.get("switch_confirm_frames", 2),
            )
            for side in SIDES
        }
        self.last_candidates: dict[str, list[CursorCandidate]] = {s: [] for s in SIDES}

    def process(self, image: np.ndarray, ts: float, players: list[Detection] | None) -> list[SelectionChange]:
        cands = self.detector.detect(image, players)
        self.last_candidates = cands
        events = []
        for side in SIDES:
            best = self._pick(side, cands.get(side, []))
            ev = self.tracks[side].update(best, ts, players)
            if ev is not None:
                events.append(ev)
        return events

    def _pick(self, side: str, cands: list[CursorCandidate]) -> CursorCandidate | None:
        if not cands:
            return None
        pos = self.tracks[side].pos
        if pos is None or len(cands) == 1:
            return cands[0]
        # Plusieurs candidats : meilleure forme, départagée par la proximité
        return max(cands, key=lambda c: c.score + (0.5 if c.player else 0)
                   - 0.001 * float(np.hypot(c.tip[0] - pos[0], c.tip[1] - pos[1])))

    def anchor(self, which: str) -> tuple[float, float] | None:
        """Pointe du curseur (pour la zone OCR « nom du joueur sélectionné »)."""
        side = {"cursor_me": "me", "cursor_opp": "opp"}.get(which, which)
        t = self.tracks.get(side)
        return t.pos if t and t.status in ("visible", "interpolé") else None

    def selected_player(self, side: str) -> Detection | None:
        t = self.tracks[side]
        return t.player if t.status == "visible" else None
