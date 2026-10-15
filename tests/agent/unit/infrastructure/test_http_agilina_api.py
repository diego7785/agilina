"""The worker adapter against the API, and its two failure paths (docs/contrato-worker-api.md):

* without the context there is one request and no retry (CA5);
* the result is kept on disk and retried while it may be transient, until a 202 (CA6).
"""

import json
import logging
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from agilina_agent.application.errors import ContextUnavailableError
from agilina_agent.infrastructure.http_agilina_api import (
    FIRST_RETRY_WAIT_SECONDS,
    MAX_RETRY_WAIT_SECONDS,
    HttpAgilinaApi,
)
from agilina_agent.infrastructure.pending_results import PendingResults
from agilina_agent.infrastructure.worker_token_unavailable_error import (
    WorkerTokenUnavailableError,
)
from agilina_agent.infrastructure.worker_tokens import KeycloakWorkerTokens
from agilina_shared.contract import CeremonyResult
from tests.agent.doubles import FakeTokenEndpoint, FakeWorkerTokens, RecordedSleep, ScriptedApi
from tests.shared.builders import TENANT, CeremonyContextBuilder, CeremonyResultBuilder

BASE_URL = "http://api.internal"
ACCEPTED = httpx.Response(202, json={"status": "received"})


def _keycloak_tokens(keycloak: FakeTokenEndpoint) -> KeycloakWorkerTokens:
    return KeycloakWorkerTokens(
        keycloak_url="http://auth.internal",
        realm_prefix="agilina-",
        client_id="agilina-worker",
        secret_of=lambda slug: SecretStr(f"{slug}-worker-secret"),
        client=keycloak.client(),
    )


def _error(status: int, code: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"status": status, "code": code, "message": "x", "request_id": "r-1"}},
    )


def _api(
    server: ScriptedApi,
    pending: PendingResults,
    sleep: RecordedSleep | None = None,
    tokens: FakeWorkerTokens | None = None,
) -> HttpAgilinaApi:
    return HttpAgilinaApi(
        base_url=f"{BASE_URL}/",
        token_for=(tokens or FakeWorkerTokens()).token_for,
        pending=pending,
        client=server.client(),
        sleep=sleep or RecordedSleep(),
    )


@pytest.fixture
def pending(tmp_path: Path) -> PendingResults:
    return PendingResults(tmp_path)


def _kept(pending: PendingResults) -> list[CeremonyResult]:
    return [result for _, result in pending.pending()]


# --------------------------------------------------------------- context ---


async def test_the_context_is_asked_with_the_token_and_the_tenant_of_the_ceremony(
    pending: PendingResults,
) -> None:
    context = CeremonyContextBuilder().build()
    server = ScriptedApi(httpx.Response(200, content=context.model_dump_json()))

    received = await _api(server, pending).get_context(TENANT, context.ceremony_id)

    assert received == context
    [request] = server.requests
    assert request.method == "GET"
    assert str(request.url) == f"{BASE_URL}/v1/ceremonies/{context.ceremony_id}/context"
    assert request.headers["Authorization"] == f"Bearer token-of-{TENANT}"
    assert request.headers["X-Agilina-Tenant"] == TENANT


@pytest.mark.parametrize(
    "reply",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        _error(500, "internal_error"),
        _error(503, "unavailable"),
        _error(401, "not_authenticated"),
        _error(403, "not_a_worker"),
        _error(404, "ceremony_not_found"),
        httpx.Response(200, json={"tenant": TENANT}),
        httpx.Response(200, content=b"<html>"),
    ],
    ids=[
        "transport",
        "timeout",
        "500",
        "503",
        "401",
        "403",
        "404",
        "body-off-contract",
        "body-not-json",
    ],
)
async def test_any_failure_asking_for_the_context_is_one_request_and_no_context(
    pending: PendingResults, reply: httpx.Response | Exception
) -> None:
    server = ScriptedApi(reply)
    sleep = RecordedSleep()
    ceremony_id = CeremonyContextBuilder().build().ceremony_id

    with pytest.raises(ContextUnavailableError):
        await _api(server, pending, sleep).get_context(TENANT, ceremony_id)

    assert len(server.requests) == 1
    assert sleep.waits == []


