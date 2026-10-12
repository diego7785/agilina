"""Invitations API.

``router`` (HU-02): check a link, activate the account, ask for a new link. Public on
purpose: the person has no account yet, and the unguessable token in the body is what
authorizes them. Nothing here is cached (it carries tokens and passwords).

``team_invitations_router`` (HU-06): an admin invites a person to their team. It lives in
identity, which owns invitations and accounts, in the ``/v1/users`` API, naming the team in
the query (``?team_id=``); only the team's admins reach it (``current_team_admin_by_query``).
"""

from fastapi import APIRouter, Depends, Response, status

from agilina_api.identity.application.commands.activate_account import (
    ActivateAccount,
    ActivateAccountHandler,
)
from agilina_api.identity.application.commands.invite_to_team import (
    InviteToTeam,
    InviteToTeamHandler,
)
from agilina_api.identity.application.commands.request_new_invitation import (
    RequestNewInvitation,
    RequestNewInvitationHandler,
)
from agilina_api.identity.application.dtos import TeamInvitationOutcome
from agilina_api.identity.application.queries.get_invitation_status import (
    GetInvitationStatus,
    GetInvitationStatusHandler,
)
from agilina_api.identity.domain.invitation import InvitationStatus
from agilina_api.identity.presentation.http.dependencies import (
    get_activate_account_handler,
    get_invitation_status_handler,
    get_invite_to_team_handler,
    get_request_new_invitation_handler,
)
from agilina_api.identity.presentation.http.errors import IdentityErrors
from agilina_api.identity.presentation.http.presenters import present_activated, present_status
from agilina_api.identity.presentation.http.schemas import (
    ActivatedAccountResponse,
    ActivateRequest,
    InvitationStatusResponse,
    InviteToTeamRequest,
    InviteToTeamResponse,
    RequestedResponse,
    TokenRequest,
)
from agilina_api.shared.application.access import TeamContext
from agilina_api.shared.presentation.http.access import current_team_admin_by_query
from agilina_api.shared.presentation.http.api_error import ApiException, SharedErrors
from agilina_api.shared.presentation.http.error_schema import errors_of
from agilina_shared.enums import TeamRole


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/v1/invitations", tags=["invitations"], dependencies=[Depends(_no_store)]
)

GONE = {
    InvitationStatus.ACCEPTED: IdentityErrors.INVITATION_USED,
    InvitationStatus.EXPIRED: IdentityErrors.INVITATION_EXPIRED,
    InvitationStatus.REVOKED: IdentityErrors.INVITATION_REVOKED,
}

TENANT = (SharedErrors.TENANT_REQUIRED, SharedErrors.TENANT_NOT_FOUND)
LINK_GONE = (
    IdentityErrors.INVITATION_USED,
    IdentityErrors.INVITATION_EXPIRED,
    IdentityErrors.INVITATION_REVOKED,
)


@router.post(
    "/status",
    response_model=InvitationStatusResponse,
    summary="What the activation page shows about a link",
    responses=errors_of(
        *TENANT, SharedErrors.VALIDATION, IdentityErrors.INVITATION_NOT_FOUND, *LINK_GONE
    ),
)
async def invitation_status(
    request: TokenRequest,
    handler: GetInvitationStatusHandler = Depends(get_invitation_status_handler),
) -> InvitationStatusResponse:
    view = await handler.handle(GetInvitationStatus(token=request.token))
    if view.status is not InvitationStatus.PENDING:
        raise ApiException(GONE[view.status])
    return present_status(view)


