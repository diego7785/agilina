"""In-memory doubles of the ceremonies ports."""

from collections.abc import Collection
from uuid import UUID

from agilina_api.ceremonies.application.dtos import CeremonyRecord, RosterRecord


class FakeCeremonyQueries:
    """The ceremonies the test gives it, by id; any other does not exist."""

    def __init__(self, ceremonies: dict[UUID, CeremonyRecord] | None = None) -> None:
        self.ceremonies = ceremonies or {}

    async def ceremony_of(self, ceremony_id: UUID) -> CeremonyRecord | None:
        return self.ceremonies.get(ceremony_id)


class FakeCeremonyRoster:
    """The roster of each (team, active sprint) the test gives it; any other pair is a team
    without an active sprint or whose active sprint is another one."""

    def __init__(self, rosters: dict[tuple[UUID, UUID], RosterRecord] | None = None) -> None:
        self.rosters = rosters or {}
        self.asked: list[tuple[UUID, UUID]] = []

    async def roster_of(self, *, team_id: UUID, sprint_id: UUID) -> RosterRecord | None:
        self.asked.append((team_id, sprint_id))
        return self.rosters.get((team_id, sprint_id))


class FakeParticipantNames:
    """The full name of the users the test gives it; anyone else has no account."""

    def __init__(self, names: dict[UUID, str] | None = None) -> None:
        self.names = names or {}

    async def names_of(self, user_ids: Collection[UUID]) -> dict[UUID, str]:
        return {user_id: self.names[user_id] for user_id in user_ids if user_id in self.names}
