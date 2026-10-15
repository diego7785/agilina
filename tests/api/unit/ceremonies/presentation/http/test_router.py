"""The worker ↔ API contract is published in the specification from the first
commit, even though delivering the result arrives with AGI-126. Asking for the context is
the worker's only (AGI-125)."""

import pytest
from httpx import AsyncClient

from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER
from tests.api.builders import next_id
from tests.api.unit.ceremonies.presentation.http.support import TOKEN_PERSON, Api


async def test_the_specification_publishes_the_two_worker_operations(client: AsyncClient):
    specification = (await client.get("/openapi.json")).json()

    paths = specification["paths"]
    assert "/v1/ceremonies/{ceremony_id}/context" in paths
    assert "/v1/ceremonies/{ceremony_id}/result" in paths


async def test_delivering_a_result_is_not_implemented_yet(client: AsyncClient):
    ceremony_id = "8f2f0d7e-0e4c-4a2e-9a0e-0b3b1a4a1c11"
    result = {
        "ceremony_id": ceremony_id,
        "status": "completed",
        "started_at": "2026-10-04T14:00:00Z",
        "closed_at": "2026-10-04T14:15:00Z",
        "present_participants": [],
        "segments": [],
        "events": [],
    }

    response = await client.post(f"/v1/ceremonies/{ceremony_id}/result", json=result)

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"


# ---------------------------------------------------- ceremony context (AGI-125) --
@pytest.fixture
def api() -> Api:
    return Api()


def _error(response) -> dict:
    error = response.json()["error"]
    assert error["request_id"] and error["status"] == response.status_code
    return error


async def test_the_worker_gets_the_context_of_the_ceremony_in_one_call(api):
    ceremony = api.ceremony

    response = await api.context(ceremony.ceremony_id)

    assert response.status_code == 200
    assert response.json() == {
        "tenant": "acme",
        "ceremony_id": str(ceremony.ceremony_id),
        "team_id": str(ceremony.team_id),
        "sprint_id": str(ceremony.sprint_id),
        "room": f"acme-{ceremony.ceremony_id}",
        "language": "en",
        "mode": "support",
        "sprint_day": 1,
        "sprint_total_days": 12,
        "participants": [
            {
                "user_id": str(api.ana),
                "name": "Ana Gil",
                "room_identity": str(api.ana),
                "role": "admin",
                "turn_order": 1,
            }
        ],
        "silence_seconds": 10,
        "stuck_turn_seconds": 30,
    }


async def test_without_a_token_or_with_one_that_is_not_valid_it_answers_401(api):
    """A worker token of another tenant's realm is not valid here either (AD-29)."""
    missing = await api.context(api.ceremony.ceremony_id, token=None)
    forged = await api.context(api.ceremony.ceremony_id, token="token-of-another-realm")

    for response in (missing, forged):
        assert response.status_code == 401
        assert _error(response)["code"] == "not_authenticated"
        assert response.headers["www-authenticate"] == "Bearer"


async def test_a_person_cannot_ask_for_the_context_even_of_a_ceremony_that_does_not_exist(api):
    """The 403 comes before the ceremony is looked up: a person cannot tell which exist."""
    own = await api.context(api.ceremony.ceremony_id, token=TOKEN_PERSON)
    unknown = await api.context(next_id(), token=TOKEN_PERSON)

    for response in (own, unknown):
        assert response.status_code == 403
        assert _error(response)["code"] == "not_a_worker"
    assert "Ana Gil" not in own.text


async def test_a_ceremony_that_does_not_exist_answers_404_ceremony_not_found(api):
    response = await api.context(next_id())

    assert response.status_code == 404
    assert _error(response)["code"] == "ceremony_not_found"


async def test_a_ceremony_of_a_sprint_that_is_no_longer_active_answers_404(api):
    response = await api.context(api.past_ceremony.ceremony_id)

    assert response.status_code == 404
    assert _error(response)["code"] == "ceremony_not_found"


async def test_a_ceremony_id_that_is_not_a_uuid_answers_422(api):
    response = await api.context("not-a-uuid")

    assert response.status_code == 422
    assert _error(response)["code"] == "validation_error"


@pytest.mark.parametrize(
    ("tenant", "status", "code"),
    [(None, 400, "tenant_required"), ("nobody", 404, "tenant_not_found")],
)
async def test_the_tenant_is_checked_before_the_token(api, tenant, status, code):
    response = await api.context(api.ceremony.ceremony_id, token=None, tenant=tenant)

    assert response.status_code == status
    assert _error(response)["code"] == code


async def test_the_openapi_documents_the_context_and_every_answer(api):
    async with api.client() as client:
        spec = (await client.get("/openapi.json")).json()

    operation = spec["paths"]["/v1/ceremonies/{ceremony_id}/context"]["get"]
    responses = operation["responses"]
    assert set(responses) == {"200", "400", "401", "403", "404", "422", "500"}
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CeremonyContext"
    }
    assert "`not_a_worker`" in responses["403"]["description"]
    assert "`ceremony_not_found`" in responses["404"]["description"]
    assert "`tenant_not_found`" in responses["404"]["description"]
    assert [p["name"] for p in operation["parameters"]] == ["ceremony_id", TENANT_HEADER]