@router.post(
    "/activate",
    response_model=ActivatedAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Choose a password and activate the account",
    responses=errors_of(
        *TENANT,
        SharedErrors.VALIDATION,
        IdentityErrors.INVITATION_NOT_FOUND,
        IdentityErrors.ACCOUNT_ALREADY_EXISTS,
        *LINK_GONE,
        IdentityErrors.PASSWORD_MISMATCH,
        IdentityErrors.PASSWORD_POLICY,
        IdentityErrors.IDENTITY_PROVIDER_UNAVAILABLE,
    ),
)
async def activate_account(
    request: ActivateRequest,
    handler: ActivateAccountHandler = Depends(get_activate_account_handler),
) -> ActivatedAccountResponse:
    if request.password != request.confirmation:
        raise ApiException(IdentityErrors.PASSWORD_MISMATCH)
    account = await handler.handle(ActivateAccount(token=request.token, password=request.password))
    return present_activated(account)


@router.post(
    "/request-new",
    response_model=RequestedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask the team's admins for a new invitation",
    responses=errors_of(
        *TENANT,
        SharedErrors.VALIDATION,
        IdentityErrors.INVITATION_NOT_FOUND,
        IdentityErrors.INVITATION_STILL_VALID,
        IdentityErrors.NO_ADMINS_TO_NOTIFY,
        SharedErrors.MAIL_UNAVAILABLE,
    ),
)
async def request_new_invitation(
    request: TokenRequest,
    handler: RequestNewInvitationHandler = Depends(get_request_new_invitation_handler),
) -> RequestedResponse:
    await handler.handle(RequestNewInvitation(token=request.token))
    return RequestedResponse()


team_invitations_router = APIRouter(prefix="/v1/users", tags=["users"])

INVITE_TO_TEAM_DESCRIPTION = f"""
Invites a person to the team with a role (`{TeamRole.MEMBER}` by default). What happens
depends on the email:

- **no account in the tenant:** an invitation is stored and its activation link (single use,
  valid for seven days) is e-mailed; activating it puts the person in the team with the
  chosen role (`{TeamInvitationOutcome.INVITATION_SENT}`);
- **an existing account:** the person joins the team right away with the chosen role and
  gets a notice with a link to the team, without an activation link
  (`{TeamInvitationOutcome.MEMBER_ADDED}`);
- **already an active member:** refused with `409 already_a_team_member`; nothing is
  stored or sent.

A pending invitation of that email to the team stops working: the new one replaces it.
The email is sent before anything is stored, so if the mail server refuses it the answer
is `502 mail_unavailable` and nothing changes. Only an admin of the team may invite; the
role is the one stored in the membership.
"""


@team_invitations_router.post(
    "/invitations",
    response_model=InviteToTeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a person to the team",
    description=INVITE_TO_TEAM_DESCRIPTION,
    responses={
        201: {"description": "Invited: an invitation was sent or the account joined the team"},
        **errors_of(
            *TENANT,
            SharedErrors.NOT_AUTHENTICATED,
            SharedErrors.ACCOUNT_NOT_ACTIVE,
            SharedErrors.NOT_A_TEAM_MEMBER,
            SharedErrors.NOT_A_TEAM_ADMIN,
            SharedErrors.TEAM_NOT_FOUND,
            IdentityErrors.ALREADY_A_TEAM_MEMBER,
            IdentityErrors.ACCOUNT_DISABLED,
            IdentityErrors.PENDING_INVITATION_EXISTS,
            SharedErrors.VALIDATION,
            IdentityErrors.INVALID_EMAIL,
            IdentityErrors.INVALID_FULL_NAME,
            SharedErrors.MAIL_UNAVAILABLE,
        ),
    },
)
async def invite_to_team(
    request: InviteToTeamRequest,
    team: TeamContext = Depends(current_team_admin_by_query),
    handler: InviteToTeamHandler = Depends(get_invite_to_team_handler),
) -> InviteToTeamResponse:
    outcome = await handler.handle(
        InviteToTeam(
            team_id=team.team_id,
            inviter_user_id=team.user_id,
            inviter_membership_id=team.membership_id,
            email=request.email,
            full_name=request.full_name,
            role=request.role,
        )
    )
    return InviteToTeamResponse(outcome=outcome)
