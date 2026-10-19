"""The daily one may join is the first whose window to join has not closed (AGI-60)."""

from datetime import UTC, datetime, timedelta

from agilina_shared.sprint_calendar import joinable_daily_at

FIRST = datetime(2026, 10, 5, 14, 0, tzinfo=UTC)
OCCURRENCES = tuple(FIRST + timedelta(days=offset) for offset in range(3))


def test_before_the_first_daily_it_is_the_first():
    assert joinable_daily_at(OCCURRENCES, FIRST - timedelta(hours=1)) == FIRST


def test_a_daily_under_way_is_still_joinable_during_its_first_fifteen_minutes():
    late = FIRST + timedelta(minutes=14, seconds=59)

    assert joinable_daily_at(OCCURRENCES, late) == FIRST


def test_fifteen_minutes_after_it_started_it_is_the_one_of_the_next_day():
    assert joinable_daily_at(OCCURRENCES, FIRST + timedelta(minutes=15)) == OCCURRENCES[1]


def test_once_the_window_of_the_last_daily_closed_there_is_none():
    assert joinable_daily_at(OCCURRENCES, OCCURRENCES[-1] + timedelta(minutes=15)) is None


def test_without_occurrences_there_is_none():
    assert joinable_daily_at((), FIRST) is None
