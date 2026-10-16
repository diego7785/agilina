"""Keycloak as the worker sees it: the token endpoint of each realm, and the token provider."""

from urllib.parse import parse_qs

import httpx

from agilina_agent.infrastructure.worker_token_unavailable_error import (
    WorkerTokenUnavailableError,
)


class FakeTokenEndpoint:
    """``/protocol/openid-connect/token``: issues ``token-1``, ``token-2``... valid for
    ``expires_in`` seconds, or answers ``status`` with ``body`` when the test sets one."""

    def __init__(self, expires_in: float = 300) -> None:
        self.expires_in = expires_in
        self.status = 200
        self.body: object | None = None
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.body is not None or self.status != 200:
            return httpx.Response(self.status, json=self.body if self.body is not None else {})
        return httpx.Response(
            200,
            json={
                "access_token": f"token-{len(self.requests)}",
                "expires_in": self.expires_in,
                "token_type": "Bearer",
            },
        )

    def form(self, index: int = -1) -> dict[str, str]:
        """The form fields of a request, one value each."""
        fields = parse_qs(self.requests[index].content.decode())
        return {name: values[0] for name, values in fields.items()}

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


class FakeWorkerTokens:
    """The token provider: ``token-of-<tenant>``, or the fail-closed error for the tenants
    in ``unavailable``."""

    def __init__(self, *unavailable: str) -> None:
        self.unavailable = set(unavailable)

    async def token_for(self, tenant: str) -> str:
        if tenant in self.unavailable:
            raise WorkerTokenUnavailableError(f"No worker secret configured for tenant {tenant}")
        return f"token-of-{tenant}"
