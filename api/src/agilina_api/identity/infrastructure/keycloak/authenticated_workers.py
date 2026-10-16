"""Keycloak implementation of the ``AuthenticatedWorkers`` port (AGI-64).

The worker signs in with the client credentials of the ``agilina-worker`` client of its
tenant's realm, so the token is checked by the same verifier as a person's (issuer of that
realm, audience ``agilina-api``): a token of another tenant is not valid here. Once it is
valid, ``azp`` (the client the token was issued to) tells the worker from a person. It is
not a role: only the worker's service account can obtain a token for its client, because
the client has neither the browser login nor the password grant.

Nothing is looked up in the database: the worker has no ``app_user``.
"""

from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from agilina_api.shared.application.access import AuthenticatedWorkers


class KeycloakAuthenticatedWorkers(AuthenticatedWorkers):
    def __init__(self, verifier: KeycloakAccessTokenVerifier, worker_client: str) -> None:
        self._verifier = verifier
        self._worker_client = worker_client

    async def is_worker(self, bearer_token: str) -> bool | None:
        claims = await self._verifier.verified_claims(bearer_token)
        if claims is None:
            return None
        return claims.get("azp") == self._worker_client
