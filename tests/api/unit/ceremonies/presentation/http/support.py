"""Fake worlds for the HTTP tests of ceremonies.

``Api`` is the worker's contract: acme is the tenant, Atlas has a ceremony scheduled in its
active sprint with Ana in the round (nothing delivered for it yet), and another ceremony belongs
to a sprint that is no longer active. The worker's token and a person's are told apart by
``FakeAuthenticatedWorkers``.

``DailiesApi`` is the routes of people (AGI-59, AGI-61): Ana and then Carla are in the round of
Atlas's daily, Bruno is the admin of Atlas but not in the round, Boreal has Ana as a member and
no active sprint, and Olga has a session but no team, like someone the link was forwarded to."""

from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from agilina_api.bootstrap.app import create_app
from agilina_api.ceremonies.application.commands.deliver_ceremony_result import (
    DeliverCeremonyResultHandler,
)
from agilina_api.ceremonies.application.commands.join_current_daily import (
    JoinCurrentDailyHandler,
)
from agilina_api.ceremonies.application.dtos import ParticipantContact
from agilina_api.ceremonies.application.queries.get_ceremony_context import (
    GetCeremonyContextHandler,
)
from agilina_api.ceremonies.application.queries.get_current_daily_participants import (
    GetCurrentDailyParticipantsHandler,
)
from agilina_api.ceremonies.presentation.http import dependencies as deps
from agilina_api.shared.application.tenancy import Tenant
from agilina_api.shared.presentation.http.access import (
    get_authenticated_users,
    get_authenticated_workers,
    get_team_access,
)
from agilina_api.shared.presentation.http.tenancy import (
    TENANT_HEADER,
    current_tenant,
    get_tenant_directory,
)
from agilina_shared.enums import TeamRole
from tests.api.builders import DAILY_TIME, CeremonyBuilder, RosterBuilder, TenantBuilder, next_id
from tests.api.doubles import (
    FakeAuthenticatedUsers,
    FakeAuthenticatedWorkers,
    FakeCeremoniesUnitOfWork,
    FakeCeremonyQueries,
    FakeCeremonyRoster,
    FakeClock,
    FakeParticipantContacts,
    FakeParticipantNames,
    FakeRooms,
    FakeTeamAccess,
    FakeTenantDirectory,
    InMemoryCeremonyRepository,
)

TOKEN_WORKER = "token-of-the-worker"
TOKEN_PERSON = "token-of-a-person"
TOKEN_ANA = "token-of-ana"
TOKEN_BRUNO = "token-of-bruno"
TOKEN_CARLA = "token-of-carla"
TOKEN_OLGA = "token-of-olga"
TOKEN_INACTIVE = "token-of-someone-not-active"
LIVEKIT_URL = "wss://livekit.example.test"


def _returning(value):
    return lambda: value


class Api:
    def __init__(self) -> None:
        self.ana = next_id()
        self.ceremony = CeremonyBuilder()
        self.past_ceremony = CeremonyBuilder()
        current = self.ceremony.build()
        ceremonies = FakeCeremonyQueries(
            {
                self.ceremony.ceremony_id: current,
                self.past_ceremony.ceremony_id: self.past_ceremony.build(),
            }
        )
        rosters = FakeCeremonyRoster(
            {
                (current.team_id, current.sprint_id): RosterBuilder()
                .with_participant(self.ana, TeamRole.ADMIN)
                .build()
            }
        )
        names = FakeParticipantNames({self.ana: "Ana Gil"})
        self.repository = InMemoryCeremonyRepository(
            self.ceremony.aggregate(), self.past_ceremony.aggregate()
        )
        uow = FakeCeremoniesUnitOfWork(self.repository)
        app = create_app()
        overrides = {
            get_tenant_directory: FakeTenantDirectory(TenantBuilder().build()),
            deps.get_get_ceremony_context_handler: GetCeremonyContextHandler(
                ceremonies, rosters, names
            ),
            deps.get_deliver_ceremony_result_handler: DeliverCeremonyResultHandler(
                lambda: uow, rosters, FakeClock()
            ),
        }
        for provider, value in overrides.items():
            app.dependency_overrides[provider] = _returning(value)
        workers = FakeAuthenticatedWorkers({TOKEN_WORKER}, {TOKEN_PERSON})

        # The real adapter is the tenant's (``from_container``), so the tenant is resolved
        # before the token is looked at: the double keeps that order.
        def workers_of_the_tenant(_: Tenant = Depends(current_tenant)) -> FakeAuthenticatedWorkers:
            return workers

        app.dependency_overrides[get_authenticated_workers] = workers_of_the_tenant
        self.app = app

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=self.app), base_url="http://tests")

    async def context(self, ceremony_id, token: str | None = TOKEN_WORKER, tenant="acme"):
        async with self.client() as client:
            return await client.get(
                f"/v1/ceremonies/{ceremony_id}/context", headers=_headers(token, tenant)
            )

    async def deliver(self, ceremony_id, body, token: str | None = TOKEN_WORKER, tenant="acme"):
        """POST the result ``body``: a ``CeremonyResult`` or the JSON a worker could send."""
        payload = body if isinstance(body, dict) else body.model_dump(mode="json")
        async with self.client() as client:
            return await client.post(
                f"/v1/ceremonies/{ceremony_id}/result",
                json=payload,
                headers=_headers(token, tenant),
            )


