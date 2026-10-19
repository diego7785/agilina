"""The room still takes participants until 15 minutes after the ceremony starts (AGI-60)."""

from datetime import UTC, datetime, timedelta

from agilina_shared.sprint_calendar import JOIN_WINDOW_TAIL, join_closes_at


def test_the_window_tail_is_fifteen_minutes():
    assert JOIN_WINDOW_TAIL == timedelta(minutes=15)


def test_it_closes_fifteen_minutes_after_the_start():
    starts_at = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)

    assert join_closes_at(starts_at) == datetime(2026, 10, 12, 14, 15, tzinfo=UTC)


def test_it_may_close_on_the_day_after():
    starts_at = datetime(2026, 10, 12, 23, 50, tzinfo=UTC)

    assert join_closes_at(starts_at) == datetime(2026, 10, 13, 0, 5, tzinfo=UTC)
