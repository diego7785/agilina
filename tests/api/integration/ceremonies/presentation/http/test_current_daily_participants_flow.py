"""AGI-61 end to end over HTTP: who is called to the team's current daily, against PostgreSQL.

The room lists the participants of the daily, connected or not, with their names and emails.
Only a participant of the daily, with a session of the tenant, sees that list: a member who was
not summoned (the admin included), someone outside the team or a session of another tenant gets
nothing of it. The wiring is the tenant's container, as in production; only the realm's key set
is simulated.
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
from agilina_api.identity.infrastructure.keycloak.authenticated_users import (
    KeycloakAuthenticatedUsers,
)
from agilina_api.shared.infrastructure.database.session import create_session_factory
from agilina_api.shared.presentation.http.access import get_authenticated_users
from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER, get_tenant_directory
from tests.api.builders import (
    AUDIENCE,
    AccessTokenBuilder,
    AppUserBuilder,
    SprintBuilder,
    TeamBuilder,
    TenantBuilder,
    signing_key,
)
from tests.api.doubles import JWKS_URL, FakeClock, FakeRealmKeys, FakeTenantDirectory
from tests.api.integration.support import stored_sprint, stored_team, stored_user

pytestmark = pytest.mark.integration

REALMS = "http://auth.test/realms/agilina-"
URL = "/v1/teams/{team_id}/dailies/current/participants"
AN_HOUR_AFTER_THE_DAILY = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
"""Wednesday 2026-10-07, an hour after its daily (09:00 in Bogota): the room's window is shut."""


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(AN_HOUR_AFTER_THE_DAILY)


@pytest.fixture
async def api(engine, ecomoda_engine, clock) -> AsyncIterator[AsyncClient]:
    """The API on the databases of this run, with each tenant's people checked against the
    issuer of that tenant's realm; the query is the container's own."""
    app: FastAPI = create_app()
    app.dependency_overrides[get_tenant_directory] = lambda: FakeTenantDirectory(
        TenantBuilder().build(), TenantBuilder().ecomoda().build()
    )

    def users_of_the_tenant(container: Container = Depends(current_container)):
        verifier = KeycloakAccessTokenVerifier(
            jwks_url=JWKS_URL,
            issuer=f"{REALMS}{container.tenant.slug}",
            audience=AUDIENCE,
            clock=clock,
            client=FakeRealmKeys(signing_key()).client(),
        )
        return KeycloakAuthenticatedUsers(verifier, create_session_factory(container.engine))

    app.dependency_overrides[get_authenticated_users] = users_of_the_tenant
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://tests") as client:
        yield client
        await app.state.tenant_containers.aclose()


def _headers(clock: FakeClock, tenant: str, subject: str) -> dict[str, str]:
    """A session of ``subject`` in ``tenant``: a token its realm signed just now."""
    token = (
        AccessTokenBuilder()
        .issued_by(f"{REALMS}{tenant}")
        .for_subject(subject)
        .issued_at_instant(clock.now())
        .build()
    )
    return {"Authorization": f"Bearer {token}", TENANT_HEADER: tenant}


async def _daily_of_atlas(session_factory):
    """Atlas, whose active sprint calls Carla first and Ana (its admin) second; Bruno is a
    member who was not summoned."""
    ana = await stored_user(
        session_factory,
        AppUserBuilder().with_unique_email().with_subject("sub-ana").named("Ana Gil"),
    )
    carla = await stored_user(
        session_factory,
        AppUserBuilder().with_unique_email().with_subject("sub-carla").named("Carla Ruiz"),
    )
    bruno = await stored_user(
        session_factory, AppUserBuilder().with_unique_email().with_subject("sub-bruno")
    )
    team = await stored_team(
        session_factory,
        TeamBuilder().with_admin(ana.id).with_member(carla.id).with_member(bruno.id),
    )
    await stored_sprint(
        session_factory, SprintBuilder().for_team(team).with_participants(carla.id, ana.id)
    )
    return team, ana, carla


async def test_a_participant_sees_who_is_called_with_names_and_emails_in_turn_order(
    api, session_factory, clock
):
    team, ana, carla = await _daily_of_atlas(session_factory)

    response = await api.get(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-ana")
    )

    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "participants": [
            {"room_identity": str(carla.id), "full_name": "Carla Ruiz", "email": carla.email.value},
            {"room_identity": str(ana.id), "full_name": "Ana Gil", "email": ana.email.value},
        ]
    }


async def test_a_member_who_was_not_summoned_is_403_not_a_daily_participant(
    api, session_factory, clock
):
    team, _, _ = await _daily_of_atlas(session_factory)

    response = await api.get(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-bruno")
    )

    assert response.status_code == 403
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == "not_a_daily_participant"


async def test_the_admin_who_was_not_summoned_is_403_not_a_daily_participant(
    api, session_factory, clock
):
    diego = await stored_user(
        session_factory, AppUserBuilder().with_unique_email().with_subject("sub-diego")
    )
    carla = await stored_user(session_factory)
    team = await stored_team(
        session_factory, TeamBuilder().with_admin(diego.id).with_member(carla.id)
    )
    await stored_sprint(session_factory, SprintBuilder().for_team(team).with_participants(carla.id))

    response = await api.get(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-diego")
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_daily_participant"


async def test_someone_outside_the_team_is_403_not_a_team_member(api, session_factory, clock):
    team, _, _ = await _daily_of_atlas(session_factory)
    await stored_user(
        session_factory, AppUserBuilder().with_unique_email().with_subject("sub-outsider")
    )

    response = await api.get(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-outsider")
    )

    assert response.status_code == 403
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == "not_a_team_member"


async def test_a_session_of_another_tenant_is_401(
    api, session_factory, ecomoda_session_factory, clock
):
    """Ana's subject exists in ecomoda too, but ecomoda's realm signed the token."""
    team, _, _ = await _daily_of_atlas(session_factory)
    await stored_user(
        ecomoda_session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana")
    )
    headers = {**_headers(clock, "ecomoda", "sub-ana"), TENANT_HEADER: "acme"}

    response = await api.get(URL.format(team_id=team.id), headers=headers)

    assert response.status_code == 401
    assert set(response.json()) == {"error"}


async def test_a_team_without_an_active_sprint_is_409_no_active_sprint(api, session_factory, clock):
    ana = await stored_user(
        session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana")
    )
    team = await stored_team(session_factory, TeamBuilder().with_admin(ana.id))

    response = await api.get(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-ana")
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_active_sprint"
