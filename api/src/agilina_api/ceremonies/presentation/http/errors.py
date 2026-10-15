"""The ceremonies errors and the HTTP response each one becomes.

``CeremoniesErrors`` is the catalog; ``CEREMONIES_ERRORS`` pairs each exception with an entry,
and the composition root registers it in ``shared.presentation.http.error_handlers``.
"""

from agilina_api.ceremonies.application.errors import CeremonyNotFoundError
from agilina_api.shared.presentation.http.api_error import ApiError
from agilina_api.shared.presentation.http.error_handlers import ErrorMapping


class CeremoniesErrors:
    CEREMONY_NOT_FOUND = ApiError(404, "ceremony_not_found", "The ceremony does not exist.")


CEREMONIES_ERRORS: tuple[ErrorMapping, ...] = (
    ErrorMapping(CeremonyNotFoundError, CeremoniesErrors.CEREMONY_NOT_FOUND),
)
