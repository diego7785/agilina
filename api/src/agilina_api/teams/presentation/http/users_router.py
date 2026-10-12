"""Users API: the people of a team, their roles and their removal (HU-06), and the caller
as a member of a team, for the app header (HU-04).

A user has a different role in each team, so every route names the team in the query
(``?team_id=``). The answers are the same as in the rest of the API, in the same order: no
tenant ``400``, no session ``401``, not a member of the team ``403 not_a_team_member`` (the
same whether the team exists or not), a member who is not an admin ``403 not_a_team_admin``.
The role is always the stored one (``current_team_*_by_query``), never the label.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, status

from agilina_api.shared.application.access import TeamContext
from agilina_api.shared.presentation.http.access import (
    current_team_admin_by_query,
    current_team_member_by_query,
)
from agilina_api.shared.presentation.http.api_error import SharedErrors
from agilina_api.shared.presentation.http.error_schema import errors_of
from agilina_api.teams.application.commands.change_member_role import (
    ChangeMemberRole,
    ChangeMemberRoleHandler,
)
from agilina_api.teams.application.commands.remove_member import RemoveMember, RemoveMemberHandler
from agilina_api.teams.application.queries.get_team_user import GetTeamUser, GetTeamUserHandler
from agilina_api.teams.application.queries.list_team_members import (
    ListTeamMembers,
    ListTeamMembersHandler,
)
from agilina_api.teams.presentation.http.dependencies import (
    get_change_member_role_handler,
    get_get_team_user_handler,
    get_list_team_members_handler,
    get_remove_member_handler,
)
from agilina_api.teams.presentation.http.errors import TeamsErrors
from agilina_api.teams.presentation.http.presenters import present_me, present_user, present_users
from agilina_api.teams.presentation.http.schemas import (
    ChangeMemberRoleRequest,
    MeResponse,
    UserInTeamResponse,
    UsersInTeamResponse,
)

router = APIRouter(prefix="/v1/users", tags=["users"])

SIGNED_IN = (
    SharedErrors.TENANT_REQUIRED,
    SharedErrors.TENANT_NOT_FOUND,
    SharedErrors.NOT_AUTHENTICATED,
    SharedErrors.ACCOUNT_NOT_ACTIVE,
)
# A route only the team's admins may use: a user outside the team gets the first, the same
# whether the team exists or not; a member who is not an admin, the second.
ADMINS_ONLY = (SharedErrors.NOT_A_TEAM_MEMBER, SharedErrors.NOT_A_TEAM_ADMIN)

USER_ID = Path(description="The `app_user` id of the user.")


@router.get(
    "",
    response_model=UsersInTeamResponse,
    summary="The users of a team, for its admins",
    description=(
        "The team's active users with their name, email, internal role, the code of the "
        "role's visible label and since when they are in the team, ordered by name ignoring "
        "case, and the roles an admin can give with their labels. Each user says why their "
        "role cannot change (`role_change_blocked_by`) or why they cannot be removed "
        "(`removal_blocked_by`) right now, with the same rules the changes enforce. Only an "
        "admin of the team gets it; the role is the one stored in the membership."
    ),
    responses=errors_of(*SIGNED_IN, SharedErrors.VALIDATION, *ADMINS_ONLY),
)
async def list_users(
    team: TeamContext = Depends(current_team_admin_by_query),
    handler: ListTeamMembersHandler = Depends(get_list_team_members_handler),
) -> UsersInTeamResponse:
    members = await handler.handle(ListTeamMembers(team_id=team.team_id))
    return present_users(members)


# ``/me`` is declared before ``/{user_id}`` so that "me" is not read as an id.
@router.get(
    "/me",
    response_model=MeResponse,
    summary="The caller as a member of a team",
    description=(
        "The caller's name, email, internal role and visible label in the team, and since "
        "when they are in it: what the app header shows. Any active member of the team may "
        "ask, and only for themselves."
    ),
    responses=errors_of(
        *SIGNED_IN,
        SharedErrors.VALIDATION,
        SharedErrors.NOT_A_TEAM_MEMBER,
        TeamsErrors.MEMBER_NOT_FOUND,
    ),
)
async def get_me(
    team: TeamContext = Depends(current_team_member_by_query),
    handler: GetTeamUserHandler = Depends(get_get_team_user_handler),
) -> MeResponse:
    member = await handler.handle(GetTeamUser(team_id=team.team_id, user_id=team.user_id))
    return present_me(member)


@router.get(
    "/{user_id}",
    response_model=UserInTeamResponse,
    summary="One user of a team, for its admins",
    description=(
        "The same data the list gives for one user: name, email, role, label, since when "
        "they are in the team, and why their role cannot change or they cannot be removed. "
        "A person who is not an active member of the team (never was, or was removed) "
        "answers `404 member_not_found`. Only an admin of the team may ask."
    ),
    responses=errors_of(
        *SIGNED_IN, SharedErrors.VALIDATION, *ADMINS_ONLY, TeamsErrors.MEMBER_NOT_FOUND
    ),
)
async def get_user(
    user_id: Annotated[UUID, USER_ID],
    team: TeamContext = Depends(current_team_admin_by_query),
    handler: GetTeamUserHandler = Depends(get_get_team_user_handler),
) -> UserInTeamResponse:
    member = await handler.handle(GetTeamUser(team_id=team.team_id, user_id=user_id))
    return present_user(member)


@router.patch(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Give a user another role in the team",
    description=(
        "Changes the internal role of an active member, who may be the admin who asks. "
        "Giving the role the member already has changes nothing. No role changes while the "
        "team has a sprint in progress (`sprint_in_progress`), and the team's only admin "
        "cannot be demoted, also when they ask it themselves (`last_admin`); either way "
        "nothing changes. Only an admin of the team may do it. A body with an unknown field "
        "or an unknown role (a label such as `scrum_master` is not a role) answers "
        "`422 validation_error`."
    ),
    responses={
        204: {"description": "Changed"},
        **errors_of(
            *SIGNED_IN,
            SharedErrors.VALIDATION,
            *ADMINS_ONLY,
            TeamsErrors.MEMBER_NOT_FOUND,
            SharedErrors.TEAM_NOT_FOUND,
            TeamsErrors.SPRINT_IN_PROGRESS,
            TeamsErrors.LAST_ADMIN,
        ),
    },
)
async def change_user_role(
    user_id: Annotated[UUID, USER_ID],
    request: ChangeMemberRoleRequest,
    team: TeamContext = Depends(current_team_admin_by_query),
    handler: ChangeMemberRoleHandler = Depends(get_change_member_role_handler),
) -> Response:
    await handler.handle(
        ChangeMemberRole(
            team_id=team.team_id, user_id=user_id, role=request.role, requested_by=team.user_id
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remove a user from the team",
    description=(
        "Ends the membership of an active member, who may be the admin who asks: they stop "
        "being called to the team's ceremonies. **Their account is not deleted**, since it "
        "may belong to other teams, and they can be invited again. The team's only admin "
        "cannot be removed, also when they ask it themselves (`last_admin`); a sprint in "
        "progress does not prevent it. If they take part in the daily of the active sprint, they "
        "leave it in the same change and whoever came after them moves one turn forward, even "
        "if the daily is left with no participant. Only an admin of the team may do it."
    ),
    responses={
        204: {"description": "Removed from the team"},
        **errors_of(
            *SIGNED_IN,
            SharedErrors.VALIDATION,
            *ADMINS_ONLY,
            TeamsErrors.MEMBER_NOT_FOUND,
            SharedErrors.TEAM_NOT_FOUND,
            TeamsErrors.LAST_ADMIN,
        ),
    },
)
async def remove_user(
    user_id: Annotated[UUID, USER_ID],
    team: TeamContext = Depends(current_team_admin_by_query),
    handler: RemoveMemberHandler = Depends(get_remove_member_handler),
) -> Response:
    await handler.handle(
        RemoveMember(team_id=team.team_id, user_id=user_id, requested_by=team.user_id)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
