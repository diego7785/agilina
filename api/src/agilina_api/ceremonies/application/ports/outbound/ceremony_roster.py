"""Port to the teams context: the team, its active sprint and the sprint's participants."""

from typing import Protocol
from uuid import UUID

from agilina_api.ceremonies.application.dtos import RosterRecord


class CeremonyRoster(Protocol):
    """Ceremonies cannot import teams (AD-21), which owns teams and sprints, so it asks for
    them through this port; the composition root implements it."""

    async def roster_of(self, *, team_id: UUID, sprint_id: UUID) -> RosterRecord | None:
        """The roster of the team's active sprint when it is ``sprint_id``; ``None`` when the
        team has no active sprint or its active sprint is another one."""
        ...
