"""Chargement et consultation de la base de connaissances.

Deux couches :
  - THÉORIE  : knowledge/*.yaml (versionnés dans Git), chaque entrée sourcée, datée, avec fiabilité et statut ;
  - OBSERVÉ  : data/knowledge_observed.json, écrit par knowledge/verify.py à partir des prix relevés par le bot.

La base est en LECTURE SEULE pour le cerveau : elle explique et contextualise, elle ne pilote aucune décision
tant que ses hypothèses ne sont pas confirmées par les données (voir docs/BILAN_ETAPE1.md).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

import config

DIR = Path(__file__).parent
STATUTS = ("confirme", "probable", "hypothese", "a_verifier", "obsolete")
SOURCE_TYPES = ("officiel_ea", "guide_communautaire", "tracker", "fuite", "consensus_historique", "observe")
REQUIRED = ("id", "cle", "niveau", "titre", "contenu", "version_jeu", "sources", "fiabilite", "statut", "verifie_le")
STATUT_LABEL = {"confirme": "confirmé", "probable": "probable", "hypothese": "hypothèse",
                "a_verifier": "à vérifier", "obsolete": "obsolète"}


def observed_path() -> Path:
    return config.DATA_DIR / "knowledge_observed.json"


def _as_date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


class KnowledgeService:
    def __init__(self, directory: Path = DIR):
        self.files: dict[str, dict] = {}
        self.entries: dict[str, dict] = {}
        self.events: list[dict] = []
        for path in sorted(directory.glob("*.yaml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            self.files[path.name] = doc
            for e in doc.get("entrees") or []:
                self.entries[e["cle"]] = {**e, "categorie": doc.get("categorie"), "fichier": path.name}
            for ev in doc.get("evenements") or []:
                self.events.append({**ev, "debut": _as_date(ev["debut"]), "fin": _as_date(ev.get("fin"))})
        self.events.sort(key=lambda e: e["debut"])

    # ------------------------------------------------------------------ consultation
    def get(self, cle: str) -> dict | None:
        return self.entries.get(cle)

    def data(self, cle: str, champ: str, default=None):
        return ((self.get(cle) or {}).get("donnees") or {}).get(champ, default)

    def by_category(self, categorie: str) -> list[dict]:
        return [e for e in self.entries.values() if e["categorie"] == categorie]

    def active(self, niveau: int | None = None) -> list[dict]:
        return [e for e in self.entries.values() if e["statut"] != "obsolete" and (niveau is None or e["niveau"] == niveau)]

    def testable(self) -> list[dict]:
        return [e for e in self.active() if e.get("test")]

    def event(self, cle: str) -> dict | None:
        return next((e for e in self.events if e["cle"] == cle), None)

    def upcoming(self, now: datetime | None = None, days: int = 10) -> list[dict]:
        """Événements qui commencent dans les `days` prochains jours (ou en cours)."""
        today = (now or datetime.now()).date()
        out = []
        for e in self.events:
            end = e.get("fin") or e["debut"]
            if e["debut"] <= today + timedelta(days=days) and end >= today:
                out.append({**e, "dans_j": (e["debut"] - today).days})
        return out

    def observed(self) -> dict:
        try:
            return json.loads(observed_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------------ textes
    def event_line(self, e: dict) -> str:
        lbl = STATUT_LABEL.get(e["statut"], e["statut"])
        when = "en cours" if e["dans_j"] <= 0 else "demain" if e["dans_j"] == 1 else f"dans {e['dans_j']} j"
        return f"{e['nom']} ({e['debut']:%d/%m}, {when}) — {lbl}"

    def upcoming_text(self, now: datetime | None = None, days: int = 10) -> list[str]:
        return [self.event_line(e) for e in self.upcoming(now, days) if e.get("type") != "saison"]

    # ------------------------------------------------------------------ validation
    def validate(self) -> list[str]:
        errors = []
        ids = set()
        for e in self.entries.values():
            where = f"{e.get('fichier')}:{e.get('cle')}"
            for f in REQUIRED:
                if e.get(f) in (None, ""):
                    errors.append(f"{where} : champ « {f} » manquant")
            if e.get("id") in ids:
                errors.append(f"{where} : id en double {e['id']}")
            ids.add(e.get("id"))
            if e.get("statut") not in STATUTS:
                errors.append(f"{where} : statut inconnu « {e.get('statut')} »")
            if not 1 <= int(e.get("fiabilite") or 0) <= 5:
                errors.append(f"{where} : fiabilité hors 1-5")
            for s in e.get("sources") or []:
                if s.get("type") not in SOURCE_TYPES:
                    errors.append(f"{where} : type de source inconnu « {s.get('type')} »")
                if s.get("type") != "consensus_historique" and not s.get("url"):
                    errors.append(f"{where} : source sans URL")
            if e.get("statut") == "confirme" and int(e.get("fiabilite") or 0) < 4:
                errors.append(f"{where} : « confirmé » exige une fiabilité >= 4")
            t = e.get("test")
            if t:
                if t.get("type") not in ("comparaison_jours", "fenetre_hebdo", "evenement"):
                    errors.append(f"{where} : type de test inconnu")
                if t.get("type") == "evenement" and not self.event(t.get("evenement")):
                    errors.append(f"{where} : événement « {t.get('evenement')} » absent du calendrier")
        for ev in self.events:
            if ev.get("statut") not in STATUTS:
                errors.append(f"calendrier:{ev.get('cle')} : statut inconnu")
            if not ev.get("source"):
                errors.append(f"calendrier:{ev.get('cle')} : source manquante")
        return errors


@lru_cache(maxsize=1)
def get_service() -> KnowledgeService:
    return KnowledgeService()
