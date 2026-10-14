"""A fake world for the HTTP tests of teams and users: Ana is admin of Atlas and Carla one of its
members, Ana is only a member of Boreal, and Bruno has no team. The sprints of Atlas live in
``members_uow`` too: the sprint queries read what the sprint commands store."""

from uuid import UUID

from httpx import ASGITransport, AsyncClient

from agilina_api.bootstrap.app import create_app
from agilina_api.shared.presentation.http.access import get_authenticated_users, get_team_access
from agilina_api.teams.application.commands.change_member_role import ChangeMemberRoleHandler
from agilina_api.teams.application.commands.create_team_as_admin import CreateTeamAsAdminHandler
from agilina_api.teams.application.commands.reconfigure_sprint import ReconfigureSprintHandler
from agilina_api.teams.application.commands.remove_member import RemoveMemberHandler
from agilina_api.teams.application.commands.start_sprint import StartSprintHandler
from agilina_api.teams.application.dtos import MemberContact, MemberRecord, TeamView, UserTeamView
from agilina_api.teams.application.queries.get_active_sprint import GetActiveSprintHandler
from agilina_api.teams.application.queries.get_team import GetTeamHandler
from agilina_api.teams.application.queries.get_team_dashboard import GetTeamDashboardHandler
from agilina_api.teams.application.queries.get_team_user import GetTeamUserHandler
from agilina_api.teams.application.queries.list_my_teams import ListMyTeamsHandler
from agilina_api.teams.application.queries.list_team_members import ListTeamMembersHandler
from agilina_api.teams.presentation.http import dependencies as deps
from agilina_shared.enums import Language, OperationMode, TeamRole
from tests.api.builders import NOW, next_id
from tests.api.doubles import (
    FakeActiveSprints,
    FakeAuthenticatedUsers,
    FakeClock,
    FakeMemberContacts,
    FakeSprintQueries,
    FakeTeamAccess,
    FakeTeamQueries,
    FakeTeamsUnitOfWork,
)

TOKEN_ANA = "token-of-ana"
TOKEN_BRUNO = "token-of-bruno"
TOKEN_CARLA = "token-of-carla"


def _returning(handler):
    """A provider that hands back this very object (see the identity router tests)."""
    return lambda: handler


class Api:
    """Ana is admin of Atlas and member of Boreal; Carla is a member of Atlas; Bruno has no
    team. The members of Atlas live in ``members_uow`` (commands) and in the queries."""

    def __init__(self) -> None:
        self.ana, self.bruno, self.carla = next_id(), next_id(), next_id()
        self.atlas, self.boreal = next_id(), next_id()
        self.clock = FakeClock()
        self.uow = FakeTeamsUnitOfWork()
        self.members_uow = FakeTeamsUnitOfWork(active_sprints=FakeActiveSprints())
        self.queries = FakeTeamQueries(
            teams_by_user={
                self.ana: (
                    UserTeamView(
                        team_id=self.atlas,
                        name="Atlas",
                        role=TeamRole.ADMIN,
                        mode=OperationMode.SUPPORT,
                    ),
                    UserTeamView(
                        team_id=self.boreal,
                        name="Boreal",
                        role=TeamRole.MEMBER,
                        mode=OperationMode.AUTONOMOUS,
                    ),
                )
            },
            views={
                self.atlas: TeamView(
                    team_id=self.atlas,
                    name="Atlas",
                    mode=OperationMode.SUPPORT,
                    language=Language.EN,
                ),
                self.boreal: TeamView(
                    team_id=self.boreal,
                    name="Boreal",
                    mode=OperationMode.AUTONOMOUS,
                    language=Language.ES,
                ),
            },
            members={
                self.atlas: (
                    MemberRecord(user_id=self.ana, role=TeamRole.ADMIN, joined_at=NOW),
                    MemberRecord(user_id=self.carla, role=TeamRole.MEMBER, joined_at=NOW),
                )
            },
        )
        contacts = FakeMemberContacts(
            {
                self.ana: MemberContact(full_name="Ana Gil", email="ana@example.test"),
                self.carla: MemberContact(full_name="Carla Ruiz", email="carla@example.test"),
            }
        )
        access = FakeTeamAccess(
            {
                (self.atlas, self.ana): TeamRole.ADMIN,
                (self.boreal, self.ana): TeamRole.MEMBER,
                (self.atlas, self.carla): TeamRole.MEMBER,
            }
        )
        users = FakeAuthenticatedUsers(
            {TOKEN_ANA: self.ana, TOKEN_BRUNO: self.bruno, TOKEN_CARLA: self.carla}
        )
        active_sprint = GetActiveSprintHandler(
            FakeSprintQueries(self.members_uow.sprints), self.clock
        )
        app = create_app()
        overrides = {
            deps.get_create_team_as_admin_handler: CreateTeamAsAdminHandler(
                lambda: self.uow, FakeClock(), new_id=next_id
            ),
            deps.get_list_my_teams_handler: ListMyTeamsHandler(self.queries),
            deps.get_get_team_handler: GetTeamHandler(self.queries),
            deps.get_list_team_members_handler: ListTeamMembersHandler(self.queries, contacts),
            deps.get_get_team_user_handler: GetTeamUserHandler(self.queries, contacts),
            deps.get_start_sprint_handler: StartSprintHandler(
                lambda: self.members_uow, new_id=next_id
            ),
            deps.get_reconfigure_sprint_handler: ReconfigureSprintHandler(lambda: self.members_uow),
            deps.get_get_active_sprint_handler: active_sprint,
            deps.get_get_team_dashboard_handler: GetTeamDashboardHandler(
                self.queries, active_sprint
            ),
            deps.get_change_member_role_handler: ChangeMemberRoleHandler(
                lambda: self.members_uow, FakeClock()
            ),
            deps.get_remove_member_handler: RemoveMemberHandler(
                lambda: self.members_uow, FakeClock()
            ),
            get_authenticated_users: users,
            get_team_access: access,
        }
        for provider, value in overrides.items():
            app.dependency_overrides[provider] = _returning(value)
        self.app = app

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=self.app), base_url="http://tests")

    async def request(self, method: str, path: str, token: str | None = None, **kwargs):
        headers = {} if token is None else {"Authorization": f"Bearer {token}"}
        async with self.client() as client:
            return await client.request(method, f"/v1/teams{path}", headers=headers, **kwargs)

    async def users(
        self,
        method: str,
        path: str = "",
        token: str | None = None,
        team: UUID | str | None = None,
        **kwargs,
    ):
        """A request to ``/v1/users{path}`` about ``team`` (Atlas unless told otherwise)."""
        headers = {} if token is None else {"Authorization": f"Bearer {token}"}
        params = {} if team == "" else {"team_id": str(team or self.atlas)}
        async with self.client() as client:
            return await client.request(
                method, f"/v1/users{path}", params=params, headers=headers, **kwargs
            )

    def role_in_atlas(self, user_id) -> TeamRole | None:
        """The role stored by the commands, or ``None`` once the person left the team."""
        membership = self.members_uow.teams.teams[self.atlas].membership_of(user_id)
        assert membership is not None
        return membership.role if membership.is_active else None