async def test_the_log_names_the_status_and_code_of_the_api_but_never_the_body(
    pending: PendingResults, caplog: pytest.LogCaptureFixture
) -> None:
    body = {"error": {"code": "ceremony_not_found", "message": "Diego's secret ceremony"}}
    server = ScriptedApi(httpx.Response(404, json=body))

    with pytest.raises(ContextUnavailableError):
        await _api(server, pending).get_context(
            TENANT, CeremonyContextBuilder().build().ceremony_id
        )

    assert "HTTP 404 ceremony_not_found" in caplog.text
    assert "Diego" not in caplog.text


async def test_without_a_worker_token_the_context_is_not_even_asked(
    pending: PendingResults,
) -> None:
    server = ScriptedApi(ACCEPTED)
    api = _api(server, pending, tokens=FakeWorkerTokens(TENANT))

    with pytest.raises(ContextUnavailableError):
        await api.get_context(TENANT, CeremonyContextBuilder().build().ceremony_id)

    assert server.requests == []


async def test_a_room_tenant_that_is_not_a_slug_builds_no_request_at_all(
    pending: PendingResults,
) -> None:
    keycloak = FakeTokenEndpoint()
    server = ScriptedApi(ACCEPTED)
    api = HttpAgilinaApi(
        BASE_URL, _keycloak_tokens(keycloak).token_for, pending, client=server.client()
    )

    with pytest.raises(ContextUnavailableError):
        await api.get_context("../acme", CeremonyContextBuilder().build().ceremony_id)

    assert keycloak.requests == []
    assert server.requests == []


# ---------------------------------------------------------------- result ---


async def test_a_delivered_result_is_posted_with_the_tenant_and_leaves_nothing_on_disk(
    pending: PendingResults,
) -> None:
    result = CeremonyResultBuilder().build()
    server = ScriptedApi(ACCEPTED)

    await _api(server, pending).deliver_result(TENANT, result)

    [request] = server.requests
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/v1/ceremonies/{result.ceremony_id}/result"
    assert request.headers["Authorization"] == f"Bearer token-of-{TENANT}"
    assert request.headers["X-Agilina-Tenant"] == TENANT
    assert request.headers["Content-Type"] == "application/json"
    assert CeremonyResult.model_validate(json.loads(request.content)) == result
    assert _kept(pending) == []


async def test_the_result_is_on_disk_before_the_first_attempt_and_until_the_api_accepts_it(
    pending: PendingResults,
) -> None:
    result = CeremonyResultBuilder().build()
    server = ScriptedApi(_error(503, "unavailable"), _error(503, "unavailable"), ACCEPTED)
    kept_while_sending: list[list[CeremonyResult]] = []
    server.on_request = lambda _: kept_while_sending.append(_kept(pending))
    sleep = RecordedSleep()

    await _api(server, pending, sleep).deliver_result(TENANT, result)

    assert kept_while_sending == [[result], [result], [result]]
    assert sleep.waits == [2.0, 4.0]
    assert _kept(pending) == []


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("connection refused"), httpx.ReadTimeout("timed out")],
    ids=["transport", "timeout"],
)
async def test_a_delivery_the_api_never_received_is_retried(
    pending: PendingResults, failure: Exception
) -> None:
    server = ScriptedApi(failure, ACCEPTED)
    sleep = RecordedSleep()

    await _api(server, pending, sleep).deliver_result(TENANT, CeremonyResultBuilder().build())

    assert len(server.requests) == 2
    assert sleep.waits == [FIRST_RETRY_WAIT_SECONDS]
    assert _kept(pending) == []


async def test_the_wait_doubles_up_to_a_ceiling_while_the_api_is_down(
    pending: PendingResults,
) -> None:
    server = ScriptedApi(*[_error(502, "bad_gateway")] * 8, ACCEPTED)
    sleep = RecordedSleep()

    await _api(server, pending, sleep).deliver_result(TENANT, CeremonyResultBuilder().build())

    assert sleep.waits == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert max(sleep.waits) == MAX_RETRY_WAIT_SECONDS


