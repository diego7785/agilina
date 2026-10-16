"""Worker tokens: client credentials of ``agilina-worker`` in the realm of each tenant.

The worker authenticates as a service, never with a user's session (CA3), and in the realm
of the ceremony's tenant (CA7, AD-29): a token of another tenant's realm is a 401. It fails
closed: a slug that is not valid or has no secret configured never reaches Keycloak. The
token is never logged.
"""

import time
from collections.abc import Callable

import httpx
from pydantic import SecretStr

from agilina_agent.infrastructure.logging_setup import get_logger
from agilina_agent.infrastructure.tenant_slug import is_tenant_slug
from agilina_agent.infrastructure.worker_token_unavailable_error import (
    WorkerTokenUnavailableError,
)

logger = get_logger(__name__)

# A token is renewed this long before it expires, so it never expires on its way to the API.
RENEWAL_MARGIN_SECONDS = 30.0


class KeycloakWorkerTokens:
    def __init__(
        self,
        keycloak_url: str,
        realm_prefix: str,
        client_id: str,
        secret_of: Callable[[str], SecretStr],
        client: httpx.AsyncClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._keycloak_url = keycloak_url.rstrip("/")
        self._realm_prefix = realm_prefix
        self._client_id = client_id
        self._secret_of = secret_of
        self._client = client
        self._clock = clock
        # tenant -> (token, instant from which it is renewed)
        self._cache: dict[str, tuple[str, float]] = {}

    async def token_for(self, tenant: str) -> str:
        if not is_tenant_slug(tenant):
            raise WorkerTokenUnavailableError("The tenant is not a valid slug")

        cached = self._cache.get(tenant)
        if cached is not None and self._clock() < cached[1]:
            return cached[0]

        secret = self._secret_of(tenant).get_secret_value()
        if not secret:
            raise WorkerTokenUnavailableError(f"No worker secret configured for tenant {tenant}")

        requested_at = self._clock()
        response = await self._client.post(
            f"{self._keycloak_url}/realms/{self._realm_prefix}{tenant}"
            "/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": secret,
            },
        )
        if response.is_client_error:
            raise WorkerTokenUnavailableError(
                f"Keycloak rejected the worker credentials of tenant {tenant} "
                f"(HTTP {response.status_code})"
            )
        # A 5xx is transient: it propagates as an httpx error and the caller decides.
        response.raise_for_status()

        try:
            body = response.json()
            token = str(body["access_token"])
            expires_in = float(body["expires_in"])
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerTokenUnavailableError(
                f"Keycloak answered without a token for tenant {tenant}"
            ) from error

        self._cache[tenant] = (token, requested_at + expires_in - RENEWAL_MARGIN_SECONDS)
        logger.info("Worker token obtained for tenant %s", tenant)
        return token
