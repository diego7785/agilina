"""AGI-59 / AGI-131 end to end over HTTP: joining today's daily against PostgreSQL and two tenants.

The link to the room carries no access: whoever opens it asks the API for a token, and only a
participant of the daily, with a session of the tenant, gets one. A forwarded link opened
without a session, with a session of another tenant, by someone outside the team or by a member
who was not summoned gets nothing, and no ceremony is stored nor room opened for them. The
wiring is the real one: the tenant's database, the token's verification against the issuer of
each tenant's realm and the LiveKit adapter, which signs for real. Only the realm's key set and
LiveKit's server (an ``httpx.MockTransport``) are simulated, so it runs in CI without LiveKit.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from agilina_api.bootstrap.app import create_app
from agilina_api.bootstrap.container import Container
from agilina_api.bootstrap.context_adapters import TeamsBackedCeremonyRoster
from agilina_api.bootstrap.tenants import current_container
from agilina_api.ceremonies.application.commands.join_current_daily import (
    JoinCurrentDailyHandler,
)
from agilina_api.ceremonies.infrastructure.livekit.livekit_rooms import (
    CREATE_ROOM_PATH,
    LiveKitRooms,
)
from agilina_api.ceremonies.infrastructure.persistence.orm_models import CeremonyRow
from agilina_api.ceremonies.infrastructure.persistence.unit_of_work import (
    ceremonies_unit_of_work_factory,
)
from agilina_api.ceremonies.presentation.http.dependencies import get_join_current_daily_handler
from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from agilina_api.identity.infrastructure.keycloak.authenticated_users import (
    KeycloakAuthenticatedUsers,
)
from agilina_api.shared.infrastructure.database.session import create_session_factory
from agilina_api.shared.presentation.http.access import get_authenticated_users
from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER, get_tenant_directory
from agilina_api.teams.infrastructure.persistence.sql_sprint_queries import SqlSprintQueries
from agilina_api.teams.infrastructure.persistence.team_queries import SqlTeamQueries
from agilina_shared.sprint_calendar import JOIN_WINDOW_TAIL
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
URL = "/v1/teams/{team_id}/dailies/current/token"
LIVEKIT_URL = "wss://livekit.example.test"
LIVEKIT_SECRET = "a-test-secret-long-enough-for-hs256-0123"  # >= 32 bytes, as pyjwt asks
IN_THE_WINDOW = datetime(2026, 10, 7, 14, 5, tzinfo=UTC)
"""Five minutes into the daily of Wednesday 2026-10-07 (09:00 in Bogota), day 3 of the sprint."""


class FakeLiveKit:
    """Answers like LiveKit's RoomService and remembers the rooms it was asked to open."""

    def __init__(self) -> None:
        self.status = 200
        self.opened: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == CREATE_ROOM_PATH
        name = json.loads(request.content)["name"]
        self.opened.append(name)
        return httpx.Response(self.status, json={"name": name})


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(IN_THE_WINDOW)


@pytest.fixture
def livekit() -> FakeLiveKit:
    return FakeLiveKit()


