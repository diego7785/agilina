from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from agilina_api.teams.presentation.http.schemas.daily_participant_response import (
    DailyParticipantResponse,
)
from agilina_api.teams.presentation.http.schemas.sprint_day_response import SprintDayResponse


class ActiveSprintResponse(BaseModel):
    id: UUID
    number: int = Field(
        description=(
            "The sprint's number in its team (the 12 of \"Sprint 12\"): 1 for the team's first "
            "sprint, then the highest the team has had plus one. The API assigns it when the "
            "sprint is saved and it never changes; it is not the day of the sprint (`day`)."
        )
    )
    start_date: date
    end_date: date
    daily_time: datetime = Field(
        description=(
            "The daily's anchor instant, in UTC. Its wall-clock time in `time_zone` is the "
            "daily's time; to show when the next daily is, use `next_daily_at`."
        )
    )
    time_zone: str = Field(description="The IANA time zone the daily's time was captured in.")
    next_daily_at: datetime | None = Field(
        description=(
            "The next daily, in UTC, computed by the API (daylight saving included); `null` "
            "once the sprint's last daily has started."
        )
    )
    participants: list[DailyParticipantResponse] = Field(
        description="The daily's participants, in turn order."
    )
    day: SprintDayResponse