class DailiesApi:
    """See the module: the clock stands at the start of Atlas's first daily."""

    def __init__(self) -> None:
        self.ana, self.bruno, self.carla, self.olga = next_id(), next_id(), next_id(), next_id()
        self.atlas, self.boreal = next_id(), next_id()
        roster = RosterBuilder().with_participant(self.ana).with_participant(self.carla).build()
        rosters = FakeCeremonyRoster({(self.atlas, roster.sprint_id): roster})
        self.repository = InMemoryCeremonyRepository()
        self.rooms = FakeRooms()
        self.clock = FakeClock(DAILY_TIME)
        handler = JoinCurrentDailyHandler(
            lambda: FakeCeremoniesUnitOfWork(self.repository),
            rosters,
            self.rooms,
            self.clock,
            LIVEKIT_URL,
            new_id=next_id,
        )
        self.contacts = FakeParticipantContacts(
            {
                self.ana: ParticipantContact(full_name="Ana Gil", email="ana@acme.test"),
                self.carla: ParticipantContact(full_name="Carla Ruiz", email="carla@acme.test"),
            }
        )
        users = FakeAuthenticatedUsers(
            {
                TOKEN_ANA: self.ana,
                TOKEN_BRUNO: self.bruno,
                TOKEN_CARLA: self.carla,
                TOKEN_OLGA: self.olga,
            },
            inactive_tokens={TOKEN_INACTIVE},
        )
        access = FakeTeamAccess(
            {
                (self.atlas, self.ana): TeamRole.MEMBER,
                (self.atlas, self.bruno): TeamRole.ADMIN,
                (self.atlas, self.carla): TeamRole.MEMBER,
                (self.boreal, self.ana): TeamRole.MEMBER,
            }
        )
        app = create_app()
        overrides = {
            get_tenant_directory: FakeTenantDirectory(TenantBuilder().build()),
            deps.get_join_current_daily_handler: handler,
            deps.get_get_current_daily_participants_handler: GetCurrentDailyParticipantsHandler(
                rosters, self.contacts
            ),
            get_authenticated_users: users,
            get_team_access: access,
        }
        for provider, value in overrides.items():
            app.dependency_overrides[provider] = _returning(value)
        self.app = app

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=self.app), base_url="http://tests")

    async def join(self, token: str | None = TOKEN_ANA, team_id=None, tenant="acme"):
        """POST the join of the daily of ``team_id`` (Atlas unless told otherwise)."""
        async with self.client() as client:
            return await client.post(
                f"/v1/teams/{team_id or self.atlas}/dailies/current/token",
                headers=_headers(token, tenant),
            )

    async def participants(self, token: str | None = TOKEN_ANA, team_id=None, tenant="acme"):
        """GET who is called to the daily of ``team_id`` (Atlas unless told otherwise)."""
        async with self.client() as client:
            return await client.get(
                f"/v1/teams/{team_id or self.atlas}/dailies/current/participants",
                headers=_headers(token, tenant),
            )


def _headers(token: str | None, tenant: str | None) -> dict[str, str]:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    if tenant is not None:
        headers[TENANT_HEADER] = tenant
    return headers