@pytest.fixture
async def api(engine, ecomoda_engine, clock, livekit) -> AsyncIterator[AsyncClient]:
    """The API on the databases of this run (``engine`` and ``ecomoda_engine`` start them
    empty). Each tenant's people are checked against the issuer of that tenant's realm, and the
    daily is joined with the real handler over that tenant's database and the real LiveKit
    adapter, both on ``clock``."""
    app: FastAPI = create_app()
    app.dependency_overrides[get_tenant_directory] = lambda: FakeTenantDirectory(
        TenantBuilder().build(), TenantBuilder().ecomoda().build()
    )
    rooms = LiveKitRooms(
        url=LIVEKIT_URL,
        api_key="test-api-key",
        api_secret=LIVEKIT_SECRET,
        client=httpx.AsyncClient(transport=httpx.MockTransport(livekit.handler)),
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

    # The container builds LiveKitRooms from settings, so this mirrors its wiring with a mock
    # transport and the test's clock.
    def join_in_the_tenant(container: Container = Depends(current_container)):
        sessions = create_session_factory(container.engine)
        return JoinCurrentDailyHandler(
            ceremonies_unit_of_work_factory(sessions),
            TeamsBackedCeremonyRoster(SqlTeamQueries(sessions), SqlSprintQueries(sessions)),
            rooms,
            clock,
            LIVEKIT_URL,
        )

    app.dependency_overrides[get_authenticated_users] = users_of_the_tenant
    app.dependency_overrides[get_join_current_daily_handler] = join_in_the_tenant
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://tests") as client:
        yield client
        await app.state.tenant_containers.aclose()
    await rooms.aclose()


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
    """Atlas, whose active sprint has Ana (its admin) and Carla as the daily's participants;
    Bruno is a member who was not summoned."""
    ana, carla, bruno = [
        await stored_user(session_factory, AppUserBuilder().with_unique_email().with_subject(sub))
        for sub in ("sub-ana", "sub-carla", "sub-bruno")
    ]
    team = await stored_team(
        session_factory,
        TeamBuilder().with_admin(ana.id).with_member(carla.id).with_member(bruno.id),
    )
    await stored_sprint(
        session_factory, SprintBuilder().for_team(team).with_participants(ana.id, carla.id)
    )
    return team, ana


async def _ceremonies(session_factory, team) -> int:
    async with session_factory() as session:
        query = select(func.count()).select_from(CeremonyRow).where(CeremonyRow.team_id == team.id)
        return (await session.execute(query)).scalar_one()


async def test_a_summoned_participant_gets_a_two_hour_audio_token_for_todays_room(
    api, session_factory, clock, livekit
):
    team, ana = await _daily_of_atlas(session_factory)

    response = await api.post(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-ana")
    )

    assert response.status_code == 201, response.text
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    # The token expires on the fake clock, not on the wall clock pyjwt reads.
    claims = jwt.decode(
        body["token"], LIVEKIT_SECRET, algorithms=["HS256"], options={"verify_exp": False}
    )
    assert claims["sub"] == str(ana.id)
    assert claims["exp"] == int((clock.now() + timedelta(hours=2)).timestamp())
    assert claims["video"] == {
        "room": body["room_name"],
        "roomJoin": True,
        "canPublish": True,
        "canPublishSources": ["microphone"],
        "canSubscribe": True,
        "canPublishData": False,
    }
    assert body["livekit_url"] == LIVEKIT_URL
    assert livekit.opened == [body["room_name"]]
    assert await _ceremonies(session_factory, team) == 1


# --------------------------------------------- the link forwarded to a third person --
async def _nobody_got_in(response, code, session_factory, team, livekit) -> None:
    assert response.json()["error"]["code"] == code
    assert set(response.json()) == {"error"}
    assert await _ceremonies(session_factory, team) == 0
    assert livekit.opened == []


async def test_a_forwarded_link_without_a_session_is_401(api, session_factory, livekit):
    team, _ = await _daily_of_atlas(session_factory)

    response = await api.post(URL.format(team_id=team.id), headers={TENANT_HEADER: "acme"})

    assert response.status_code == 401
    await _nobody_got_in(response, "not_authenticated", session_factory, team, livekit)


async def test_a_forwarded_link_with_a_session_of_another_tenant_is_401(
    api, session_factory, ecomoda_session_factory, clock, livekit
):
    """Ana's subject exists in ecomoda too, but ecomoda's realm signed the token."""
    team, _ = await _daily_of_atlas(session_factory)
    await stored_user(
        ecomoda_session_factory, AppUserBuilder().with_unique_email().with_subject("sub-ana")
    )
    headers = {**_headers(clock, "ecomoda", "sub-ana"), TENANT_HEADER: "acme"}

    response = await api.post(URL.format(team_id=team.id), headers=headers)

    assert response.status_code == 401
    await _nobody_got_in(response, "not_authenticated", session_factory, team, livekit)


async def test_a_forwarded_link_to_someone_outside_the_team_is_403_not_a_team_member(
    api, session_factory, clock, livekit
):
    team, _ = await _daily_of_atlas(session_factory)
    await stored_user(
        session_factory, AppUserBuilder().with_unique_email().with_subject("sub-outsider")
    )

    response = await api.post(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-outsider")
    )

    assert response.status_code == 403
    await _nobody_got_in(response, "not_a_team_member", session_factory, team, livekit)


async def test_a_member_who_was_not_summoned_is_403_not_a_daily_participant(
    api, session_factory, clock, livekit
):
    team, _ = await _daily_of_atlas(session_factory)

    response = await api.post(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-bruno")
    )

    assert response.status_code == 403
    await _nobody_got_in(response, "not_a_daily_participant", session_factory, team, livekit)


async def test_outside_the_window_the_daily_is_409_not_open(api, session_factory, clock, livekit):
    """Fifteen minutes after the start is already out: the window excludes it."""
    team, _ = await _daily_of_atlas(session_factory)
    clock.current = datetime(2026, 10, 7, 14, 0, tzinfo=UTC) + JOIN_WINDOW_TAIL

    response = await api.post(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-ana")
    )

    assert response.status_code == 409
    await _nobody_got_in(response, "daily_not_open", session_factory, team, livekit)


# ------------------------------------------------------------------ one room per daily --
async def test_two_dailies_in_a_row_get_two_rooms_with_the_tenant_in_the_name(
    api, session_factory, clock, livekit
):
    team, _ = await _daily_of_atlas(session_factory)
    url = URL.format(team_id=team.id)

    today = await api.post(url, headers=_headers(clock, "acme", "sub-ana"))
    clock.advance(days=1)
    tomorrow = await api.post(url, headers=_headers(clock, "acme", "sub-ana"))

    assert (today.status_code, tomorrow.status_code) == (201, 201), today.text + tomorrow.text
    rooms = [today.json()["room_name"], tomorrow.json()["room_name"]]
    assert rooms[0] != rooms[1]
    assert livekit.opened == rooms
    assert all(room.startswith("acme-") for room in rooms)
    assert await _ceremonies(session_factory, team) == 2


async def test_two_participants_joining_at_once_share_one_ceremony(api, session_factory, clock):
    team, _ = await _daily_of_atlas(session_factory)
    url = URL.format(team_id=team.id)

    ana, carla = await asyncio.gather(
        api.post(url, headers=_headers(clock, "acme", "sub-ana")),
        api.post(url, headers=_headers(clock, "acme", "sub-carla")),
    )

    assert (ana.status_code, carla.status_code) == (201, 201), ana.text + carla.text
    assert ana.json()["room_name"] == carla.json()["room_name"]
    assert await _ceremonies(session_factory, team) == 1


async def test_the_room_service_down_is_503_room_service_unavailable(
    api, session_factory, clock, livekit
):
    team, _ = await _daily_of_atlas(session_factory)
    livekit.status = 503

    response = await api.post(
        URL.format(team_id=team.id), headers=_headers(clock, "acme", "sub-ana")
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "room_service_unavailable"
    assert set(response.json()) == {"error"}
