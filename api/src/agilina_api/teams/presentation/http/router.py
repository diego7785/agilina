"""Teams API: create a team, list the authenticated user's teams and read one (HU-05) and
configure its active sprint (HU-07).

Every route needs an authenticated user, and that user is always the one behind the
access token (``current_user_id``), never one named in the body. A route about one team
is also kept to its members (``current_team_member``), and one that changes it to its admins
(``current_team_admin``). The users of a team (their roles, removing them) are the
``/v1/users`` API (``users_router``).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from agilina_api.shared.application.access import TeamContext
from agilina_api.shared.presentation.http.access import (
    current_team_admin,
    current_team_member,
    current_user_id,
)
from agilina_api.shared.presentation.http.api_error import SharedErrors
from agilina_api.shared.presentation.http.error_schema import errors_of
from agilina_api.teams.application.commands.create_team_as_admin import (
    CreateTeamAsAdmin,
    CreateTeamAsAdminHandler,
)
from agilina_api.teams.application.commands.reconfigure_sprint import (
    ReconfigureSprint,
    ReconfigureSprintHandler,
)
from agilina_api.teams.application.commands.start_sprint import StartSprint, StartSprintHandler
from agilina_api.teams.application.queries.get_active_sprint import (
    GetActiveSprint,
    GetActiveSprintHandler,
)
from agilina_api.teams.application.queries.get_team import GetTeam, GetTeamHandler
from agilina_api.teams.application.queries.list_my_teams import ListMyTeams, ListMyTeamsHandler
from agilina_api.teams.domain.errors import NoActiveSprintError
from agilina_api.teams.presentation.http.dependencies import (
    get_create_team_as_admin_handler,
    get_get_active_sprint_handler,
    get_get_team_handler,
    get_list_my_teams_handler,
    get_reconfigure_sprint_handler,
    get_start_sprint_handler,
)
from agilina_api.teams.presentation.http.errors import TeamsErrors
from agilina_api.teams.presentation.http.presenters import (
    present_active_sprint,
    present_created,
    present_my_team,
    present_team,
)
from agilina_api.teams.presentation.http.schemas import (
    ActiveSprintResponse,
    CreatedTeamResponse,
    CreateTeamRequest,
    MyTeamResponse,
    SprintRequest,
    TeamResponse,
)
from agilina_shared.enums import Language, OperationMode, TeamRole

router = APIRouter(prefix="/v1/teams", tags=["teams"])

SIGNED_IN = (
    SharedErrors.TENANT_REQUIRED,
    SharedErrors.TENANT_NOT_FOUND,
    SharedErrors.NOT_AUTHENTICATED,
    SharedErrors.ACCOUNT_NOT_ACTIVE,
)
# A route only the team's admins may use: a user outside the team gets the first, the same
# whether the team exists or not; a member who is not an admin, the second.
ADMINS_ONLY = (SharedErrors.NOT_A_TEAM_MEMBER, SharedErrors.NOT_A_TEAM_ADMIN)

CREATE_TEAM_DESCRIPTION = f"""
Creates a team in a single transaction, with these defaults:

