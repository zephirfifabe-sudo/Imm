"""Signaux évalués par les conditions de knowledge/rules.yaml.

Chaque signal vaut None tant qu'il n'est pas mesurable (pas d'homographie,
pas de porteur, postes inconnus…) : la règle qui l'utilise est alors
ignorée. Tous les calculs sont dans le repère normalisé (j'attaque vers +x).
Seuils en mètres / secondes, choisis pour EA FC (à affiner sur vidéos réelles).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from fccoach.analysis.formation import DEFENDERS, MIDFIELD, FormationTracker
from fccoach.analysis.geometry import closing_speed, dist_point_segment, lane_free, nearest
from fccoach.analysis.opponent_live import OpponentLive
from fccoach.analysis.opponent_profile import OpponentProfile
from fccoach.analysis.world import PlayerState, World
from fccoach.events.detector import EventDetector
from fccoach.tracking.pitch import BOX_DEPTH, BOX_HW, HL

FAR = 999.0


@dataclass
class SignalMemory:
    """Minuteries d'un pas à l'autre."""

    carrier_marked_since: float | None = None
    carrier_tid: int | None = None
    cursor_beaten_since: float | None = None
    reception_tid: int | None = None
    reception_t: float | None = None
    reception_v: tuple[float, float] = (0.0, 0.0)
    reception_turned: bool = False
    lost_after_reception_s: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def ball_zone(x: float, y: float) -> str:
    if x < -HL / 3:
        return "my_third"
    if abs(y) > 22:
        return "wing"
    return "opp_third" if x > HL / 3 else "mid"


def opp_line_x(opps: list[PlayerState]) -> float | None:
    """Hauteur (x) de la ligne défensive adverse : moyenne de ses défenseurs."""
    # Postes connus uniquement : avec une vue partielle, « les 4 plus reculés visibles »
    # ne sont pas forcément ses défenseurs (fausse ligne haute = faux conseil).
    defs = [p for p in opps if p.role in DEFENDERS]
    if len(defs) < 2:
        return None
    return sum(p.x for p in defs) / len(defs)


def line_height_prof(line_x: float) -> float:
    """Distance ligne -> son but convertie en « profondeur » EA (0-100). Milieu de terrain ≈ 95."""
    d = HL - line_x
    return max(0.0, min(100.0, d / HL * 95))


def slot_owner(slots: list[tuple[float, float, str]], x: float, y: float) -> str | None:
    if not slots:
        return None
    return min(slots, key=lambda s: math.hypot(s[0] - x, s[1] - y))[2]


def compute_signals(w: World, ev: EventDetector, form_me: FormationTracker, form_opp: FormationTracker,
                    opp_live: OpponentLive, profile: OpponentProfile, mem: SignalMemory, seq_id: int,
                    formation_min_conf: float = 0.7) -> dict[str, Any]:
    s: dict[str, Any] = {}
    me, opp = w.team("me"), w.team("opp")
    my_poss = ev.possession == "me"
    s["my_possession"] = my_poss if ev.possession is not None else None
    fm, fo = form_me.estimate, form_opp.estimate
    s["my_formation"] = fm.name if fm.confidence >= formation_min_conf else None
    s["opp_formation"] = fo.name if fo.confidence >= formation_min_conf else None
    # Habitudes (profil)
    s["habit_midfield_only_count"] = profile.effective("midfield_only")
    s["habit_opp_dc_out_count"] = profile.effective("dc_out")
    s["habit_closes_lanes_count"] = profile.effective("closes_lanes")
    s["habit_ignores_runs_count"] = profile.effective("ignores_runs")
    s["opp_rush_on_carrier_count"] = profile.effective("rush_carrier")
    # Temps depuis perte / récupération / corner adverse
    s["ball_lost"] = bool(ev.possession == "opp" and ev.last_loss and w.t - ev.last_loss.t <= 15)
    s["seconds_since_loss"] = w.t - ev.last_loss.t if ev.last_loss and s["ball_lost"] else None
    s["loss_zone"] = ev.last_loss.data.get("loss_zone") if ev.last_loss and s["ball_lost"] else None
    s["seconds_since_recovery"] = (w.t - ev.last_recovery.t) if my_poss and ev.last_recovery else FAR
    s["seconds_since_opp_corner"] = (w.t - ev.last_opp_corner_t) if ev.last_opp_corner_t is not None else FAR
    s["passes_without_progress"] = ev.passes_without_progress if my_poss else 0
    if not w.pitch_ok or w.ball is None:
        return s
    bx, by = w.ball
    s["ball_zone"] = ball_zone(bx, by)
    s["ball_in_my_half"] = bx < 0
    s["ball_in_my_box"] = bx < -HL + BOX_DEPTH and abs(by) < BOX_HW
    slots_me = form_me.slot_positions()
    slots_opp = [(-x, -y, r) for x, y, r in form_opp.slot_positions()]   # gabarit adverse ramené à mon repère
    s["ball_zone_owner_me"] = slot_owner(slots_me, bx, by)
    s["ball_zone_owner_opp"] = slot_owner(slots_opp, bx, by)
    # Ligne du 10 adverse : ballon plus près de son but que son MOC
    opp10 = [p for p in opp if p.role == "MOC"]
    s["ball_behind_opp_line10"] = (bx > max(p.x for p in opp10)) if opp10 else None
    lx = opp_line_x(opp)
    if lx is not None:
        h = line_height_prof(lx)
        s["opp_line_height"] = h
        if my_poss and bx < 0:
            profile.line_heights.append(h)
    else:
        s["opp_line_height"] = None
    carrier = ev.owner if ev.owner is not None else None
    if carrier is not None:
        carrier = w.by_tid(carrier.tid) or carrier
    my_carrier = carrier if (carrier is not None and carrier.team == "me" and my_poss) else None
    opp_carrier = carrier if (carrier is not None and carrier.team == "opp" and not my_poss) else None
    s.update(opp_live.update(w, my_carrier, my_poss, seq_id, slots_opp, lx))
    _carrier_signals(s, w, my_carrier, me, opp, ev, mem)
    _my_shape(s, w, me, opp, lx, fm.name if fm.confidence >= formation_min_conf else None, slots_me)
    _defence(s, w, opp_carrier, me, opp, ev, mem)
    _reception(s, w, ev, mem)
    return s


def _carrier_signals(s: dict[str, Any], w: World, c: PlayerState | None, me: list[PlayerState],
                     opp: list[PlayerState], ev: EventDetector, mem: SignalMemory) -> None:
    keys = ("space_ahead_m", "carrier_role", "carrier_marked_s", "carrier_speed_high", "nearest_opp_to_carrier_m",
            "clear_forward_lane", "weak_side_empty", "my_run_in_progress", "receiver_pressed",
            "long_forward_pass_started", "axial_pass_started", "my_bu_in_dc_lat_gap")
    if c is None:
        for k in keys:
            s[k] = None
        mem.carrier_marked_since = None
        return
    # Espace devant : adversaire le plus proche dans un cône de ±35° vers l'avant
    ahead = [o for o in opp if o.x > c.x and abs(math.degrees(math.atan2(o.y - c.y, o.x - c.x))) < 35]
    space = min((o.dist(c.x, c.y) for o in ahead), default=HL - c.x)
    # Hors champ, l'espace est inconnu : on ne compte que la partie visible devant le porteur
    visible_ahead = 0.0
    while visible_ahead < 40 and w.visible(c.x + visible_ahead + 1, c.y):
        visible_ahead += 1
    s["space_ahead_m"] = min(space, 40.0, visible_ahead)
    s["carrier_role"] = c.role
    _, d_near = nearest(opp, c.x, c.y)
    s["nearest_opp_to_carrier_m"] = d_near if d_near != math.inf else FAR
    if mem.carrier_tid != c.tid:
        mem.carrier_tid, mem.carrier_marked_since = c.tid, None
    if d_near <= 1.5:
        mem.carrier_marked_since = mem.carrier_marked_since or w.t
    else:
        mem.carrier_marked_since = None
    s["carrier_marked_s"] = (w.t - mem.carrier_marked_since) if mem.carrier_marked_since else 0.0
    s["carrier_speed_high"] = c.speed > 7.0
    mates = [m for m in me if m.tid != c.tid]
    s["clear_forward_lane"] = any(m.x > c.x + 8 and lane_free(c, m, opp) for m in mates)
    ball_y = w.ball[1] if w.ball else c.y
    weak = [o for o in opp if (o.y * ball_y < 0) and abs(o.y) > 10]
    side = -1 if ball_y >= 0 else 1
    weak_seen = w.visible(c.x + 10, side * 22) and w.visible(c.x + 10, side * 12)
    s["weak_side_empty"] = (len(weak) <= 1 and len(opp) >= 6) if weak_seen else None
    s["my_run_in_progress"] = any(m.vx > 5 and m.x > c.x for m in mates)
    lp = ev.last_pass_start
    fresh = lp is not None and lp.team == "me" and w.t - lp.t <= 0.6
    s["long_forward_pass_started"] = bool(fresh and lp.data.get("long"))  # type: ignore[union-attr]
    s["axial_pass_started"] = bool(fresh and lp.data.get("axial") and lp.data.get("forward"))  # type: ignore[union-attr]
    # Receveur visé : coéquipier le plus proche de la trajectoire du ballon
    s["receiver_pressed"] = None
    if fresh and w.ball:
        bx, by = w.ball
        vx, vy = w.ball_v
        tgt = min(mates, key=lambda m: dist_point_segment(m.x, m.y, bx, by, bx + vx, by + vy), default=None)
        if tgt is not None:
            _, d = nearest(opp, tgt.x, tgt.y)
            s["receiver_pressed"] = d < 2.5
    # BU entre DC et latéral adverses, près de leur ligne
    gap = False
    opp_dc = [o for o in opp if o.role == "DC"]
    opp_lat = [o for o in opp if o.role == "LAT"]
    for bu in (m for m in me if m.role == "BU"):
        for dc in opp_dc:
            for lat in opp_lat:
                if (dc.y - bu.y) * (lat.y - bu.y) < 0 and abs(bu.x - (dc.x + lat.x) / 2) < 6:
                    gap = True
    s["my_bu_in_dc_lat_gap"] = gap if (opp_dc and opp_lat) else None


def _my_shape(s: dict[str, Any], w: World, me: list[PlayerState], opp: list[PlayerState], lx: float | None,
              my_formation: str | None, slots_me: list[tuple[float, float, str]]) -> None:
    dcs = [p for p in me if p.role == "DC"]
    defs = [p for p in me if p.role in DEFENDERS]
    if dcs and len(defs) >= 3:
        out = []
        for dc in dcs:
            others = [p.x for p in defs if p.tid != dc.tid]
            out.append(dc.x - sorted(others)[len(others) // 2])
        s["my_dc_out_of_line_m"] = max(0.0, max(out))
    else:
        s["my_dc_out_of_line_m"] = None
    mdcs = [p for p in me if p.role == "MDC"]
    if mdcs:
        mdc_slots = [y for _, y, r in slots_me if r == "MDC"]
        offs = [min(abs(m.y - y) for y in mdc_slots) if mdc_slots else abs(m.y) for m in mdcs]
        s["my_mdc_off_axis_m"] = max(offs)
        s["my_6_free_m"] = min(nearest(opp, m.x, m.y)[1] for m in mdcs) if opp else FAR
    else:
        s["my_mdc_off_axis_m"] = None
        s["my_6_free_m"] = None
    bus = [p for p in me if p.role == "BU"]
    opp_dc = [o for o in opp if o.role == "DC"]
    s["my_bu_to_opp_dc_m"] = min(b.dist(d.x, d.y) for b in bus for d in opp_dc) if bus and opp_dc else None
    s["my_bu_on_opp_line"] = any(abs(b.x - lx) < 2 for b in bus) if (bus and lx is not None) else None
    # Mon latéral côté ballon par rapport à mon DC le plus proche
    if w.ball and dcs:
        lats = [p for p in me if p.role == "LAT" and p.y * w.ball[1] >= 0]
        s["my_lat_to_dc_m"] = min(abs(l.y - d.y) for l in lats for d in dcs) if lats else None
    else:
        s["my_lat_to_dc_m"] = None
    if my_formation == "4213" and w.ball and len(mdcs) >= 2:
        side = 1 if w.ball[1] >= 0 else -1
        s["both_mdc_ball_side"] = all(m.y * side > 3 for m in mdcs)
    else:
        s["both_mdc_ball_side"] = None if my_formation is None else False
    opp_roles = {o.role for o in opp if o.role}
    s["opp_no_winger_my_side"] = ("AIL" not in opp_roles) if opp_roles else None


def _defence(s: dict[str, Any], w: World, oc: PlayerState | None, me: list[PlayerState], opp: list[PlayerState],
             ev: EventDetector, mem: SignalMemory) -> None:
    sel = w.selected("me")
    s["my_cursor_role"] = sel.role if sel else None
    s["my_cursor_to_ball_m"] = sel.dist(*w.ball) if (sel and w.ball) else None
    runners = [o for o in opp if (oc is None or o.tid != oc.tid) and o.vx < -5]
    s["no_opp_run"] = not runners
    my_mid = [p for p in me if p.role in MIDFIELD]
    mid_line = min((p.x for p in my_mid), default=None)
    s["opp_deep_run"] = any(mid_line is not None and o.x < mid_line for o in runners) if runners else False
    defs = [p for p in me if p.role in DEFENDERS]
    gap_run = False
    dcs = [p for p in me if p.role == "DC"]
    lats = [p for p in me if p.role == "LAT"]
    for o in runners:
        for dc in dcs:
            for lat in lats:
                if (dc.y - o.y) * (lat.y - o.y) < 0 and abs(o.x - (dc.x + lat.x) / 2) < 10:
                    gap_run = True
    s["opp_run_in_dc_lat_gap"] = gap_run if (dcs and lats) else None
    lp = ev.last_pass_start
    s["opp_back_pass_started"] = bool(lp and lp.team == "opp" and w.t - lp.t <= 0.6 and lp.data.get("backward"))
    keys = ("my_cursor_not_goal_side", "my_cursor_rushing_carrier", "my_cursor_pressing_carrier",
            "my_cursor_beaten_s", "my_midfield_off_lanes", "opp_carrier_behind_my_midfield", "opp_heavy_touch")
    if oc is None:
        for k in keys:
            s[k] = None
        mem.cursor_beaten_since = None
        return
    if sel is not None:
        s["my_cursor_not_goal_side"] = sel.x > oc.x + 1.0      # mon but est en x = -52,5
        cl = closing_speed(sel, oc)
        d = sel.dist(oc.x, oc.y)
        s["my_cursor_rushing_carrier"] = d < 8 and cl > 5
        s["my_cursor_pressing_carrier"] = d < 3
        if sel.x > oc.x + 2:
            mem.cursor_beaten_since = mem.cursor_beaten_since or w.t
        else:
            mem.cursor_beaten_since = None
        s["my_cursor_beaten_s"] = (w.t - mem.cursor_beaten_since) if mem.cursor_beaten_since else 0.0
    else:
        for k in keys[:4]:
            s[k] = None
    mates = [o for o in opp if o.tid != oc.tid and o.dist(oc.x, oc.y) < 30]
    if my_mid and mates:
        covered = any(dist_point_segment(m.x, m.y, oc.x, oc.y, o.x, o.y) < 3 for m in my_mid for o in mates)
        s["my_midfield_off_lanes"] = not covered
    else:
        s["my_midfield_off_lanes"] = None
    s["opp_carrier_behind_my_midfield"] = (oc.x < mid_line) if mid_line is not None else None
    own = ev.owner_since
    s["opp_heavy_touch"] = bool(w.ball and w.t - own <= 0.7 and oc.dist(*w.ball) > 2.5)
    _ = defs


def _reception(s: dict[str, Any], w: World, ev: EventDetector, mem: SignalMemory) -> None:
    """Contrôle « retourné » (fiche 5) : demi-tour à la réception puis perte rapide."""
    rec = ev.last_reception
    if rec is not None and rec.team == "me" and rec.data.get("tid") != mem.reception_tid:
        mem.reception_tid, mem.reception_t = rec.data.get("tid"), rec.t
        mem.reception_v = (rec.data.get("vx", 0.0), rec.data.get("vy", 0.0))
        mem.reception_turned, mem.lost_after_reception_s = False, None
    if mem.reception_t is not None and mem.reception_tid is not None and w.t - mem.reception_t <= 0.8:
        p = w.by_tid(mem.reception_tid)
        if p is not None and p.speed > 1.5:
            v0 = mem.reception_v
            n0 = math.hypot(*v0)
            if n0 > 1.0 and (v0[0] * p.vx + v0[1] * p.vy) / (n0 * p.speed) < -0.5:
                mem.reception_turned = True
    if ev.last_loss is not None and mem.reception_t is not None and ev.last_loss.t >= mem.reception_t:
        mem.lost_after_reception_s = ev.last_loss.t - mem.reception_t
    s["last_reception_turned"] = mem.reception_turned if mem.reception_t is not None else None
    s["lost_within_s"] = mem.lost_after_reception_s
