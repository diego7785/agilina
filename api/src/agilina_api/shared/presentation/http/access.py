"""Who is calling and whether they belong to the team, as FastAPI dependencies every
context can use.

A route that needs to know who is calling declares ``Depends(current_user_id)``: it gets
the ``app_user.id`` or the request ends in ``401 not_authenticated``.

A route about one team has ``{team_id}`` in its path and declares
``Depends(current_team_member)``: it gets the ``TeamContext`` with the caller's stored role,
or the request ends in ``403 not_a_team_member``. That is how every route of a team keeps
the other teams out (HU-05).

A route only an admin of the team may use declares ``Depends(current_team_admin)`` instead:
a member who is not an admin gets ``403 not_a_team_admin`` (HU-06).

The routes about the users of a team (``/v1/users``) are not under ``/v1/teams/{team_id}``:
they name the team in the query (``?team_id=``), because a user has a different role in each
team. ``current_team_member_by_query`` and ``current_team_admin_by_query`` are the same two
dependencies for them, with the same answers in the same order.

The routes of the agent worker (``/v1/ceremonies``) are not a person's: they declare
``Depends(current_worker)``, which answers ``401 not_authenticated`` without a valid token
and ``403 not_a_worker`` with a person's.

The adapters are declared here and provided by the composition root, so this layer never
imports the infrastructure one.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agilina_api.shared.application.access import (
    AuthenticatedUsers,
    AuthenticatedWorkers,
    NotATeamAdminError,
    NotATeamMemberError,
    NotAuthenticatedError,
    NotAWorkerError,
    TeamAccess,
    TeamContext,
)
from agilina_shared.enums import TeamRole

bearer = HTTPBearer(
    auto_error=False,
    description="The access token Keycloak issues at login, in `Authorization: Bearer <token>`.",
)
"""``auto_error=False`` so that a missing token goes through the API's single error handler
and answers with the common error body. It also documents the security scheme in
OpenAPI."""


def get_authenticated_users() -> AuthenticatedUsers:
    raise NotImplementedError("Wired by the composition root")


def get_team_access() -> TeamAccess:
    raise NotImplementedError("Wired by the composition root")


def get_authenticated_workers() -> AuthenticatedWorkers:
    raise NotImplementedError("Wired by the composition root")


async def current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    users: AuthenticatedUsers = Depends(get_authenticated_users),
) -> UUID:
    """The ``app_user.id`` of whoever sent the request."""
    if credentials is None:
        raise NotAuthenticatedError("The request carries no bearer token")
    user_id = await users.user_id_for(credentials.credentials)
    if user_id is None:
        raise NotAuthenticatedError("The bearer token does not identify a user of Agilina")
    return user_id


async def current_worker(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    workers: AuthenticatedWorkers = Depends(get_authenticated_workers),
) -> None:
    """Lets the request through only when the agent worker sent it.

    The token is validated before anything is read from it, so a request without a valid
    one answers ``401`` before the ``403``. What tells the worker apart is ``azp``, the
    client the token was issued to: it identifies a service, it is not a team role, so the
    rule that roles come from the stored membership still holds.
    """
    if credentials is None:
        raise NotAuthenticatedError("The request carries no bearer token")
    is_worker = await workers.is_worker(credentials.credentials)
    if is_worker is None:
        raise NotAuthenticatedError("The bearer token is not valid")
    if not is_worker:
        raise NotAWorkerError("Only the agent worker may do this")


async def _membership(team_id: UUID, user_id: UUID, access: TeamAccess) -> TeamContext:
    membership = await access.membership_of(team_id=team_id, user_id=user_id)
    if membership is None:
        raise NotATeamMemberError("The user is not an active member of the team")
    return TeamContext(
        team_id=team_id,
        user_id=user_id,
        membership_id=membership.membership_id,
        role=membership.role,
    )


def _require_admin(team: TeamContext) -> TeamContext:
    if team.role is not TeamRole.ADMIN:
        raise NotATeamAdminError("Only an admin of the team may do this")
    return team


async def current_team_member(
    team_id: Annotated[UUID, Path(description="The team the request is about.")],
    user_id: UUID = Depends(current_user_id),
    access: TeamAccess = Depends(get_team_access),
) -> TeamContext:
    """The team of the route's ``{team_id}`` and the caller's membership in it.

    Generic on purpose: it knows nothing of the route, so any route of a team can use it,
    and a rule on the role (only an admin may…) is another dependency built on top of
    this one. The caller is resolved first, so a request without a valid token answers
    ``401`` before the membership is looked at.
    """
    return await _membership(team_id, user_id, access)


async def current_team_admin(team: TeamContext = Depends(current_team_member)) -> TeamContext:
    """The team of the route's ``{team_id}``, only when the caller is one of its admins.

    Built on ``current_team_member``, so a request without a valid token still answers
    ``401`` and a user outside the team ``403 not_a_team_member`` first. The role is the one
    stored in the membership, never a claim of the token.
    """
    return _require_admin(team)


async def current_team_member_by_query(
    team_id: Annotated[UUID, Query(description="The team the request is about.")],
    user_id: UUID = Depends(current_user_id),
    access: TeamAccess = Depends(get_team_access),
) -> TeamContext:
    """``current_team_member`` for a route that names the team in ``?team_id=``."""
    return await _membership(team_id, user_id, access)


async def current_team_admin_by_query(
    team: TeamContext = Depends(current_team_member_by_query),
) -> TeamContext:
    """``current_team_admin`` for a route that names the team in ``?team_id=``."""
    return _require_admin(team)
