"""The worker is told apart from a person by the client its valid token was issued to
(``azp``), without looking anything up in the database (AGI-64). The realm's keys are
simulated; the signatures are real."""

import pytest

from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from agilina_api.identity.infrastructure.keycloak.authenticated_workers import (
    KeycloakAuthenticatedWorkers,
)
from tests.api.builders import AUDIENCE, ISSUER, AccessTokenBuilder, signing_key
from tests.api.doubles import JWKS_URL, FakeClock, FakeRealmKeys


@pytest.fixture
def workers() -> KeycloakAuthenticatedWorkers:
    verifier = KeycloakAccessTokenVerifier(
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
        clock=FakeClock(),
        client=FakeRealmKeys(signing_key()).client(),
    )
    return KeycloakAuthenticatedWorkers(verifier, "agilina-worker")


async def test_a_valid_token_issued_to_the_worker_client_is_the_worker(workers):
    assert await workers.is_worker(AccessTokenBuilder().as_worker().build()) is True


@pytest.mark.parametrize("azp", ["agilina-web", "agilina-api", "agilina-worker-2", None])
async def test_a_valid_token_issued_to_another_client_is_not_the_worker(workers, azp):
    token = AccessTokenBuilder().with_claim("azp", azp).build()

    assert await workers.is_worker(token) is False


async def test_a_token_that_is_not_valid_is_no_answer_even_if_it_names_the_worker(workers):
    forged = AccessTokenBuilder().as_worker().signed_with(signing_key("key-1", "attacker"))

    assert await workers.is_worker(forged.build()) is None
    assert await workers.is_worker("not a token") is None


async def test_the_worker_token_of_another_tenant_is_not_valid_here(workers):
    """Its issuer is the realm of the other tenant: the ``401`` of CA7."""
    token = AccessTokenBuilder().as_worker().issued_by("http://kc.test/realms/agilina-other")

    assert await workers.is_worker(token.build()) is None
