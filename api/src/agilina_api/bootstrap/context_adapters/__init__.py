"""Adapters that connect one bounded context to another.

The contexts cannot import each other (AD-21), so each declares what it needs
from the other as ports; the implementations live here, in the composition root, which is
the only place allowed to know them all.
"""

from agilina_api.bootstrap.context_adapters.identity_backed_member_contacts import (
    IdentityBackedMemberContacts,
)
from agilina_api.bootstrap.context_adapters.identity_backed_participant_contacts import (
    IdentityBackedParticipantContacts,
)
from agilina_api.bootstrap.context_adapters.identity_backed_participant_names import (
    IdentityBackedParticipantNames,
)
from agilina_api.bootstrap.context_adapters.team_membership_factory import team_membership_factory
from agilina_api.bootstrap.context_adapters.teams_backed_ceremony_roster import (
    TeamsBackedCeremonyRoster,
)
from agilina_api.bootstrap.context_adapters.teams_backed_contacts import TeamsBackedContacts
from agilina_api.bootstrap.context_adapters.teams_backed_membership import TeamsBackedMembership

__all__ = [
    "IdentityBackedMemberContacts",
    "IdentityBackedParticipantContacts",
    "IdentityBackedParticipantNames",
    "TeamsBackedCeremonyRoster",
    "TeamsBackedContacts",
    "TeamsBackedMembership",
    "team_membership_factory",
]
