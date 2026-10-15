"""Worker ↔ API contract.

These are the only two operations the worker needs (architecture, 5.3): ask for the context
before joining the room and deliver the result on close. Both are the agent worker's only
(``current_worker``) and name the tenant in ``X-Agilina-Tenant``, the one the context carries.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status

from agilina_api.ceremonies.application.commands.deliver_ceremony_result import (
    DeliverCeremonyResult,
    DeliverCeremonyResultHandler,
)
from agilina_api.ceremonies.application.queries.get_ceremony_context import (
    GetCeremonyContext,
    GetCeremonyContextHandler,
)
from agilina_api.ceremonies.presentation.http.dependencies import (
    get_deliver_ceremony_result_handler,
    get_get_ceremony_context_handler,
)
from agilina_api.ceremonies.presentation.http.errors import CeremoniesErrors
from agilina_api.shared.application.tenancy import Tenant
from agilina_api.shared.presentation.http.access import current_worker
from agilina_api.shared.presentation.http.api_error import SharedErrors
from agilina_api.shared.presentation.http.error_schema import errors_of
from agilina_api.shared.presentation.http.tenancy import current_tenant
from agilina_shared import CeremonyContext, CeremonyResult, ResultReceipt

router = APIRouter(prefix="/v1/ceremonies", tags=["ceremonies"])

GET_CONTEXT_DESCRIPTION = """
Everything the agent worker needs before joining the ceremony's room, in one call: the tenant,
the team and the sprint, the room's name, the team's language and mode, the sprint's day N of M
on the day the ceremony is scheduled (in the sprint's calendar, AD-31) and the participants of
the active sprint in turn order, with their name, role and room identity.

Only the agent worker of the tenant's realm may ask. A ceremony that does not exist, or whose
sprint is no longer the team's active one, is `404 ceremony_not_found`.
"""

DELIVER_RESULT_DESCRIPTION = """
What the agent worker captured when the ceremony closed: the attributed transcript and the
ceremony's events, stored in one transaction. It neither starts the post-processing nor closes
the room.

Delivering the same result again (the same canonical JSON) answers `202` again and stores
nothing twice, so the worker retries safely; another result for the ceremony is
`409 result_already_received`. A segment or an event attributed to someone who is not a
participant of the ceremony's sprint, or a `ceremony_id` in the body that is not the path's, is
`422 validation_error` with `details.fields` saying where (`reason`: `not_a_participant` or
`does_not_match_path`), never the value. Only the agent worker of the tenant's realm may
deliver, and a ceremony it could not get the context of is `404 ceremony_not_found`.
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
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Result received, also when the same one arrives again"},
        **errors_of(
            SharedErrors.TENANT_REQUIRED,
            SharedErrors.TENANT_NOT_FOUND,
            SharedErrors.NOT_AUTHENTICATED,
            SharedErrors.NOT_A_WORKER,
            CeremoniesErrors.CEREMONY_NOT_FOUND,
            CeremoniesErrors.RESULT_ALREADY_RECEIVED,
            SharedErrors.VALIDATION,
        ),
    },
    summary="Result the worker delivers when the ceremony closes",
    description=DELIVER_RESULT_DESCRIPTION,
    # Before the handler: the tenant and the worker's token are checked before anything is read.
    dependencies=[Depends(current_worker)],
)
async def deliver_result(
    ceremony_id: Annotated[UUID, Path(description="The ceremony the result is of.")],
    result: CeremonyResult,
    handler: DeliverCeremonyResultHandler = Depends(get_deliver_ceremony_result_handler),
) -> ResultReceipt:
    await handler.handle(DeliverCeremonyResult(ceremony_id=ceremony_id, result=result))
    return ResultReceipt()