- `mode`: `{OperationMode.SUPPORT}` (a human Scrum Master approves Agilina's actions);
- `language`: `{Language.EN}` (English);
- the user who creates it becomes its `{TeamRole.ADMIN}` and is recorded as its creator.

If anything fails, neither the team nor the membership is stored.
"""


@router.post(
    "",
    response_model=CreatedTeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team and become its admin",
    description=CREATE_TEAM_DESCRIPTION,
    responses={
        201: {"description": "Created; `Location` points to the new team"},
        **errors_of(*SIGNED_IN, SharedErrors.VALIDATION, TeamsErrors.INVALID_TEAM_NAME),
    },
)
async def create_team(
    request: CreateTeamRequest,
    response: Response,
    user_id: UUID = Depends(current_user_id),
    handler: CreateTeamAsAdminHandler = Depends(get_create_team_as_admin_handler),
) -> CreatedTeamResponse:
    team_id = await handler.handle(CreateTeamAsAdmin(name=request.name, user_id=user_id))
    response.headers["Location"] = f"{router.prefix}/{team_id}"
    return present_created(team_id)


@router.get(
    "",
    response_model=list[MyTeamResponse],
    summary="The teams of the authenticated user",
    description=(
        "Every team where the user is an active member, with their role in it, ordered by "
        "name ignoring case. Empty when the user has no team."
    ),
    responses=errors_of(*SIGNED_IN),
)
async def list_my_teams(
    user_id: UUID = Depends(current_user_id),
    handler: ListMyTeamsHandler = Depends(get_list_my_teams_handler),
) -> list[MyTeamResponse]:
    views = await handler.handle(ListMyTeams(user_id=user_id))
    return [present_my_team(view) for view in views]


@router.get(
    "/{team_id}",
    response_model=TeamResponse,
    summary="One of the user's teams",
    description=(
        "The team's name, mode and language, and the user's role in it. Only an active "
        "member gets it: any other user receives `403 not_a_team_member`, whether the team "
        "exists or not. A `team_id` that is not a UUID answers `422 validation_error`."
    ),
    responses=errors_of(
        *SIGNED_IN,
        SharedErrors.VALIDATION,
        SharedErrors.NOT_A_TEAM_MEMBER,
        SharedErrors.TEAM_NOT_FOUND,
    ),
)
async def get_team(
    team: TeamContext = Depends(current_team_member),
    handler: GetTeamHandler = Depends(get_get_team_handler),
) -> TeamResponse:
    view = await handler.handle(GetTeam(team_id=team.team_id))
    return present_team(view, team.role)


ACTIVE_SPRINT_BODY = (
    "The body is the active sprint as `GET …/sprints/active` returns it: its day N of M and "
    "its next daily are computed at the moment of the request."
)
SPRINT_RULES = (
    "The end date cannot be before the start date (`sprint_ends_before_start`; both may be "
    "the same day), the time zone must be a known IANA one (`invalid_time_zone`), and the "
    "daily needs at least one participant (`no_daily_participants`), none twice "
    "(`duplicate_daily_participant`) and each an active member of the team "
    "(`daily_participant_not_a_member`); when a rule is broken, nothing is saved."
)
# The configuration of the sprint breaks one of these rules.
SPRINT_RULE_ERRORS = (
    TeamsErrors.SPRINT_ENDS_BEFORE_START,
    TeamsErrors.INVALID_TIME_ZONE,
    TeamsErrors.NO_DAILY_PARTICIPANTS,
    TeamsErrors.DUPLICATE_DAILY_PARTICIPANT,
    TeamsErrors.DAILY_PARTICIPANT_NOT_A_MEMBER,
)


async def _active_sprint(handler: GetActiveSprintHandler, team_id: UUID) -> ActiveSprintResponse:
    """The sprint a command just saved, read back through the query (CQRS)."""
    view = await handler.handle(GetActiveSprint(team_id=team_id))
    if view is None:
        raise NoActiveSprintError(f"Team {team_id} has no active sprint")
    return present_active_sprint(view)


@router.post(
    "/{team_id}/sprints",
    response_model=ActiveSprintResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Configure the team's sprint, which starts active",
    description=(
        "Stores the sprint with its period, the daily's time (one for the whole team, with the "
        "time zone of the browser of whoever saves) and the daily's participants in turn "
        "order. The sprint is saved `active`, and while it is, no role changes in the team. "
        "A team has one active sprint at most: while it has one, it is edited with `PUT "
        f"…/sprints/active` and starting another answers `active_sprint_exists`. {SPRINT_RULES} "
        f"Only an admin of the team may do it. {ACTIVE_SPRINT_BODY}"
    ),
    responses={
        201: {"description": "Created; `Location` points to the team's active sprint"},
        **errors_of(
            *SIGNED_IN,
            SharedErrors.VALIDATION,
            *ADMINS_ONLY,
            SharedErrors.TEAM_NOT_FOUND,
            TeamsErrors.NO_ACTIVE_SPRINT,
            TeamsErrors.ACTIVE_SPRINT_EXISTS,
            *SPRINT_RULE_ERRORS,
        ),
    },
)
async def start_sprint(
    request: SprintRequest,
    response: Response,
    team: TeamContext = Depends(current_team_admin),
    handler: StartSprintHandler = Depends(get_start_sprint_handler),
    active_sprint: GetActiveSprintHandler = Depends(get_get_active_sprint_handler),
) -> ActiveSprintResponse:
    await handler.handle(
        StartSprint(
            team_id=team.team_id,
            start_date=request.start_date,
            end_date=request.end_date,
            daily_time=request.daily_time,
            time_zone=request.time_zone,
            participants=tuple(request.participants),
            requested_by=team.user_id,
        )
    )
    response.headers["Location"] = f"{router.prefix}/{team.team_id}/sprints/active"
    return await _active_sprint(active_sprint, team.team_id)


@router.get(
    "/{team_id}/sprints/active",
    response_model=ActiveSprintResponse | None,
    summary="The team's active sprint and its day N of M",
    description=(
        "The team's active sprint with its day N of M and its next daily, computed at the "
        "moment of the request in the calendar of the daily's capture time zone; `null` when "
        "the team has no active sprint, which is a normal state and not an error. Any member "
        "of the team gets it."
    ),
    responses=errors_of(*SIGNED_IN, SharedErrors.VALIDATION, SharedErrors.NOT_A_TEAM_MEMBER),
)
async def get_active_sprint(
    team: TeamContext = Depends(current_team_member),
    handler: GetActiveSprintHandler = Depends(get_get_active_sprint_handler),
) -> ActiveSprintResponse | None:
    view = await handler.handle(GetActiveSprint(team_id=team.team_id))
    return present_active_sprint(view) if view is not None else None


@router.put(
    "/{team_id}/sprints/active",
    response_model=ActiveSprintResponse,
    summary="Edit the team's active sprint",
    description=(
        "Replaces the whole configuration of the active sprint: its period, the daily's time "
        "with the time zone of the browser of whoever saves (it replaces the stored one) and "
        "the daily's participants in turn order. The sprint stays `active`. "
        f"{SPRINT_RULES} Only an admin of the team may do it. {ACTIVE_SPRINT_BODY}"
    ),
    responses=errors_of(
        *SIGNED_IN,
        SharedErrors.VALIDATION,
        *ADMINS_ONLY,
        SharedErrors.TEAM_NOT_FOUND,
        TeamsErrors.NO_ACTIVE_SPRINT,
        *SPRINT_RULE_ERRORS,
    ),
)
async def reconfigure_sprint(
    request: SprintRequest,
    team: TeamContext = Depends(current_team_admin),
    handler: ReconfigureSprintHandler = Depends(get_reconfigure_sprint_handler),
    active_sprint: GetActiveSprintHandler = Depends(get_get_active_sprint_handler),
) -> ActiveSprintResponse:
    await handler.handle(
        ReconfigureSprint(
            team_id=team.team_id,
            start_date=request.start_date,
            end_date=request.end_date,
            daily_time=request.daily_time,
            time_zone=request.time_zone,
            participants=tuple(request.participants),
            requested_by=team.user_id,
        )
    )
    return await _active_sprint(active_sprint, team.team_id)
