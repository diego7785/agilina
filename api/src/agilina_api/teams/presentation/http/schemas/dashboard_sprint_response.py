from datetime import date

from pydantic import BaseModel, Field

from agilina_api.teams.presentation.http.schemas.sprint_day_response import SprintDayResponse


class DashboardSprintResponse(BaseModel):
    number: int = Field(description='The sprint\'s number in its team (the 12 of "Sprint 12").')
    start_date: date = Field(description="First day of the sprint, a calendar date.")
    end_date: date = Field(description="Last day of the sprint, a calendar date, included.")
    day: SprintDayResponse
