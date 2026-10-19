"""In-memory doubles of the ceremonies ports."""

import copy
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from agilina_api.ceremonies.application.dtos import CeremonyRecord, RosterRecord
from agilina_api.ceremonies.application.errors import RoomServiceUnavailableError
from agilina_api.ceremonies.domain.ceremony import Ceremony
from agilina_shared import CeremonyResult


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

    async def active_roster_of(self, *, team_id: UUID) -> RosterRecord | None:
        return next((roster for (team, _), roster in self.rosters.items() if team == team_id), None)

    async def roster_of(self, *, team_id: UUID, sprint_id: UUID) -> RosterRecord | None:
        self.asked.append((team_id, sprint_id))
        return self.rosters.get((team_id, sprint_id))


class FakeParticipantNames:
    """The full name of the users the test gives it; anyone else has no account."""

    def __init__(self, names: dict[UUID, str] | None = None) -> None:
        self.names = names or {}

    async def names_of(self, user_ids: Collection[UUID]) -> dict[UUID, str]:
        return {user_id: self.names[user_id] for user_id in user_ids if user_id in self.names}


@dataclass(frozen=True)
class Admission:
    """What ``FakeRooms.admission_for`` was asked to sign."""

    room_name: str
    identity: str
    expires_at: datetime


class FakeRooms:
    """Records the rooms it opens and the admissions it signs, each one a deterministic token;
    with ``unavailable`` it fails like a room server that is down or not configured."""

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.opened: list[str] = []
        self.admissions: list[Admission] = []

    async def open(self, room_name: str) -> None:
        if self.unavailable:
            raise RoomServiceUnavailableError("the fake room server is down")
        self.opened.append(room_name)

    def admission_for(self, *, room_name: str, identity: str, expires_at: datetime) -> str:
        if self.unavailable:
            raise RoomServiceUnavailableError("the fake room server is down")
        self.admissions.append(Admission(room_name, identity, expires_at))
        return f"token-{room_name}-{identity}-{expires_at.isoformat()}"


@dataclass(frozen=True)
class StoredResult:
    """What ``InMemoryCeremonyRepository.add_result`` was given."""

    digest: str | None
    result: CeremonyResult
    received_at: datetime


class InMemoryCeremonyRepository:
    """Stores and returns *copies* of the ceremonies, like a database does: a result received
    by a ceremony that is never stored is lost."""

    def __init__(self, *ceremonies: Ceremony) -> None:
        self.ceremonies = {ceremony.id: copy.deepcopy(ceremony) for ceremony in ceremonies}
        self.results: dict[UUID, StoredResult] = {}

    async def add_or_get(self, ceremony: Ceremony) -> Ceremony:
        occurrence = (ceremony.team_id, ceremony.sprint_id, ceremony.scheduled_at)
        stored = next(
            (
                found
                for found in self.ceremonies.values()
                if (found.team_id, found.sprint_id, found.scheduled_at) == occurrence
            ),
            None,
        )
        if stored is None:
            stored = self.ceremonies[ceremony.id] = copy.deepcopy(ceremony)
        return copy.deepcopy(stored)

    async def lock(self, ceremony_id: UUID) -> Ceremony | None:
        found = self.ceremonies.get(ceremony_id)
        return copy.deepcopy(found) if found is not None else None

    async def add_result(
        self, ceremony: Ceremony, result: CeremonyResult, *, received_at: datetime
    ) -> None:
        self.ceremonies[ceremony.id] = copy.deepcopy(ceremony)
        self.results[ceremony.id] = StoredResult(ceremony.result_digest, result, received_at)


class FakeCeremoniesUnitOfWork:
    def __init__(self, ceremonies: InMemoryCeremonyRepository | None = None) -> None:
        self.ceremonies = ceremonies or InMemoryCeremonyRepository()
        self.commits = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None
