"""Coach : règles de knowledge/rules.yaml -> UN conseil à la fois.

Principes (non négociables) :
  - aucun conseil hors de rules.yaml ; aucune règle ne correspond -> rien ;
  - chaque conseil cite sa fiche ; les boutons sont « suggérés », jamais « vus » ;
  - un signal inconnu (None) -> la règle est ignorée (zéro conseil vaut mieux qu'un douteux) ;
  - équipe / formation sous 70 % de confiance -> règles dépendantes bloquées ;
  - pas de conseil pendant l'engagement ni en pause ; ensuite un conseil
    toutes les 20 à 30 s au plus ;
  - habitudes : 2 occurrences -> « à confirmer », 3 -> installée (fiche 10) ;
  - historique (Phase 5) : à priorité égale, les règles que je rate le plus
    souvent passent devant.
Chaque fois qu'une règle devient vraie (front montant), une « occurrence »
est notée pour le bilan (« ce que j'aurais dû faire »), même si elle n'est pas affichée.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from fccoach.coach.rules import Rule

log = logging.getLogger(__name__)

_ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Name, ast.Load, ast.Constant, ast.List,
            ast.Tuple, ast.UnaryOp, ast.Not, ast.In, ast.NotIn, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_HABIT_SIGNAL = re.compile(r"(habit_\w+_count|opp_rush_on_carrier_count)")


class MissingSignal(Exception):
    pass


class Condition:
    """Expression de rules.yaml compilée en arbre sûr (aucun appel, aucun attribut)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.tree = ast.parse(text, mode="eval")
        for node in ast.walk(self.tree):
            if not isinstance(node, _ALLOWED):
                raise ValueError(f"élément interdit dans la condition : {type(node).__name__} ({text})")
        self.names = sorted({n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)})

    def evaluate(self, signals: dict[str, Any]) -> bool:
        return bool(self._eval(self.tree.body, signals))

    def _eval(self, n: ast.AST, s: dict[str, Any]) -> Any:
        if isinstance(n, ast.BoolOp):
            if isinstance(n.op, ast.And):
                return all(self._eval(v, s) for v in n.values)
            return any(self._eval(v, s) for v in n.values)
        if isinstance(n, ast.UnaryOp):
            return not self._eval(n.operand, s)
        if isinstance(n, ast.Name):
            if n.id in ("True", "False", "None"):
                return {"True": True, "False": False, "None": None}[n.id]
            v = s.get(n.id)
            if v is None:
                raise MissingSignal(n.id)
            return v
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, (ast.List, ast.Tuple)):
            return [self._eval(e, s) for e in n.elts]
        if isinstance(n, ast.Compare):
            left = self._eval(n.left, s)
            for op, comp in zip(n.ops, n.comparators):
                right = self._eval(comp, s)
                ok = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b, ast.Lt: lambda a, b: a < b,
                      ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
                      ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}[type(op)](left, right)
                if not ok:
                    return False
                left = right
            return True
        raise ValueError(type(n).__name__)


@dataclass
class Advice:
    rule_id: str
    text: str            # conseil + fiche citée
    conseil: str
    fiche: str
    source: int
    bouton: str | None
    priorite: int
    contexte: str
    t: float
    to_confirm: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "text": self.text, "conseil": self.conseil, "fiche": self.fiche,
                "source": self.source, "bouton": self.bouton, "priorite": self.priorite, "contexte": self.contexte,
                "t": round(self.t, 2), "to_confirm": self.to_confirm}


@dataclass
class Occurrence:
    rule_id: str
    t: float
    clock: str | None = None
    clip: str | None = None


@dataclass
class CoachConfig:
    min_interval_s: float = 20.0
    display_s: float = 30.0
    repeat_after_s: float = 90.0
    min_confidence: float = 0.70
    live: bool = True


@dataclass
class _RuleState:
    active: bool = False
    last_shown: float = -1e9
    occurrences: int = 0


class Coach:
    def __init__(self, rules: list[Rule], cfg: CoachConfig | None = None,
                 personal_weight: dict[str, float] | None = None) -> None:
        self.cfg = cfg or CoachConfig()
        self.rules = rules
        self.conditions = {r.id: Condition(r.declencheur.condition) for r in rules}
        self.personal = personal_weight or {}
        self._state: dict[str, _RuleState] = {r.id: _RuleState() for r in rules}
        self.current: Advice | None = None
        self._last_advice_t = -1e9
        self.occurrences: list[Occurrence] = []
        self.shown: list[Advice] = []
        self.skipped_missing: dict[str, int] = {}

    def gates(self, rule: Rule, team_conf: float, formation_conf: float) -> bool:
        d = rule.declencheur
        if d.depend_equipe and team_conf < self.cfg.min_confidence:
            return False
        if d.depend_formation and formation_conf < self.cfg.min_confidence:
            return False
        return True

    def matching(self, signals: dict[str, Any], team_conf: float, formation_conf: float) -> list[Rule]:
        out = []
        for r in self.rules:
            if not self.gates(r, team_conf, formation_conf):
                continue
            try:
                ok = self.conditions[r.id].evaluate(signals)
            except MissingSignal as m:
                self.skipped_missing[str(m)] = self.skipped_missing.get(str(m), 0) + 1
                ok = False
            except TypeError:
                ok = False
            if ok and r.declencheur.historique >= 2:
                ok = self._habit_count(r, signals) >= 2
            out.append(r) if ok else None
        return out

    def _habit_count(self, r: Rule, signals: dict[str, Any]) -> int:
        names = _HABIT_SIGNAL.findall(r.declencheur.condition)
        vals = [int(signals.get(n) or 0) for n in names]
        return max(vals) if vals else r.declencheur.historique

    def update(self, t: float, signals: dict[str, Any], team_conf: float, formation_conf: float,
               play_running: bool, clock: str | None = None) -> Advice | None:
        """À appeler à chaque pas d'analyse. Retourne un NOUVEAU conseil à afficher, sinon None."""
        matched = self.matching(signals, team_conf, formation_conf) if play_running else []
        ids = {r.id for r in matched}
        for r in self.rules:
            st = self._state[r.id]
            if r.id in ids and not st.active:
                st.occurrences += 1
                self.occurrences.append(Occurrence(r.id, t, clock))
            st.active = r.id in ids
        if self.current is not None and t - self.current.t > self.cfg.display_s:
            self.current = None
        if not (play_running and self.cfg.live and matched):
            return None
        if t - self._last_advice_t < self.cfg.min_interval_s:
            return None
        cands = [r for r in matched if t - self._state[r.id].last_shown >= self.cfg.repeat_after_s]
        if not cands:
            return None
        best = min(cands, key=lambda r: (r.priorite, -self.personal.get(r.id, 0.0), self._state[r.id].last_shown))
        to_confirm = best.declencheur.historique >= 2 and self._habit_count(best, signals) < 3
        text = best.affichage() + (" — à confirmer" if to_confirm else "")
        adv = Advice(best.id, text, best.conseil, best.fiche, best.source, best.bouton, best.priorite,
                     best.contexte, t, to_confirm)
        self._state[best.id].last_shown = t
        self._last_advice_t = t
        self.current = adv
        self.shown.append(adv)
        log.info("Conseil : %s", text)
        return adv

    def occurrence_counts(self) -> dict[str, int]:
        return {rid: st.occurrences for rid, st in self._state.items() if st.occurrences}
