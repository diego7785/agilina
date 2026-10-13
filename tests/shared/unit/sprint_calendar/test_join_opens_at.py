"""The room opens to the participants 10 minutes before the ceremony starts."""

from datetime import UTC, datetime, timedelta

from agilina_shared.sprint_calendar import JOIN_WINDOW_LEAD, join_opens_at


def test_the_window_lead_is_ten_minutes():
    assert JOIN_WINDOW_LEAD == timedelta(minutes=10)


def test_it_opens_ten_minutes_before_the_start():
    starts_at = datetime(2026, 10, 12, 14, 15, tzinfo=UTC)

    assert join_opens_at(starts_at) == datetime(2026, 10, 12, 14, 5, tzinfo=UTC)


def test_it_may_open_on_the_day_before():
    starts_at = datetime(2026, 10, 12, 0, 5, tzinfo=UTC)

    assert join_opens_at(starts_at) == datetime(2026, 10, 11, 23, 55, tzinfo=UTC)
