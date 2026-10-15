"""AGI-64 / AGI-125 end to end over HTTP: the real wiring against PostgreSQL, with the worker's
token signed for real by a simulated realm of each tenant.

One call gives the worker the tenant, the sprint and its day, the participants in turn order,
the language and the mode (the story's first test case). A worker token of another tenant's
realm is a 401 (the fourth one). Nothing but the realm's key set is doubled: the container of
each tenant, its database and the token's verification are the ones the API runs with.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from agilina_api.bootstrap.app import create_app
from agilina_api.bootstrap.container import Container
from agilina_api.bootstrap.tenants import current_container
from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from agilina_api.identity.infrastructure.keycloak.authenticated_workers import (
    KeycloakAuthenticatedWorkers,
)
from agilina_api.shared.presentation.http.access import get_authenticated_workers
from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER, get_tenant_directory
from agilina_shared.enums import Language, OperationMode
from tests.api.builders import (
    AUDIENCE,
    AccessTokenBuilder,
    AppUserBuilder,
    CeremonyBuilder,
    SprintBuilder,
    TeamBuilder,
    TenantBuilder,
    signing_key,
)
from tests.api.doubles import JWKS_URL, FakeClock, FakeRealmKeys, FakeTenantDirectory
from tests.api.integration.support import stored_ceremony, stored_sprint, stored_team, stored_user

pytestmark = pytest.mark.integration

REALMS = "http://auth.test/realms/agilina-"


def _worker_token(tenant: str) -> str:
    return AccessTokenBuilder().issued_by(f"{REALMS}{tenant}").as_worker().build()


def _headers(token: str, tenant: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", TENANT_HEADER: tenant}


@pytest.fixture
async def api(engine, ecomoda_engine) -> AsyncIterator[AsyncClient]:
    """The API on the databases of this run (``engine`` and ``ecomoda_engine`` start them
    empty); each tenant's worker is checked against the issuer of that tenant's realm."""
    clock = FakeClock()
    app: FastAPI = create_app()
    app.dependency_overrides[get_tenant_directory] = lambda: FakeTenantDirectory(
        TenantBuilder().build(), TenantBuilder().ecomoda().build()
    )

    def workers_of_the_tenant(container: Container = Depends(current_container)):
        verifier = KeycloakAccessTokenVerifier(
            jwks_url=JWKS_URL,
            issuer=f"{REALMS}{container.tenant.slug}",
            audience=AUDIENCE,
            clock=clock,
            client=FakeRealmKeys(signing_key()).client(),
        )
        return KeycloakAuthenticatedWorkers(verifier, "agilina-worker")

    app.dependency_overrides[get_authenticated_workers] = workers_of_the_tenant
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://tests") as client:
        yield client
        await app.state.tenant_containers.aclose()


async def _scheduled_daily(session_factory):
    """Atlas, in Spanish and autonomous, with Carla first and Ana second in the round, and its
    daily scheduled on Wednesday 2026-10-07 at 09:00 in Bogota (day 3 of 12)."""
    ana = await stored_user(session_factory, AppUserBuilder().with_unique_email().named("Ana Gil"))
    carla = await stored_user(
        session_factory, AppUserBuilder().with_unique_email().named("Carla Ruiz")
    )
    team = await stored_team(
        session_factory,
        TeamBuilder()
        .in_language(Language.ES)
        .in_mode(OperationMode.AUTONOMOUS)
        .with_admin(ana.id)
        .with_member(carla.id),
    )
    sprint = await stored_sprint(
        session_factory, SprintBuilder().for_team(team).with_participants(carla.id, ana.id)
    )
    ceremony_id = await stored_ceremony(
        session_factory,
        CeremonyBuilder()
        .for_sprint(sprint)
        .scheduled_at_instant(datetime(2026, 10, 7, 14, 0, tzinfo=UTC)),
    )
    return ceremony_id, team, sprint, ana, carla


async def test_one_call_gives_the_worker_the_whole_context_of_the_ceremony(api, session_factory):
    ceremony_id, team, sprint, ana, carla = await _scheduled_daily(session_factory)

    response = await api.get(
        f"/v1/ceremonies/{ceremony_id}/context", headers=_headers(_worker_token("acme"), "acme")
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "tenant": "acme",
        "ceremony_id": str(ceremony_id),
        "team_id": str(team.id),
        "sprint_id": str(sprint.id),
        "room": f"acme-{ceremony_id}",
        "language": "es",
        "mode": "autonomous",
        "sprint_day": 3,
        "sprint_total_days": 12,
        "participants": [
            {
                "user_id": str(carla.id),
                "name": "Carla Ruiz",
                "room_identity": str(carla.id),
                "role": "member",
                "turn_order": 1,
            },
            {
                "user_id": str(ana.id),
                "name": "Ana Gil",
                "room_identity": str(ana.id),
                "role": "admin",
                "turn_order": 2,
            },
        ],
        "silence_seconds": 10,
        "stuck_turn_seconds": 30,
    }


async def test_a_worker_token_of_another_tenant_answers_401(api, session_factory):
    ceremony_id, *_ = await _scheduled_daily(session_factory)

    response = await api.get(
        f"/v1/ceremonies/{ceremony_id}/context",
        headers=_headers(_worker_token("ecomoda"), "acme"),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_a_ceremony_lives_only_in_the_database_of_its_tenant(api, session_factory):
    """Ecomoda's worker, with its own valid token, does not find a ceremony of acme."""
    ceremony_id, *_ = await _scheduled_daily(session_factory)

    response = await api.get(
        f"/v1/ceremonies/{ceremony_id}/context",
        headers=_headers(_worker_token("ecomoda"), "ecomoda"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ceremony_not_found"


async def test_a_person_of_the_tenant_cannot_ask_for_the_context(api, session_factory):
    ceremony_id, *_ = await _scheduled_daily(session_factory)
    person = AccessTokenBuilder().issued_by(f"{REALMS}acme").build()

    response = await api.get(
        f"/v1/ceremonies/{ceremony_id}/context", headers=_headers(person, "acme")
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_worker"
