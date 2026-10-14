"""In-memory doubles of the teams ports."""

import copy
from collections.abc import Collection
from types import TracebackType
from typing import Self
from uuid import UUID

from agilina_api.shared.application.access import MembershipRef
from agilina_api.teams.application.dtos import (
    ActiveSprintRecord,
    MemberContact,
    MemberRecord,
    TeamMemberRecords,
    TeamSummary,
    TeamView,
    UserTeamView,
)
from agilina_api.teams.domain.sprint import Sprint, SprintStatus
from agilina_api.teams.domain.team import Team
from agilina_shared.enums import OperationMode


class InMemoryTeamRepository:
    """Stores and returns *copies*, like a database does: a change to a team that is never
    saved is lost, and a test cannot mistake it for persisted state."""

    def __init__(self) -> None:
        self.teams: dict[UUID, Team] = {}
        self.saved: list[UUID] = []

    async def add(self, team: Team) -> None:
        self.teams[team.id] = copy.deepcopy(team)

    async def get(self, team_id: UUID) -> Team | None:
        found = self.teams.get(team_id)
        return copy.deepcopy(found) if found is not None else None

    async def save(self, team: Team) -> None:
        self.saved.append(team.id)
        self.teams[team.id] = copy.deepcopy(team)


class InMemorySprintRepository:
    """Stores and returns *copies* of the sprints, like a database does (HU-07)."""

    def __init__(self) -> None:
        self.sprints: dict[UUID, Sprint] = {}
        self.saved: list[UUID] = []

    async def add(self, sprint: Sprint) -> None:
        self.sprints[sprint.id] = copy.deepcopy(sprint)

    async def next_number(self, team_id: UUID) -> int:
        numbers = [sprint.number for sprint in self.sprints.values() if sprint.team_id == team_id]
        return max(numbers, default=0) + 1

    async def get_active(self, team_id: UUID) -> Sprint | None:
        found = self.active_of(team_id)
        return copy.deepcopy(found) if found is not None else None

    async def save(self, sprint: Sprint) -> None:
        if sprint.id not in self.sprints:
            raise LookupError(f"Sprint {sprint.id} does not exist")
        self.saved.append(sprint.id)
        self.sprints[sprint.id] = copy.deepcopy(sprint)

    def active_of(self, team_id: UUID) -> Sprint | None:
        """The stored active sprint of the team, as it is (for the test to read)."""
        return next(
            (
                sprint
                for sprint in self.sprints.values()
                if sprint.team_id == team_id and sprint.status is SprintStatus.ACTIVE
            ),
            None,
        )


class FakeSprintQueries:
    """The read side of the sprints ``repository`` holds, as ``SqlSprintQueries`` reads the
    rows the repository writes: a route that saves and then reads sees what it saved."""

    def __init__(self, repository: InMemorySprintRepository | None = None) -> None:
        self.repository = repository or InMemorySprintRepository()

    async def active_sprint_of(self, team_id: UUID) -> ActiveSprintRecord | None:
        sprint = self.repository.active_of(team_id)
        if sprint is None:
            return None
        return ActiveSprintRecord(
            sprint_id=sprint.id,
            number=sprint.number,
            start_date=sprint.period.start,
            end_date=sprint.period.end,
            daily_time=sprint.daily_time.at,
            time_zone=sprint.daily_time.time_zone,
            participants=sprint.participants,
        )


class FakeActiveSprints:
    """The teams the test says have a sprint in progress."""

    def __init__(self, teams_with_active_sprint: set[UUID] | None = None) -> None:
        self.teams_with_active_sprint = teams_with_active_sprint or set()

    async def has_active_sprint(self, team_id: UUID) -> bool:
        return team_id in self.teams_with_active_sprint


class FakeMemberContacts:
    """The name and email of the users the test gives it; anyone else has no account."""

    def __init__(self, contacts: dict[UUID, MemberContact] | None = None) -> None:
        self.contacts = contacts or {}

    async def contacts_of(self, user_ids: Collection[UUID]) -> dict[UUID, MemberContact]:
        return {user_id: self.contacts[user_id] for user_id in user_ids if user_id in self.contacts}


class FakeTeamsUnitOfWork:
    def __init__(
        self,
        teams: InMemoryTeamRepository | None = None,
        active_sprints: FakeActiveSprints | None = None,
        sprints: InMemorySprintRepository | None = None,
    ) -> None:
        self.teams = teams or InMemoryTeamRepository()
        self.sprints = sprints or InMemorySprintRepository()
        self.active_sprints = active_sprints or FakeActiveSprints()
        self.committed = False

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
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False


class FakeTeamQueries:
    """Answers with what the test gives it: summaries, views and members by team, teams by
    user, memberships by team and user, the teams with a sprint in progress and the mode of
    each team (support unless the test says otherwise)."""

    def __init__(
        self,
        summaries: dict[UUID, TeamSummary] | None = None,
        teams_by_user: dict[UUID, tuple[UserTeamView, ...]] | None = None,
        views: dict[UUID, TeamView] | None = None,
        memberships: dict[tuple[UUID, UUID], MembershipRef] | None = None,
        members: dict[UUID, tuple[MemberRecord, ...]] | None = None,
        teams_with_active_sprint: set[UUID] | None = None,
        modes: dict[UUID, OperationMode] | None = None,
    ) -> None:
        self.summaries = summaries or {}
        self.teams_by_user = teams_by_user or {}
        self.views = views or {}
        self.memberships = memberships or {}
        self.members = members or {}
        self.teams_with_active_sprint = teams_with_active_sprint or set()
        self.modes = modes or {}

    async def get_summary(self, team_id: UUID) -> TeamSummary | None:
        return self.summaries.get(team_id)

    async def list_for_user(self, user_id: UUID) -> tuple[UserTeamView, ...]:
        return self.teams_by_user.get(user_id, ())

    async def get_team(self, team_id: UUID) -> TeamView | None:
        return self.views.get(team_id)

    async def list_members(self, team_id: UUID) -> TeamMemberRecords:
        return TeamMemberRecords(
            members=self.members.get(team_id, ()),
            has_active_sprint=team_id in self.teams_with_active_sprint,
            mode=self.modes.get(team_id, OperationMode.SUPPORT),
        )

    async def membership_of(self, *, team_id: UUID, user_id: UUID) -> MembershipRef | None:
        return self.memberships.get((team_id, user_id))
