"""AGI-64 / AGI-125 / AGI-126 end to end over HTTP: the real wiring against PostgreSQL, with the
worker's token signed for real by a simulated realm of each tenant.

One call gives the worker the tenant, the sprint and its day, the participants in turn order,
the language and the mode (the story's first test case). A worker token of another tenant's
realm is a 401 (the fourth one). On close the worker delivers the attributed transcript and the
events once, however many times it retries (CA2, CA6). Nothing but the realm's key set is
doubled: the container of each tenant, its database and the token's verification are the ones
the API runs with.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from agilina_api.bootstrap.app import create_app
from agilina_api.bootstrap.container import Container
from agilina_api.bootstrap.tenants import current_container
from agilina_api.ceremonies.infrastructure.persistence.orm_models import (
    CeremonyResultRow,
    TranscriptSegmentRow,
)
from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from agilina_api.identity.infrastructure.keycloak.authenticated_workers import (
    KeycloakAuthenticatedWorkers,
)
from agilina_api.shared.presentation.http.access import get_authenticated_workers
from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER, get_tenant_directory
from agilina_shared import CeremonyEventType
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
from tests.shared.builders import (
    CeremonyEventBuilder,
    CeremonyResultBuilder,
    TranscriptSegmentBuilder,
)

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


def _assert_reveals_nothing_of(response, team, sprint, *people) -> None:
    """The error is the generic one, and nothing of the ceremony's tenant shows in it."""
    values = ["acme", team.id, team.name, sprint.id]
    values += [value for person in people for value in (person.id, person.full_name)]
    assert set(response.json()["error"]) == {"status", "code", "message", "request_id"}
    assert [value for value in values if str(value) in response.text] == []


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
    """Ecomoda's worker, with its own valid token, does not find a ceremony of acme, and the
    answer says nothing of it."""
    ceremony_id, team, sprint, ana, carla = await _scheduled_daily(session_factory)

    response = await api.get(
        f"/v1/ceremonies/{ceremony_id}/context",
        headers=_headers(_worker_token("ecomoda"), "ecomoda"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ceremony_not_found"
    _assert_reveals_nothing_of(response, team, sprint, ana, carla)


async def test_the_context_carries_the_tenant_of_the_header(api, ecomoda_session_factory):
    """Ecomoda's worker gets its own ceremony with ecomoda as the tenant (acme's is above)."""
    ceremony_id, *_ = await _scheduled_daily(ecomoda_session_factory)

    response = await api.get(
        f"/v1/ceremonies/{ceremony_id}/context",
        headers=_headers(_worker_token("ecomoda"), "ecomoda"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["tenant"] == "ecomoda"
    assert response.json()["room"] == f"ecomoda-{ceremony_id}"


async def test_a_person_of_the_tenant_cannot_ask_for_the_context(api, session_factory):
    ceremony_id, *_ = await _scheduled_daily(session_factory)
    person = AccessTokenBuilder().issued_by(f"{REALMS}acme").build()

    response = await api.get(
        f"/v1/ceremonies/{ceremony_id}/context", headers=_headers(person, "acme")
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_worker"


# ------------------------------------------------------- the result (AGI-126) --
def _result_of(ceremony_id, *speakers) -> dict:
    """What the worker posts: each speaker said one thing in their turn."""
    return (
        CeremonyResultBuilder()
        .for_ceremony(ceremony_id)
        .with_present(*(speaker.id for speaker in speakers))
        .with_segments(*(TranscriptSegmentBuilder().said_by(s.id).build() for s in speakers))
        .with_events(
            *(
                CeremonyEventBuilder().of_type(CeremonyEventType.TURN_STARTED).about(s.id).build()
                for s in speakers
            )
        )
        .build()
        .model_dump(mode="json")
    )


async def _count(session_factory, row, ceremony_id) -> int:
    async with session_factory() as session:
        query = select(func.count()).select_from(row).where(row.ceremony_id == ceremony_id)
        return (await session.execute(query)).scalar_one()


async def test_the_worker_delivers_the_result_once_however_many_times_it_retries(
    api, session_factory
):
    ceremony_id, _, _, ana, carla = await _scheduled_daily(session_factory)
    url = f"/v1/ceremonies/{ceremony_id}/result"
    headers = _headers(_worker_token("acme"), "acme")
    body = _result_of(ceremony_id, carla, ana)

    first = await api.post(url, json=body, headers=headers)
    retry = await api.post(url, json=body, headers=headers)
    another = await api.post(url, json=_result_of(ceremony_id, ana), headers=headers)

    assert (first.status_code, retry.status_code) == (202, 202), first.text
    assert first.json() == retry.json() == {"status": "received"}
    assert another.status_code == 409
    assert another.json()["error"]["code"] == "result_already_received"
    assert await _count(session_factory, CeremonyResultRow, ceremony_id) == 1
    assert await _count(session_factory, TranscriptSegmentRow, ceremony_id) == 2


async def test_a_result_with_someone_outside_the_sprint_is_refused_and_not_stored(
    api, session_factory
):
    ceremony_id, *_ = await _scheduled_daily(session_factory)
    outsider = await stored_user(session_factory)

    response = await api.post(
        f"/v1/ceremonies/{ceremony_id}/result",
        json=_result_of(ceremony_id, outsider),
        headers=_headers(_worker_token("acme"), "acme"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"] == {
        "fields": [
            {"field": "body.segments.0.user_id", "reason": "not_a_participant"},
            {"field": "body.events.0.user_id", "reason": "not_a_participant"},
        ]
    }
    assert str(outsider.id) not in response.text
    assert await _count(session_factory, CeremonyResultRow, ceremony_id) == 0


async def test_a_result_reaches_only_the_database_of_its_tenant(api, session_factory):
    """Ecomoda's worker cannot deliver to a ceremony of acme, and its token is no good in acme."""
    ceremony_id, team, sprint, ana, carla = await _scheduled_daily(session_factory)
    url = f"/v1/ceremonies/{ceremony_id}/result"
    body = _result_of(ceremony_id, ana)

    elsewhere = await api.post(
        url, json=body, headers=_headers(_worker_token("ecomoda"), "ecomoda")
    )
    crossed = await api.post(url, json=body, headers=_headers(_worker_token("ecomoda"), "acme"))

    assert elsewhere.status_code == 404
    assert elsewhere.json()["error"]["code"] == "ceremony_not_found"
    _assert_reveals_nothing_of(elsewhere, team, sprint, ana, carla)
    assert crossed.status_code == 401
    assert crossed.json()["error"]["code"] == "not_authenticated"
    assert await _count(session_factory, CeremonyResultRow, ceremony_id) == 0
