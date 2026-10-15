"""SqlCeremonyQueries against PostgreSQL: a ceremony as it is stored (AGI-64)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from agilina_api.ceremonies.application.dtos import CeremonyRecord
from agilina_api.ceremonies.infrastructure.persistence.ceremony_queries import SqlCeremonyQueries
from tests.api.builders import CeremonyBuilder, SprintBuilder, TeamBuilder, next_id
from tests.api.integration.support import stored_ceremony, stored_sprint, stored_team, stored_user

pytestmark = pytest.mark.integration


async def _sprint(session_factory):
    ana = await stored_user(session_factory)
    team = await stored_team(session_factory, TeamBuilder().with_admin(ana.id))
    return await stored_sprint(session_factory, SprintBuilder().for_team(team))


async def test_a_stored_ceremony_is_found_with_its_team_sprint_and_instant(session_factory):
    sprint = await _sprint(session_factory)
    at = datetime(2026, 10, 7, 14, 0, tzinfo=UTC)
    ceremony_id = await stored_ceremony(
        session_factory, CeremonyBuilder().for_sprint(sprint).scheduled_at_instant(at)
    )

    found = await SqlCeremonyQueries(session_factory).ceremony_of(ceremony_id)

    assert found == CeremonyRecord(team_id=sprint.team_id, sprint_id=sprint.id, scheduled_at=at)


async def test_a_ceremony_that_does_not_exist_is_none(session_factory):
    await stored_ceremony(
        session_factory, CeremonyBuilder().for_sprint(await _sprint(session_factory))
    )

    assert await SqlCeremonyQueries(session_factory).ceremony_of(next_id()) is None


async def test_a_ceremony_cannot_be_in_a_sprint_of_another_team(session_factory):
    """The foreign key shares ``team_id`` with the sprint's (user decision Q1)."""
    sprint = await _sprint(session_factory)
    other = await stored_team(
        session_factory, TeamBuilder().with_admin((await stored_user(session_factory)).id)
    )

    with pytest.raises(IntegrityError, match="ceremony_sprint_fk"):
        await stored_ceremony(
            session_factory, CeremonyBuilder().for_team_and_sprint(other.id, sprint.id)
        )
