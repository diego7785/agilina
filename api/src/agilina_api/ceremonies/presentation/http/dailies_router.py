"""The ceremonies API for people: a participant of the daily joins today's room (AGI-59).

Unlike the worker's routes (``router``), these are a person's: they name the team in the path
and declare ``Depends(current_team_member)``. Being a member is not enough to join, though: the
rule of the participant lives in the use case, so the admin of the team gets ``403`` too when
they are not among the daily's participants.
"""

from fastapi import APIRouter, Depends, Response, status

from agilina_api.ceremonies.application.commands.join_current_daily import (
    JoinCurrentDaily,
    JoinCurrentDailyHandler,
)
from agilina_api.ceremonies.presentation.http.dependencies import get_join_current_daily_handler
from agilina_api.ceremonies.presentation.http.errors import CeremoniesErrors
from agilina_api.ceremonies.presentation.http.schemas import RoomAdmissionResponse
from agilina_api.shared.application.access import TeamContext
from agilina_api.shared.application.tenancy import Tenant
from agilina_api.shared.presentation.http.access import current_team_member
from agilina_api.shared.presentation.http.api_error import SharedErrors
from agilina_api.shared.presentation.http.error_schema import errors_of
from agilina_api.shared.presentation.http.tenancy import current_tenant


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/v1/teams/{team_id}/dailies", tags=["ceremonies"], dependencies=[Depends(_no_store)]
)

JOIN_CURRENT_DAILY_DESCRIPTION = """
The access token to the LiveKit room of the team's daily of today, issued at the moment it is
asked for and never carried by a link. The room is a new one for each daily, named after the
tenant and the ceremony, and it is opened on the room server before the token is signed. The
token carries the user's identity (`str(user_id)`), lets them into only that room, publishing
their microphone and listening to the others, and lasts two hours.

Only a participant of the active sprint's daily, as stored, gets it: any other member of the
team, its admin included, is `403 not_a_daily_participant`, and someone outside the team is
`403 not_a_team_member`. A team without an active sprint is `409 no_active_sprint`, and outside
the daily's window to join (from ten minutes before it starts to fifteen minutes after) it is
`409 daily_not_open`. When the room server does not answer, or it is not configured, it is
`503 room_service_unavailable`; asking again joins the same room.
"""


@router.post(
    "/current/token",
    response_model=RoomAdmissionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Token issued for the room of today's daily"},
        **errors_of(
            SharedErrors.TENANT_REQUIRED,
            SharedErrors.TENANT_NOT_FOUND,
            SharedErrors.NOT_AUTHENTICATED,
            SharedErrors.ACCOUNT_NOT_ACTIVE,
            SharedErrors.NOT_A_TEAM_MEMBER,
            CeremoniesErrors.NOT_A_DAILY_PARTICIPANT,
            SharedErrors.NO_ACTIVE_SPRINT,
            CeremoniesErrors.DAILY_NOT_OPEN,
            SharedErrors.VALIDATION,
            CeremoniesErrors.ROOM_SERVICE_UNAVAILABLE,
        ),
    },
    summary="Join the room of the team's daily of today",
    description=JOIN_CURRENT_DAILY_DESCRIPTION,
)
async def join_current_daily(
    tenant: Tenant = Depends(current_tenant),
    team: TeamContext = Depends(current_team_member),
    handler: JoinCurrentDailyHandler = Depends(get_join_current_daily_handler),
) -> RoomAdmissionResponse:
    admission = await handler.handle(
        JoinCurrentDaily(tenant=tenant.slug, team_id=team.team_id, user_id=team.user_id)
    )
    return RoomAdmissionResponse(
        room_name=admission.room_name,
        token=admission.token,
        expires_at=admission.expires_at,
        livekit_url=admission.livekit_url,
    )
