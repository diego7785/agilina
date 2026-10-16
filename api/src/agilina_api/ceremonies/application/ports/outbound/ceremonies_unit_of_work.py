"""One transaction around a ceremonies command."""

from typing import Protocol

from agilina_api.ceremonies.application.ports.outbound.ceremony_repository import (
    CeremonyRepository,
)
from agilina_api.shared.application.ports import UnitOfWork


class CeremoniesUnitOfWork(UnitOfWork, Protocol):
    ceremonies: CeremonyRepository
