"""Overlay de debug : chaque joueur avec équipe, confiance, couleurs des prototypes, curseurs."""

from __future__ import annotations

import cv2
import numpy as np

from fccoach.vision.color import lab_to_bgr
from fccoach.vision.cursor import CursorSystem
from fccoach.vision.teams import TeamClassifier
from fccoach.vision.types import Detection

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_CURSOR_COLOR = {"me": (40, 40, 230), "opp": (245, 245, 245)}


def _proto_color(teams: TeamClassifier, team: str | None) -> tuple[int, int, int]:
    p = teams.protos.get(team) if team else None
    if p is None:
        return (128, 128, 128)
    b, g, r = lab_to_bgr(p.shirt)[0]
    return int(b), int(g), int(r)


def draw_debug(image: np.ndarray, dets: list[Detection], cursors: CursorSystem, teams: TeamClassifier) -> np.ndarray:
    out = image.copy()
    for d in dets:
        if d.cls == "ball":
            cv2.circle(out, (int(d.cx), int((d.y1 + d.y2) / 2)), 8, (0, 255, 255), 2)
            continue
        if d.cls != "player":
            color = (0, 200, 255) if d.cls == "goalkeeper" else (0, 0, 0)
            cv2.rectangle(out, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), color, 1)
            cv2.putText(out, "GB" if d.cls == "goalkeeper" else "ARB", (int(d.x1), int(d.y1) - 4), _FONT, 0.45, color, 1)
            continue
        color = _proto_color(teams, d.team)
        thick = 3 if d.team_conf >= teams.cfg.min_confidence else 1
        cv2.rectangle(out, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), color, thick)
        label = {"me": "MOI", "opp": "ADV"}.get(d.team or "", "?")
        txt = f"{label} {d.team_conf:.0%}" + (f" #{d.track_id}" if d.track_id is not None else "")
        cv2.putText(out, txt, (int(d.x1), int(d.y2) + 14), _FONT, 0.45, (0, 0, 0), 3)
        cv2.putText(out, txt, (int(d.x1), int(d.y2) + 14), _FONT, 0.45, color, 1)
    # Curseurs : candidats (fins) et position suivie (épais)
    for side, cands in cursors.last_candidates.items():
        for c in cands:
            x, y, w, h = c.bbox
            cv2.rectangle(out, (x - 2, y - 2), (x + w + 2, y + h + 2), _CURSOR_COLOR[side], 1)
    for side, t in cursors.tracks.items():
        if t.pos is None or t.status == "absent":
            continue
        px, py = int(t.pos[0]), int(t.pos[1])
        cv2.drawMarker(out, (px, py), _CURSOR_COLOR[side], cv2.MARKER_TRIANGLE_DOWN, 26, 2)
        cv2.putText(out, f"{'MOI' if side == 'me' else 'ADV'} [{t.status}]", (px + 14, py - 8), _FONT, 0.5,
                    _CURSOR_COLOR[side], 1)
    # Prototypes en haut à droite
    x0, y0 = out.shape[1] - 260, 20
    cv2.rectangle(out, (x0 - 10, y0 - 10), (out.shape[1] - 10, y0 + 90), (20, 20, 20), -1)
    for i, team in enumerate(("me", "opp")):
        p = teams.protos[team]
        y = y0 + i * 40
        cv2.putText(out, "Moi" if team == "me" else "Adv", (x0, y + 20), _FONT, 0.55, (255, 255, 255), 1)
        if p is None:
            cv2.putText(out, "en attente", (x0 + 60, y + 20), _FONT, 0.5, (160, 160, 160), 1)
            continue
        for j, lab in enumerate((p.shirt, p.shorts, p.socks)):
            if lab is None:
                continue
            b, g, r = lab_to_bgr(lab)[0]
            cv2.rectangle(out, (x0 + 60 + j * 40, y), (x0 + 92 + j * 40, y + 28), (int(b), int(g), int(r)), -1)
            cv2.rectangle(out, (x0 + 60 + j * 40, y), (x0 + 92 + j * 40, y + 28), (255, 255, 255), 1)
    st = teams.status
    msg = f"Equipes {st.confidence:.0%}" + (" CLASH" if st.clash else "")
    cv2.putText(out, msg, (x0, y0 + 88), _FONT, 0.5, (0, 255, 0) if st.reliable else (0, 0, 255), 1)
    return out
