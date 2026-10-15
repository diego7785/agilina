"""The worker authenticates as a service in the realm of each tenant (CA3, CA7) and fails
closed: a tenant it cannot vouch for never reaches Keycloak."""

import logging

import httpx
import pytest
from pydantic import SecretStr

from agilina_agent.infrastructure.worker_token_unavailable_error import (
    WorkerTokenUnavailableError,
)
from agilina_agent.infrastructure.worker_tokens import RENEWAL_MARGIN_SECONDS, KeycloakWorkerTokens
from tests.agent.doubles import FakeMonotonicClock, FakeTokenEndpoint

SECRETS = {"acme": "acme-worker-secret", "ecomoda": "ecomoda-worker-secret"}


def _secret_of(slug: str) -> SecretStr:
    return SecretStr(SECRETS.get(slug, ""))


def _tokens(endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock) -> KeycloakWorkerTokens:
    return KeycloakWorkerTokens(
        keycloak_url="http://auth.internal/",
        realm_prefix="agilina-",
        client_id="agilina-worker",
        secret_of=_secret_of,
        client=endpoint.client(),
        clock=clock,
    )


@pytest.fixture
def endpoint() -> FakeTokenEndpoint:
    return FakeTokenEndpoint(expires_in=300)


@pytest.fixture
def clock() -> FakeMonotonicClock:
    return FakeMonotonicClock()


async def test_the_token_is_asked_to_the_realm_of_the_tenant_with_its_own_secret(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock
) -> None:
    token = await _tokens(endpoint, clock).token_for("acme")

    assert token == "token-1"
    request = endpoint.requests[0]
    assert request.method == "POST"
    assert str(request.url) == (
        "http://auth.internal/realms/agilina-acme/protocol/openid-connect/token"
    )
    assert endpoint.form() == {
        "grant_type": "client_credentials",
        "client_id": "agilina-worker",
        "client_secret": "acme-worker-secret",
    }


async def test_a_valid_token_is_reused(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock
) -> None:
    tokens = _tokens(endpoint, clock)
    first = await tokens.token_for("acme")
    clock.advance(300 - RENEWAL_MARGIN_SECONDS - 1)

    assert await tokens.token_for("acme") == first
    assert len(endpoint.requests) == 1


async def test_a_token_close_to_expiring_is_renewed(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock
) -> None:
    tokens = _tokens(endpoint, clock)
    await tokens.token_for("acme")
    clock.advance(300 - RENEWAL_MARGIN_SECONDS)

    assert await tokens.token_for("acme") == "token-2"
    assert len(endpoint.requests) == 2


async def test_each_tenant_has_its_own_token(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock
) -> None:
    tokens = _tokens(endpoint, clock)

    acme = await tokens.token_for("acme")
    ecomoda = await tokens.token_for("ecomoda")

    assert acme != ecomoda
    assert "/realms/agilina-ecomoda/" in str(endpoint.requests[1].url)
    assert endpoint.form(1)["client_secret"] == "ecomoda-worker-secret"
    assert await tokens.token_for("acme") == acme


async def test_the_token_never_reaches_the_logs(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    token = await _tokens(endpoint, clock).token_for("acme")

    assert caplog.records
    assert token not in caplog.text
    assert "acme-worker-secret" not in caplog.text


@pytest.mark.parametrize("tenant", ["../x", "Acme", "a", "acme/../ecomoda", ""])
async def test_a_tenant_that_is_not_a_slug_never_reaches_keycloak(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock, tenant: str
) -> None:
    with pytest.raises(WorkerTokenUnavailableError):
        await _tokens(endpoint, clock).token_for(tenant)

    assert endpoint.requests == []


async def test_a_tenant_without_a_configured_secret_never_reaches_keycloak(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock
) -> None:
    with pytest.raises(WorkerTokenUnavailableError):
        await _tokens(endpoint, clock).token_for("initech")

    assert endpoint.requests == []


@pytest.mark.parametrize("status", [400, 401])
async def test_rejected_credentials_are_not_transient(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock, status: int
) -> None:
    endpoint.status = status

    with pytest.raises(WorkerTokenUnavailableError):
        await _tokens(endpoint, clock).token_for("acme")


async def test_a_keycloak_server_error_is_left_to_the_caller_as_transient(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock
) -> None:
    endpoint.status = 503

    with pytest.raises(httpx.HTTPStatusError):
        await _tokens(endpoint, clock).token_for("acme")


@pytest.mark.parametrize(
    "body", [{"token_type": "Bearer"}, {"access_token": "t", "expires_in": "soon"}, []]
)
async def test_an_answer_without_a_token_is_not_a_token(
    endpoint: FakeTokenEndpoint, clock: FakeMonotonicClock, body: object
) -> None:
    endpoint.body = body

    with pytest.raises(WorkerTokenUnavailableError):
        await _tokens(endpoint, clock).token_for("acme")
