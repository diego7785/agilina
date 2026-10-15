"""Turns every failure into the one error body, whatever raised it.

Four kinds are caught: a mapped domain exception, an ``ApiException``, a request that fails
validation (or a route that does not exist: Starlette's ``HTTPException``) and anything
unexpected. The composition root registers them all with ``register_error_handlers``.
"""

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from agilina_api.shared.application.access import (
    AccountNotActiveError,
    NotATeamAdminError,
    NotATeamMemberError,
    NotAuthenticatedError,
    NotAWorkerError,
)
from agilina_api.shared.application.ports import MailDeliveryError
from agilina_api.shared.application.tenancy import TenantNotFoundError, TenantRequiredError
from agilina_api.shared.presentation.http.api_error import ApiError, ApiException, SharedErrors
from agilina_api.shared.presentation.http.request_id import REQUEST_ID_HEADER

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorMapping:
    """Which catalog entry one exception type becomes.

    ``details`` extracts stable codes from the error when the interface needs more than the
    ``code``.
    """

    error_type: type[Exception]
    error: ApiError
    details: Callable[[Exception], Mapping[str, Any]] | None = None


SHARED_ERRORS: tuple[ErrorMapping, ...] = (
    ErrorMapping(TenantRequiredError, SharedErrors.TENANT_REQUIRED),
    ErrorMapping(TenantNotFoundError, SharedErrors.TENANT_NOT_FOUND),
    ErrorMapping(NotAuthenticatedError, SharedErrors.NOT_AUTHENTICATED),
    ErrorMapping(AccountNotActiveError, SharedErrors.ACCOUNT_NOT_ACTIVE),
    ErrorMapping(NotATeamMemberError, SharedErrors.NOT_A_TEAM_MEMBER),
    ErrorMapping(NotATeamAdminError, SharedErrors.NOT_A_TEAM_ADMIN),
    ErrorMapping(NotAWorkerError, SharedErrors.NOT_A_WORKER),
    ErrorMapping(MailDeliveryError, SharedErrors.MAIL_UNAVAILABLE),
)

# Starlette's own errors that have an entry in the catalog; any other status keeps its number
# under a code derived from it.
_STARLETTE = {404: SharedErrors.NOT_FOUND, 405: SharedErrors.METHOD_NOT_ALLOWED}


def error_response(
    request: Request, error: ApiError, details: Mapping[str, Any] | None = None
) -> JSONResponse:
    request_id = request.scope.get("request_id", "-")
    body: dict[str, Any] = {"status": error.status, "code": error.code, "message": error.message}
    if details:
        body["details"] = details
    body["request_id"] = request_id
    return JSONResponse(
        status_code=error.status,
        content={"error": body},
        headers={
            **(error.headers or {}),
            "Cache-Control": "no-store",
            REQUEST_ID_HEADER: request_id,
        },
    )


def _validation_details(error: RequestValidationError) -> dict[str, Any]:
    # Where and why, never the value: a rejected password must not travel back.
    fields = [
        {"field": ".".join(str(part) for part in item["loc"]), "reason": item["type"]}
        for item in error.errors()
    ]
    return {"fields": fields}


def register_error_handlers(app: FastAPI, mappings: Iterable[ErrorMapping]) -> None:
    for mapping in mappings:

        async def handle_mapped(
            request: Request, error: Exception, mapping: ErrorMapping = mapping
        ) -> JSONResponse:
            details = mapping.details(error) if mapping.details is not None else None
            return error_response(request, mapping.error, details)

        app.add_exception_handler(mapping.error_type, handle_mapped)

    async def handle_api_exception(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, ApiException)
        return error_response(request, error.error, error.details)

    async def handle_validation(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, RequestValidationError)
        return error_response(request, SharedErrors.VALIDATION, _validation_details(error))

    async def handle_http(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, StarletteHTTPException)
        known = _STARLETTE.get(error.status_code)
        if known is None:
            known = ApiError(error.status_code, f"http_{error.status_code}", "The request failed.")
        return error_response(request, known)

    async def handle_unexpected(request: Request, error: Exception) -> JSONResponse:
        # The traceback goes to the log under the request id; the caller gets only the id.
        logger.error("Unhandled error", exc_info=error)
        return error_response(request, SharedErrors.INTERNAL)

    app.add_exception_handler(ApiException, handle_api_exception)
    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(StarletteHTTPException, handle_http)
    app.add_exception_handler(Exception, handle_unexpected)
