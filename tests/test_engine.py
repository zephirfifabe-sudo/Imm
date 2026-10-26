import pytest

from fccoach.coach.engine import Coach, CoachConfig, Condition, MissingSignal
from fccoach.coach.rules import load_rules

RULES = load_rules("knowledge/rules.yaml")


def test_all_conditions_compile():
    for r in RULES:
        Condition(r.declencheur.condition)


@pytest.mark.parametrize("bad", ["__import__('os')", "a.b", "f(1)", "x[0]", "lambda: 1"])
def test_condition_is_sandboxed(bad):
    with pytest.raises((ValueError, SyntaxError)):
        Condition(bad)


def test_missing_signal_skips():
    c = Condition("a and b > 2")
    with pytest.raises(MissingSignal):
        c.evaluate({"a": True})
    assert c.evaluate({"a": True, "b": 3})
    assert not Condition("x in ['4312','41212']").evaluate({"x": "4213"})


def rule(rid):
    return [r for r in RULES if r.id == rid]


def test_one_advice_with_interval_and_citation():
    coach = Coach(RULES, CoachConfig(min_interval_s=20, repeat_after_s=90))
    sig = {"my_possession": True, "space_ahead_m": 15, "passes_without_progress": 3}
    a = coach.update(100.0, sig, 0.9, 0.0, play_running=True)
    assert a is not None and a.rule_id == "porte_le_ballon"
    assert "fiche 1" in a.text
    assert coach.update(105.0, sig, 0.9, 0.0, True) is None          # < 20 s
    assert coach.update(130.0, sig, 0.9, 0.0, True) is None          # même règle avant 90 s


def test_no_advice_when_team_unsure_or_not_running():
    coach = Coach(RULES)
    sig = {"my_possession": True, "space_ahead_m": 15, "passes_without_progress": 3}
    assert coach.update(10.0, sig, 0.6, 1.0, True) is None           # équipe < 70 %
    assert coach.update(40.0, sig, 0.9, 1.0, False) is None          # engagement / pause
    assert coach.update(70.0, sig, 0.9, 1.0, True) is not None


def test_formation_rule_needs_formation_confidence():
    coach = Coach(rule("ligne_du_10_fais_tourner"))
    sig = {"my_formation": "41212", "opp_formation": "4213", "my_possession": True, "ball_behind_opp_line10": True}
    assert coach.update(0.0, sig, 0.9, 0.5, True) is None
    a = coach.update(30.0, sig, 0.9, 0.8, True)
    assert a.conseil == "Fais tourner : 4 milieux contre 2" and a.source == 6


def test_habit_to_confirm_then_installed():
    coach = Coach(rule("habitude_ramene_milieux"), CoachConfig(repeat_after_s=0))
    sig = {"my_possession": True, "habit_midfield_only_count": 1}
    assert coach.update(0.0, sig, 0.9, 0.0, True) is None
    sig["habit_midfield_only_count"] = 2
    a = coach.update(30.0, sig, 0.9, 0.0, True)
    assert a.to_confirm and "à confirmer" in a.text
    sig["habit_midfield_only_count"] = 3
    a = coach.update(60.0, sig, 0.9, 0.0, True)
    assert not a.to_confirm


def test_occurrences_on_rising_edge_even_if_not_shown():
    coach = Coach(rule("ramene_ton_dc"))
    on = {"my_possession": False, "my_dc_out_of_line_m": 15}
    off = {"my_possession": False, "my_dc_out_of_line_m": 2}
    for t, s in [(0, on), (1, on), (2, off), (3, on)]:
        coach.update(float(t), s, 0.9, 0.0, True)
    assert coach.occurrence_counts() == {"ramene_ton_dc": 2}
    assert len(coach.shown) == 1


def test_personal_weight_breaks_ties():
    rs = rule("ramene_ton_dc") + rule("mdc_dans_axe")
    sig = {"my_possession": False, "my_dc_out_of_line_m": 15, "my_mdc_off_axis_m": 20}
    assert Coach(rs).update(0.0, sig, 0.9, 0.9, True).rule_id == "ramene_ton_dc"
    assert Coach(rs, personal_weight={"mdc_dans_axe": 3.0}).update(0.0, sig, 0.9, 0.9, True).rule_id == "mdc_dans_axe"
