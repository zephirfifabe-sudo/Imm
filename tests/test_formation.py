import numpy as np
import pytest

from fccoach.analysis.formation import TEMPLATES, FormationTracker
from fccoach.analysis.world import PlayerState


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_each_formation_recognized_with_partial_view(name):
    """8 joueurs visibles sur 10, bloc qui coulisse, ±3 m de bruit."""
    rng = np.random.default_rng(abs(hash(name)) % 1000)
    tpl = TEMPLATES[name]
    ft = FormationTracker()
    for _ in range(20):
        idx = rng.choice(10, 8, replace=False)
        off = rng.uniform(-10, 10)
        est = ft.observe([PlayerState(int(i), "me", tpl[i][0] + off + rng.normal(0, 3), tpl[i][1] + rng.normal(0, 3))
                          for i in idx])
    assert est.name == name and est.confidence >= 0.7


def test_unreadable_shape_gives_no_formation():
    rng = np.random.default_rng(0)
    ft = FormationTracker()
    for _ in range(30):
        est = ft.observe([PlayerState(i, "me", rng.uniform(-45, 30), rng.uniform(-30, 30)) for i in range(10)])
    assert est.confidence < 0.7


def test_too_few_players_no_estimate():
    ft = FormationTracker()
    assert ft.observe([PlayerState(i, "me", -30.0 + i, 0.0) for i in range(5)]).name is None
