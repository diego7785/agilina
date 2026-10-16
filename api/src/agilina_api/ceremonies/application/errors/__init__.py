"""Errors of the ceremonies use cases."""

from agilina_api.ceremonies.application.errors.ceremony_not_found_error import (
    CeremonyNotFoundError,
)
from agilina_api.ceremonies.application.errors.result_of_another_ceremony_error import (
    ResultOfAnotherCeremonyError,
)

__all__ = [
    "CeremonyNotFoundError",
    "ResultOfAnotherCeremonyError",
]