async def test_a_keycloak_outage_is_retried_like_an_api_outage(
    pending: PendingResults,
) -> None:
    keycloak = FakeTokenEndpoint()
    keycloak.status = 503
    server = ScriptedApi(ACCEPTED)
    sleep = RecordedSleep(during_wait=lambda: setattr(keycloak, "status", 200))
    tokens = _keycloak_tokens(keycloak)
    api = HttpAgilinaApi(BASE_URL, tokens.token_for, pending, server.client(), sleep)

    await api.deliver_result(TENANT, CeremonyResultBuilder().build())

    assert sleep.waits == [2.0]
    assert len(keycloak.requests) == 2
    assert len(server.requests) == 1
    assert _kept(pending) == []


@pytest.mark.parametrize(
    "reply",
    [_error(409, "result_already_received"), _error(422, "validation_error"), _error(400, "x")],
    ids=["409", "422", "400"],
)
async def test_a_rejected_result_is_not_retried_and_stays_on_disk(
    pending: PendingResults, reply: httpx.Response, caplog: pytest.LogCaptureFixture
) -> None:
    result = CeremonyResultBuilder().build()
    server = ScriptedApi(reply, ACCEPTED)
    sleep = RecordedSleep()

    with pytest.raises(httpx.HTTPStatusError):
        await _api(server, pending, sleep).deliver_result(TENANT, result)

    assert len(server.requests) == 1
    assert sleep.waits == []
    assert _kept(pending) == [result]
    assert any(
        record.levelno == logging.ERROR and str(result.ceremony_id) in record.getMessage()
        for record in caplog.records
    )


async def test_an_unexpected_success_status_is_not_an_acceptance(pending: PendingResults) -> None:
    result = CeremonyResultBuilder().build()

    with pytest.raises(httpx.HTTPStatusError):
        await _api(ScriptedApi(httpx.Response(200)), pending).deliver_result(TENANT, result)

    assert _kept(pending) == [result]


async def test_without_a_worker_token_the_result_stays_on_disk_unsent(
    pending: PendingResults,
) -> None:
    result = CeremonyResultBuilder().build()
    server = ScriptedApi(ACCEPTED)
    sleep = RecordedSleep()

    with pytest.raises(WorkerTokenUnavailableError):
        await _api(server, pending, sleep, FakeWorkerTokens(TENANT)).deliver_result(TENANT, result)

    assert server.requests == []
    assert sleep.waits == []
    assert _kept(pending) == [result]


# --------------------------------------------------------------- startup ---


async def test_on_startup_each_kept_result_gets_one_attempt_and_failures_stay(
    pending: PendingResults, caplog: pytest.LogCaptureFixture
) -> None:
    accepted = CeremonyResultBuilder().build()
    refused = CeremonyResultBuilder().build()
    unreachable = CeremonyResultBuilder().build()
    pending.save("acme", accepted)
    pending.save("acme", refused)
    pending.save("ecomoda", unreachable)
    server = ScriptedApi(ACCEPTED, _error(409, "result_already_received"), httpx.ConnectError("x"))
    sleep = RecordedSleep()

    await _api(server, pending, sleep).resend_pending()

    assert [request.headers["X-Agilina-Tenant"] for request in server.requests] == [
        "acme",
        "acme",
        "ecomoda",
    ]
    assert sleep.waits == []
    assert pending.pending() == [("acme", refused), ("ecomoda", unreachable)]
    assert sum(record.levelno == logging.ERROR for record in caplog.records) == 2


async def test_closing_the_adapter_closes_its_client(pending: PendingResults) -> None:
    client = ScriptedApi(ACCEPTED).client()
    api = HttpAgilinaApi(BASE_URL, FakeWorkerTokens().token_for, pending, client=client)

    await api.close()

    assert client.is_closed
