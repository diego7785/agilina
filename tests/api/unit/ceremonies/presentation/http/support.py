"""A fake world for the HTTP tests of the worker's contract: acme is the tenant, Atlas has a
ceremony scheduled in its active sprint with Ana in the round (nothing delivered for it yet),
and another ceremony belongs to a sprint that is no longer active. The worker's token and a
person's are told apart by ``FakeAuthenticatedWorkers``."""

from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from agilina_api.bootstrap.app import create_app
from agilina_api.ceremonies.application.commands.deliver_ceremony_result import (
    DeliverCeremonyResultHandler,
)
from agilina_api.ceremonies.application.queries.get_ceremony_context import (
    GetCeremonyContextHandler,
)
from agilina_api.ceremonies.presentation.http import dependencies as deps
from agilina_api.shared.application.tenancy import Tenant
from agilina_api.shared.presentation.http.access import get_authenticated_workers
from agilina_api.shared.presentation.http.tenancy import (
    TENANT_HEADER,
    current_tenant,
    get_tenant_directory,
)
from agilina_shared.enums import TeamRole
from tests.api.builders import CeremonyBuilder, RosterBuilder, TenantBuilder, next_id
from tests.api.doubles import (
    FakeAuthenticatedWorkers,
    FakeCeremoniesUnitOfWork,
    FakeCeremonyQueries,
    FakeCeremonyRoster,
    FakeClock,
    FakeParticipantNames,
    FakeTenantDirectory,
    InMemoryCeremonyRepository,
)

TOKEN_WORKER = "token-of-the-worker"
TOKEN_PERSON = "token-of-a-person"


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


def _headers(token: str | None, tenant: str | None) -> dict[str, str]:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    if tenant is not None:
        headers[TENANT_HEADER] = tenant
    return headers
