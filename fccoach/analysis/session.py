"""Chaîne d'analyse commune au direct et aux clips, à chaque pas de détection :

  détections -> suivi (joueurs, balle) -> équipes -> homographie / terrain 2D
  -> événements -> formations -> adversaire -> coach -> bilan / historique

Les événements des curseurs et de l'OCR arrivent d'autres threads : ils
sont mis en file et traités au pas suivant (aucun verrou dans l'analyse).
"""

from __future__ import annotations

import logging
import queue
from pathlib import Path
from typing import Any, Callable

import numpy as np

from fccoach.analysis.match import MatchAnalyzer
from fccoach.analysis.opponent_profile import OpponentDB
from fccoach.coach.engine import Advice, CoachConfig
from fccoach.coach.rules import load_rules
from fccoach.core.config import Config, resolve_path
from fccoach.storage.db import MatchDB
from fccoach.tracking.homography import Calibration, HomographyTracker
from fccoach.tracking.tracker import BallState, BallTracker, PlayerTracker
from fccoach.vision.cursor import CursorSystem, SelectionChange
from fccoach.vision.teams import TeamClassifier
from fccoach.vision.types import Detection

log = logging.getLogger(__name__)


def load_homography(cfg: Config) -> HomographyTracker:
    cal = None
    try:
        cal = Calibration.load(resolve_path(cfg.pitch.calibration_file))
    except Exception as exc:
        log.warning("Calibration du terrain illisible (%s) : à refaire dans le dashboard", exc)
    if cal is None:
        log.warning("Terrain non calibré : terrain 2D, événements et conseils inactifs. "
                    "Calibre-le une fois dans le dashboard (page « Calibration »).")
    return HomographyTracker(cal)


class Session:
    def __init__(self, cfg: Config, cursors: CursorSystem, teams: TeamClassifier, source: str = "live",
                 out_root: str | Path | None = None, use_db: bool = True,
                 clip_request: Callable[[float, float, Path], None] | None = None) -> None:
        self.cfg = cfg
        self.cursors = cursors
        self.teams = teams
        self.source = source
        self.rules = load_rules(resolve_path(cfg.coach.rules_file))
        self.homography = load_homography(cfg)
        self.players = PlayerTracker()
        self.ball = BallTracker()
        self.db = MatchDB(resolve_path(cfg.storage.matches_db)) if use_db else None
        self.opp_db = OpponentDB(resolve_path(cfg.storage.opponents_db)) if use_db else None
        self.out_root = Path(out_root) if out_root else resolve_path(cfg.storage.matches_dir)
        self.clip_request = clip_request
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.ball_state: BallState | None = None
        self.match = self._new_match()
        self._ocr: dict[str, Any] = {}

    def _new_match(self) -> MatchAnalyzer:
        c = self.cfg.coach
        coach_cfg = CoachConfig(c.min_interval_s, c.display_s, c.repeat_after_s, c.min_confidence,
                                live=self.cfg.live_coaching)
        out = self.out_root / ("match_{id:05d}" if self.db else "analyse")
        return MatchAnalyzer(self.rules, self.homography, out, self.db, self.opp_db, self.source, coach_cfg,
                             self.clip_request, self.cfg.pitch.homography_hz,
                             max_clips_per_rule_half=c.max_clips_per_rule_half,
                             clip_before_s=c.clip_before_s, clip_after_s=c.clip_after_s)

    # ------------------------------------------------------------ entrées
    def push_selection(self, ev: SelectionChange) -> None:
        self._events.put(("selection", ev))

    def push_ocr_event(self, ev: dict[str, Any]) -> None:
        self._events.put(("ocr", ev))

    def set_ocr(self, ocr: dict[str, Any], overlay: bool = False) -> None:
        self._ocr = {**ocr, "overlay": overlay}

    # ------------------------------------------------------------ pas
    def step(self, t: float, image: np.ndarray, raw_dets: list[Detection]) -> tuple[list[Detection], Advice | None]:
        dets = self.players.update(raw_dets, t)
        self.ball_state = self.ball.update(raw_dets, t)
        players = [d for d in dets if d.cls == "player"]
        cursor_players = {side: (self.cursors.detector.player_below(tr.pos, players)
                                 if tr.pos is not None and tr.status == "visible" else None)
                          for side, tr in self.cursors.tracks.items()}
        clock_s = self._ocr.get("clock_s")
        self.teams.process(image, dets, cursor_players, clock_s)
        self._drain(dets)
        if self.match.finished and clock_s == 0:
            log.info("Nouveau match détecté (chrono à 00:00)")
            self.match = self._new_match()
        m = self.match
        m.set_ocr(clock_s, self._ocr.get("clock"), bool(self._ocr.get("overlay")))
        if self._ocr.get("pause_by") and m.profile.pseudo != self._ocr["pause_by"]:
            m.set_opponent(self._ocr["pause_by"])
        st = self.teams.status
        selected = {s: (p.track_id if p is not None else None) for s, p in cursor_players.items()}
        advice = m.step(t, image, dets, self.ball_state, selected, st.my_attack_dir, st.confidence, st.reliable)
        # Délai de réaction adverse : mesuré depuis ma dernière passe / conduite
        self.cursors.tracks["opp"].reference_ts = m.last_my_action_t
        return dets, advice

    def _drain(self, dets: list[Detection]) -> None:
        while True:
            try:
                kind, ev = self._events.get_nowait()
            except queue.Empty:
                return
            if kind == "selection":
                role = None
                if ev.track_id is not None and self.match.world is not None:
                    p = self.match.world.by_tid(ev.track_id)
                    role = p.role if p else None
                self.match.on_selection_change(ev.side, ev.ts, ev.reaction_delay_s, ev.zone, role)
            else:
                if ev.get("type") == "halftime" or (ev.get("type") == "period_start" and ev.get("clock_s") == 45 * 60):
                    self.teams.new_half()
                self.match.on_ocr_event(ev)

    def calibrate(self, points: list[dict], image: np.ndarray) -> Calibration:
        cal = Calibration.from_points(points, image)
        cal.save(resolve_path(self.cfg.pitch.calibration_file))
        self.homography.set_calibration(cal)
        return cal

    def snapshot(self) -> dict[str, Any]:
        return self.match.snapshot()

    def close(self) -> None:
        if not self.match.finished:
            self.match.finish()
        if self.db:
            self.db.close()
        if self.opp_db:
            self.opp_db.close()
