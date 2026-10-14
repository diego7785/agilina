from agilina_api.shared.application.ports import Clock
from agilina_api.teams.application.dtos import ActiveSprintView
from agilina_api.teams.application.ports.outbound import SprintQueries
from agilina_api.teams.application.queries.get_active_sprint.get_active_sprint import (
    GetActiveSprint,
)
from agilina_api.teams.domain.sprint import DailyTime
from agilina_shared.sprint_calendar import daily_occurrences, next_daily_at, sprint_day_at


class GetActiveSprintHandler:
    """It does not check who asks: the route lets only the team's members get here.

    The day N of M and the next daily are computed at the instant the ``Clock`` gives, in
    the calendar of the daily's capture time zone, with the shared sprint calendar (AD-31):
    the API is the only authority on the schedule, and the web just formats what it gets.
    A team without an active sprint gets ``None``: it is a normal state, not an error.
    """

    def __init__(self, queries: SprintQueries, clock: Clock) -> None:
        self._queries = queries
        self._clock = clock

    async def handle(self, query: GetActiveSprint) -> ActiveSprintView | None:
        sprint = await self._queries.active_sprint_of(query.team_id)
        if sprint is None:
            return None
        now = self._clock.now()
        daily_time = DailyTime(at=sprint.daily_time, time_zone=sprint.time_zone)
        occurrences = daily_occurrences(
            start=sprint.start_date,
            end=sprint.end_date,
            local_time=daily_time.local_time,
            time_zone=daily_time.zone,
        )
        return ActiveSprintView(
            sprint=sprint,
            day=sprint_day_at(
                start=sprint.start_date, end=sprint.end_date, time_zone=daily_time.zone, now=now
            ),
            next_daily_at=next_daily_at(occurrences, now),
        )
