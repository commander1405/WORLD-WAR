"""World calendar unit tests (no external DB)."""
from datetime import date, datetime, timezone

from engine.world_engine import WorldEngine


class _DummyDB:
    pass


def test_year_advancement():
    eng = WorldEngine(_DummyDB(), game_start="2020-01-01", real_days_per_year=15)
    started = "2020-01-01T00:00:00+00:00"
    # 0 days
    assert eng.compute_game_date(started, "2020-01-01", 15, datetime(2020, 1, 1, tzinfo=timezone.utc)) == date(2020, 1, 1)
    # 14 days -> still 2020
    assert eng.compute_game_date(started, "2020-01-01", 15, datetime(2020, 1, 15, tzinfo=timezone.utc)) == date(2020, 1, 1)
    # 15 days -> 2021
    assert eng.compute_game_date(started, "2020-01-01", 15, datetime(2020, 1, 16, tzinfo=timezone.utc)) == date(2021, 1, 1)
    # 30 days -> 2022
    assert eng.compute_game_date(started, "2020-01-01", 15, datetime(2020, 1, 31, tzinfo=timezone.utc)) == date(2022, 1, 1)


def test_leap_year_safe():
    eng = WorldEngine(_DummyDB(), game_start="2020-02-29", real_days_per_year=15)
    started = "2020-02-29T00:00:00+00:00"
    # +1 year from Feb 29 2020 -> 2021-02-28
    d = eng.compute_game_date(started, "2020-02-29", 15, datetime(2020, 3, 15, tzinfo=timezone.utc))
    assert d == date(2021, 2, 28)
