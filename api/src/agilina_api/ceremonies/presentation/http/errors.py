"""The ceremonies errors and the HTTP response each one becomes.

``CeremoniesErrors`` is the catalog; ``CEREMONIES_ERRORS`` pairs each exception with an entry,
and the composition root registers it in ``shared.presentation.http.error_handlers``. A result
attributed to someone who is not a participant, or delivered to another ceremony, is a
``validation_error`` that says where, in the format of every other one, never the value.
"""

from collections.abc import Mapping
from typing import Any, cast

from agilina_api.ceremonies.application.errors import (
    CeremonyNotFoundError,
    ResultOfAnotherCeremonyError,
)
from agilina_api.ceremonies.domain.errors import NotAParticipantError, ResultAlreadyReceivedError
from agilina_api.shared.presentation.http.api_error import ApiError, SharedErrors
from agilina_api.shared.presentation.http.error_handlers import ErrorMapping


class CeremoniesErrors:
    CEREMONY_NOT_FOUND = ApiError(404, "ceremony_not_found", "The ceremony does not exist.")
    RESULT_ALREADY_RECEIVED = ApiError(
        409, "result_already_received", "The ceremony already has another result."
    )


def _not_a_participant_details(error: Exception) -> Mapping[str, Any]:
    # The mapping below registers it only for NotAParticipantError.
    fields = cast(NotAParticipantError, error).fields
    return {
        "fields": [{"field": f"body.{field}", "reason": "not_a_participant"} for field in fields]
    }


def _another_ceremony_details(_: Exception) -> Mapping[str, Any]:
    return {"fields": [{"field": "body.ceremony_id", "reason": "does_not_match_path"}]}


CEREMONIES_ERRORS: tuple[ErrorMapping, ...] = (
    ErrorMapping(CeremonyNotFoundError, CeremoniesErrors.CEREMONY_NOT_FOUND),
    ErrorMapping(ResultAlreadyReceivedError, CeremoniesErrors.RESULT_ALREADY_RECEIVED),
    ErrorMapping(NotAParticipantError, SharedErrors.VALIDATION, details=_not_a_participant_details),
    ErrorMapping(
        ResultOfAnotherCeremonyError, SharedErrors.VALIDATION, details=_another_ceremony_details
    ),
)
