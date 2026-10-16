"""Errors of the ceremonies domain."""

from agilina_api.ceremonies.domain.errors.not_a_participant_error import NotAParticipantError
from agilina_api.ceremonies.domain.errors.result_already_received_error import (
    ResultAlreadyReceivedError,
)

__all__ = [
    "NotAParticipantError",
    "ResultAlreadyReceivedError",
]
