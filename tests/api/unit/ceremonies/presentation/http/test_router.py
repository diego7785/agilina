"""The worker ↔ API contract is published in the specification. Asking for the context
(AGI-125) and delivering the result (AGI-126) are the worker's only."""

import pytest
from httpx import AsyncClient

from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER
from agilina_shared import CeremonyEventType
from tests.api.builders import next_id
from tests.api.unit.ceremonies.presentation.http.support import TOKEN_PERSON, Api
from tests.shared.builders import (
    CeremonyEventBuilder,
    CeremonyResultBuilder,
    TranscriptSegmentBuilder,
)


async def test_the_specification_publishes_the_two_worker_operations(client: AsyncClient):
    specification = (await client.get("/openapi.json")).json()

    paths = specification["paths"]
    assert "/v1/ceremonies/{ceremony_id}/context" in paths
    assert "/v1/ceremonies/{ceremony_id}/result" in paths


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


# ----------------------------------------------------- ceremony result (AGI-126) --
def _result(api: Api, ceremony_id=None) -> CeremonyResultBuilder:
    """Ana spoke in her turn of the daily."""
    return (
        CeremonyResultBuilder()
        .for_ceremony(ceremony_id or api.ceremony.ceremony_id)
        .with_present(api.ana)
        .with_segments(TranscriptSegmentBuilder().said_by(api.ana).build())
        .with_events(
            CeremonyEventBuilder().of_type(CeremonyEventType.TURN_STARTED).about(api.ana).build()
        )
    )


async def test_the_worker_delivers_the_result_and_gets_a_receipt(api):
    result = _result(api).build()

    response = await api.deliver(api.ceremony.ceremony_id, result)

    assert response.status_code == 202
    assert response.json() == {"status": "received"}
    assert api.repository.results[api.ceremony.ceremony_id].result == result


async def test_the_same_result_again_answers_202_without_storing_it_twice(api):
    result = _result(api).build()
    await api.deliver(api.ceremony.ceremony_id, result)

    again = await api.deliver(api.ceremony.ceremony_id, result)

    assert again.status_code == 202
    assert again.json() == {"status": "received"}
    assert list(api.repository.results) == [api.ceremony.ceremony_id]


async def test_another_result_for_the_ceremony_answers_409_result_already_received(api):
    await api.deliver(api.ceremony.ceremony_id, _result(api).build())

    response = await api.deliver(
        api.ceremony.ceremony_id,
        CeremonyResultBuilder().for_ceremony(api.ceremony.ceremony_id).build(),
    )

    assert response.status_code == 409
    assert _error(response)["code"] == "result_already_received"


async def test_a_result_with_someone_who_is_not_a_participant_says_where_never_who(api):
    stranger = next_id()
    result = (
        _result(api)
        .with_segments(
            TranscriptSegmentBuilder().said_by(api.ana).build(),
            TranscriptSegmentBuilder().said_by(stranger).build(),
        )
        .with_events(
            CeremonyEventBuilder().of_type(CeremonyEventType.TURN_STARTED).about(stranger).build()
        )
        .build()
    )

    response = await api.deliver(api.ceremony.ceremony_id, result)

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation_error"
    assert error["details"] == {
        "fields": [
            {"field": "body.segments.1.user_id", "reason": "not_a_participant"},
            {"field": "body.events.0.user_id", "reason": "not_a_participant"},
        ]
    }
    assert str(stranger) not in response.text
    assert api.repository.results == {}


async def test_a_result_of_another_ceremony_answers_422_on_the_ceremony_id(api):
    response = await api.deliver(api.ceremony.ceremony_id, _result(api, next_id()).build())

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation_error"
    assert error["details"] == {
        "fields": [{"field": "body.ceremony_id", "reason": "does_not_match_path"}]
    }


async def test_a_segment_that_ends_before_it_starts_answers_422(api):
    body = _result(api).build().model_dump(mode="json")
    body["segments"][0].update(start_ms=2400, end_ms=1000)

    response = await api.deliver(api.ceremony.ceremony_id, body)

    assert response.status_code == 422
    assert _error(response)["code"] == "validation_error"


async def test_a_result_of_a_ceremony_that_does_not_exist_answers_404(api):
    unknown = next_id()

    response = await api.deliver(unknown, _result(api, unknown).build())

    assert response.status_code == 404
    assert _error(response)["code"] == "ceremony_not_found"


async def test_a_result_of_a_ceremony_of_a_sprint_no_longer_active_answers_404(api):
    past = api.past_ceremony.ceremony_id

    response = await api.deliver(past, CeremonyResultBuilder().for_ceremony(past).build())

    assert response.status_code == 404
    assert _error(response)["code"] == "ceremony_not_found"


async def test_without_a_valid_worker_token_the_result_answers_401(api):
    result = _result(api).build()
    missing = await api.deliver(api.ceremony.ceremony_id, result, token=None)
    forged = await api.deliver(api.ceremony.ceremony_id, result, token="token-of-another-realm")

    for response in (missing, forged):
        assert response.status_code == 401
        assert _error(response)["code"] == "not_authenticated"
    assert api.repository.results == {}


async def test_a_person_cannot_deliver_a_result_even_of_a_ceremony_that_does_not_exist(api):
    unknown = next_id()
    own = await api.deliver(api.ceremony.ceremony_id, _result(api).build(), token=TOKEN_PERSON)
    other = await api.deliver(unknown, _result(api, unknown).build(), token=TOKEN_PERSON)

    for response in (own, other):
        assert response.status_code == 403
        assert _error(response)["code"] == "not_a_worker"
    assert api.repository.results == {}


@pytest.mark.parametrize(
    ("tenant", "status", "code"),
    [(None, 400, "tenant_required"), ("nobody", 404, "tenant_not_found")],
)
async def test_the_result_checks_the_tenant_before_the_token(api, tenant, status, code):
    response = await api.deliver(
        api.ceremony.ceremony_id, _result(api).build(), token=None, tenant=tenant
    )

    assert response.status_code == status
    assert _error(response)["code"] == code


async def test_the_openapi_documents_the_result_and_every_answer(api):
    async with api.client() as client:
        spec = (await client.get("/openapi.json")).json()

    operation = spec["paths"]["/v1/ceremonies/{ceremony_id}/result"]["post"]
    responses = operation["responses"]
    assert set(responses) == {"202", "400", "401", "403", "404", "409", "422", "500"}
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CeremonyResult"
    }
    assert responses["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ResultReceipt"
    }
    assert "`result_already_received`" in responses["409"]["description"]
    assert "`ceremony_not_found`" in responses["404"]["description"]
    assert "`not_a_worker`" in responses["403"]["description"]
