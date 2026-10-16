"""Read side of the ceremonies (CQRS): a ceremony as it is stored, with no aggregate."""

from typing import Protocol
from uuid import UUID

from agilina_api.ceremonies.application.dtos import CeremonyRecord


class CeremonyQueries(Protocol):
    async def ceremony_of(self, ceremony_id: UUID) -> CeremonyRecord | None:
        """The ceremony, or ``None`` if it does not exist.

        The one read keyed by the ceremony instead of the team: the worker knows only the
        ceremony (from the room's name), so this is where its team is found out. Every read
        after it is about that team.
        """
        ...
