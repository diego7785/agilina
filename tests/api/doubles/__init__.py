"""Doubles of the ports: in-memory implementations the use case tests run against."""

from tests.api.doubles.access import (
    FakeAuthenticatedUsers,
    FakeAuthenticatedWorkers,
    FakeTeamAccess,
)
from tests.api.doubles.ceremonies import (
    FakeCeremoniesUnitOfWork,
    FakeCeremonyQueries,
    FakeCeremonyRoster,
    FakeParticipantNames,
    FakeRooms,
    InMemoryCeremonyRepository,
)
from tests.api.doubles.clock import FakeClock
from tests.api.doubles.identity import (
    FakeIdentityProvider,
    FakeIdentityUnitOfWork,
    FakeInvitationQueries,
    FakeTeamContactsDirectory,
    FakeTeamMembership,
    FakeTokenGenerator,
    InMemoryInvitationRepository,
    InMemoryUserRepository,
)
from tests.api.doubles.keycloak import JWKS_URL, FakeRealmKeys
from tests.api.doubles.mail import FakeMailer, FakeRenderer
from tests.api.doubles.teams import (
    FakeActiveSprints,
    FakeMemberContacts,
    FakeSprintQueries,
    FakeTeamQueries,
    FakeTeamsUnitOfWork,
    InMemorySprintRepository,
    InMemoryTeamRepository,
)
from tests.api.doubles.tenancy import FakeTenantDirectory

__all__ = [
    "FakeActiveSprints",
    "FakeAuthenticatedUsers",
    "FakeAuthenticatedWorkers",
    "JWKS_URL",
    "FakeCeremoniesUnitOfWork",
    "FakeCeremonyQueries",
    "FakeCeremonyRoster",
    "FakeClock",
    "FakeIdentityProvider",
    "FakeIdentityUnitOfWork",
    "FakeInvitationQueries",
    "FakeMailer",
    "FakeMemberContacts",
    "FakeParticipantNames",
    "FakeRooms",
    "FakeRealmKeys",
    "FakeRenderer",
    "FakeSprintQueries",
    "FakeTeamAccess",
    "FakeTeamContactsDirectory",
    "FakeTeamMembership",
    "FakeTeamQueries",
    "FakeTeamsUnitOfWork",
    "FakeTenantDirectory",
    "FakeTokenGenerator",
    "InMemoryCeremonyRepository",
    "InMemoryInvitationRepository",
    "InMemorySprintRepository",
    "InMemoryTeamRepository",
    "InMemoryUserRepository",
]
