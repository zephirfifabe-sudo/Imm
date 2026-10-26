"""Analyse d'un match (direct ou clip) : terrain 2D, événements, formations,
adversaire, coach, bilan, historique.

Appelé à chaque pas de détection avec les sorties de la vision. Le même code
sert au direct (horloge monotone) et aux clips (temps de la vidéo).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from fccoach.analysis.formation import FormationTracker
from fccoach.analysis.opponent_live import OpponentLive
from fccoach.analysis.opponent_profile import HABITS, OpponentDB, OpponentProfile
from fccoach.analysis.signals import SignalMemory, compute_signals
from fccoach.analysis.world import PlayerState, World, WorldBuilder
from fccoach.coach.engine import Advice, Coach, CoachConfig
from fccoach.coach.rules import Rule
from fccoach.events.detector import EventDetector, GameEvent
from fccoach.storage.db import MatchDB
from fccoach.tracking.homography import HomographyTracker
from fccoach.tracking.pitch import HL, HW, LENGTH, WIDTH, PitchCanvas
from fccoach.tracking.tracker import BallState
from fccoach.vision.types import Detection

log = logging.getLogger(__name__)

ClipRequest = Callable[[float, float, Path], None]


def fmt_clock(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


@dataclass
class Stats:
    possession_s: dict[str, float] = field(default_factory=lambda: {"me": 0.0, "opp": 0.0})
    counts: dict[str, int] = field(default_factory=dict)
    reaction_delays: list[float] = field(default_factory=list)

    def add(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def as_dict(self) -> dict[str, Any]:
        tot = sum(self.possession_s.values())
        return {
            "possession_pct": {k: round(100 * v / tot) for k, v in self.possession_s.items()} if tot > 5 else None,
            **{k: v for k, v in sorted(self.counts.items())},
            "opp_reaction_delay_mean_s": round(float(np.mean(self.reaction_delays)), 2) if self.reaction_delays else None,
        }


class Heatmaps:
    """Positions accumulées (grille de 1 m) par équipe et par mi-temps."""

    def __init__(self) -> None:
        self.grids: dict[str, np.ndarray] = {}
        self._last = -1e9

    def add(self, w: World, half: int, period_s: float = 0.5) -> None:
        if w.t - self._last < period_s:
            return
        self._last = w.t
        for p in w.players:
            for key in (f"{p.team}_h{half}", p.team) + ((f"selected_{p.selected}",) if p.selected else ()):
                g = self.grids.setdefault(key, np.zeros((int(WIDTH), int(LENGTH)), np.float32))
                ix = int(np.clip(p.x + HL, 0, LENGTH - 1))
                iy = int(np.clip(p.y + HW, 0, WIDTH - 1))
                g[iy, ix] += 1

    def save(self, out_dir: Path) -> dict[str, str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        canvas = PitchCanvas()
        titles = {"me": "Moi (j'attaque ->)", "opp": "Adversaire", "selected_me": "Mon joueur sélectionné",
                  "selected_opp": "Joueur sélectionné adverse"}
        files = {}
        for key, g in self.grids.items():
            title = titles.get(key, key.replace("_h", " mi-temps ").replace("me", "Moi").replace("opp", "Adversaire"))
            path = out_dir / f"heatmap_{key}.png"
            cv2.imwrite(str(path), canvas.heatmap(g, title))
            files[key] = path.name
        return files


class MatchAnalyzer:
    def __init__(self, rules: list[Rule], homography: HomographyTracker, out_dir: str | Path,
                 db: MatchDB | None = None, opp_db: OpponentDB | None = None, source: str = "live",
                 coach_cfg: CoachConfig | None = None, clip_request: ClipRequest | None = None,
                 homography_hz: float = 10.0, formation_hz: float = 1.0, max_clips_per_rule_half: int = 3,
                 clip_before_s: float = 6.0, clip_after_s: float = 3.0) -> None:
        """out_dir peut contenir « {id} », remplacé par le numéro du match en base."""
        self.rules = {r.id: r for r in rules}
        self.homo = homography
        self.db = db
        self.opp_db = opp_db
        self.source = source
        self.clip_request = clip_request
        self.homography_period = 1.0 / homography_hz
        self.formation_period = 1.0 / formation_hz
        self.max_clips = max_clips_per_rule_half
        personal = db.rule_rates() if db else {}
        self.coach = Coach(rules, coach_cfg, personal)
        self.builder = WorldBuilder()
        self.events = EventDetector()
        self.form_me, self.form_opp = FormationTracker(), FormationTracker()
        self.profile = OpponentProfile()
        self.opp_live = OpponentLive(self.profile)
        self.mem = SignalMemory()
        self.stats = Stats()
        self.heat = Heatmaps()
        self.world: World | None = None
        self.signals: dict[str, Any] = {}
        self.half = 1
        self.seq_id = 0
        self.match_id = db.start_match(source) if db else None
        self.out_dir = Path(str(out_dir).format(id=self.match_id or 0))
        self.clip_before_s, self.clip_after_s = clip_before_s, clip_after_s
        self.home_is_me: bool | None = None
        self.score: list[int] | None = None
        self.clock_s: int | None = None
        self.clock_text: str | None = None
        self._clock_changed_t = -1e9
        self._overlay = False
        self._start_t: float | None = None
        self._last_homo_t = -1e9
        self._last_form_t = -1e9
        self._last_t: float | None = None
        self.last_my_action_t: float | None = None
        self._occ_seen = 0
        self._clips_per_rule: dict[tuple[str, int], int] = {}
        self.occurrence_records: list[dict[str, Any]] = []
        self.game_events: list[dict[str, Any]] = []
        self.bilans: dict[str, Any] = {}
        self.finished = False
        self.pitch_ok_steps = 0
        self.out_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------- entrées OCR
    def set_ocr(self, clock_s: int | None, clock_text: str | None, overlay: bool = False) -> None:
        # Le chrono « tourne » s'il avance (une reprise à 45:00 n'est pas du jeu lancé)
        if clock_s is not None and self.clock_s is not None and clock_s > self.clock_s:
            self._clock_changed_t = self._last_t if self._last_t is not None else 0.0
        self.clock_s, self.clock_text, self._overlay = clock_s, clock_text, overlay

    def on_ocr_event(self, ev: dict[str, Any]) -> None:
        t = self._last_t or 0.0
        typ = ev.get("type")
        if typ == "goal":
            self._on_goal(ev.get("score"), t)
        elif typ == "pause" and ev.get("by"):
            self.set_opponent(str(ev["by"]))
        elif typ == "halftime" or (typ == "period_start" and ev.get("clock_s") == 45 * 60):
            self.new_half()
        elif typ == "fulltime":
            self.finish()

    def set_opponent(self, pseudo: str) -> None:
        if self.profile.pseudo == pseudo:
            return
        self.profile.pseudo = pseudo
        if self.opp_db:
            self.profile.prior = self.opp_db.load(pseudo)
            n = self.opp_db.matches(pseudo)
            if n:
                known = [HABITS[k] for k, v in self.profile.prior.items() if v >= 3 and k in HABITS]
                log.info("Adversaire déjà rencontré (%d match(s)) : %s", n, ", ".join(known) or "aucune habitude installée")
        if self.db and self.match_id:
            self.db.update_match(self.match_id, opponent=pseudo)

    def on_selection_change(self, side: str, t: float, delay_s: float | None, zone: str | None,
                            role: str | None = None) -> None:
        self.stats.add(f"changements_joueur_{side}")
        if side == "opp":
            self.opp_live.on_switch(t, delay_s)
            if delay_s is not None:
                self.stats.reaction_delays.append(delay_s)
        self._record({"type": "selection_change", "side": side, "t": t, "zone": zone, "role": role,
                      "reaction_delay_s": delay_s})

    def _on_goal(self, score: list[int] | None, t: float) -> None:
        if score is None:
            return
        prev = self.score or [0, 0]
        idx = 0 if score[0] > prev[0] else 1
        shots = [e for e in self.events.history if e.type == "tir" and t - e.t < 15]
        scorer = shots[-1].team if shots else self.events.possession
        if scorer in ("me", "opp") and self.home_is_me is None:
            self.home_is_me = (idx == 0) == (scorer == "me")
        self.score = list(score)
        team = None if self.home_is_me is None else ("me" if (idx == 0) == self.home_is_me else "opp")
        self.stats.add(f"buts_{team or 'inconnu'}")
        self._record({"type": "but", "t": t, "team": team, "score": list(score)})

    # ----------------------------------------------------------- pas d'analyse
    def step(self, t: float, image: np.ndarray, dets: list[Detection], ball: BallState | None,
             selected_tids: dict[str, int | None], my_attack_dir: str | None, team_conf: float,
             team_reliable: bool) -> Advice | None:
        if self.finished:
            return None
        if self._start_t is None:
            self._start_t = t
        dt = 0.0 if self._last_t is None else max(0.0, t - self._last_t)
        self._last_t = t
        if t - self._last_homo_t >= self.homography_period:
            self.homo.update(image, t)
            self._last_homo_t = t
        w = self.builder.build(t, dets, self.homo, ball, selected_tids, my_attack_dir, team_conf, team_reliable)
        self.world = w
        if w.pitch_ok:
            self.pitch_ok_steps += 1
        kickoff = self.clock_s in (0, 45 * 60) and not self.play_running(t)
        if w.pitch_ok and t - self._last_form_t >= self.formation_period:
            self._last_form_t = t
            mine = [p for p in w.players if p.team == "me" and p.conf >= 0.7]
            theirs = [PlayerState(p.tid, "opp", -p.x, -p.y, -p.vx, -p.vy, conf=p.conf)
                      for p in w.players if p.team == "opp" and p.conf >= 0.7]
            self.form_me.observe(mine, kickoff)
            self.form_opp.observe(theirs, kickoff)
        for p in w.players:
            p.role = (self.form_me if p.team == "me" else self.form_opp).role_of(p.tid)
        for ev in self.events.update(w):
            self._on_game_event(ev)
        if self.events.possession in ("me", "opp"):
            self.stats.possession_s[self.events.possession] += dt
        if w.pitch_ok:
            self.heat.add(w, self.half)
        self.signals = compute_signals(w, self.events, self.form_me, self.form_opp, self.opp_live, self.profile,
                                       self.mem, self.seq_id)
        form_conf = min(self.form_me.estimate.confidence, self.form_opp.estimate.confidence)
        advice = self.coach.update(t, self.signals, team_conf if team_reliable else 0.0, form_conf,
                                   self.play_running(t), self.clock_text)
        if advice is not None and self.db and self.match_id:
            self.db.add_advice(self.match_id, t, self.clock_text, advice.rule_id, advice.text)
        self._collect_occurrences()
        return advice

    def play_running(self, t: float) -> bool:
        """Jeu lancé : chrono qui tourne (sinon, faute d'OCR, 10 s après le début), sans pause."""
        if self._overlay or self.world is None or not self.world.pitch_ok:
            return False
        if self.clock_s is not None:
            return t - self._clock_changed_t <= 2.5
        return self._start_t is not None and t - self._start_t > 10

    def _on_game_event(self, ev: GameEvent) -> None:
        if ev.type in ("perte", "recuperation"):
            self.seq_id += 1
        if ev.type == "pressing":
            self.profile.count("rush_carrier", self.seq_id)
        if ev.team == "me" and ev.type in ("passe_debut", "conduite"):
            self.last_my_action_t = ev.t
        if ev.type != "passe_debut":
            key = {"passe": "passes", "perte": "pertes", "recuperation": "recuperations", "tir": "tirs",
                   "corner": "corners", "conduite": "conduites", "pressing": "pressings_subis"}.get(ev.type, ev.type)
            self.stats.add(f"{key}_{ev.team}" if ev.type not in ("perte", "recuperation", "pressing") else key)
            self._record(ev.as_dict())

    def _record(self, ev: dict[str, Any]) -> None:
        ev = {**ev, "clock": self.clock_text, "half": self.half}
        self.game_events.append(ev)
        if self.db and self.match_id:
            data = {k: v for k, v in ev.items() if k not in ("t", "clock", "type", "team")}
            self.db.add_event(self.match_id, float(ev.get("t") or 0.0), self.clock_text, ev["type"], ev.get("team"), data)

    def _collect_occurrences(self) -> None:
        occs = self.coach.occurrences
        while self._occ_seen < len(occs):
            o = occs[self._occ_seen]
            self._occ_seen += 1
            rule = self.rules[o.rule_id]
            clip_name = None
            key = (o.rule_id, self.half)
            if self.clip_request and rule.priorite <= 2 and self._clips_per_rule.get(key, 0) < self.max_clips:
                self._clips_per_rule[key] = self._clips_per_rule.get(key, 0) + 1
                clip_name = f"{o.rule_id}_h{self.half}_{self._clips_per_rule[key]}.webm"
                self.clip_request(o.t - self.clip_before_s, o.t + self.clip_after_s, self.out_dir / "clips" / clip_name)
            rec = {"rule_id": o.rule_id, "t": round(o.t, 2), "clock": o.clock, "half": self.half,
                   "clip": f"clips/{clip_name}" if clip_name else None}
            self.occurrence_records.append(rec)
            if self.db and self.match_id:
                self.db.add_occurrence(self.match_id, o.t, o.clock, o.rule_id, self.half, rec["clip"])

    # ----------------------------------------------------------- mi-temps / fin
    def new_half(self) -> None:
        if self.half >= 2:
            return
        self.bilans["mi-temps"] = self.bilan(half=1)
        self._save_bilan("mi-temps")
        self.half = 2
        self.builder.new_half()
        self.events.reset_half()
        log.info("Bilan de mi-temps prêt (%d règles déclenchées)", len(self.bilans["mi-temps"]["rules"]))

    def finish(self) -> dict[str, Any]:
        if self.finished:
            return self.bilans.get("fin", {})
        self.finished = True
        heat = self.heat.save(self.out_dir / "heatmaps")
        bilan = self.bilan(half=None)
        bilan["heatmaps"] = {k: f"heatmaps/{v}" for k, v in heat.items()}
        self.bilans["fin"] = bilan
        self._save_bilan("fin")
        if self.opp_db:
            self.opp_db.save(self.profile)
        if self.db and self.match_id:
            sm, so = self.my_score()
            self.db.update_match(self.match_id, ended=time.time(), score_me=sm, score_opp=so,
                                 my_formation=self.form_me.estimate.name, opp_formation=self.form_opp.estimate.name,
                                 summary={"stats": bilan["stats"], "bilan_file": "bilan_fin.json"})
        log.info("Bilan de fin de match prêt : %s", self.out_dir / "bilan_fin.json")
        return bilan

    def my_score(self) -> tuple[int | None, int | None]:
        if self.score is None or self.home_is_me is None:
            return None, None
        return (self.score[0], self.score[1]) if self.home_is_me else (self.score[1], self.score[0])

    def bilan(self, half: int | None) -> dict[str, Any]:
        occ = [o for o in self.occurrence_records if half is None or o["half"] == half]
        by_rule: dict[str, list[dict[str, Any]]] = {}
        for o in occ:
            by_rule.setdefault(o["rule_id"], []).append(o)
        rules = []
        for rid, items in by_rule.items():
            r = self.rules[rid]
            rules.append({"rule_id": rid, "conseil": r.conseil, "fiche": r.fiche, "source": r.source,
                          "bouton": r.bouton, "priorite": r.priorite, "contexte": r.contexte,
                          "situation": r.declencheur.description, "count": len(items),
                          "moments": [{"clock": i["clock"], "t": i["t"], "clip": i["clip"]} for i in items]})
        rules.sort(key=lambda x: (x["priorite"], -x["count"]))
        sm, so = self.my_score()
        return {
            "half": half, "match_id": self.match_id, "source": self.source,
            "score": {"me": sm, "opp": so, "raw": self.score},
            "stats": self.stats.as_dict(),
            "formations": {"me": self.form_me.estimate.as_dict(), "opp": self.form_opp.estimate.as_dict()},
            "opponent": {"pseudo": self.profile.pseudo, "habits": self.profile.summary(),
                         "line_height": self.profile.mean_line_height()},
            "rules": rules,
            "advice_shown": [a.as_dict() for a in self.coach.shown],
        }

    def _save_bilan(self, name: str) -> None:
        (self.out_dir / f"bilan_{name.replace('-', '_')}.json").write_text(
            json.dumps(self.bilans[name], indent=1, ensure_ascii=False), encoding="utf-8")

    # ----------------------------------------------------------- dashboard
    def snapshot(self) -> dict[str, Any]:
        w = self.world
        sel_opp = w.selected("opp") if w else None
        return {
            "match_id": self.match_id, "half": self.half,
            "pitch": {
                "status": self.homo.status, "calibrated": self.homo.calibration is not None,
                "attack_known": bool(w and w.attack_known),
                "players": [{"x": round(p.x, 1), "y": round(p.y, 1), "team": p.team, "role": p.role,
                             "selected": p.selected, "tid": p.tid} for p in (w.players if w else [])],
                "ball": [round(w.ball[0], 1), round(w.ball[1], 1)] if (w and w.ball) else None,
            },
            "possession": self.events.possession,
            "formations": {"me": self.form_me.estimate.as_dict(), "opp": self.form_opp.estimate.as_dict()},
            "opponent": {"pseudo": self.profile.pseudo, "selected_role": sel_opp.role if sel_opp else None,
                         "habits": self.profile.summary(), "line_height": self.profile.mean_line_height(),
                         "known": bool(self.profile.prior)},
            "advice": self.coach.current.as_dict() if self.coach.current else None,
            "stats": self.stats.as_dict(),
            "score_me_opp": self.my_score(),
            "play_running": self.play_running(self._last_t or 0.0),
            "occurrences": len(self.occurrence_records),
        }
