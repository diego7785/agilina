"""GetActiveSprint: the team's active sprint with its day N of M and its next daily, computed
at the clock's instant in the calendar of the daily's capture time zone (HU-07, AD-31).

The sprint of most cases runs from Monday 2026-10-05 to Friday 2026-10-16 (M = 12: every
calendar day counts) with the daily at 09:00 in America/Bogota, that is 14:00 UTC.
"""

from datetime import UTC, date, datetime

import pytest

from agilina_api.teams.application.dtos import ActiveSprintRecord
from agilina_api.teams.application.queries.get_active_sprint import (
    GetActiveSprint,
    GetActiveSprintHandler,
)
from agilina_shared.sprint_calendar import SprintDay, SprintPhase
from tests.api.builders import NOW, SprintBuilder, next_id
from tests.api.doubles import FakeClock, FakeSprintQueries


def _at(day: int, hour: int, minute: int = 0, month: int = 10, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class Scenario:
    def __init__(self) -> None:
        self.team_id = next_id()
        self.queries = FakeSprintQueries()
        self.clock = FakeClock()
        self.handler = GetActiveSprintHandler(self.queries, self.clock)

    async def a_sprint(self, builder: SprintBuilder | None = None):
        builder = builder or SprintBuilder()
        return await builder.for_team_id(self.team_id).saved_in(self.queries.repository)

    async def at(self, instant: datetime):
        self.clock.current = instant
        return await self.handler.handle(GetActiveSprint(team_id=self.team_id))


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


async def test_a_team_without_an_active_sprint_gets_none(scenario):
    await scenario.a_sprint(SprintBuilder().closed())

    assert await scenario.at(NOW) is None


async def test_the_view_carries_the_sprint_as_it_is_stored(scenario):
    ana, bruno = next_id(), next_id()
    sprint = await scenario.a_sprint(SprintBuilder().with_participants(bruno, ana))

    view = await scenario.at(NOW)

    assert view is not None
    assert view.sprint == ActiveSprintRecord(
        sprint_id=sprint.id,
        number=1,
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 16),
        daily_time=_at(5, 14),
        time_zone="America/Bogota",
        participants=(bruno, ana),
    )


async def test_the_day_before_the_start_it_has_not_started_and_the_next_daily_is_the_first(
    scenario,
):
    await scenario.a_sprint()

    view = await scenario.at(NOW)  # Sunday 2026-10-04, 07:00 in Bogota

    assert view is not None
    assert view.day == SprintDay(number=0, total=12, phase=SprintPhase.NOT_STARTED)
    assert view.next_daily_at == _at(5, 14)


@pytest.mark.parametrize(
    ("now", "number", "next_daily"),
    [
        (_at(5, 5, 0), 1, _at(5, 14)),  # the first day, 00:00 in Bogota
        (_at(10, 13), 6, _at(10, 14)),  # Saturday counts like any day
        (_at(10, 14), 6, _at(10, 14)),  # the daily that is starting right now is the next one
        (_at(10, 14, 1), 6, _at(11, 14)),  # once it started, the next is Sunday's
        (_at(11, 20), 7, _at(12, 14)),  # Sunday
        (_at(16, 13), 12, _at(16, 14)),  # the last day, before its daily
    ],
)
async def test_while_in_progress_the_day_and_the_next_daily_follow_the_calendar(
    scenario, now, number, next_daily
):
    await scenario.a_sprint()

    view = await scenario.at(now)

    assert view is not None
    assert view.day == SprintDay(number=number, total=12, phase=SprintPhase.IN_PROGRESS)
    assert view.next_daily_at == next_daily


@pytest.mark.parametrize(
    ("now", "next_daily", "joinable"),
    [
        (_at(10, 13), _at(10, 14), _at(10, 14)),  # before the daily, both are today's
        (_at(10, 14, 14), _at(11, 14), _at(10, 14)),  # late: today's is still joinable
        (_at(10, 14, 15), _at(11, 14), _at(11, 14)),  # its window closed: tomorrow's
        (_at(16, 14, 10), None, _at(16, 14)),  # the last daily, under way
        (_at(16, 14, 15), None, None),  # the window of the last daily closed
    ],
)
async def test_the_joinable_daily_stays_the_one_under_way_until_its_window_closes(
    scenario, now, next_daily, joinable
):
    await scenario.a_sprint()

    view = await scenario.at(now)

    assert view is not None
    assert view.next_daily_at == next_daily
    assert view.joinable_daily_at == joinable


async def test_once_the_last_daily_started_there_is_no_next_one(scenario):
    await scenario.a_sprint()

    view = await scenario.at(_at(16, 15))

    assert view is not None
    assert view.day == SprintDay(number=12, total=12, phase=SprintPhase.IN_PROGRESS)
    assert view.next_daily_at is None


async def test_after_the_last_day_it_is_finished_and_still_answers_until_it_is_closed(scenario):
    await scenario.a_sprint()

    view = await scenario.at(_at(17, 5, 0))  # Saturday 2026-10-17, 00:00 in Bogota

    assert view is not None
    assert view.day == SprintDay(number=12, total=12, phase=SprintPhase.FINISHED)
    assert view.next_daily_at is None


async def test_the_calendar_is_the_capture_time_zone_not_utc(scenario):
    """08:00 in Tokyo is 23:00 UTC of the day before. At 23:30 UTC on 2026-10-04 it is
    already Monday 2026-10-05 in Tokyo: the first day, and its daily has already started."""
    await scenario.a_sprint(SprintBuilder().with_daily_time(_at(4, 23), "Asia/Tokyo"))

    before = await scenario.at(_at(4, 14))  # 23:00 on Sunday in Tokyo
    first_day = await scenario.at(_at(4, 23, 30))

    assert before is not None and first_day is not None
    assert before.day == SprintDay(number=0, total=12, phase=SprintPhase.NOT_STARTED)
    assert before.next_daily_at == _at(4, 23)
    assert first_day.day == SprintDay(number=1, total=12, phase=SprintPhase.IN_PROGRESS)
    assert first_day.next_daily_at == _at(5, 23)


async def test_the_next_daily_keeps_its_wall_clock_time_across_a_daylight_saving_change(
    scenario,
):
    """09:00 in New York is 14:00 UTC before 2027-03-14 and 13:00 UTC from that day on."""
    await scenario.a_sprint(
        SprintBuilder()
        .with_period(date(2027, 3, 8), date(2027, 3, 19))
        .with_daily_time(_at(8, 14, month=3, year=2027), "America/New_York")
    )

    view = await scenario.at(_at(13, 15, month=3, year=2027))  # after Saturday's daily

    assert view is not None
    assert view.day == SprintDay(number=6, total=12, phase=SprintPhase.IN_PROGRESS)
    assert view.next_daily_at == _at(14, 13, month=3, year=2027)
