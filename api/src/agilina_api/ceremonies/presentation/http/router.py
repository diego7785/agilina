"""Worker ↔ API contract.

These are the only two operations the worker needs (architecture, 5.3): ask for the context
before joining the room and deliver the result on close. Both are the agent worker's only
(``current_worker``) and name the tenant in ``X-Agilina-Tenant``, the one the context carries.
Delivering the result arrives with AGI-126.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from agilina_api.ceremonies.application.queries.get_ceremony_context import (
    GetCeremonyContext,
    GetCeremonyContextHandler,
)
from agilina_api.ceremonies.presentation.http.dependencies import get_get_ceremony_context_handler
from agilina_api.ceremonies.presentation.http.errors import CeremoniesErrors
from agilina_api.shared.application.tenancy import Tenant
from agilina_api.shared.presentation.http.access import current_worker
from agilina_api.shared.presentation.http.api_error import ApiException, SharedErrors
from agilina_api.shared.presentation.http.error_schema import errors_of
from agilina_api.shared.presentation.http.tenancy import current_tenant
from agilina_shared import CeremonyContext, CeremonyResult

router = APIRouter(prefix="/v1/ceremonies", tags=["ceremonies"])

PENDING = "Contract defined in Sprint 0; implementation pending (HU-56)."

GET_CONTEXT_DESCRIPTION = """
Everything the agent worker needs before joining the ceremony's room, in one call: the tenant,
the team and the sprint, the room's name, the team's language and mode, the sprint's day N of M
on the day the ceremony is scheduled (in the sprint's calendar, AD-31) and the participants of
the active sprint in turn order, with their name, role and room identity.

Only the agent worker of the tenant's realm may ask. A ceremony that does not exist, or whose
sprint is no longer the team's active one, is `404 ceremony_not_found`.
"""


@router.get(
    "/{ceremony_id}/context",
    responses={
        200: {"model": CeremonyContext, "description": "Ceremony context"},
        **errors_of(
            SharedErrors.TENANT_REQUIRED,
            SharedErrors.TENANT_NOT_FOUND,
            SharedErrors.NOT_AUTHENTICATED,
            SharedErrors.NOT_A_WORKER,
            CeremoniesErrors.CEREMONY_NOT_FOUND,
            SharedErrors.VALIDATION,
        ),
    },
    summary="Context the worker needs before joining the room",
    description=GET_CONTEXT_DESCRIPTION,
    # Before the handler: the tenant and the worker's token are checked before anything is read.
    dependencies=[Depends(current_worker)],
)
async def get_context(
    ceremony_id: Annotated[UUID, Path(description="The ceremony the worker facilitates.")],
    tenant: Tenant = Depends(current_tenant),
    handler: GetCeremonyContextHandler = Depends(get_get_ceremony_context_handler),
) -> CeremonyContext:
    return await handler.handle(GetCeremonyContext(tenant=tenant.slug, ceremony_id=ceremony_id))


@router.post(
    "/{ceremony_id}/result",
    responses=errors_of(SharedErrors.VALIDATION, SharedErrors.NOT_IMPLEMENTED),
    summary="Result the worker delivers when the ceremony closes",
    description=PENDING,
)
async def deliver_result(ceremony_id: UUID, result: CeremonyResult) -> None:
    raise ApiException(SharedErrors.NOT_IMPLEMENTED)
