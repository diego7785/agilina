"""Errors of the ceremonies use cases."""

from agilina_api.ceremonies.application.errors.ceremony_not_found_error import (
    CeremonyNotFoundError,
)
from agilina_api.ceremonies.application.errors.result_of_another_ceremony_error import (
    ResultOfAnotherCeremonyError,
)
from agilina_api.ceremonies.application.errors.room_service_unavailable_error import (
    RoomServiceUnavailableError,
)

__all__ = [
    "CeremonyNotFoundError",
    "ResultOfAnotherCeremonyError",
    "RoomServiceUnavailableError",
]
