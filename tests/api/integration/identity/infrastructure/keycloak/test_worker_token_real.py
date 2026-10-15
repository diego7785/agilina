"""The agent worker against the real Keycloak (AGI-64, AD-29).

Run with ``make test-keycloak``, once per tenant. They check what the simulated tests assume:
that the ``agilina-worker`` client of a tenant's realm gives a token with its secret of the
``.env`` (client credentials), that the API recognizes that token as the worker's, that a
person's token is valid but not the worker's, and that the worker token of one tenant is not
valid in another.
"""

import uuid

import httpx
import pytest

from agilina_api.identity.domain.value_objects import Email
from agilina_api.identity.infrastructure.keycloak.authenticated_workers import (
    KeycloakAuthenticatedWorkers,
)
from tests.api.integration.identity.infrastructure.keycloak.test_access_token_verifier_real import (
    PASSWORD,
    Realm,
)

pytestmark = pytest.mark.keycloak


async def _worker_token(settings, tenant: str, secret: str | None = None) -> httpx.Response:
    realm = Realm(settings, tenant)
    async with httpx.AsyncClient() as client:
        return await client.post(
            f"{realm.base}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.keycloak_worker_client,
                "client_secret": (
                    settings.tenant_worker_secret(tenant).get_secret_value()
                    if secret is None
                    else secret
                ),
            },
        )


def _workers(settings, tenant: str) -> KeycloakAuthenticatedWorkers:
    return KeycloakAuthenticatedWorkers(
        Realm(settings, tenant).verifier(), settings.keycloak_worker_client
    )


async def test_the_worker_signs_in_with_its_secret_and_the_api_recognizes_it(settings, tenant):
    answer = await _worker_token(settings, tenant)
    assert answer.status_code == 200
    workers = _workers(settings, tenant)

    assert await workers.is_worker(answer.json()["access_token"]) is True
    await workers._verifier.aclose()  # noqa: SLF001


async def test_the_worker_does_not_sign_in_with_a_wrong_secret(settings, tenant):
    answer = await _worker_token(settings, tenant, secret="not-the-secret")  # noqa: S106

    assert answer.status_code == 401


async def test_the_worker_secret_of_one_tenant_does_not_open_another(settings, tenant):
    other = "ecomoda" if tenant == "acme" else "acme"
    secret = settings.tenant_worker_secret(other).get_secret_value()

    assert (await _worker_token(settings, tenant, secret=secret)).status_code == 401


async def test_the_worker_token_of_one_tenant_is_not_valid_in_another(settings, tenant):
    other = "ecomoda" if tenant == "acme" else "acme"
    token = (await _worker_token(settings, tenant)).json()["access_token"]
    foreign = _workers(settings, other)

    assert await foreign.is_worker(token) is None
    await foreign._verifier.aclose()  # noqa: SLF001


async def test_the_token_of_a_person_is_valid_but_not_the_worker(
    settings, tenant, provider, created
):
    email = Email(f"it-{uuid.uuid4().hex[:10]}@example.test")
    created.append(
        await provider.create_user(email=email, full_name="Julián Torres", password=PASSWORD)
    )
    access_token = (await Realm(settings, tenant).sign_in(email.value, PASSWORD))["access_token"]
    workers = _workers(settings, tenant)

    assert await workers.is_worker(access_token) is False
    await workers._verifier.aclose()  # noqa: SLF001
