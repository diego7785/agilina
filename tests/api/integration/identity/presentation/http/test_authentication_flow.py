"""HU-03 over HTTP: a signed token opens the routes of a user's teams, and nothing else does.

Real PostgreSQL behind the API and the real token validation; only the realm's key set is
simulated (the signatures are real)."""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from agilina_api.bootstrap.app import create_app
from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from agilina_api.identity.infrastructure.keycloak.authenticated_users import (
    KeycloakAuthenticatedUsers,
)
from agilina_api.shared.presentation.http.access import get_authenticated_users, get_team_access
from agilina_api.teams.application.commands.create_team_as_admin import CreateTeamAsAdminHandler
from agilina_api.teams.application.queries.list_my_teams import ListMyTeamsHandler
from agilina_api.teams.infrastructure.persistence.team_queries import SqlTeamQueries
from agilina_api.teams.infrastructure.persistence.unit_of_work import teams_unit_of_work_factory
from agilina_api.teams.presentation.http import dependencies as deps
from tests.api.builders import (
    AUDIENCE,
    ISSUER,
    NOW,
    AccessTokenBuilder,
    AppUserBuilder,
    TeamBuilder,
    signing_key,
)
from tests.api.doubles import JWKS_URL, FakeClock, FakeRealmKeys
from tests.api.integration.support import stored_team, stored_user

pytestmark = pytest.mark.integration


def _returning(value):
    """A provider that hands back this very object. (A lambda with the value as a default
    argument would not do: FastAPI reads that default as a parameter and copies it.)"""
    return lambda: value


@pytest.fixture
async def api(session_factory) -> AsyncClient:
    verifier = KeycloakAccessTokenVerifier(
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
        clock=FakeClock(),
        client=FakeRealmKeys(signing_key()).client(),
    )
    queries = SqlTeamQueries(session_factory)
    app = create_app()
    overrides = {
        get_authenticated_users: KeycloakAuthenticatedUsers(verifier, session_factory),
        get_team_access: queries,
        deps.get_list_my_teams_handler: ListMyTeamsHandler(queries),
        deps.get_create_team_as_admin_handler: CreateTeamAsAdminHandler(
            teams_unit_of_work_factory(session_factory), FakeClock()
        ),
    }
    for dependency, value in overrides.items():
        app.dependency_overrides[dependency] = _returning(value)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://tests") as client:
        yield client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_signed_in_user_sees_their_teams_and_only_theirs(api, session_factory):
    ana = await stored_user(
        session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana")
    )
    await stored_team(session_factory, TeamBuilder().named("Atlas").with_admin(ana.id))
    await stored_team(session_factory, TeamBuilder().named("Borealis"))  # not Ana's

    response = await api.get(
        "/v1/teams", headers=_bearer(AccessTokenBuilder().for_subject("sub-ana").build())
    )

    assert response.status_code == 200
    assert [team["name"] for team in response.json()] == ["Atlas"]


async def test_an_expired_token_is_a_401_so_that_the_application_signs_in_again(
    api, session_factory
):
    await stored_user(session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana"))
    expired = (
        AccessTokenBuilder()
        .for_subject("sub-ana")
        .issued_at_instant(NOW - timedelta(hours=1))
        .build()
    )

    response = await api.get("/v1/teams", headers=_bearer(expired))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_a_token_signed_by_someone_else_is_a_401(api, session_factory):
    await stored_user(session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana"))
    forged = (
        AccessTokenBuilder()
        .for_subject("sub-ana")
        .signed_with(signing_key("key-1", "attacker"))
        .build()
    )

    assert (await api.get("/v1/teams", headers=_bearer(forged))).status_code == 401


async def test_a_valid_token_of_someone_without_a_user_is_a_403_not_a_loop(api, session_factory):
    await stored_user(session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana"))
    unknown = AccessTokenBuilder().for_subject("created-in-the-keycloak-console").build()

    response = await api.get("/v1/teams", headers=_bearer(unknown))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_active"
