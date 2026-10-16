"""The Agilina API, seen from the worker: as a port double and as an HTTP server."""

from collections.abc import Callable
from uuid import UUID

import httpx

from agilina_agent.application.errors import ContextUnavailableError
from agilina_shared.contract import CeremonyContext, CeremonyResult


class FakeAgilinaApi:
    """The port, in memory: hands over ``context`` or, without one, fails as the adapter does."""

    def __init__(self, context: CeremonyContext | None = None) -> None:
        self.context = context
        self.asked: list[tuple[str, UUID]] = []
        self.delivered: list[tuple[str, CeremonyResult]] = []

    async def get_context(self, tenant: str, ceremony_id: UUID) -> CeremonyContext:
        self.asked.append((tenant, ceremony_id))
        if self.context is None:
            raise ContextUnavailableError("The API did not answer")
        return self.context

    async def deliver_result(self, tenant: str, result: CeremonyResult) -> None:
        self.delivered.append((tenant, result))


Reply = httpx.Response | Exception


class ScriptedApi:
    """Answers each request with the next scripted reply (a response, or an error raised as
    the transport would); the last one repeats. ``on_request`` sees every request first."""

    def __init__(self, *replies: Reply) -> None:
        self._replies = list(replies)
        self.requests: list[httpx.Request] = []
        self.on_request: Callable[[httpx.Request], None] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.on_request is not None:
            self.on_request(request)
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
