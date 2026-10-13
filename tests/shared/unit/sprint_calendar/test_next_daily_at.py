"""The next daily is the first occurrence at or after the current instant (AD-31)."""

from datetime import UTC, datetime, timedelta

from agilina_shared.sprint_calendar import next_daily_at

FIRST = datetime(2026, 10, 5, 14, 0, tzinfo=UTC)
OCCURRENCES = tuple(FIRST + timedelta(days=offset) for offset in range(3))


def test_before_the_first_daily_it_is_the_first():
    assert next_daily_at(OCCURRENCES, FIRST - timedelta(hours=1)) == FIRST


def test_the_daily_starting_right_now_is_still_the_next_one():
    assert next_daily_at(OCCURRENCES, FIRST) == FIRST


def test_one_instant_after_a_daily_started_it_is_the_one_of_the_next_day():
    assert next_daily_at(OCCURRENCES, FIRST + timedelta(microseconds=1)) == OCCURRENCES[1]


def test_after_the_last_daily_there_is_none():
    assert next_daily_at(OCCURRENCES, OCCURRENCES[-1] + timedelta(minutes=1)) is None


def test_without_occurrences_there_is_none():
    assert next_daily_at((), FIRST) is None
