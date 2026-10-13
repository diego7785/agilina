from typing import Protocol
from uuid import UUID

from agilina_api.teams.domain.sprint import Sprint


class SprintRepository(Protocol):
    async def add(self, sprint: Sprint) -> None:
        """Store a new sprint with its participants."""
        ...

    async def next_number(self, team_id: UUID) -> int:
        """The number the team's next sprint takes: 1 for the first, otherwise the highest the
        team has ever had plus one, whatever the status of that sprint (numbers are not reused).
        Called with the team locked, so two new sprints of a team never get the same one."""
        ...

    async def get_active(self, team_id: UUID) -> Sprint | None:
        """The team's sprint with status ``active``, with its participants in turn order, or
        ``None`` when the team has none."""
        ...

    async def save(self, sprint: Sprint) -> None:
        """Store the changes of a sprint that ``get_active`` loaded, its participants
        included."""
        ...
