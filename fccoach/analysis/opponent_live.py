"""Lecture de l'adversaire en direct, à partir de son curseur BLANC (source n°1).

Signaux instantanés (aucun historique nécessaire) :
  opp_cursor_role, opp_cursor_pressing_carrier, opp_cursor_moving_to_lane,
  opp_cursor_dezoned, opp_switch_delay_s, free_lane_count
Et comptage des habitudes (opponent_profile) une fois par séquence de possession.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from fccoach.analysis.formation import DEFENDERS, MIDFIELD
from fccoach.analysis.geometry import closing_speed, dist_point_segment, lane_free
from fccoach.analysis.opponent_profile import OpponentProfile
from fccoach.analysis.world import PlayerState, World


@dataclass
class OppSwitch:
    t: float
    delay_s: float | None


class OpponentLive:
    def __init__(self, profile: OpponentProfile) -> None:
        self.profile = profile
        self.last_switch: OppSwitch | None = None
        self._lanes_since: float | None = None
        self._prev_lane_dist: float | None = None

    def on_switch(self, t: float, delay_s: float | None) -> None:
        self.last_switch = OppSwitch(t, delay_s)

    def update(self, w: World, carrier: PlayerState | None, my_possession: bool, seq_id: int,
               opp_slots: list[tuple[float, float, str]], opp_line_x: float | None) -> dict[str, Any]:
        sig: dict[str, Any] = {}
        sel = w.selected("opp")
        sig["opp_cursor_role"] = sel.role if sel else None
        # Délai de réaction : valable 3 s après son changement de joueur
        if self.last_switch and w.t - self.last_switch.t <= 3.0 and self.last_switch.delay_s is not None:
            sig["opp_switch_delay_s"] = self.last_switch.delay_s
        else:
            sig["opp_switch_delay_s"] = 0.0 if self.last_switch else None
        mates = [p for p in w.team("me") if carrier is None or p.tid != carrier.tid]
        opps = w.team("opp")
        if carrier is not None and my_possession:
            free = [m for m in mates if m.dist(carrier.x, carrier.y) < 30 and lane_free(carrier, m, opps)]
            sig["free_lane_count"] = len(free)
        else:
            sig["free_lane_count"] = None
        if sel is None or carrier is None:
            for k in ("opp_cursor_pressing_carrier", "opp_cursor_moving_to_lane", "opp_cursor_dezoned"):
                sig[k] = None
            return sig
        d_carrier = sel.dist(carrier.x, carrier.y)
        pressing = my_possession and d_carrier < 4.0 and closing_speed(sel, carrier) > 0.5
        sig["opp_cursor_pressing_carrier"] = pressing
        # Se dirige vers la ligne porteur -> mon attaquant le plus avancé
        target = max((m for m in mates if m.role == "BU"), key=lambda m: m.x, default=None) \
            or max(mates, key=lambda m: m.x, default=None)
        moving = False
        if target is not None:
            d_lane = dist_point_segment(sel.x, sel.y, carrier.x, carrier.y, target.x, target.y)
            moving = (self._prev_lane_dist is not None and d_lane < 6 and d_lane < self._prev_lane_dist - 0.3)
            self._prev_lane_dist = d_lane
        sig["opp_cursor_moving_to_lane"] = moving
        # Dézoné : loin du poste de son gabarit (repère de l'adversaire déjà ramené au mien)
        dezoned = None
        if sel.role and opp_slots:
            slots = [(x, y) for x, y, r in opp_slots if r == sel.role]
            if slots:
                d = min(math.hypot(sel.x - x, sel.y - y) for x, y in slots)
                dezoned = d > 18
        sig["opp_cursor_dezoned"] = dezoned
        if my_possession:
            self._count_habits(w, sel, carrier, mates, seq_id, opp_line_x, pressing)
        return sig

    def _count_habits(self, w: World, sel: PlayerState, carrier: PlayerState, mates: list[PlayerState],
                      seq_id: int, opp_line_x: float | None, pressing: bool) -> None:
        prof = self.profile
        ball_x = w.ball[0] if w.ball else carrier.x
        # Ramène ses milieux : mon porteur attaque dans son camp, il défend avec un milieu
        if sel.role in MIDFIELD and ball_x > 10 and sel.vx > 1.5:
            opp_dc = [p for p in w.team("opp") if p.role == "DC"]
            if any(p.dist(carrier.x, carrier.y) < 20 for p in opp_dc):
                prof.count("midfield_only", seq_id)
        # Sort son DC : un DC adverse 12 m devant sa ligne
        if opp_line_x is not None:
            for p in w.team("opp"):
                if p.role == "DC" and p.x < opp_line_x - 12:
                    prof.count("dc_out", seq_id)
                    break
        # Ferme les lignes sans presser : sur une ligne de passe, loin du porteur, 1,5 s
        on_lane = any(dist_point_segment(sel.x, sel.y, carrier.x, carrier.y, m.x, m.y) < 2.0 for m in mates)
        if on_lane and sel.dist(carrier.x, carrier.y) > 6:
            if self._lanes_since is None:
                self._lanes_since = w.t
            elif w.t - self._lanes_since >= 1.5:
                prof.count("closes_lanes", seq_id)
        else:
            self._lanes_since = None
        # Presse au lieu de suivre l'appel
        runners = [m for m in mates if m.vx > 5 and m.x > carrier.x]
        if runners and pressing and sel.role not in DEFENDERS + ("BU",):
            prof.count("ignores_runs", seq_id)
