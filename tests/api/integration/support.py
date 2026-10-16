"""Storing builder-made objects in the real PostgreSQL, committed, as a test's starting data."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agilina_api.ceremonies.infrastructure.persistence.orm_models import CeremonyRow
from agilina_api.identity.domain.invitation import Invitation
from agilina_api.identity.domain.user import AppUser
from agilina_api.identity.infrastructure.persistence.invitation_repository import (
    SqlAlchemyInvitationRepository,
)
from agilina_api.identity.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from agilina_api.shared.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agilina_api.teams.domain.sprint import Sprint
from agilina_api.teams.domain.team import Team
from agilina_api.teams.infrastructure.persistence.sprint_repository import (
    SqlAlchemySprintRepository,
)
from agilina_api.teams.infrastructure.persistence.team_repository import SqlAlchemyTeamRepository
from tests.api.builders import (
    NOW,
    AppUserBuilder,
    CeremonyBuilder,
    InvitationBuilder,
    SprintBuilder,
    TeamBuilder,
)

SessionFactory = async_sessionmaker[AsyncSession]


async def stored_team(session_factory: SessionFactory, builder: TeamBuilder | None = None) -> Team:
    """A committed team: invitations and memberships reference it. A removed member comes
    from ``TeamBuilder.with_removed_member``."""
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        team = await (builder or TeamBuilder()).saved_in(SqlAlchemyTeamRepository(uow.session))
        await uow.commit()
    return team


async def stored_user(
    session_factory: SessionFactory, builder: AppUserBuilder | None = None
) -> AppUser:
    """A committed user: an accepted invitation points to the person who used it."""
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        user = await (builder or AppUserBuilder().with_unique_email()).saved_in(
            SqlAlchemyUserRepository(uow.session)
        )
        await uow.commit()
    return user


async def stored_invitation(
    session_factory: SessionFactory, builder: InvitationBuilder
) -> Invitation:
    """A committed invitation (its team must already be stored)."""
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        invitation = await builder.saved_in(SqlAlchemyInvitationRepository(uow.session))
        await uow.commit()
    return invitation


async def stored_sprint(session_factory: SessionFactory, builder: SprintBuilder) -> Sprint:
    """A committed sprint, through the repository. Its team must already be stored, and its
    participants must be members of it (``SprintBuilder.for_team`` takes the team's active
    members). A closed or planned sprint comes from ``SprintBuilder.closed()`` or
    ``planned()``."""
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        sprint = await builder.saved_in(SqlAlchemySprintRepository(uow.session))
        await uow.commit()
    return sprint


async def stored_ceremony(session_factory: SessionFactory, builder: CeremonyBuilder) -> UUID:
    """A committed ceremony, written as a row: nothing creates ceremonies yet (AGI-59). Its
    sprint must already be stored, in the same team (``CeremonyBuilder.for_sprint``), because
    the database requires it. Returns its id."""
    record = builder.build()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            CeremonyRow(
                id=builder.ceremony_id,
                team_id=record.team_id,
                sprint_id=record.sprint_id,
                scheduled_at=record.scheduled_at,
                created_at=NOW,
            )
        )
        await uow.commit()
    return builder.ceremony_id
