"""Chargement et validation de knowledge/rules.yaml (source de vérité tactique).

Le moteur de conseils (Phase 4) n'affichera QUE des conseils issus de ce
fichier, chacun citant sa fiche. Ce module vérifie dès maintenant que le
fichier respecte le format attendu.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONTEXTES = {"attaque", "defense", "relance", "perte", "adversaire"}
MAX_MOTS = 15


@dataclass(frozen=True)
class Declencheur:
    description: str
    condition: str
    historique: int = 0
    depend_equipe: bool = True
    depend_formation: bool = False


@dataclass(frozen=True)
class Rule:
    id: str
    fiche: str
    contexte: str
    declencheur: Declencheur
    conseil: str
    bouton: str | None
    priorite: int
    source: int

    def affichage(self) -> str:
        """Texte affiché : conseil + citation de la fiche."""
        txt = self.conseil
        if self.bouton:
            txt += f" (bouton suggéré : {self.bouton})"
        return f"{txt} — fiche {self.source} « {self.fiche} »"


class RulesError(ValueError):
    pass


def word_count(text: str) -> int:
    return len([w for w in text.replace(":", " ").split() if any(c.isalnum() for c in w)])


def load_rules(path: str | Path) -> list[Rule]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    fiches: dict[int, str] = {int(k): v for k, v in raw.get("fiches", {}).items()}
    rules: list[Rule] = []
    seen: set[str] = set()
    for r in raw.get("rules", []):
        rid = r.get("id")
        if not rid or rid in seen:
            raise RulesError(f"id manquant ou dupliqué : {rid}")
        seen.add(rid)
        if r["contexte"] not in CONTEXTES:
            raise RulesError(f"{rid} : contexte invalide {r['contexte']}")
        if not 1 <= int(r["priorite"]) <= 3:
            raise RulesError(f"{rid} : priorité hors 1-3")
        src = int(r["source"])
        if src not in fiches:
            raise RulesError(f"{rid} : fiche source {src} inconnue")
        if fiches[src] != r["fiche"]:
            raise RulesError(f"{rid} : fiche « {r['fiche']} » ne correspond pas à la source {src} « {fiches[src]} »")
        if word_count(r["conseil"]) > MAX_MOTS:
            raise RulesError(f"{rid} : conseil de plus de {MAX_MOTS} mots")
        d = r["declencheur"]
        rules.append(Rule(
            id=rid, fiche=r["fiche"], contexte=r["contexte"],
            declencheur=Declencheur(d["description"], d["condition"], int(d.get("historique", 0)),
                                    bool(d.get("depend_equipe", True)), bool(d.get("depend_formation", False))),
            conseil=r["conseil"], bouton=r.get("bouton"), priorite=int(r["priorite"]), source=src,
        ))
    return rules
