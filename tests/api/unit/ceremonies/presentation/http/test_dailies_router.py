"""POST /v1/teams/{team_id}/dailies/current/token: the token of today's room is issued only to
a participant of the daily, at the moment it is asked for (AGI-59)."""

import logging
from datetime import timedelta

import pytest

from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER
from tests.api.builders import DAILY_TIME
from tests.api.unit.ceremonies.presentation.http.support import (
    LIVEKIT_URL,
    TOKEN_BRUNO,
    TOKEN_INACTIVE,
    TOKEN_OLGA,
    DailiesApi,
)

PATH = "/v1/teams/{team_id}/dailies/current/token"


@pytest.fixture
def api() -> DailiesApi:
    return DailiesApi()


def _error(response) -> dict:
    error = response.json()["error"]
    assert error["request_id"] and error["status"] == response.status_code
    return error


def _assert_nobody_got_in(api: DailiesApi) -> None:
    assert api.repository.ceremonies == {}
    assert api.rooms.opened == []
    assert api.rooms.admissions == []


async def test_a_participant_gets_the_token_of_todays_room(api):
    response = await api.join()

    assert response.status_code == 201
    (ceremony_id,) = api.repository.ceremonies
    room = f"acme-{ceremony_id}"
    expires_at = DAILY_TIME + timedelta(hours=2)
    assert response.json() == {
        "room_name": room,
        "token": f"token-{room}-{api.ana}-{expires_at.isoformat()}",
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "livekit_url": LIVEKIT_URL,
    }
    assert response.headers["cache-control"] == "no-store"
    assert api.rooms.opened == [room]


async def test_without_a_session_it_answers_401_before_any_403(api):
    """Not even a team of which nobody knows it is a member is looked at."""
    missing = await api.join(token=None)
    forged = await api.join(token="token-that-is-not-valid", team_id=api.boreal)

    for response in (missing, forged):
        assert response.status_code == 401
        assert _error(response)["code"] == "not_authenticated"
        assert response.headers["www-authenticate"] == "Bearer"
    _assert_nobody_got_in(api)


async def test_an_account_that_is_not_active_answers_403(api):
    response = await api.join(token=TOKEN_INACTIVE)

    assert response.status_code == 403
    assert _error(response)["code"] == "account_not_active"
    _assert_nobody_got_in(api)


async def test_the_link_forwarded_to_someone_outside_the_team_does_not_let_them_in(api):
    """Olga signs in with her own session: the link carries no token, and she is not a member."""
    response = await api.join(token=TOKEN_OLGA)

    assert response.status_code == 403
    assert _error(response)["code"] == "not_a_team_member"
    assert "token" not in response.json()
    _assert_nobody_got_in(api)


async def test_a_member_who_is_not_in_the_round_answers_403_even_the_admin(api):
    response = await api.join(token=TOKEN_BRUNO)

    assert response.status_code == 403
    assert _error(response)["code"] == "not_a_daily_participant"
    _assert_nobody_got_in(api)


async def test_a_team_without_an_active_sprint_answers_409_no_active_sprint(api):
    response = await api.join(team_id=api.boreal)

    assert response.status_code == 409
    assert _error(response)["code"] == "no_active_sprint"
    _assert_nobody_got_in(api)


async def test_outside_the_window_of_the_daily_it_answers_409_daily_not_open(api):
    api.clock.advance(hours=1)

    response = await api.join()

    assert response.status_code == 409
    assert _error(response)["code"] == "daily_not_open"
    _assert_nobody_got_in(api)


async def test_when_the_room_server_does_not_answer_it_answers_503(api):
    api.rooms.unavailable = True

    response = await api.join()

    assert response.status_code == 503
    assert _error(response)["code"] == "room_service_unavailable"
    assert api.rooms.admissions == []


async def test_a_team_id_that_is_not_a_uuid_answers_422(api):
    response = await api.join(team_id="not-a-uuid")

    assert response.status_code == 422
    assert _error(response)["code"] == "validation_error"


@pytest.mark.parametrize(
    ("tenant", "status", "code"),
    [(None, 400, "tenant_required"), ("nobody", 404, "tenant_not_found")],
)
async def test_the_tenant_is_checked_before_the_session(api, tenant, status, code):
    response = await api.join(token=None, tenant=tenant)

    assert response.status_code == status
    assert _error(response)["code"] == code


async def test_the_token_never_reaches_the_logs(api, caplog):
    caplog.set_level(logging.DEBUG)

    response = await api.join()

    assert response.status_code == 201
    assert response.json()["room_name"] in caplog.text
    assert response.json()["token"] not in caplog.text


async def test_the_openapi_documents_the_route_and_every_answer(api):
    async with api.client() as client:
        spec = (await client.get("/openapi.json")).json()

    operation = spec["paths"][PATH]["post"]
    responses = operation["responses"]
    assert operation["tags"] == ["ceremonies"]
    assert set(responses) == {"201", "400", "401", "403", "404", "409", "422", "500", "503"}
    assert responses["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RoomAdmissionResponse"
    }
    for code in ("`account_not_active`", "`not_a_team_member`", "`not_a_daily_participant`"):
        assert code in responses["403"]["description"]
    for code in ("`no_active_sprint`", "`daily_not_open`"):
        assert code in responses["409"]["description"]
    assert "`room_service_unavailable`" in responses["503"]["description"]
    assert "requestBody" not in operation
    assert [p["name"] for p in operation["parameters"]] == ["team_id", TENANT_HEADER]
