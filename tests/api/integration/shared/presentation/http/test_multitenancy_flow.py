"""AD-29 over HTTP, against real databases: every tenant has its own, and nothing crosses.

The application is wired for real: the catalog of tenants in PostgreSQL, one object graph (and
so one database) per tenant, and the real token validation with the issuer of each tenant's
realm. Only the key set of the realms is simulated (the signatures are real): every tenant's
realm signs with the same test key, so what keeps tenants apart is the issuer and the database.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

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
from agilina_api.shared.infrastructure.tenancy.sql_tenant_directory import SqlTenantDirectory
from agilina_api.shared.presentation.http.access import get_authenticated_users
from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER, get_tenant_directory
from tests.api.builders import (
    AUDIENCE,
    AccessTokenBuilder,
    AppUserBuilder,
    InvitationBuilder,
    TeamBuilder,
    signing_key,
)
from tests.api.doubles import JWKS_URL, FakeClock, FakeRealmKeys
from tests.api.integration.conftest import PlatformDatabases
from tests.api.integration.support import (
    stored_invitation,
    stored_team,
    stored_user,
)

pytestmark = pytest.mark.integration

REALMS = "http://auth.test/realms/agilina-"


def _token(tenant: str, subject: str) -> str:
    """An access token the realm of ``tenant`` signed for ``subject``."""
    return AccessTokenBuilder().issued_by(f"{REALMS}{tenant}").for_subject(subject).build()


def _bearer(token: str, tenant: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", TENANT_HEADER: tenant}


@pytest.fixture
async def platform(platform_databases: PlatformDatabases, engine, ecomoda_engine) -> AsyncIterator:
    """The application on top of the databases of this run, with a catalog that also knows a
    suspended tenant. ``engine`` and ``ecomoda_engine`` start both tenants empty."""
    settings = platform_databases.settings
    catalog = create_async_engine(settings.platform_dsn, poolclass=NullPool)
    async with catalog.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO tenant (slug, display_name, status) "
                "VALUES ('initech', 'Initech', 'suspended') ON CONFLICT DO NOTHING"
            )
        )
    clock = FakeClock()
    app: FastAPI = create_app()
    app.dependency_overrides[get_tenant_directory] = lambda: SqlTenantDirectory(
        create_session_factory(catalog), clock
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
    async with catalog.begin() as connection:
        await connection.execute(text("DELETE FROM tenant WHERE slug = 'initech'"))
    await catalog.dispose()


async def test_each_tenant_serves_the_teams_of_its_own_database(
    platform, session_factory, ecomoda_session_factory
):
    ana = await stored_user(
        session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana")
    )
    await stored_team(session_factory, TeamBuilder().named("Atlas").with_admin(ana.id))
    bruno = await stored_user(
        ecomoda_session_factory, AppUserBuilder().with_unique_email().with_subject("sub-bruno")
    )
    await stored_team(ecomoda_session_factory, TeamBuilder().named("Moda").with_admin(bruno.id))

    acme = await platform.get("/v1/teams", headers=_bearer(_token("acme", "sub-ana"), "acme"))
    ecomoda = await platform.get(
        "/v1/teams", headers=_bearer(_token("ecomoda", "sub-bruno"), "ecomoda")
    )

    assert [team["name"] for team in acme.json()] == ["Atlas"]
    assert [team["name"] for team in ecomoda.json()] == ["Moda"]


async def test_a_token_of_one_tenant_does_not_open_another(platform, session_factory):
    """Ana exists in acme only; the realm of acme signed her token. Naming ecomoda in the header
    is a 401: the token's issuer is not ecomoda's."""
    await stored_user(session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana"))
    token = _token("acme", "sub-ana")

    own = await platform.get("/v1/teams", headers=_bearer(token, "acme"))
    foreign = await platform.get("/v1/teams", headers=_bearer(token, "ecomoda"))

    assert own.status_code == 200
    assert foreign.status_code == 401 and foreign.json()["error"]["code"] == "not_authenticated"


async def test_the_same_person_in_two_tenants_has_two_separate_accounts(
    platform, session_factory, ecomoda_session_factory
):
    """The same Keycloak subject exists in both databases, each with its own user and teams."""
    shared = AppUserBuilder().with_subject("sub-same")
    acme_user = await stored_user(session_factory, shared.with_email("laura@acme.test"))
    ecomoda_user = await stored_user(
        ecomoda_session_factory, shared.with_email("laura@ecomoda.test")
    )
    await stored_team(session_factory, TeamBuilder().named("Atlas").with_admin(acme_user.id))

    acme = await platform.get("/v1/teams", headers=_bearer(_token("acme", "sub-same"), "acme"))
    ecomoda = await platform.get(
        "/v1/teams", headers=_bearer(_token("ecomoda", "sub-same"), "ecomoda")
    )

    assert [team["name"] for team in acme.json()] == ["Atlas"]
    assert ecomoda.json() == []  # her ecomoda account belongs to no team there
    assert ecomoda_user.id is not None


async def test_a_team_of_one_tenant_does_not_exist_in_another(
    platform, session_factory, ecomoda_session_factory
):
    ana = await stored_user(
        session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana")
    )
    team = await stored_team(session_factory, TeamBuilder().named("Atlas").with_admin(ana.id))
    await stored_user(
        ecomoda_session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana")
    )

    here = await platform.get(
        f"/v1/teams/{team.id}", headers=_bearer(_token("acme", "sub-ana"), "acme")
    )
    there = await platform.get(
        f"/v1/teams/{team.id}", headers=_bearer(_token("ecomoda", "sub-ana"), "ecomoda")
    )

    assert here.status_code == 200
    assert there.status_code == 403 and there.json()["error"]["code"] == "not_a_team_member"


async def test_the_members_of_a_team_are_read_from_the_database_of_its_tenant(
    platform, session_factory, ecomoda_session_factory
):
    """HU-06 through the real wiring: the list joins the memberships and the accounts of the
    tenant the request names, and an admin of a team in one tenant is nobody in another."""
    shared = AppUserBuilder().with_subject("sub-ana").named("Ana")
    ana = await stored_user(session_factory, shared.with_email("ana@acme.test"))
    bruno = await stored_user(
        session_factory, AppUserBuilder().with_email("bruno@acme.test").named("Bruno")
    )
    atlas = await stored_team(
        session_factory, TeamBuilder().named("Atlas").with_admin(ana.id).with_member(bruno.id)
    )
    ana_there = await stored_user(ecomoda_session_factory, shared.with_email("ana@ecomoda.test"))
    moda = await stored_team(
        ecomoda_session_factory, TeamBuilder().named("Moda").with_admin(ana_there.id)
    )

    here = await platform.get(
        f"/v1/users?team_id={atlas.id}", headers=_bearer(_token("acme", "sub-ana"), "acme")
    )
    there = await platform.get(
        f"/v1/users?team_id={moda.id}", headers=_bearer(_token("ecomoda", "sub-ana"), "ecomoda")
    )
    crossed = await platform.get(
        f"/v1/users?team_id={atlas.id}", headers=_bearer(_token("ecomoda", "sub-ana"), "ecomoda")
    )

    assert [member["email"] for member in here.json()["users"]] == [
        "ana@acme.test",
        "bruno@acme.test",
    ]
    assert [member["email"] for member in there.json()["users"]] == ["ana@ecomoda.test"]
    assert crossed.status_code == 403 and crossed.json()["error"]["code"] == "not_a_team_member"


async def test_an_invitation_is_only_found_in_the_database_of_its_tenant(platform, session_factory):
    team = await stored_team(session_factory)
    # The application of this fixture runs on the real clock (only the token validation uses a
    # fake one), so the invitation is issued now: one issued at the builder's fixed instant
    # would expire as the calendar moves on.
    await stored_invitation(
        session_factory,
        InvitationBuilder().for_team(team.id).issued_at_instant(datetime.now(UTC)),
    )
    body = {"token": InvitationBuilder().token}

    acme = await platform.post("/v1/invitations/status", json=body, headers={TENANT_HEADER: "acme"})
    ecomoda = await platform.post(
        "/v1/invitations/status", json=body, headers={TENANT_HEADER: "ecomoda"}
    )

    assert acme.status_code == 200
    assert ecomoda.status_code == 404 and ecomoda.json()["error"]["code"] == "invitation_not_found"


async def test_a_request_without_a_tenant_or_with_one_that_is_not_there_never_reaches_a_database(
    platform,
):
    assert (await platform.get("/v1/teams")).status_code == 400
    for tenant in ["nobody", "initech"]:  # initech is suspended
        response = await platform.get("/v1/teams", headers={TENANT_HEADER: tenant})
        assert (
            response.status_code == 404 and response.json()["error"]["code"] == "tenant_not_found"
        )
