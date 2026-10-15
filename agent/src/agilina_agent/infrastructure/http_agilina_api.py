"""Worker adapter against the Agilina API.

Every request carries the worker token of the ceremony's tenant and names that tenant in
``X-Agilina-Tenant`` (AD-29). The two operations fail differently on purpose
(docs/contrato-worker-api.md):

* asking for the context makes one request and never retries: any failure is a
  ``ContextUnavailableError`` and the room hears that there is no facilitation (CA5);
* delivering the result keeps it on disk before the first attempt and retries what may be
  transient, with a growing wait, while the job lives: losing a ceremony because the API
  restarted is not acceptable (CA6). The file is removed only on a ``202``.
"""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

import httpx

from agilina_agent.application.errors import ContextUnavailableError
from agilina_agent.application.ports import AgilinaApi
from agilina_agent.infrastructure.logging_setup import get_logger
from agilina_agent.infrastructure.pending_results import PendingResults
from agilina_agent.infrastructure.worker_token_unavailable_error import (
    WorkerTokenUnavailableError,
)
from agilina_shared.contract import CeremonyContext, CeremonyResult

logger = get_logger(__name__)

REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=3.0)
TENANT_HEADER = "X-Agilina-Tenant"
FIRST_RETRY_WAIT_SECONDS = 2.0
MAX_RETRY_WAIT_SECONDS = 60.0


class HttpAgilinaApi(AgilinaApi):
    def __init__(
        self,
        base_url: str,
        token_for: Callable[[str], Awaitable[str]],
        pending: PendingResults,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_for = token_for
        self._pending = pending
        self._client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        self._sleep = sleep

    async def get_context(self, tenant: str, ceremony_id: UUID) -> CeremonyContext:
        try:
            response = await self._client.get(
                f"{self._base_url}/v1/ceremonies/{ceremony_id}/context",
                headers=await self._headers(tenant),
            )
            response.raise_for_status()
            context = CeremonyContext.model_validate_json(response.content)
        except (httpx.HTTPError, WorkerTokenUnavailableError, ValueError) as error:
            logger.error("Context of ceremony %s unavailable: %s", ceremony_id, _describe(error))
            raise ContextUnavailableError(f"No context for ceremony {ceremony_id}") from error

        logger.info("Context of ceremony %s received", ceremony_id)
        return context

    async def deliver_result(self, tenant: str, result: CeremonyResult) -> None:
        kept_at = self._pending.save(tenant, result)
        wait = FIRST_RETRY_WAIT_SECONDS
        while True:
            try:
                await self._send(tenant, result)
                return
            except (httpx.HTTPError, WorkerTokenUnavailableError) as error:
                if not _is_transient(error):
                    logger.error(
                        "Result of ceremony %s not delivered (%s); it stays in %s",
                        result.ceremony_id,
                        _describe(error),
                        kept_at,
                    )
                    raise
                logger.warning(
                    "Delivery of ceremony %s failed (%s); retrying in %s s",
                    result.ceremony_id,
                    _describe(error),
                    wait,
                )
            await self._sleep(wait)
            wait = min(wait * 2, MAX_RETRY_WAIT_SECONDS)

    async def resend_pending(self) -> None:
        """One attempt per kept result, when the worker starts: what fails stays on disk."""
        for tenant, result in self._pending.pending():
            try:
                await self._send(tenant, result)
            except (httpx.HTTPError, WorkerTokenUnavailableError) as error:
                logger.error(
                    "Pending result of ceremony %s not delivered (%s); it stays on disk",
                    result.ceremony_id,
                    _describe(error),
                )

    async def close(self) -> None:
        await self._client.aclose()

    async def _send(self, tenant: str, result: CeremonyResult) -> None:
        response = await self._client.post(
            f"{self._base_url}/v1/ceremonies/{result.ceremony_id}/result",
            content=result.model_dump_json(),
            headers={"Content-Type": "application/json", **await self._headers(tenant)},
        )
        if response.status_code != httpx.codes.ACCEPTED:
            raise httpx.HTTPStatusError(
                f"Unexpected HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        self._pending.remove(tenant, result.ceremony_id)
        logger.info("Result of ceremony %s delivered", result.ceremony_id)

    async def _headers(self, tenant: str) -> dict[str, str]:
        token = await self._token_for(tenant)
        return {"Authorization": f"Bearer {token}", TENANT_HEADER: tenant}


def _is_transient(error: Exception) -> bool:
    """A failed connection or a 5xx may be gone on the next attempt; a rejected result (409,
    422) or a worker that cannot get its token will not change by retrying."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.is_server_error
    return isinstance(error, httpx.TransportError)


def _describe(error: Exception) -> str:
    """What the log says about a failure: the status and the error code of the API, never a
    body that may carry names or a token."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code} {_error_code(error.response)}".rstrip()
    if isinstance(error, ValueError):
        return "the body does not follow the contract"
    return f"{type(error).__name__}: {error}"


def _error_code(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["code"])
    except (KeyError, TypeError, ValueError):
        return ""
