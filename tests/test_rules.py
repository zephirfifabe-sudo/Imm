from pathlib import Path

import pytest

from fccoach.coach.rules import MAX_MOTS, load_rules, word_count

RULES = Path(__file__).resolve().parents[1] / "knowledge" / "rules.yaml"


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES)


def test_pdf_present():
    assert (RULES.parent / "paastek.pdf").stat().st_size > 1_000_000


def test_all_eleven_fiches_covered(rules):
    assert {r.source for r in rules} == set(range(1, 12))


def test_conseils_short_and_cited(rules):
    for r in rules:
        assert word_count(r.conseil) <= MAX_MOTS, r.id
        assert f"fiche {r.source}" in r.affichage()


@pytest.mark.parametrize("conseil,source", [
    ("Fais tourner : 4 milieux contre 2", 6),
    ("Pas d'axe : balance L1+△ avec un joueur lancé de loin", 7),
    ("Porte le ballon", 1),
    ("Quadrille, reforme le bloc", 9),
    ("Ramène ton DC", 3),
    ("MDC dans l'axe, ne le dézone pas", 8),
    ("Joue en arrière, puis profondeur dans son dos", 2),
    ("R1 sur l'attaquant pour le décrocher", 11),
    ("Sors par le latéral, une touche côté, reviens", 4),
    ("Il a lâché son DC : va tout droit en R2", 10),
    ("Ton attaquant est déjà parti : un temps d'avance", 11),
    ("Joue à l'inverse du curseur", 1),
    ("Il est dézoné : attaque son côté", 8),
    ("Il réagit trop tard : prends l'espace", 2),
])
def test_priority_rules_present(rules, conseil, source):
    match = [r for r in rules if r.conseil == conseil]
    assert match, conseil
    assert match[0].source == source


def test_habits_need_history(rules):
    for r in rules:
        if r.id.startswith("habitude_"):
            assert r.declencheur.historique >= 2
