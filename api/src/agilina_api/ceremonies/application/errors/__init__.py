"""Errors of the ceremonies use cases."""

from agilina_api.ceremonies.application.errors.ceremony_not_found_error import (
    CeremonyNotFoundError,
)
from agilina_api.ceremonies.application.errors.daily_not_open_error import DailyNotOpenError
from agilina_api.ceremonies.application.errors.no_active_sprint_error import NoActiveSprintError
from agilina_api.ceremonies.application.errors.not_a_daily_participant_error import (
    NotADailyParticipantError,
)
from agilina_api.ceremonies.application.errors.result_of_another_ceremony_error import (
    ResultOfAnotherCeremonyError,
)
from agilina_api.ceremonies.application.errors.room_service_unavailable_error import (
    RoomServiceUnavailableError,
)

__all__ = [
    "CeremonyNotFoundError",
    "DailyNotOpenError",
    "NoActiveSprintError",
    "NotADailyParticipantError",
    "ResultOfAnotherCeremonyError",
    "RoomServiceUnavailableError",
]
