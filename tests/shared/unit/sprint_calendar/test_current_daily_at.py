"""The current daily is the occurrence whose window to join holds the instant: from 10 minutes
before it starts to an hour after (AGI-59)."""

from datetime import UTC, datetime, timedelta

from agilina_shared.sprint_calendar import DAILY_JOIN_GRACE, JOIN_WINDOW_LEAD, current_daily_at

TODAY = datetime(2026, 10, 5, 14, 0, tzinfo=UTC)
OCCURRENCES = tuple(TODAY + timedelta(days=offset) for offset in range(3))


def test_the_grace_for_who_arrives_late_is_one_hour():
    assert DAILY_JOIN_GRACE == timedelta(hours=1)


def test_before_the_window_opens_there_is_none():
    now = TODAY - JOIN_WINDOW_LEAD - timedelta(microseconds=1)

    assert current_daily_at(OCCURRENCES, now) is None


def test_right_when_the_window_opens_it_is_the_daily_of_today():
    assert current_daily_at(OCCURRENCES, TODAY - JOIN_WINDOW_LEAD) == TODAY


def test_after_the_start_and_within_the_grace_it_is_still_the_daily_of_today():
    now = TODAY + DAILY_JOIN_GRACE - timedelta(microseconds=1)

    assert current_daily_at(OCCURRENCES, now) == TODAY


def test_once_the_grace_is_over_there_is_none():
    assert current_daily_at(OCCURRENCES, TODAY + DAILY_JOIN_GRACE) is None


def test_with_several_occurrences_it_is_the_one_of_today_and_not_of_tomorrow():
    tomorrow = OCCURRENCES[1]

    assert current_daily_at(OCCURRENCES, TODAY + timedelta(minutes=5)) == TODAY
    assert current_daily_at(OCCURRENCES, tomorrow) == tomorrow


def test_without_occurrences_there_is_none():
    assert current_daily_at((), TODAY) is None
