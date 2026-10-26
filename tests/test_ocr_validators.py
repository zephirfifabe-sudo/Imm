from fccoach.ocr.validators import ClockValidator, ScoreValidator, TextVoteValidator, parse_clock, parse_score


def test_parse():
    assert parse_clock("45:07") == 2707
    assert parse_clock("O5:3O") == 330      # O lu à la place de 0
    assert parse_clock("bruit") is None
    assert parse_score("2 - 1") == (2, 1)
    assert parse_score("1:O") == (1, 0)


def test_clock_never_goes_back():
    v = ClockValidator()
    assert v.feed("10:00", now=0) == 600
    assert v.feed("09:58", now=1) == 600      # recul ignoré
    assert v.feed("10:07", now=1) == 607
    assert v.rejected == 1


def test_clock_second_half_restarts_at_45():
    v = ClockValidator()
    v.feed("44:50", now=0)
    v.feed("46:30", now=15)                    # temps additionnel
    assert v.feed("45:00", now=200) == 2700    # reprise de la 2e mi-temps
    assert v.period_started == 2700
    assert v.feed("45:00", now=201) == 2700
    assert v.feed("44:00", now=202) == 2700    # vrai recul : ignoré


def test_clock_rejects_absurd_jump():
    v = ClockValidator()
    v.feed("10:00", now=0)
    assert v.feed("80:00", now=1) == 600       # +70 min en 1 s : mauvaise lecture
    assert v.feed("10:10", now=2) == 610


def test_score_plus_one_confirmed():
    v = ScoreValidator(confirm=2)
    assert v.feed("0-0") == ((0, 0), False)
    assert v.feed("1-0") == ((0, 0), False)    # à confirmer
    assert v.feed("1-0") == ((1, 0), True)     # but confirmé
    assert v.feed("3-0") == ((1, 0), False)    # +2 : incohérent
    assert v.feed("0-0") == ((1, 0), False)    # recul : incohérent
    assert v.feed("2-1") == ((1, 0), False)    # deux côtés à la fois
    assert v.rejected == 3


def test_score_resume_mid_match():
    v = ScoreValidator(confirm=2)
    for _ in range(2):
        v.feed("2-1")
    assert not v.initialized
    v.feed("2-1")
    assert v.value == (2, 1)


def test_name_vote():
    v = TextVoteValidator()
    v.feed("MBAPPE")
    assert v.value is None
    v.feed("MBAPP3")
    v.feed("MBAPPE")
    assert v.value == "MBAPPE"
